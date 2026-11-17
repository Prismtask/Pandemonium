"""
combat/map_boss.py — the Seasonal Warden's arena (docs/map_boss_design.md §6–§7).

One arena encounter, five enemy slots at most: the Warden plus up to four
seasonal adds. The fight runs through
``superboss_common.superboss_combat_loop`` — a runtime reuse only; the Warden
is **not** a superboss-pool member (no ledger, no shards, no capture).

Three layers define the fight:

1. **The projected clock** (§7.2) — every round is one block. The arena reads
   ``day_blocks + (round - 1)`` without ever spending time; the whole fight is
   committed in one batch by ``world/dungeon.py`` on exit, so no day-rollover
   side effects can fire mid-combat.
2. **Phase aggression** (§7.3) — Morning *Dormant* → Noon *Stirring* → Night
   *Rampage*, with a two-round *Dawn Lull* after every night. Phase damage and
   initiative buffs carry ``source="map_boss_phase"`` so they can be cleared
   without touching mechanic state.
3. **The seasonal mechanic** (§6.3) — ten unlocked effects per season (Bloom,
   Heat, Harvest, Frostbite), plus ``mechanic_rank`` scaling past Echo 9.

The boss is built with ``enemy_stats(KEY)`` **without** a player (so no
Morning/Noon/Night or Full Moon multiplier) and every stat is then overridden
from the Echo payload, which is what keeps the arena's difficulty exactly the
Echo's difficulty.
"""

import random

from pandemonium.combat.ally import compute_ally_stats, get_living_party
from pandemonium.combat.combat_io import c_clear, c_input, c_print
from pandemonium.combat.combat_ui import print_combat_hud
from pandemonium.combat.enemy_ai import enemy_attack
from pandemonium.combat.stats import enemy_stats
from pandemonium.combat.status_effects import (
    apply_bleed,
    apply_blind,
    apply_burn_to_player,
    apply_dread,
    apply_poison,
    apply_slow_to_player,
    apply_weaken,
    check_status_resisted,
    try_consume_death_ward,
)
from pandemonium.combat.superboss.superboss_common import superboss_combat_loop
from pandemonium.core.utils import display_name
from pandemonium.resources import map_boss_data as data
import pandemonium.world.map_boss as map_boss
from pandemonium.core.time_blocks import get_day_phase
from pandemonium.core.time_blocks import format_block_track
from pandemonium.combat.weapon.map_boss_uniques import sync_party_phase

# ── Encounter constants ────────────────────────────────────────────────────
WARDEN_KEYS = {
    "spring": "warden_spring_bloom",
    "summer": "warden_summer_noon",
    "autumn": "warden_autumn_crown",
    "winter": "warden_winter_light",
}

ADD_KEY = "map_boss_add"          # synthetic: never in ENEMIES (no bestiary)
ADD_HP_PCT = 0.03                 # 3% of the Warden's max HP
ADD_DAMAGE_PCT = 0.40             # 0.4x the Warden's STR
MAX_ENEMIES = 5                   # HUD limit: boss + 4 adds
ADD_ROMAN = ("I", "II", "III", "IV")

PHASE_SOURCE = "map_boss_phase"
HEAT_SOURCE = "map_boss_heat"
HARVEST_SOURCE = "map_boss_harvest"

PHASE_DAMAGE = {"morning": 1.00, "noon": data.MAP_BOSS_NOON_DAMAGE,
                "night": data.MAP_BOSS_NIGHT_DAMAGE}
PHASE_INITIATIVE = {"morning": 0.0, "noon": 0.10, "night": 0.20}
PHASE_LABEL = {"morning": "Dormant", "noon": "Stirring", "night": "Rampage"}

# Actions available per phase. The cycle is deterministic so the log reads.
PHASE_ACTIONS = {
    "morning": ("censure", "weight"),
    "noon": ("censure", "weight", "noonfire"),
    "night": ("censure", "weight", "nightfall", "reap"),
}


# ══════════════════════════════════════════════════════════════════════════
#  Encounter building
# ══════════════════════════════════════════════════════════════════════════

def warden_key(season):
    """ENEMIES key for a season (falls back to Spring)."""
    return WARDEN_KEYS.get(season, WARDEN_KEYS["spring"])


def is_boss(enemy):
    return bool(enemy.get("_map_boss"))


def is_add(enemy):
    return bool(enemy.get("_map_boss_add"))


def find_boss(enemies):
    return next((e for e in enemies if is_boss(e)), None)


def build_boss(site):
    """Create the Warden's enemy dict for the active Echo.

    Built without a player so ``enemy_stats`` applies no time-of-day or event
    multiplier; the Echo payload is the authority for every stat.
    """
    season = site.get("season") or "spring"
    boss = enemy_stats(warden_key(season))

    level = max(1, int(site.get("level", 20) or 20))
    max_hp = max(1, int(site.get("max_hp", boss["hp"]) or boss["hp"]))
    hp = max(0, min(max_hp, int(site.get("hp", max_hp) or max_hp)))
    element = site.get("element") or data.get_warden(season)["element"]

    boss.update({
        "name": site.get("warden_name") or boss["name"],
        "level": level,
        "max_hp": max_hp,
        "hp": hp,
        "str_mod": max(1, int(site.get("str", boss["str_mod"]) or boss["str_mod"])),
        "con_mod": max(0, int(site.get("armor", boss["con_mod"]) or 0)),
        "elemental_res": dict(site.get("elemental_res") or {}),
        "elemental_dmg": {element: 1.0},
        "status_res": float(site.get("status_res", 0.0) or 0.0),
        "initiative_bonus": 0,
        "boss": True,
        "super_boss": False,
        "ai_disabled": True,
        "_map_boss": True,
    })
    boss.setdefault("active_buffs", [])
    boss.setdefault("active_debuffs", [])
    boss["_map_boss_base_con"] = boss["con_mod"]
    return boss


def build_add(site, boss, index):
    """A seasonal add — synthetic key, no XP, no loot, no bestiary entry."""
    add_name = site.get("add_name") or "Bloomling"
    suffix = ADD_ROMAN[index % len(ADD_ROMAN)]
    max_hp = max(1, int(boss["max_hp"] * ADD_HP_PCT))
    element = site.get("element") or "earth"
    return {
        "key": ADD_KEY,
        "name": f"{add_name} {suffix}",
        "race": "Elemental",
        "level": boss["level"],
        "hp": max_hp,
        "max_hp": max_hp,
        "str_mod": max(1, int(boss["str_mod"] * ADD_DAMAGE_PCT)),
        "con_mod": 2,
        "dex_mod": 8,
        "monster_girl": False,
        "boss": False,
        "super_boss": False,
        "status_res": 0.0,
        "dialogue": {},
        "abilities": None,
        "ai_disabled": True,
        "elemental_res": {element: 1.0},
        "elemental_dmg": {element: 1.0},
        "active_buffs": [],
        "active_debuffs": [],
        "no_bestiary": True,
        "_map_boss_add": True,
    }


def build_encounter(site):
    """Fresh enemy list for one attempt (boss only; adds spawn in-round)."""
    return [build_boss(site)]


# ══════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════

def _party(player):
    """Living party members (player + active allies)."""
    return [m for m in get_living_party(player) if m.get("current_hp", 0) > 0]


def _player_con(player):
    """The player's effective Constitution (armour basis in enemy_attack)."""
    try:
        from pandemonium.combat.stats import compute_player_stats
        return int(compute_player_stats(player)[1])
    except Exception:
        return 0


def _target_con(member, player, p_con):
    if member is player:
        return p_con
    return compute_ally_stats(member)[1]


def _is_defending(member, player, defending):
    if member is player:
        return defending
    return bool(member.get("defending_this_turn", False))


def _pick_target(player):
    """Weighted random party target (the player draws twice the aggro)."""
    from pandemonium.combat.status_effects import get_aggro_multiplier
    party = _party(player)
    if not party:
        return None
    if len(party) == 1:
        return party[0]
    weights = [(2.0 if m is player else 1.0) * get_aggro_multiplier(m)
               for m in party]
    return random.choices(party, weights=weights)[0]


def _has(ctx, effect_id):
    """True when the current Echo has unlocked a mechanic effect."""
    return effect_id in (ctx.get("effects") or ())


def _add_buff(actor, source, btype, value):
    """Replace a sourced buff (never stacks duplicates of the same source)."""
    actor["active_buffs"] = [
        b for b in actor.get("active_buffs", [])
        if not (b.get("source") == source and b.get("type") == btype)
    ]
    actor["active_buffs"].append({
        "type": btype, "value": value, "remaining": 999, "source": source,
    })


def _clear_source(actor, source):
    actor["active_buffs"] = [
        b for b in actor.get("active_buffs", []) if b.get("source") != source
    ]


def _heal(boss, amount):
    amount = max(0, int(amount))
    if amount <= 0:
        return 0
    before = boss["hp"]
    boss["hp"] = min(boss["max_hp"], boss["hp"] + amount)
    return boss["hp"] - before


# ── Phase clock ────────────────────────────────────────────────────────────

def _phase_of(blocks):
    return get_day_phase(int(blocks) % 24)


def projected_time_label(player, blocks):
    """The arena clock label for a projected block count.

    ``format_block_track`` reads ``day_blocks`` off the player dict, so the
    projection renders through a shallow copy — the real clock is untouched.
    """
    proxy = dict(player)
    proxy["day_blocks"] = int(blocks) % 24
    proxy["_combat_time_label"] = ""
    return format_block_track(proxy, include_day=False)


def _clear_phase_buffs(boss):
    """Drop phase buffs and restore the base armour (§7.3)."""
    _clear_source(boss, PHASE_SOURCE)
    boss["initiative_bonus"] = 0
    if "_map_boss_base_con" in boss:
        boss["con_mod"] = boss["_map_boss_base_con"]


def _apply_phase(ctx, boss, phase, lull):
    """Set the phase's damage / initiative / armour modifiers."""
    _clear_phase_buffs(boss)
    damage = PHASE_DAMAGE.get(phase, 1.0)
    label = PHASE_LABEL.get(phase, "Dormant")
    if lull:
        damage = data.MAP_BOSS_DAWN_LULL_DAMAGE
        label = "Dawn Lull"
        boss["con_mod"] = max(0, int(boss["_map_boss_base_con"] * 0.8))
    _add_buff(boss, PHASE_SOURCE, "damage_boost", damage - 1.0)
    boss["initiative_bonus"] = int(boss.get("dex_mod", 10)
                                   * PHASE_INITIATIVE.get(phase, 0.0))
    ctx["phase_damage"] = damage
    armour_note = " \u00b7 armour \u221220%" if lull else ""
    c_print(f"\n\u2699 [PHASE] {phase.title()} \u2014 the Warden is {label} "
            f"(\u00d7{damage:.2f} damage{armour_note}).")


def _despawn_adds(enemies):
    """Dawn: every seasonal add crumbles."""
    adds = [e for e in enemies if is_add(e)]
    for add in adds:
        add["hp"] = 0
    if adds:
        c_print("\n\u2699 [PHASE] Dawn breaks \u2014 the seasonal adds crumble "
                "to spent hours.")


# ══════════════════════════════════════════════════════════════════════════
#  Mechanic engine
# ══════════════════════════════════════════════════════════════════════════

def _rank(ctx):
    return float(ctx.get("rank_scale", 1.0) or 1.0)


def _status_chance(ctx):
    """Base chance to land the mechanic's status on a basic strike."""
    base = 1.0 if ctx["mechanic"] == "harvest" else 0.45
    if ctx.get("phase") == "night":
        base += 0.25          # Rampage: status chance +25% (§7.3)
    return min(1.0, base)


def _poison_damage(boss, ctx):
    dmg = max(2, int(boss["str_mod"] * 0.12 * _rank(ctx)))
    if _has(ctx, "bloom_poison_amp"):
        dmg = int(dmg * 1.5)
    return dmg


def _heat_tier(ctx):
    return min(5, 1 + int(ctx.get("tier", 1)) // 4)


def _bleed_damage(boss, ctx):
    dmg = max(2, int(boss["str_mod"] * 0.18 * _rank(ctx)))
    if _has(ctx, "bleed_amp"):
        dmg = int(dmg * 1.5)
    return dmg


def _frost_damage(ctx):
    return 2 + (2 if _has(ctx, "frost_damage_up") else 0)


def _freeze(actor, turns):
    """Freeze an actor: their next action is lost (re-applied while it lasts)."""
    turns = max(1, int(turns))
    actor["stunned"] = True
    actor.setdefault("active_debuffs", []).append({
        "type": "stun", "remaining": turns, "source": "map_boss_freeze",
    })
    if turns > 1:
        actor["_map_boss_freeze"] = turns - 1


def _apply_freeze_vulnerability(actor, ctx):
    """Frozen targets take +20% damage (Echo 5 effect)."""
    if not _has(ctx, "frozen_vuln"):
        return
    actor.setdefault("active_debuffs", []).append({
        "type": "vulnerable", "value": 0.20, "remaining": 2,
        "source": "map_boss_frost",
    })


def _frost_stacks(actor):
    return int(actor.get("_map_boss_frost_stacks", 0) or 0)


def _set_frost_stacks(actor, value):
    value = max(0, int(value))
    if value:
        actor["_map_boss_frost_stacks"] = value
    else:
        actor.pop("_map_boss_frost_stacks", None)


def _frostbite(ctx, actor, boss):
    """Apply one Frostbite stack: -DEX, water DoT, 3 turns (§6.3 Winter)."""
    stacks = _frost_stacks(actor) + 1
    _set_frost_stacks(actor, stacks)

    existing = next((d for d in actor.get("active_debuffs", [])
                     if d.get("type") == "frostbite"), None)
    payload = {"type": "frostbite", "damage": _frost_damage(ctx),
               "remaining": 3, "source": "map_boss_frostbite"}
    if existing:
        existing.update(payload)
    else:
        actor.setdefault("active_debuffs", []).append(payload)
    apply_slow_to_player(actor, duration=2)

    name = actor.get("name") or "You"
    c_print(f"  \u2744 Frostbite grips {name} ({stacks} stack(s)).")

    freeze_at = 5 if _has(ctx, "absolute_zero") else 3
    if stacks >= freeze_at:
        if _has(ctx, "absolute_zero") and freeze_at == 5:
            turns = 2 if _has(ctx, "freeze_duration") else 1
            c_print("\u2699 [GIMMICK] ABSOLUTE ZERO \u2014 the hour stops for "
                    "the whole party!")
            for member in _party(ctx["player"]):
                _freeze(member, turns)
                _apply_freeze_vulnerability(member, ctx)
                _set_frost_stacks(member, 0)
                member["active_debuffs"] = [
                    d for d in member.get("active_debuffs", [])
                    if d.get("type") != "frostbite"
                ]
        else:
            turns = 2 if _has(ctx, "freeze_duration") else 1
            c_print(f"\u2699 [GIMMICK] {name} is FROZEN solid!")
            _freeze(actor, turns)
            _apply_freeze_vulnerability(actor, ctx)
            _set_frost_stacks(actor, 0)
            actor["active_debuffs"] = [
                d for d in actor.get("active_debuffs", [])
                if d.get("type") != "frostbite"
            ]


def _tick_frostbite(ctx, player):
    """Water damage for every active Frostbite, then expire old ones."""
    died = False
    for member in _party(player):
        for debuff in member.get("active_debuffs", [])[:]:
            if debuff.get("type") != "frostbite":
                continue
            dmg = max(1, int(debuff.get("damage", 2) * _rank(ctx)))
            member["current_hp"] = member.get("current_hp", 0) - dmg
            name = member.get("name") or "You"
            c_print(f"  \u2744 {name} takes {dmg} frost damage.")
            debuff["remaining"] = int(debuff.get("remaining", 1)) - 1
            if debuff["remaining"] <= 0:
                member["active_debuffs"].remove(debuff)
                _set_frost_stacks(member, 0)
        if member.get("current_hp", 0) <= 0:
            if member is player:
                if not try_consume_death_ward(player):
                    return True
            elif not member.get("defeated"):
                member["defeated"] = True
                c_print(f"  {display_name(member)} succumbs to the cold!")
    return died


def _refresh_heat(ctx, boss):
    """Heat stacks: +2% damage and +2% initiative each (§6.3 Summer)."""
    stacks = int(ctx.get("stacks", 0) or 0)
    _clear_source(boss, HEAT_SOURCE)
    if stacks > 0:
        _add_buff(boss, HEAT_SOURCE, "damage_boost", 0.02 * stacks)
        boss["initiative_bonus"] = int(boss.get("initiative_bonus", 0)
                                       + boss.get("dex_mod", 10) * 0.02 * stacks)


def _refresh_harvest(ctx, boss):
    """Harvest stacks: +2% damage and +1% lifesteal each (§6.3 Autumn)."""
    stacks = int(ctx.get("harvest", 0) or 0)
    _clear_source(boss, HARVEST_SOURCE)
    if stacks > 0:
        _add_buff(boss, HARVEST_SOURCE, "damage_boost", 0.02 * stacks)
    lifesteal = stacks * (0.02 if _has(ctx, "lifesteal_up") else 0.01)
    ctx["lifesteal"] = lifesteal


def _refresh_ice_armor(ctx, boss):
    """Ice Armor: -3% damage taken per stack (§6.3 Winter)."""
    armor = int(ctx.get("ice_armor", 0) or 0)
    boss["active_debuffs"] = [
        d for d in boss.get("active_debuffs", [])
        if d.get("source") != "map_boss_ice"
    ]
    if armor > 0:
        boss["active_debuffs"].append({
            "type": "damage_taken_up", "value": -0.03 * armor,
            "remaining": 999, "source": "map_boss_ice",
        })


def _aoe(ctx, boss, player, p_con, defending, power, name,
         status=None, ignore_armor=0.0):
    """Strike the whole party (reuses every defensive path). Returns 'dead'."""
    ctx["aoe_hits"] = ctx.get("aoe_hits", 0) + 1
    for member in _party(player):
        is_def = _is_defending(member, player, defending)
        con = _target_con(member, player, p_con)
        outcome = enemy_attack(
            boss, member, con, is_def,
            power_mult=power,
            armor_mult=max(0.0, 1.0 - ignore_armor),
            skill_name=name,
            all_enemies=ctx.get("_enemies"),
            actual_player=player,
            skip_turn_start=True,
        )
        if outcome == "dead":
            if try_consume_death_ward(member):
                if member is not player:
                    member["current_hp"] = max(1, member.get("current_hp", 1))
                c_print(f"  {member.get('name', 'An ally')} clings to life!")
                continue
            if member is player:
                return "dead"
            member["defeated"] = True
            member["current_hp"] = 0
            c_print(f"  {display_name(member)} falls!")
            continue
        if status and member.get("current_hp", 0) > 0:
            status(member)
    return None


# ── Mechanic: per-round advancement ────────────────────────────────────────

def _advance_bloom(ctx, player, boss, phase):
    """Bloom: stacks heal the Warden at cap; poison rides on its attacks."""
    tier_cap = data.MAP_BOSS_BLOOM_CAP_BASE + (1 if _has(ctx, "bloom_cap_up") else 0)
    gain = 1
    if phase == "noon" and _has(ctx, "bloom_noon_gain"):
        gain += 1
    if phase == "night":
        gain += 1
    ctx["stacks"] = min(tier_cap, int(ctx.get("stacks", 0) or 0) + gain)
    if ctx["stacks"] < tier_cap:
        return None

    heal_pct = 0.05
    if _has(ctx, "bloom_cap_heal_10"):
        heal_pct = 0.10
    if _has(ctx, "bloom_cap_heal_15"):
        heal_pct = 0.15
    healed = _heal(boss, boss["max_hp"] * heal_pct * _rank(ctx))
    ctx["stacks"] = 0
    c_print(f"\n\u2699 [GIMMICK] Bloom bursts \u2014 the Warden drinks it back "
            f"(+{healed} HP).")

    if _has(ctx, "bloom_cap_heal_15"):
        for member in _party(player):
            apply_poison(member, _poison_damage(boss, ctx), 2)
        c_print("  Spores burst over the whole party!")

    if _has(ctx, "bloom_summon") and len(ctx.get("_enemies") or []) < MAX_ENEMIES:
        add = build_add(ctx["site"], boss, ctx.get("adds_spawned", 0))
        ctx["_enemies"].append(add)
        ctx["adds_spawned"] = ctx.get("adds_spawned", 0) + 1
        c_print(f"  A {add['name']} unfurls from the loam!")

    if _has(ctx, "bloom_overbloom"):
        c_print("\u2699 [GIMMICK] OVERBLOOM \u2014 the roots lash out!")
        for member in _party(player):
            apply_poison(member, _poison_damage(boss, ctx), 2)
        deaths = _aoe(ctx, boss, player, ctx["p_con"], ctx["defending"],
                      0.75, "Overbloom")
        if deaths == "dead":
            return "dead"
    return None


def _advance_heat(ctx, player, boss, phase):
    """Heat: stacks build, then vent — Solar Flare once Echo 2 is reached."""
    cap = data.MAP_BOSS_HEAT_CAP_BASE + (1 if _has(ctx, "heat_cap_up") else 0)
    gain = 1
    if phase == "noon" and _has(ctx, "heat_noon_gain"):
        gain += 1
    if phase == "night" and _has(ctx, "heat_night_gain"):
        gain += 1
    ctx["stacks"] = min(cap, int(ctx.get("stacks", 0) or 0) + gain)
    _refresh_heat(ctx, boss)
    if ctx["stacks"] < cap:
        return None

    ctx["stacks"] = 0
    _refresh_heat(ctx, boss)
    if not _has(ctx, "solar_flare"):
        c_print("\n\u2699 [GIMMICK] The Warden vents its heat \u2014 the air "
                "shimmers and stills.")
        return None

    c_print("\n\u2699 [GIMMICK] SOLAR FLARE!")
    ignore = 0.30 if _has(ctx, "flare_armor_pierce") else 0.0
    hits = 2 if _has(ctx, "second_sun") else 1
    for index in range(hits):
        power = 0.75 if index == 0 else 0.375
        name = "Solar Flare" if index == 0 else "Second Sun"
        status = ((lambda m: _apply_burn(ctx, m, boss))
                  if _has(ctx, "heat_burn") else None)
        if _aoe(ctx, boss, player, ctx["p_con"], ctx["defending"], power,
                name, status=status, ignore_armor=ignore) == "dead":
            return "dead"
    return None


def _advance_harvest(ctx, player, boss, phase):
    """Harvest: bleeding party members feed stacks; the cap spends on Reap."""
    cap = data.MAP_BOSS_HARVEST_CAP_BASE + (1 if _has(ctx, "harvest_cap_up") else 0)
    bleeding = sum(
        1 for member in _party(player)
        if any(d.get("type") == "bleed" for d in member.get("active_debuffs", []))
    )
    if bleeding:
        ctx["harvest"] = min(cap, int(ctx.get("harvest", 0) or 0) + bleeding)
        c_print(f"  \U0001F342 The bleeding harvest feeds the Warden "
                f"({ctx['harvest']}/{cap}).")
    _refresh_harvest(ctx, boss)
    if int(ctx.get("harvest", 0) or 0) < cap or not _has(ctx, "reap"):
        return None

    ctx["harvest"] = 0
    _refresh_harvest(ctx, boss)
    heal_pct = 0.60 if _has(ctx, "reap_heal_60") else 0.50
    if _has(ctx, "final_harvest"):
        party = _party(player)
        before = sum(max(0, m.get("current_hp", 0)) for m in party)
        c_print("\n\u2699 [GIMMICK] FINAL HARVEST \u2014 the Warden reaps the "
                "whole field!")
        if _aoe(ctx, boss, player, ctx["p_con"], ctx["defending"], 0.9,
                "Final Harvest") == "dead":
            return "dead"
        after = sum(max(0, m.get("current_hp", 0)) for m in party)
        healed = _heal(boss, max(0, before - after) * heal_pct * _rank(ctx))
        c_print(f"  The Warden drinks the harvest (+{healed} HP).")
        return None

    target = _pick_target(player)
    if target is None:
        return None
    con = _target_con(target, player, ctx["p_con"])
    c_print(f"\n\u2699 [GIMMICK] REAP \u2014 the Warden's scythe finds "
            f"{target.get('name', 'you')}!")
    before_hp = target.get("current_hp", 0)
    outcome = enemy_attack(
        boss, target, con, _is_defending(target, player, ctx["defending"]),
        power_mult=1.5, skill_name="Reap",
        all_enemies=ctx.get("_enemies"), actual_player=player,
        skip_turn_start=True,
    )
    dealt = max(0, before_hp - target.get("current_hp", 0))
    healed = _heal(boss, dealt * heal_pct * _rank(ctx))
    c_print(f"  The Warden drinks the wound (+{healed} HP).")
    if _has(ctx, "reap_party_bleed"):
        for member in _party(player):
            apply_bleed(member, _bleed_damage(boss, ctx), 3)
        c_print("  Blood sprays across the arena \u2014 the whole party bleeds!")
    if outcome == "dead":
        if try_consume_death_ward(target):
            c_print(f"  {target.get('name', 'You')} clings to life!")
        elif target is player:
            return "dead"
        else:
            target["defeated"] = True
            target["current_hp"] = 0
            c_print(f"  {display_name(target)} falls!")
    return None


def _advance_frostbite(ctx, player, boss, phase):
    """Frostbite: a party member freezes each round; Ice Armor builds."""
    targets = 1 + (1 if (phase == "night" and _has(ctx, "night_extra_target")) else 0)
    for _ in range(targets):
        member = _pick_target(player)
        if member is None:
            break
        _frostbite(ctx, member, boss)

    if _has(ctx, "ice_armor"):
        cap = data.MAP_BOSS_ICE_CAP_BASE + (1 if _has(ctx, "ice_cap_up") else 0)
        ctx["ice_armor"] = min(cap, int(ctx.get("ice_armor", 0) or 0) + 1)
        _refresh_ice_armor(ctx, boss)
    if _tick_frostbite(ctx, player):
        return "dead"
    return None


_MECHANIC_ADVANCE = {
    "bloom": _advance_bloom,
    "heat": _advance_heat,
    "harvest": _advance_harvest,
    "frostbite": _advance_frostbite,
}


# ── Mechanic: on-hit statuses ─────────────────────────────────────────────

def _apply_poison(ctx, target, boss):
    if check_status_resisted(target):
        return f"  The Warden's spores find no hold."
    apply_poison(target, _poison_damage(boss, ctx), 2)
    msg = f"  \u2623 Poison seeps into {target.get('name', 'you')}."
    if _has(ctx, "bloom_poison_weaken"):
        apply_weaken(target, penalty_pct=0.10, duration=2)
        msg += " Their strength sags."
    return msg


def _apply_burn(ctx, target, boss):
    if check_status_resisted(target):
        return "  The heat washes over without catching."
    duration = 3 + (1 if _has(ctx, "burn_duration") else 0)
    apply_burn_to_player(target, tier=_heat_tier(ctx), duration=duration)
    if _has(ctx, "burn_amp"):
        for debuff in target.get("active_debuffs", []):
            if debuff.get("type") == "burn":
                debuff["damage"] = int(debuff.get("damage", 0) * 1.5)
    return f"  \U0001F525 {target.get('name', 'You')} catches fire."


def _apply_bleed_status(ctx, target, boss):
    if check_status_resisted(target):
        return "  The wind's edge passes harmlessly."
    duration = 3 + (1 if _has(ctx, "bleed_duration") else 0)
    apply_bleed(target, _bleed_damage(boss, ctx), duration)
    return f"  \U0001F342 {target.get('name', 'You')} starts to bleed."


def _on_hit_status(ctx, target, boss):
    """The mechanic's on-hit status for one struck party member."""
    mechanic = ctx.get("mechanic")
    if mechanic == "bloom":
        if _has(ctx, "bloom_poison") and ctx.get("stacks", 0) >= 3:
            return _apply_poison(ctx, target, boss)
        return None
    if mechanic == "heat":
        if _has(ctx, "heat_burn") and ctx.get("stacks", 0) >= 4:
            return _apply_burn(ctx, target, boss)
        return None
    if mechanic == "harvest":
        return _apply_bleed_status(ctx, target, boss)
    return None


def _owned_statuses(ctx):
    """Statuses the 'Long Day' finisher can roll for (§7.4)."""
    owned = []
    if _has(ctx, "bloom_poison"):
        owned.append("poison")
    if _has(ctx, "heat_burn"):
        owned.append("burn")
    if ctx.get("mechanic") == "harvest":
        owned.append("bleed")
    if _has(ctx, "frost_freeze"):
        owned.append("freeze")
    return owned


def _apply_status_name(ctx, name, target, boss):
    if name == "poison":
        return _apply_poison(ctx, target, boss)
    if name == "burn":
        return _apply_burn(ctx, target, boss)
    if name == "bleed":
        return _apply_bleed_status(ctx, target, boss)
    if name == "freeze":
        _frostbite(ctx, target, boss)
        return None
    return None


# ══════════════════════════════════════════════════════════════════════════
#  Loop hooks
# ══════════════════════════════════════════════════════════════════════════

def _pre_round_hook(ctx, enemies):
    """Advance the projected clock, phases and the seasonal mechanic.

    Runs after pruning and *before* the round header so the header can show
    the phase the round is actually fought in (§7.2).
    """
    player = ctx["player"]
    boss = find_boss(enemies)
    if boss is None:
        # The Warden is the encounter: with it gone the arena is over, even
        # if seasonal adds are still standing.
        return "victory"

    round_num = max(1, int(ctx.get("round", 1) or 1))
    ctx["round"] = round_num
    cursor = ctx["start_blocks"] + (round_num - 1)
    ctx["clock_blocks"] = cursor
    ctx["rounds_fought"] = round_num
    player["_map_boss_clock_blocks"] = cursor
    player["_map_boss_rounds"] = round_num
    player["_combat_time_label"] = projected_time_label(player, cursor)
    # Warden uniques read the projected phase; allies mirror the clock.
    sync_party_phase(player)

    phase = _phase_of(cursor)
    day_index = cursor // 24
    started = ctx.get("phase") is None
    previous = ctx.get("phase")
    dawn = (phase == "morning"
            and (started or previous != "morning"
                 or day_index != ctx.get("day_index")))
    if dawn:
        _despawn_adds(enemies)
        ctx["lull_rounds"] = data.MAP_BOSS_DAWN_LULL_ROUNDS
        ctx["adds_spawned"] = 0
        ctx["ice_armor"] = 0
        _refresh_ice_armor(ctx, boss)

    transitioning = started or phase != previous
    if transitioning:
        _apply_phase(ctx, boss, phase, lull=ctx.get("lull_rounds", 0) > 0)
    elif ctx.get("lull_rounds", 0) > 0:
        pass  # the lull holds its buff for its full duration
    ctx["phase"] = phase
    ctx["day_index"] = day_index

    if ctx.get("lull_rounds", 0) > 0:
        ctx["lull_rounds"] -= 1
        if ctx["lull_rounds"] == 0:
            _apply_phase(ctx, boss, phase, lull=False)

    if boss.get("hp", 0) <= 0:
        return "victory"

    advance = _MECHANIC_ADVANCE.get(ctx.get("mechanic"))
    if advance is not None:
        result = advance(ctx, player, boss, phase)
        if result == "dead":
            return "dead"
    return None


def _pre_player_hook(ctx, enemies):
    """Spawn seasonal adds as the phase escalates (§7.5)."""
    boss = find_boss(enemies)
    if boss is None:
        return None
    phase = ctx.get("phase")
    wanted = 2 if phase == "noon" else (4 if phase == "night" else 0)
    present = sum(1 for e in enemies if is_add(e))
    if wanted <= present or len(enemies) >= MAX_ENEMIES:
        return None
    site = ctx["site"]
    spawned = []
    while present < wanted and len(enemies) < MAX_ENEMIES:
        add = build_add(site, boss, ctx.get("adds_spawned", 0))
        ctx["adds_spawned"] = ctx.get("adds_spawned", 0) + 1
        enemies.append(add)
        spawned.append(add["name"])
        present += 1
    if spawned:
        c_print(f"\n\u2699 [PHASE] The hour spawns its servants \u2014 "
                f"{', '.join(spawned)} join the fight!")
    return None


def _enemy_turn_hook(enemy, ctx, player, p_con, defending, **kwargs):
    """The Warden's action kit and the adds' basic attacks (§7.4)."""
    if is_add(enemy):
        return 1, False, None, 1.0, 0

    boss = enemy
    ctx["p_con"] = p_con
    ctx["defending"] = defending
    ctx["boss_actions"] = ctx.get("boss_actions", 0) + 1
    action_no = ctx["boss_actions"]
    phase = ctx.get("phase", "morning")

    # ── The Long Day: every 3rd action, every 2nd at Night ────────────
    cadence = 2 if phase == "night" else 3
    if action_no % cadence == 0:
        return _long_day(ctx, boss, player, p_con, defending)

    actions = data.MAP_BOSS_NIGHT_ACTIONS if phase == "night" else 1
    cycle = PHASE_ACTIONS.get(phase, PHASE_ACTIONS["morning"])
    action = cycle[(action_no - 1) % len(cycle)]

    if action == "noonfire":
        status = ((lambda m: _apply_burn(ctx, m, boss))
                  if _has(ctx, "heat_burn") else None)
        if _aoe(ctx, boss, player, p_con, defending, 0.75, "Noonfire",
                status=status) == "dead":
            return "dead"
        return 1, True, None, 1.0, 0

    if action == "nightfall":
        if _aoe(ctx, boss, player, p_con, defending, 0.90,
                "Nightfall") == "dead":
            return "dead"
        blinded = 0
        for member in _party(player):
            if check_status_resisted(member):
                continue
            apply_blind(member, 2)
            apply_dread(member, 2)
            blinded += 1
        if blinded:
            c_print("  The dark presses in \u2014 the party is Blinded and "
                    "Dreaded.")
        return 1, True, None, 1.0, 0

    if action == "reap":
        def _reap_logic(e, target, dmg):
            if dmg > 0:
                healed = _heal(boss, dmg * max(0.02, ctx.get("lifesteal", 0.0)))
                if healed:
                    return f"  The Warden drinks deep (+{healed} HP)."
            return None
        return (1, False, _reap_logic, 0.70,
                int(boss["str_mod"] * 0.60))

    if action == "weight":
        def _weight_logic(e, target, dmg):
            if dmg <= 0:
                return None
            return _on_hit_status(ctx, target, boss)
        return 1, False, _weight_logic, 1.0, int(boss["str_mod"] * 0.20)

    # Censure: basic pressure, occasional mechanic status.
    def _censure_logic(e, target, dmg):
        if dmg <= 0 or random.random() >= _status_chance(ctx):
            return None
        return _on_hit_status(ctx, target, boss)
    return actions, False, _censure_logic, 1.0, 0


def _long_day(ctx, boss, player, p_con, defending):
    """AoE finisher; rolls every owned status at 50% (§7.4)."""
    c_print(f"\n\u2699 [GIMMICK] THE LONG DAY \u2014 the {boss['name']} spends "
            f"an hour on the whole party!")
    owned = _owned_statuses(ctx)
    status = None
    if owned:
        def status(member):
            for name in owned:
                if random.random() < 0.5:
                    _apply_status_name(ctx, name, member, boss)
    if _aoe(ctx, boss, player, p_con, defending, 1.0, "The Long Day",
            status=status) == "dead":
        return "dead"
    return 1, True, None, 1.0, 0


def _on_player_hit_hook(target, elist, ctx, attacker=None):
    """Ice Armor melts when fire lands on the Warden (Winter Echo 2/7)."""
    from pandemonium.combat.elemental import get_attack_element
    if not is_boss(target) or attacker is None:
        return
    if int(ctx.get("ice_armor", 0) or 0) <= 0:
        return
    if get_attack_element(attacker) != "fire":
        return
    ctx["ice_armor"] = max(0, int(ctx["ice_armor"]) - 1)
    boss = find_boss(elist)
    if boss is not None:
        _refresh_ice_armor(ctx, boss)
    c_print("  \U0001F525 Fire hisses against the Ice Armor \u2014 a layer "
            "melts away!")
    if _has(ctx, "shatter") and boss is not None:
        shatter = max(1, int(boss["str_mod"] * 0.5))
        attacker["current_hp"] = attacker.get("current_hp", 0) - shatter
        name = attacker.get("name") or "You"
        c_print(f"  \u2744 SHATTER! {name} takes {shatter} water damage from "
                f"the bursting ice.")
        if attacker.get("current_hp", 0) <= 0:
            if not try_consume_death_ward(attacker):
                if attacker is ctx["player"]:
                    ctx["force_dead"] = True
                else:
                    attacker["defeated"] = True


def _custom_hud(ctx, enemies):
    """`Seasonal Warden: … | ❄ Winter Echo II` plus the mechanic tags."""
    boss = find_boss(enemies)
    site = ctx["site"]
    tags = []
    if boss is not None:
        tags.append(f"ECHO {map_boss.echo_label(site.get('echo', 0)).upper()}")
        if ctx.get("phase"):
            tags.append(ctx["phase"].upper())
        mechanic = ctx.get("mechanic")
        stack_tag = site.get("stack_tag") or "STACK"
        if mechanic == "frostbite":
            worst = max((_frost_stacks(m) for m in _party(ctx["player"])),
                        default=0)
            tags.append(f"FROST\u00d7{worst}")
            if ctx.get("ice_armor"):
                tags.append(f"ICE\u00d7{ctx['ice_armor']}")
        elif mechanic == "harvest":
            tags.append(f"{stack_tag}\u00d7{ctx.get('harvest', 0)}")
        else:
            tags.append(f"{stack_tag}\u00d7{ctx.get('stacks', 0)}")
        boss["_custom_tags"] = tags
    header = (f"Seasonal Warden: {site.get('warden_name', 'The Warden')} | "
              f"{site.get('season_name', '')} Echo "
              f"{map_boss.echo_label(site.get('echo', 0))} \u00b7 "
              f"Lv {site.get('level', '?')}")
    print_combat_hud(ctx["player"], enemies, header=header)


def _on_kill(target, elist, ctx):
    """Adds leave nothing behind; the Warden's loot is granted by the caller."""
    if is_add(target):
        c_print(f"  {target['name']} unravels into spent minutes.")
        return
    if is_boss(target):
        c_print(f"\n  The {target['name']} collapses into spent hours \u2014 "
                f"and the hours begin to run backward.")
        # Its servants are made of the same hour: they go with it.
        for other in elist:
            if is_add(other) and other.get("hp", 0) > 0:
                other["hp"] = 0


# ══════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════

_INTRO = {
    "spring": ("The Warden of the First Bloom unfolds \u2014 every root is a "
               "finger, and the air is thick with green."),
    "summer": ("The Warden of the Long Noon stands in the white heat. The air "
               "bends around it like a held breath."),
    "autumn": ("The Warden of the Falling Crown walks through a storm of its "
               "own leaves. Each one is a year it has taken."),
    "winter": ("The Warden of the Last Light exhales, and the frost answers."),
}


def combat_map_boss(player, floor=None, enemies=None):
    """Run one arena attempt.

    Returns ``"victory"``, ``"fled"`` or ``"dead"``. The caller
    (``world/dungeon._explore_map_boss_arena``) owns HP persistence and the
    single time commit; this function only fights.
    """
    site = map_boss.get_active_boss(player)
    if not site:
        return "fled"

    boss = None
    if enemies:
        boss = find_boss(enemies)
    if boss is None:
        enemies = build_encounter(site)
        boss = enemies[0]

    season = site.get("season") or "spring"
    warden = data.get_warden(season)
    start_blocks = int(player.get("day_blocks", 0) or 0)
    echo_lbl = map_boss.echo_label(site.get("echo", 0))
    hp_pct = int(round(100.0 * boss["hp"] / max(1, boss["max_hp"])))

    c_clear()
    c_print(_INTRO.get(season, _INTRO["spring"]))
    c_print("")
    if hp_pct < 100:
        c_print(f"The {site.get('warden_name', 'Warden')} remembers. "
                f"{hp_pct}% of this Echo remains.")
    else:
        c_print(f"The {site.get('warden_name', 'Warden')} turns to face you.")
    c_print(f"{site.get('season_name', '')} Echo {echo_lbl} \u00b7 "
            f"Lv {site.get('level', '?')} \u00b7 {warden['mechanic_name']} "
            f"T{site.get('mechanic_tier', 1)}")
    c_print(f"HP: {boss['hp']} / {boss['max_hp']}")
    c_input("\nPress Enter to face the Warden...")

    # A fresh attempt never inherits the previous fight's per-actor state.
    for actor in [player] + list(player.get("allies", [])):
        actor.pop("_map_boss_frost_stacks", None)
        actor.pop("_map_boss_freeze", None)
        if actor.get("active_debuffs"):
            actor["active_debuffs"] = [
                d for d in actor["active_debuffs"]
                if d.get("source") not in ("map_boss_frost", "map_boss_frostbite",
                                           "map_boss_freeze")
            ]

    context = {
        "player": player,
        "site": site,
        "season": season,
        "mechanic": warden["mechanic"],
        "tier": int(site.get("mechanic_tier", 1) or 1),
        "rank_scale": data.mechanic_rank_scale(site.get("mechanic_rank", 1)),
        "effects": tuple(site.get("mechanic_effects") or ()),
        "start_blocks": start_blocks,
        "round": 0,
        "rounds_fought": 0,
        "phase": None,
        "day_index": None,
        "lull_rounds": 0,
        "stacks": 0,
        "harvest": 0,
        "ice_armor": 0,
        "lifesteal": 0.0,
        "boss_actions": 0,
        "adds_spawned": 0,
        "p_con": _player_con(player),
        "defending": False,
        "_enemies": enemies,
    }

    # The round header has no floor to show ("Floor Arena" would be nonsense);
    # the DungeonScreen's own top bar keeps its Arena label after the fight.
    floor_label = player.pop("_combat_floor_label", None)
    try:
        result = superboss_combat_loop(
            player, enemies, None,
            boss_name=site.get("warden_name", "The Warden"),
            context=context,
            pre_round_hook=_pre_round_hook,
            pre_player_hook=_pre_player_hook,
            custom_hud_hook=_custom_hud,
            on_kill_hook=_on_kill,
            enemy_turn_hook=_enemy_turn_hook,
            on_player_hit_hook=_on_player_hit_hook,
        )
    finally:
        if floor_label is not None:
            player["_combat_floor_label"] = floor_label

    if context.pop("force_dead", False) and result != "victory":
        result = "dead"

    # Rounds fought drive the single time commit on exit (§7.2). The hook
    # also stores the count each round, so an interrupted fight still pays.
    rounds = int(context.get("rounds_fought", 0) or 0)
    if rounds:
        player["_map_boss_rounds"] = rounds

    # Clear phase/mechanic buffs so nothing leaks into the next encounter.
    if boss is not None:
        _clear_phase_buffs(boss)
        _clear_source(boss, HEAT_SOURCE)
        _clear_source(boss, HARVEST_SOURCE)
        boss["active_buffs"] = []
        boss["active_debuffs"] = [
            d for d in boss.get("active_debuffs", [])
            if d.get("source") != "map_boss_ice"
        ]
        boss["_custom_tags"] = []
    return result
