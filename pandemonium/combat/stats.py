# stats.py – attribute math, scaling, and enemy stats
from pandemonium.resources.enemies import ENEMIES, ENEMY_RACES
from pandemonium.combat.boss_styles import apply_solo_boss_budget, is_solo_boss
from pandemonium.resources.races_classes import ATTRIBUTES
from pandemonium.inventory.core import get_total_equipment_mods
from pandemonium.core.utils import get_difficulty_multiplier_from_time
from pandemonium.combat.status_effects import get_weaken_pct
from pandemonium.progression.titles import combat_stat_bonus
from pandemonium.combat.form_perks import get_form_crit_chance_bonus
from pandemonium.combat.form_perks import get_form_crit_damage_bonus
from pandemonium.combat.form_perks import get_form_evasion


# ===========================================================================
# FLAT STAT BUFF SCALING
# ===========================================================================
# Flat attribute buffs grow with the holder's level so they stay relevant
# next to percentage damage buffs (which scale with total power).
STAT_BUFF_FLAT_BONUS = 1          # small baseline buff on every flat stat buff
STAT_BUFF_SCALE_PER_LEVEL = 0.15  # +0.15 per level above 1


def scaled_stat_buff_value(base, entity, per_level=None, flat_bonus=STAT_BUFF_FLAT_BONUS):
    """Return a flat stat buff magnitude scaled to the holder's level.

    ``per_level=None`` uses STAT_BUFF_SCALE_PER_LEVEL. A base +2 buff becomes
    +3 at Lv1, +5 at Lv15 and +8 at Lv40 (before mastery multipliers).
    """
    if per_level is None:
        per_level = STAT_BUFF_SCALE_PER_LEVEL
    level = max(1, int(entity.get("level", 1) or 1))
    return int(base + flat_bonus + (level - 1) * per_level + 0.5)


def compute_enemy_attributes(enemy_key):
    template = ENEMIES[enemy_key]
    race_name = template["race"]
    race_mods = ENEMY_RACES[race_name].get("mods", {})
    personal_mods = template.get("mods", {})

    base = {attr: 0 for attr in ATTRIBUTES}
    for attr, mod in race_mods.items():
        base[attr] += mod
    for attr, mod in personal_mods.items():
        base[attr] += mod
    return base


def enemy_stats(enemy_key, player=None):
    from pandemonium.world.event_horizon import in_run as _eh_in_run
    from pandemonium.combat.elemental import compute_enemy_elemental
    from pandemonium.world.event_horizon import apply_enemy_scaling
    template = ENEMIES[enemy_key]
    attrs = compute_enemy_attributes(enemy_key)

    eh_frozen = False
    if player:
        # Event Horizon runs freeze difficulty too (docs §2.1, 2026-10-06).
        eh_frozen = _eh_in_run(player)
    if player and (player.get("pandemonium_mode") or eh_frozen):
        # Pandemonium / Event Horizon runs ignore phase scaling —
        # enemies always carry the night baseline (×1.25, §7) so difficulty
        # doesn't swing with the clock mid-run.
        multiplier = 1.25
    else:
        multiplier = get_difficulty_multiplier_from_time(player) if player else 1.0
    # Daily events: Full Moon — monsters grow restless (+20% difficulty)
    if player and player.get("daily_effects", {}).get("full_moon"):
        multiplier *= 1.20
    # Soft cap so stacked time-of-day + event modifiers stay fair
    multiplier = min(multiplier, 2.2)
    pandemonium_mult = 1.7 if player and player.get("pandemonium_mode") else 1.0

    base_hp = template["base_hp"]
    str_mod = attrs["Strength"]
    con_mod = attrs["Constitution"]
    dex_mod = attrs["Dexterity"]
    wis_mod = attrs["Wisdom"]
    ler_mod = attrs["Learning"]
    cha_mod = attrs["Charisma"]

    scaled_hp = int(base_hp * multiplier * pandemonium_mult)
    scaled_str = int(str_mod * (1 + (multiplier - 1) * 0.7) * pandemonium_mult)
    scaled_con = int(con_mod * (1 + (multiplier - 1) * 0.6) * pandemonium_mult)
    scaled_dex = int(dex_mod * (1 + (multiplier - 1) * 0.5) * pandemonium_mult)
    # WIS / LER / CHA drive healing, skill frequency and debuff chance
    # (combat/enemy_scaling.py). Race mods can make them negative (Undead
    # WIS −2, Construct CHA −5), so clamp at zero instead of scaling a
    # negative into a healing penalty.
    scaled_wis = max(0, int(wis_mod * (1 + (multiplier - 1) * 0.5) * pandemonium_mult))
    scaled_ler = max(0, int(ler_mod * (1 + (multiplier - 1) * 0.5) * pandemonium_mult))
    scaled_cha = max(0, int(cha_mod * (1 + (multiplier - 1) * 0.6) * pandemonium_mult))

    result = {
        "key": enemy_key,
        "name": template["name"],
        "race": template.get("race", ""),
        "hp": scaled_hp,
        "max_hp": scaled_hp,
        "str_mod": scaled_str,
        "con_mod": scaled_con,
        "dex_mod": scaled_dex,
        "wis_mod": scaled_wis,
        "ler_mod": scaled_ler,
        "cha_mod": scaled_cha,
        "level": template["level"],
        "multiplier": round(multiplier, 2),
        "monster_girl": template.get("monster_girl", False),
        "boss": template.get("boss", False),
        "super_boss": template.get("super_boss", False),
        "role": template.get("role"),
        "dialogue": template.get("dialogue", {}),
        "status_res": template.get("status_res", 0.0),
        # Regular-enemy ability kit overrides (combat/enemy_skills.py).
        # Absent keys mean "derive from race + name keywords".
        "abilities": template.get("abilities"),
        "ai_disabled": template.get("ai_disabled", False),
    }

    # Solo bosses board alone: trade the escort minions for a much larger HP
    # pool, a stat bump and a second action (combat_engine reads
    # boss_actions). Applied before Event Horizon scaling so the rift scales
    # the buffed instance.
    if template.get("boss") and is_solo_boss(enemy_key, template):
        apply_solo_boss_budget(result)

    # Add elemental stats
    e_res, e_dmg = compute_enemy_elemental(result)
    result["elemental_res"] = e_res
    result["elemental_dmg"] = e_dmg

    # Event Horizon: room scaling + negative trial cards (no-op outside a run)
    apply_enemy_scaling(result, player)

    return result


def get_effective_attribute(player, attr_name):
    """Return effective attribute value after curse/weaken/buffs/equipment/passive."""
    from pandemonium.combat.skills import get_player_passive_effects
    from pandemonium.combat.weapon.authors_pen import get_authors_pen_stat_bonus
    from pandemonium.combat.weapon.tarnished_jade import get_tarnished_jade_str_bonus, get_tarnished_jade_wis_bonus
    base = player["attributes"].get(attr_name, 0)
    equip_mods = get_total_equipment_mods(player)
    total = base + equip_mods.get(attr_name, 0)

    # Apply passive skill bonuses (class passive, or the upgraded profession passive)
    if player.get("passive_unlocked", True):
        for effect in get_player_passive_effects(player):
            if effect.get("stat") == "all":
                if attr_name in effect.get("stats", []):
                    total += effect.get("value", 0)
            elif effect.get("stat") == attr_name:
                total += effect.get("value", 0)

    for debuff in player.get("active_debuffs", []):
        if debuff.get("type") == "curse":
            penalty = debuff.get("penalty", 2)
            total -= penalty

    if attr_name == "Strength":
        weaken_pct = get_weaken_pct(player)
        if weaken_pct > 0:
            total = int(total * (1.0 - weaken_pct))

    for buff in player.get("active_buffs", []):
        if buff.get("type") in ("blessing", "well_rested", "dream_blessed") or buff.get("stat") == "all":
            total += buff.get("value", 0)
        elif buff.get("stat") == attr_name:
            total += buff.get("value", 0)

    # Apply percentage buffs (e.g., cosmic_gravity)
    pct_mult = 1.0
    for buff in player.get("active_buffs", []):
        if buff.get("type") == "wedding_stats":
            pct_mult += buff.get("value", 0)
    if pct_mult != 1.0:
        total = int(total * pct_mult)

    # --- Author's Pen passive: +4 all stats while in Wonderland ---
    total += get_authors_pen_stat_bonus(player, attr_name)

    # --- Tarnished Jade stat bonuses ---
    total += get_tarnished_jade_str_bonus(player)
    total += get_tarnished_jade_wis_bonus(player)

    # --- Tarnished Jade Wedge Backlash 50% debuff ---
    if player.get("tarnished_jade_weakened"):
        total = int(total * 0.5)

    # --- Event Horizon: Entropy (−% all attributes, run-scoped) ---
    for debuff in player.get("active_debuffs", []):
        if debuff.get("type") == "eh_entropy":
            total = int(total * (1.0 - min(0.95, debuff.get("value", 0))))
            break

    # --- Fatigue (§5): −1 all stats per stack (EH runs only — Pande
    # penalizes as of rev 3.5) ---
    fatigue = int(player.get("fatigue_stacks", 0) or 0)
    if fatigue and not player.get("_eh_in_run"):
        total -= fatigue

    # Deed titles: flat attribute bonus (player-only — allies carry no title).
    total += combat_stat_bonus(player, attr_name)

    return total


def compute_player_stats(player):
    p_str = get_effective_attribute(player, "Strength")
    p_con = get_effective_attribute(player, "Constitution")
    p_dex = get_effective_attribute(player, "Dexterity")
    p_ler = get_effective_attribute(player, "Learning")
    p_wis = get_effective_attribute(player, "Wisdom")
    p_cha = get_effective_attribute(player, "Charisma")
    if player.get("training_buff"):
        p_str += player["training_buff"].get("strength", 0)
    return p_str, p_con, p_dex, p_ler, p_wis, p_cha

def player_str_mod(player):
    return get_effective_attribute(player, "Strength")


def player_con_mod(player):
    return get_effective_attribute(player, "Constitution")









# ── Critical Hit System ─────────────────────────────────────────────────────

import random

CRIT_MULTIPLIER = 1.5

# ── Caps & overflow conversion (crit rework 2026-09-27) ──
# Player/ally crit chance caps at 100%. Chance beyond the cap converts to
# bonus crit damage at 2:1 (rate 0.5) — the rate keeps expected damage
# linear across the cap: below it each +100% chance is worth (M-1) = +50%
# damage, and each +100% overflow adds +50% crit damage. Enemies keep their
# old 12% cap with no conversion.
CRIT_CHANCE_CAP = 1.00
CRIT_OVERFLOW_TO_DAMAGE = 0.50
ENEMY_CRIT_CHANCE_CAP = 0.12


def get_raw_critical_chance(entity, entity_type="player", dex=None, lrn=None, bonus=0.0):
    """Return the raw (uncapped) critical hit chance for an entity.

    Formula (Player / Ally):
        Base 5% + min(DEX * 0.003, 8%) + min(LRN * 0.002, 5%) + buffs
    Formula (Enemy):
        Base 3% + min(DEX * 0.003, 6%)

    `bonus` is a flat additive chance (e.g. a skill's crit_bonus).
    Optional dex / lrn can be passed in to avoid circular imports for allies.
    """
    from pandemonium.combat.skills import get_player_passive_crit_bonus
    from pandemonium.progression.family import father_legacy_crit_chance
    if entity_type == "enemy":
        base = 0.03
        dex_val = dex if dex is not None else entity.get("dex_mod", 0)
        dex_bonus = min(dex_val * 0.003, 0.06)
        crit_chance = base + dex_bonus
    else:
        base = 0.05
        if dex is None:
            dex = get_effective_attribute(entity, "Dexterity")
        if lrn is None:
            lrn = get_effective_attribute(entity, "Learning")
        dex_bonus = min(dex * 0.003, 0.08)
        lrn_bonus = min(lrn * 0.002, 0.05)
        crit_chance = base + dex_bonus + lrn_bonus

    # Temporary buffs / debuffs that affect crit chance
    for buff in entity.get("active_buffs", []):
        if buff.get("type") == "crit_chance":
            crit_chance += buff.get("value", 0)
    for debuff in entity.get("active_debuffs", []):
        if debuff.get("type") == "crit_chance_down":
            crit_chance -= debuff.get("value", 0)

    # Profession passive crit chance (player only; allies have no class passives)
    if entity_type != "enemy":
        crit_chance += get_player_passive_crit_bonus(entity)
        # Form tradition (Keen)
        crit_chance += get_form_crit_chance_bonus(entity)
        # Father's Legacy (Halfling child): +5% crit
        if entity.get("is_ally"):
            crit_chance += father_legacy_crit_chance(entity)

    return crit_chance + bonus


def resolve_critical_chance(entity, entity_type="player", dex=None, lrn=None, bonus=0.0):
    """Return (effective_chance, overflow_crit_damage_bonus).

    Player / ally: chance caps at CRIT_CHANCE_CAP (100%); everything above
    converts to a crit-damage multiplier bonus at CRIT_OVERFLOW_TO_DAMAGE.
    Enemy: capped at ENEMY_CRIT_CHANCE_CAP (12%) with no conversion.
    """
    raw = get_raw_critical_chance(entity, entity_type, dex, lrn, bonus)
    if entity_type == "enemy":
        # The Wheel of Fortune (Event Horizon) raises the enemy crit cap.
        cap = entity.get("_eh_crit_cap", ENEMY_CRIT_CHANCE_CAP)
        return max(0.0, min(raw, cap)), 0.0
    overflow = max(0.0, raw - CRIT_CHANCE_CAP)
    # Crit-damage buffs (Perfect Opening, Reckless Abandon) add straight to
    # the crit multiplier — they cannot overflow into the chance cap.
    crit_dmg_bonus = 0.0
    for buff in entity.get("active_buffs", []):
        if buff.get("type") == "crit_damage":
            crit_dmg_bonus += buff.get("value", 0)
    # Form tradition (Brutal)
    if entity_type != "enemy":
        crit_dmg_bonus += get_form_crit_damage_bonus(entity)
    chance = max(0.0, min(raw, CRIT_CHANCE_CAP))
    return chance, overflow * CRIT_OVERFLOW_TO_DAMAGE + crit_dmg_bonus




def format_crit_summary(entity, entity_type="player", dex=None, lrn=None, compact=False):
    """Human-readable crit summary, e.g. 'Crit: 24% (×1.50)'.

    `compact` is used by the combat HUD; the long form is for the character
    stat screens. Includes the overflow bonus when crit chance exceeds 100%.
    """
    chance, overflow = resolve_critical_chance(entity, entity_type, dex, lrn)
    mult = CRIT_MULTIPLIER + overflow
    if compact:
        return f"Crit: {int(round(chance * 100))}%  (×{mult:.2f})"
    text = f"Crit: {int(round(chance * 100))}% chance, ×{mult:.2f} damage"
    if overflow > 0:
        text += f" (overflow bonus +{int(round(overflow * 100))}%)"
    return text


def roll_critical_hit(entity, entity_type="player", dex=None, lrn=None, bonus=0.0):
    """Roll for a critical hit.

    Returns (is_crit, chance, overflow) — add `overflow` to the multiplier
    passed to apply_critical_damage(). Enemies always get overflow 0.0.
    """
    chance, overflow = resolve_critical_chance(entity, entity_type, dex, lrn, bonus)
    return random.random() < chance, chance, overflow


def apply_critical_damage(damage, is_crit, multiplier=CRIT_MULTIPLIER):
    """Apply critical hit multiplier to damage."""
    if is_crit:
        return int(damage * multiplier)
    return damage


def format_critical_tag(is_crit):
    """Return a combat message tag for critical hits."""
    return " [CRITICAL!]" if is_crit else ""

# ── Unified Dodge System ───────────────────────────────────────────────────

PLAYER_DODGE_CAP = 0.80
ENEMY_DODGE_CAP = 0.50


def _get_dodge_dex(entity):
    """Get effective Dexterity for dodge calculations."""
    if "dex_mod" in entity and "attributes" not in entity:
        return entity.get("dex_mod", 0)
    return get_effective_attribute(entity, "Dexterity")


def _get_dodge_wis(entity):
    """Get effective Wisdom for dodge calculations.

    Enemies carry ``wis_mod`` since 2026-11-24 (``enemy_stats`` used to drop
    it). A wise attacker is harder to dodge, so late-game foes with WIS 6–9
    now shave 12–18% off a DEX-only dodge build — the intended counter to the
    80% dodge cap. Hand-built enemy dicts without ``wis_mod`` keep the old
    behaviour (0).
    """
    if "dex_mod" in entity and "attributes" not in entity:
        return entity.get("wis_mod", 0) or 0
    return get_effective_attribute(entity, "Wisdom")


def get_dodge_chance(defender, attacker):
    """Calculate dodge chance based on defender vs attacker DEX & WIS.

    Core formula:
        dex_diff = defender_DEX - attacker_DEX
        wis_diff = defender_WIS - attacker_WIS
        base = max(0, dex_diff * 0.03 + wis_diff * 0.02)

    A highly dexterous / wise defender is hard to hit.
    A highly dexterous / wise attacker is hard to dodge.

    Modifiers (applied before cap):
        Attacker blinded  → +25% dodge (can't aim)
        Attacker dreaded  → +40% dodge (shaky hands)
        Defender blinded  → -25% dodge (can't see to dodge)
        Defender evasion buffs

    Caps: 80% for player / allies, 50% for enemies.
    Wedding bonuses are NOT included — callers add those separately.
    """
    from pandemonium.combat.ally_skills import get_race_evasion
    from pandemonium.progression.family import father_legacy_evasion
    from pandemonium.combat.skills import get_player_passive_evasion
    from pandemonium.combat.weapon.black_silence_gloves import get_gloves_dodge_bonus
    from pandemonium.combat.weapon.palette_brush import get_brush_dodge_bonus
    def_dex = _get_dodge_dex(defender)
    att_dex = _get_dodge_dex(attacker)
    def_wis = _get_dodge_wis(defender)
    att_wis = _get_dodge_wis(attacker)

    dex_diff = def_dex - att_dex
    wis_diff = def_wis - att_wis

    base = max(0.0, dex_diff * 0.03 + wis_diff * 0.02)

    # Status-effect modifiers
    if attacker.get("blinded"):
        base += 0.25
    if attacker.get("dreaded"):
        base += 0.40
    if defender.get("blinded"):
        base -= 0.25

    # Evasion buffs on defender
    for buff in defender.get("active_buffs", []):
        if buff.get("type") == "evasion":
            base += buff.get("value", 0)

    # Sylvana's Queen's Grace — party +5% evasion while she lives
    if defender.get("_mirror_grace"):
        base += 0.05

    # Race passive evasion (Goblin dodge, Shadow evade — allies only)
    if defender.get("is_ally"):
        base += get_race_evasion(defender)
        # Father's Legacy (Elf child): +5% dodge
        base += father_legacy_evasion(defender)

    # Profession passive evasion (player only)
    if not defender.get("is_ally"):
        base += get_player_passive_evasion(defender)

    # Form tradition evasion (Nimble)
    base += get_form_evasion(defender)

    # Black Silence Gloves: +8% dodge when equipped
    base += get_gloves_dodge_bonus(defender)

    # Palette's Brush: +7% dodge for Palette heroine in Verdant stance
    base += get_brush_dodge_bonus(defender)

    # Determine cap by defender type
    is_player_or_ally = "attributes" in defender
    cap = PLAYER_DODGE_CAP if is_player_or_ally else ENEMY_DODGE_CAP
    # Per-entity cap override (e.g. superboss dodge states above the enemy cap)
    override = defender.get("dodge_cap_override")
    if override is not None:
        try:
            cap = max(0.0, min(1.0, float(override)))
        except (TypeError, ValueError):
            pass

    return max(0.0, min(base, cap))


def roll_dodge(defender, attacker, extra_chance=0.0):
    """Roll for dodge. Returns (is_dodged, dodge_chance).

    ``extra_chance`` adds a flat, separately-floored accuracy penalty
    (e.g. the White Knight's ally penalty) on top of the computed dodge,
    capped at +0.35 total and 0.95 absolute.
    """
    chance = get_dodge_chance(defender, attacker)
    if extra_chance:
        extra = min(max(extra_chance, 0.0), 0.35)
        chance = min(chance + extra, 0.95)
    if chance <= 0:
        return False, chance
    return random.random() < chance, chance


def roll_skill_dodge(target):
    """Roll a target's skill dodge (once per action). True = dodged.

    The ``_skill_dodge_used`` marker is cleared at the start of each party /
    ally action, so multi-hit skills roll once per activation.
    """
    if target.get("_skill_dodge_used"):
        return False
    chance = target.get("skill_dodge_chance", 0.0) or 0.0
    if chance <= 0:
        return False
    target["_skill_dodge_used"] = True
    if chance >= 1.0:
        return True
    return random.random() < chance


def roll_accuracy_penalty(target):
    """Roll a target's flat accuracy penalty vs allies (once per action).

    Used by the White Knight's Disarming Flourish (allies suffer -20% hit
    rate, floored at -35%).
    """
    if target.get("_accuracy_penalty_used"):
        return False
    chance = min(max(target.get("ally_accuracy_penalty", 0.0) or 0.0, 0.0), 0.35)
    if chance <= 0:
        return False
    target["_accuracy_penalty_used"] = True
    return random.random() < chance
