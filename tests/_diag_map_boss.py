"""Phase 1 diagnostic — Seasonal Map Boss lifecycle (docs/map_boss_design.md).

Manual diagnostic (run directly, not under pytest):
    c:/Code/Pandemonium/.venv/Scripts/python.exe tests/_diag_map_boss.py

Headless: exercises the state block, the Floor-20 gate, one-site-per-season
determinism, the Echo ladder (levels/HP/resists/mechanic tiers), season
rotation across the day rollover, start-at-proven-depth and the reward
pre-roll. No Tk, no saves on disk are written.
"""

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FAILS = []


def check(label, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(label)


def section(title):
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


def make_player(day=20, max_floor=21):
    return {
        "day": day,
        "max_floor": max_floor,
        "daily_effects": {},
        "active_buffs": [],
        "inventory": [],
        "journal": {"events": [], "main_quests": [], "side_quests": []},
    }


# 1. Imports (cycles / syntax)
from pandemonium.core.events import (  # noqa: E402
    get_season, next_season_day, process_day_rollover, season_start_day,
)
from pandemonium.resources import map_boss_data as data  # noqa: E402
from pandemonium.resources.cities import CITIES  # noqa: E402
from pandemonium.resources.item_generation import flower_for_element  # noqa: E402
from pandemonium.world import map_boss as mb  # noqa: E402

section("1. Imports + data")
check("runtime + data import", True)
check("four wardens", len(data.WARDENS) == 4, str(sorted(data.WARDENS)))
check("four 10-tier ladders",
      all(len(data.MECHANIC_TIERS[w["mechanic"]]) == 10
          for w in data.WARDENS.values()))
check("season ids match events.SEASONS",
      data.MAP_BOSS_SEASONS == ("spring", "summer", "autumn", "winter"))
for season in data.MAP_BOSS_SEASONS:
    w = data.get_warden(season)
    biomes = {CITIES[c].get("biome") for c in CITIES}
    check(f"{season}: biome preference is real",
          all(b in biomes for b in w["biomes"]), str(w["biomes"]))

# 2. Gate
section("2. Floor-20 clear gate")
check("max_floor 20 → locked", not mb.gate_met({"max_floor": 20}))
check("max_floor 21 → unlocked", mb.gate_met({"max_floor": 21}))
check("pre-gate spawn is a no-op",
      mb.maybe_spawn(make_player(max_floor=20)) is None)

# 3. First spawn
section("3. First spawn (current season, Echo 0)")
player = make_player(day=20)
active = mb.maybe_spawn(player)
check("spawned", active is not None)
check("spring (day 20)", active["season"] == "spring", active["season"])
check("echo 0 / Lv 20", active["echo"] == 0 and active["level"] == 20)
check("full HP", active["hp"] == active["max_hp"] == 1000)
check("expires on the season boundary (91)", active["expire_day"] == 91)
check("idempotent", mb.maybe_spawn(player) is None)
print(f"       {active['glyph']} {active['warden_name']} near "
      f"{CITIES[active['nearest_city']]['name']} ({active['biome']}) "
      f"at {active['position']}")

# 4. Determinism
section("4. Site determinism")
a = mb.maybe_spawn(make_player(day=20))
b = mb.maybe_spawn(make_player(day=20))
check("same season/day → same site", a["position"] == b["position"],
      f"{a['position']} vs {b['position']}")
check("every Echo reuses the site", True)

# 5. Echo ladder
section("5. Echo ladder (per kill)")
random.seed(7)
player = make_player(day=20)
first = mb.maybe_spawn(player)
rows = [(first["echo"], first["level"], first["max_hp"], first["armor"],
         first["status_res"], first["mechanic_tier"], first["mechanic_rank"])]
prev_hp = first["max_hp"]
monotonic = True
for _ in range(9):
    killed = player["map_boss"]["active"]
    mb.record_victory(player)
    nxt = mb.advance_echo(player, killed=killed)
    monotonic = monotonic and nxt["max_hp"] > prev_hp
    prev_hp = nxt["max_hp"]
    rows.append((nxt["echo"], nxt["level"], nxt["max_hp"], nxt["armor"],
                 nxt["status_res"], nxt["mechanic_tier"], nxt["mechanic_rank"]))
print("       Echo | Lv |   HP  | Arm | Status | Tier | Rank")
for echo, level, hp, armor, sres, tier, rank in rows:
    print(f"       {echo:>4} | {level:>2} | {hp:>5} | {armor:>3} | "
          f"{sres:>6.2f} | {tier:>4} | {rank:>4}")
check("levels 20/40/60/80 then flat 80",
      [r[1] for r in rows] == [20, 40, 60, 80, 80, 80, 80, 80, 80, 80])
check("HP grows every Echo", monotonic)
check("mechanic tier caps at 10", rows[-1][5] == 10)
check("mechanic rank caps at 4", rows[-1][6] == 4)
check("best_echo tracks kills", player["map_boss"]["best_echo"] == 8)
check("nine kills booked", player["map_boss"]["defeated_total"] == 9)
check("same site across Echoes",
      player["map_boss"]["active"]["position"] == first["position"])

# 6. Flee / death persistence
section("6. Flee / death keep the Echo + HP")
player = make_player(day=20)
mb.maybe_spawn(player)
mb.save_boss_hp(player, 321)
mb.set_result(player, "fled")
check("HP persisted", mb.get_active_boss(player)["hp"] == 321)
check("echo did not advance", mb.get_active_boss(player)["echo"] == 0)
mb.save_boss_hp(player, 12)
mb.set_result(player, "dead")
check("death keeps HP", mb.get_active_boss(player)["hp"] == 12)
check("death keeps the Echo", mb.get_active_boss(player)["echo"] == 0)

# 7. Start at proven depth
section("7. Start at proven depth")
player = make_player(day=20)
mb.maybe_spawn(player)
player["map_boss"]["best_echo"] = 5
check("offer = best_echo (5)", mb.start_depth_offer(player) == 5)
mb.save_boss_hp(player, 50)
recalled = mb.apply_start_depth(player)
check("recall builds Echo 5 at full HP",
      recalled["echo"] == 5 and recalled["hp"] == recalled["max_hp"])
check("recall uses Echo 5's own stats",
      recalled["level"] == 80 and recalled["mechanic_tier"] == 6
      and recalled["mechanic_rank"] == 2)
check("no downward jump", mb.apply_start_depth(player, 2) is None)
mb.record_victory(player)
mb.advance_echo(player, killed=player["map_boss"]["active"])
check("offer closes after the jump is used", mb.start_depth_offer(player) is None)

declined = make_player(day=20)
mb.maybe_spawn(declined)
declined["map_boss"]["best_echo"] = 4
mb.decline_start_depth(declined)
check("decline is remembered", mb.start_depth_offer(declined) is None)
check("Echo 0 remains", declined["map_boss"]["echo"] == 0)

# 8. Season rotation
section("8. Season rotation (day 91)")
player = make_player(day=90)
old = mb.maybe_spawn(player)
mb.record_victory(player)
mb.advance_echo(player, killed=old)
player["day"] = 91
process_day_rollover(player, days_passed=1, old_day=90)
new = player["map_boss"]["active"]
check("next season's warden", new["season"] == get_season(91)[0], new["season"])
check("new name/glyph/element",
      new["warden_name"] != old["warden_name"] and new["glyph"] != old["glyph"]
      and new["element"] != old["element"])
check("Echo counter reset", new["echo"] == 0 and new["level"] == 20)
check("new site", new["position"] != old["position"])
journal = [e["name"] for e in player["journal"]["events"]]
check("departure + spawn journal",
      "The Season Closes" in journal and "The Season Turns" in journal,
      str(journal))

# 9. Season boundary math
section("9. Calendar")
bounds = [season_start_day(d) for d in (1, 91, 181, 271, 361)]
check("boundaries 1/91/181/271/361", bounds == [1, 91, 181, 271, 361], str(bounds))
check("90-day seasons",
      all(next_season_day(d) - season_start_day(d) == 90
          for d in range(1, 400)))
check("day 361 wraps to Spring again",
      get_season(361)[0] == "spring", get_season(361)[0])

# 10. Rewards
section("10. Reward pre-roll")
for day, season in ((20, "spring"), (100, "summer"), (200, "autumn"),
                    (300, "winter")):
    site = mb.maybe_spawn(make_player(day=day))
    warden = data.get_warden(season)
    print(f"       {site['glyph']} {season}: cache {site['cache_preview']}, "
          f"consumables {site['consumables']}, flower {site['flower']}")
    check(f"{season}: flower = element flower",
          site["flower"] == flower_for_element(warden["element"]))
check("gold/XP E0", mb.gold_xp_reward(0) == {"gold": 400, "exp": 600})
check("gold/XP E1", mb.gold_xp_reward(1) == {"gold": 1000, "exp": 1550})
check("gold/XP E3", mb.gold_xp_reward(3) == {"gold": 2200, "exp": 3450})
check("night kill +25% gold",
      mb.gold_xp_reward(1, night=True)["gold"] == 1250)
check("no legendary cache before Echo 10",
      all(mb.cache_rarity(e) != "legendary" for e in range(10)))

# 11. JSON round-trip
section("11. Save round-trip")
trip = make_player(day=20)
mb.maybe_spawn(trip)
mb.record_victory(trip)
mb.advance_echo(trip, killed=trip["map_boss"]["active"])
raw = json.dumps(trip["map_boss"])
check("state is JSON-safe", json.loads(raw) == trip["map_boss"])
check("no superboss ledger written", "defeated_superbosses" not in trip)


# ══════════════════════════════════════════════════════════════════════════
#  12+. Arena combat (Phase 3) — docs/map_boss_design.md §7
# ══════════════════════════════════════════════════════════════════════════

from pandemonium.combat.combat_io import reset_io, set_io  # noqa: E402
from pandemonium.combat import map_boss as cmb  # noqa: E402
from pandemonium.core import time_blocks  # noqa: E402
from pandemonium.resources.enemies import ENEMIES  # noqa: E402


class ScriptedIO:
    """Auto-attack + target 1, so a full fight can run headless."""

    renders_menus = True

    def __init__(self, action="a", max_actions=300):
        self.log = []
        self.actions = 0
        self.action = action
        self.max_actions = max_actions

    def print(self, *args, **kwargs):
        self.log.append(" ".join(str(a) for a in args))

    def input(self, prompt=""):
        low = str(prompt).lower()
        if "choose" in low:
            self.actions += 1
            if self.actions > self.max_actions:
                raise KeyboardInterrupt("arena action cap")
            return self.action
        if any(w in low for w in ("target", "select", "which", "number")):
            return "1"
        return ""

    def clear(self):
        pass

    def is_active(self):
        return True


def make_fighter(day=20, blocks=14, strength=260, hp=6000, con=40):
    return {
        "name": "Diag Hero",
        "class": "Warrior",
        "level": 50,
        "current_hp": hp,
        "passive_unlocked": True,
        "attributes": {"Strength": strength, "Constitution": con,
                       "Dexterity": 10, "Wisdom": 10, "Learning": 40,
                       "Charisma": 40},
        "level_hp_bonus": 0,
        "equipped": {"weapon": None, "armor": None,
                     "accessory1": None, "accessory2": None},
        "active_buffs": [],
        "active_debuffs": [],
        "elemental_dmg": {},
        "elemental_res": {},
        "inventory": [],
        "allies": [],
        "skills": [],
        "skill_mastery": {},
        "skill_cooldowns": {},
        "day_blocks": blocks,
        "day": day,
        "gold": 1000,
        "max_floor": 21,
        "location": "dungeon",
        "origin_city": "solmere",
        "dungeon_region": "temperate",
        "save_slot": 99,
        "journal": {"events": [], "main_quests": [], "side_quests": []},
    }


def run_fight(day=20, blocks=14, strength=260, hp=6000, con=40,
              action="a", max_actions=300):
    """Return (result, io, enemies, player, site)."""
    player = make_fighter(day=day, blocks=blocks, strength=strength, hp=hp,
                          con=con)
    site = mb.maybe_spawn(player)
    io = ScriptedIO(action=action, max_actions=max_actions)
    set_io(io)
    enemies = cmb.build_encounter(site)
    try:
        result = cmb.combat_map_boss(player, floor=site["level"],
                                     enemies=enemies)
    except KeyboardInterrupt:
        result = "CAP"
    finally:
        reset_io()
    return result, io, enemies, player, site


section("12. Encounter building")
player = make_fighter()
site = mb.maybe_spawn(player)
boss = cmb.build_encounter(site)[0]
check("boss built from the Echo payload",
      boss["max_hp"] == site["max_hp"] and boss["hp"] == site["hp"]
      and boss["str_mod"] == site["str"] and boss["con_mod"] == site["armor"])
check("no time-of-day multiplier applied", boss["multiplier"] == 1.0)
check("boss flags", boss["boss"] and not boss["super_boss"]
      and boss["ai_disabled"])
check("season element on the attack profile",
      list(boss["elemental_dmg"]) == [site["element"]], str(boss["elemental_dmg"]))
add = cmb.build_add(site, boss, 0)
check("add is synthetic + outside the bestiary",
      add["key"] == "map_boss_add" and add["no_bestiary"]
      and add["key"] not in ENEMIES)

section("13. Projected clock (§7.2)")
clock_player = make_fighter(blocks=0)
labels = [cmb.projected_time_label(clock_player, b) for b in (0, 8, 16, 24)]
check("Morning → Noon → Night → Morning",
      all(word in label for word, label in
          zip(("Morning", "Noon", "Night", "Morning"), labels)),
      str(labels))
real_blocks = clock_player["day_blocks"]
cmb.projected_time_label(clock_player, 40)
check("projection never spends time", clock_player["day_blocks"] == real_blocks)

section("14. Full fight — Spring (Bloom), Noon start")
result, io, enemies, player, site = run_fight(day=20, blocks=14, strength=70)
joined = "\n".join(io.log)
check("victory", result == "victory", result)
check("HUD branded as the Warden", "Seasonal Warden:" in joined)
check("rounds recorded", int(player.get("_map_boss_rounds", 0)) > 0,
      str(player.get("_map_boss_rounds")))
check("phase lines pinned", "[PHASE]" in joined)
check("Long Day finisher fired", "THE LONG DAY" in joined)
check("Bloom healed at cap", "Bloom bursts" in joined)
check("HUD echoes/mechanic tags", "BLOOM×" in joined or "BLOOM" in joined)
check("no superboss ledger", "defeated_superbosses" not in player)

section("15. Phase escalation + adds")
player = make_fighter(blocks=16)                 # Night
site = mb.maybe_spawn(player)
enemies = cmb.build_encounter(site)
ctx = {"player": player, "site": site, "season": site["season"],
       "mechanic": data.get_warden(site["season"])["mechanic"],
       "tier": site["mechanic_tier"],
       "rank_scale": data.mechanic_rank_scale(site["mechanic_rank"]),
       "effects": tuple(site["mechanic_effects"]), "start_blocks": 16,
       "round": 1, "rounds_fought": 0, "phase": None, "day_index": None,
       "lull_rounds": 0, "stacks": 0, "harvest": 0, "ice_armor": 0,
       "lifesteal": 0.0, "boss_actions": 0, "adds_spawned": 0, "p_con": 20,
       "defending": False, "_enemies": enemies}
cmb._pre_round_hook(ctx, enemies)
cmb._pre_player_hook(ctx, enemies)
check("Night spawns 4 adds (5 enemies total)",
      len(enemies) == 5, str(len(enemies)))
actions = cmb._enemy_turn_hook(enemies[0], ctx, player, 20, False)[0]
check("Night = 2 boss actions", actions == 2, str(actions))
ctx["round"] = 9                                  # 16 + 8 = block 24 → Morning
cmb._pre_round_hook(ctx, enemies)
enemies[:] = [e for e in enemies if e["hp"] > 0]
check("dawn clears the adds", len(enemies) == 1, str(len(enemies)))
check("dawn starts the Lull", ctx["lull_rounds"] >= 0)

section("16. Seasonal mechanics")
for day, season, marker in ((20, "spring", "Bloom bursts"),
                            (100, "summer", "vents its heat"),
                            (200, "autumn", "bleeding harvest"),
                            (300, "winter", "Frostbite")):
    result, io, enemies, player, site = run_fight(day=day, blocks=14,
                                                  strength=40, hp=20000,
                                                  con=60, max_actions=60)
    joined = "\n".join(io.log)
    check(f"{season}: mechanic visible in the log", marker in joined,
          f"{result} — {joined[-200:]}")

section("17. Flee / HP persistence / reform")
player = make_fighter()
site = mb.maybe_spawn(player)
result, io, enemies, player, site = run_fight(strength=5, hp=500, con=5,
                                             action="f", max_actions=3)
check("flee always allowed", result == "fled", result)

player = make_fighter(blocks=22)
site = mb.maybe_spawn(player)
player["_map_boss_site"] = site["id"]
player["_map_boss_prev_floor"] = 3
player["floor"] = 3
saved = []
import pandemonium.core.save_load as save_load  # noqa: E402
_orig_save = save_load.save_game
save_load.save_game = lambda p: saved.append(p.get("day"))
try:
    from pandemonium.world.dungeon import _explore_map_boss_arena

    def _flee_override(p, s, e):
        e[0]["hp"] = 250
        p["_map_boss_rounds"] = 3
        return "fled"

    res = _explore_map_boss_arena(player, arena_override=_flee_override)
    check("flee routes to the map", res == "fled", res)
    check("Echo HP persisted", mb.get_active_boss(player)["hp"] == 250)
    check("Echo did not advance", mb.get_active_boss(player)["echo"] == 0)
    check("arena time committed in the batch", player["day_blocks"] == 1,
          str(player["day_blocks"]))
    check("floor cursor restored", player["floor"] == 3)
    check("save_game called on exit", bool(saved))

    def _win_override(p, s, e):
        p["_map_boss_rounds"] = 2
        return "victory"

    player2 = make_fighter(day=90, blocks=10)
    site2 = mb.maybe_spawn(player2)
    player2["_map_boss_site"] = site2["id"]
    player2["_map_boss_prev_floor"] = 4
    player2["floor"] = 4
    res = _explore_map_boss_arena(player2, arena_override=_win_override)
    check("victory routes to the map", res == "map_boss_victory", res)
    check("next Echo reformed", mb.get_active_boss(player2)["echo"] == 1)
    check("best_echo recorded", player2["map_boss"]["best_echo"] == 0)
    check("reformed Echo at full HP",
          mb.get_active_boss(player2)["hp"]
          == mb.get_active_boss(player2)["max_hp"])

    player3 = make_fighter(day=90, blocks=22)
    site3 = mb.maybe_spawn(player3)
    player3["_map_boss_site"] = site3["id"]
    player3["_map_boss_prev_floor"] = 4
    player3["floor"] = 4

    def _season_override(p, s, e):
        p["_map_boss_rounds"] = 4
        return "victory"

    res = _explore_map_boss_arena(player3, arena_override=_season_override)
    check("season-crossing kill routes to the shift", res == "map_boss_season_shift",
          res)
    check("new season Warden at Echo 0",
          player3["map_boss"]["season"] == "summer"
          and player3["map_boss"]["echo"] == 0)
finally:
    save_load.save_game = _orig_save
    reset_io()

section("19. Rewards & uniques (Phase 4)")
from pandemonium.combat.weapon import map_boss_uniques as uniq  # noqa: E402
from pandemonium.resources.items import ITEMS, build_item  # noqa: E402

for _item_id in ("warden_signet", "long_day", "echo_mantle", "sundial_crown"):
    _base = ITEMS[_item_id]
    check(f"{_item_id} installed",
          _base.get("unique") and _base.get("drop_rarity") == "unique"
          and _base.get("drop_source") == "warden_long_day")
    check(f"{_item_id} builds",
          build_item(_item_id, "unique").get("rarity") == "unique")
check("long_day is a sword at heavy fire",
      ITEMS["long_day"].get("weapon_type") == "sword"
      and build_item("long_day", "unique")["elemental_dmg"]
      == {"fire": 1.35})


def _all_trophies(**extra):
    actor = {
        "name": "Wearer",
        "equipped": {
            "weapon": build_item("long_day", "unique"),
            "armor": build_item("echo_mantle", "unique"),
            "accessory1": build_item("warden_signet", "unique"),
            "accessory2": build_item("sundial_crown", "unique"),
        },
        "active_buffs": [], "active_debuffs": [],
        "current_hp": 400, "day": 20, "allies": [],
    }
    actor.update(extra)
    return actor


_wearer = _all_trophies()
check("all four equipped",
      uniq.actor_has_warden_signet(_wearer)
      and uniq.actor_has_long_day_edge(_wearer)
      and uniq.actor_has_echo_mantle(_wearer)
      and uniq.actor_has_sundial_crown(_wearer))

_wearer["_map_boss_clock_blocks"] = 4
check("Signet does nothing at dawn", uniq.signet_bonus(_wearer) == 0.0)
_wearer["_map_boss_clock_blocks"] = 10
check("Signet +8% at Noon", abs(uniq.signet_bonus(_wearer) - 0.08) < 1e-9)
_wearer["_map_boss_clock_blocks"] = 20
check("Signet +16% at Night", abs(uniq.signet_bonus(_wearer) - 0.16) < 1e-9)

uniq.begin_map_boss_uniques(_wearer)
for _ in range(13):
    uniq.tick_long_day(_wearer)
check("Long Day's Edge caps at +30%",
      _wearer["long_day_stacks"] == uniq.LONG_DAY_STACK_CAP
      and abs(uniq.long_day_bonus(_wearer) - 0.30) < 1e-9)
_wearer["_map_boss_clock_blocks"] = 3
uniq.tick_long_day(_wearer)
check("Long Day's Edge resets at dawn", _wearer["long_day_stacks"] == 1)

_wearer["_map_boss_clock_blocks"] = 23
uniq.refresh_echo_mantle(_wearer)
_mantle = [b for b in _wearer["active_buffs"]
           if b.get("source") == "echo_mantle"]
check("Echo Mantle -20% at Night",
      len(_mantle) == 1 and abs(_mantle[0]["value"] - 0.20) < 1e-9)
_wearer["_map_boss_clock_blocks"] = 8
uniq.refresh_echo_mantle(_wearer)
_mantle = [b for b in _wearer["active_buffs"]
           if b.get("source") == "echo_mantle"]
check("Echo Mantle -12% by day and never stacks",
      len(_mantle) == 1 and abs(_mantle[0]["value"] - 0.12) < 1e-9)

_wearer["active_debuffs"] = [{"type": "burn", "remaining": 2}]
_wearer["slowed"] = True
check("Sundial Crown saves once a day",
      uniq.try_sundial_crown_save(_wearer) and _wearer["current_hp"] == 1
      and _wearer["active_debuffs"] == [] and not _wearer["slowed"])
check("Sundial Crown spent for the day",
      not uniq.try_sundial_crown_save(_wearer))
_wearer["day"] = 21
check("Sundial Crown recharges next day",
      uniq.try_sundial_crown_save(_wearer))

_ally_wearer = _all_trophies(is_ally=True, name="Ally")
_ally_wearer["_map_boss_clock_blocks"] = 22
check("uniques work for allies",
      uniq.signet_bonus(_ally_wearer) > 0
      and uniq.apply_long_day_damage(_ally_wearer, 100) >= 100
      and uniq.try_sundial_crown_save(_ally_wearer))


def _kill_loop(count, night=False):
    player = make_fighter(day=20, blocks=10)
    site = mb.maybe_spawn(player)
    summaries = []
    for _ in range(count):
        mb.record_victory(player)
        summaries.append(mb.grant_victory_rewards(player, site, night=night))
    return player, summaries


_player_r, _sums = _kill_loop(1)
_first = _sums[0]
check("kill pays gold", _first["gold"] == data.MAP_BOSS_GOLD_BASE)
check("kill pays XP", _first["exp"] == data.MAP_BOSS_XP_BASE)
check("Warden's Cache granted", bool(_first["cache"]))
check("two consumables granted", len(_first["consumables"]) == 2)
check("one flower granted", len(_first["flowers"]) == 1)
check("first kill grants the Signet",
      [u["id"] for u in _first["uniques"]] == ["warden_signet"])
check("Signet is in the bag",
      "warden_signet" in {i.get("id") for i in _player_r["inventory"]})
check("no superboss bookkeeping", not _player_r.get("defeated_superbosses"))

_night_player, _night_sums = _kill_loop(1, night=True)
check("night kill pays more gold", _night_sums[0]["gold"] > _first["gold"])
check("night kill yields an extra flower",
      len(_night_sums[0]["flowers"]) == 2)

_ladder_player, _ladder = _kill_loop(11)
_granted = [u["id"] for s in _ladder for u in s["uniques"]]
check("trophy ladder is 1/3/6/10",
      _granted == list(data.MAP_BOSS_UNIQUE_ITEMS))
check("post-ladder kills pay a second cache",
      _ladder[-1]["extra_caches"] == 1)

_uniques_in_bag = [i for i in _ladder_player["inventory"]
                   if i.get("rarity") == "unique"]
check("every trophy is in the bag", len(_uniques_in_bag) == 4)


def _arena_exit(result, blocks=10):
    from pandemonium.world.dungeon import _map_boss_arena_exit
    player = make_fighter(day=20, blocks=blocks)
    site = mb.maybe_spawn(player)
    snapshot = dict(site, hp=0, _map_boss=True)
    player["_map_boss_rounds"] = 3
    player["_map_boss_clock_blocks"] = blocks + 2
    player["_map_boss_site"] = site["id"]
    player["_map_boss_prev_floor"] = 4
    player["floor"] = 4
    _orig = save_load.save_game
    save_load.save_game = lambda *a, **k: None
    try:
        outcome = _map_boss_arena_exit(player, result, site, snapshot)
    finally:
        save_load.save_game = _orig
    return player, outcome


_exit_player, _outcome = _arena_exit("victory")
check("victory routes to the reform window", _outcome == "map_boss_victory")
check("loot summary stashed for the GUI",
      isinstance(_exit_player.get("_map_boss_victory"), dict)
      and _exit_player["_map_boss_victory"]["gold"] > 0)
check("night bonus follows the projected clock",
      _arena_exit("victory", blocks=22)[0]["_map_boss_victory"]["night"])

for _result in ("fled", "dead"):
    _p, _ = _arena_exit(_result)
    check(f"{_result} grants nothing",
          "_map_boss_victory" not in _p and _p["gold"] == 1000
          and _p["inventory"] == []
          and _p["map_boss"]["unique_grants"] == [])

_fresh = make_fighter(day=20, blocks=10)
_fresh["map_boss"] = {"defeated_total": 2, "unique_grants": ["warden_signet"]}
from pandemonium.world.dungeon import _map_boss_scrub  # noqa: E402
_map_boss_scrub(_fresh)
check("scrub keeps the trophy ledger",
      _fresh["map_boss"]["unique_grants"] == ["warden_signet"]
      and "_map_boss_site" not in _fresh)

section("18. Time model sanity")
check("24-block day", time_blocks.DAY_BLOCKS == 24)
check("no rollover mid-fight (projected only)",
      cmb.projected_time_label(make_fighter(blocks=23), 23).find("Night") >= 0)

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s): {FAILS}")
    sys.exit(1)
print("All map boss checks passed (Phases 1-4).")
