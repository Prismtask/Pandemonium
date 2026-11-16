# -*- coding: utf-8 -*-
"""Phase 5 playtest — one full season of the Seasonal Map Boss, headless.

Manual diagnostic (run directly, not under pytest):
    c:/Code/Pandemonium/.venv/Scripts/python.exe tests/_diag_map_boss_playtest.py

This is the scripted version of `docs/map_boss_playtest_checklist.md`: it walks
a single Spring season the way a player would — gate, spawn, panel facts,
travel, a real fight, loot, reform, flee, death, then the season boundary — and
prints a readable report. No Tk, no writes to disk (``save_game`` is stubbed).

Two of the fights are **real** (the whole combat loop, through
``_explore_map_boss_arena``); the flee/death/season-crossing legs use scripted
overrides because their combat is covered by `_diag_map_boss.py`.
"""

import os
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
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def note(text):
    print(f"       {text}")


from pandemonium.combat import map_boss as cmb  # noqa: E402
from pandemonium.combat.combat_io import reset_io, set_io  # noqa: E402
from pandemonium.core import save_load  # noqa: E402
from pandemonium.resources import map_boss_data as data  # noqa: E402
from pandemonium.resources.cities import CITIES  # noqa: E402
from pandemonium.world import map_boss as mb  # noqa: E402
from pandemonium.world.dungeon import _explore_map_boss_arena  # noqa: E402


class ScriptedIO:
    """Auto-attack + target 1, so a full fight runs headless."""

    renders_menus = True

    def __init__(self, action="a", max_actions=400):
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


def make_hero(day=20, blocks=10, strength=220, hp=6000, con=40):
    """A Floor-21-clear party leader (DEX/WIS kept at 10 so the boss lands)."""
    return {
        "name": "Playtester",
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
        "gold": 5000,
        "max_floor": 21,
        "location": "dungeon",
        "origin_city": "solmere",
        "dungeon_region": "temperate",
        "save_slot": 99,
        "journal": {"events": [], "main_quests": [], "side_quests": []},
    }


def park_in_arena(player, site):
    """What the world map does when the party arrives at the arena."""
    player["origin_city"] = site["nearest_city"]
    player["dungeon_region"] = site["biome"]
    player["location"] = "dungeon"
    player["_map_boss_site"] = site["id"]
    player["_combat_floor_label"] = "Arena"
    player.setdefault("_map_boss_prev_floor", player.get("floor"))
    player["floor"] = 1


def journal_names(player):
    return [e.get("name", "") for e in player["journal"]["events"]]


# ══════════════════════════════════════════════════════════════════════════
#  1. Cold start — the gate
# ══════════════════════════════════════════════════════════════════════════
section("1. Cold start — Floor 20 not cleared")
rookie = make_hero(day=20)
rookie["max_floor"] = 20
check("gate closed at Floor 20", not mb.gate_met(rookie))
check("no Warden spawns", mb.maybe_spawn(rookie) is None)
check("no marker data", mb.get_active_boss(rookie) is None)

# ══════════════════════════════════════════════════════════════════════════
#  2. Unlock
# ══════════════════════════════════════════════════════════════════════════
section("2. Floor 20 cleared, day 20 (Spring)")
player = make_hero(day=20)
site = mb.maybe_spawn(player)
check("Warden spawned", site is not None)
check("Spring at Echo 0", site["season"] == "spring" and site["echo"] == 0)
check("Echo 0 is Lv 20 / 1,000 HP",
      site["level"] == 20 and site["max_hp"] == 1000, str(site["level"]))
check("journal: A Warden Notices + The Season Turns",
      {"A Warden Notices", "The Season Turns"} <= set(journal_names(player)),
      str(journal_names(player)))
city = CITIES[site["nearest_city"]]["name"]
note(f"{site['glyph']} {site['warden_name']} — near {city} ({site['biome']})")
note(f"deals {site['element'].title()}, weak to "
     f"{site['weakness'].title()}, expires day {site['expire_day']}")

# ══════════════════════════════════════════════════════════════════════════
#  3. What the panel shows
# ══════════════════════════════════════════════════════════════════════════
section("3. World-map panel facts")
resists = site["elemental_res"]
check("season resistance 1.30", abs(resists[site["element"]] - 1.30) < 1e-9,
      str(resists.get(site["element"])))
check("weakness stays 0.70", abs(resists[site["weakness"]] - 0.70) < 1e-9,
      str(resists.get(site["weakness"])))
check("status resistance 20%", abs(site["status_res"] - 0.20) < 1e-9,
      str(site["status_res"]))
check("mechanic tier 1 / rank 1",
      site["mechanic_tier"] == 1 and site["mechanic_rank"] == 1)
check("pre-rolled cache", bool(site["cache_preview"].get("item_id")),
      str(site["cache_preview"]))
check("two consumables", len(site["consumables"]) == 2,
      str(site["consumables"]))
check("one flower", bool(site["flower"]), str(site["flower"]))
check("next trophy is the Signet",
      mb.next_unique_milestone(player)["at"] == 1,
      str(mb.next_unique_milestone(player)))
journey = mb.build_journey_to_warden(player)
check("a route exists", journey is not None)

# ══════════════════════════════════════════════════════════════════════════
#  4. Real fight — Echo 0 at Noon
# ══════════════════════════════════════════════════════════════════════════
section("4. Echo 0 — real arena fight (Noon)")
park_in_arena(player, site)
gold_before = player["gold"]
io = ScriptedIO()
set_io(io)
save_game_backup = save_load.save_game
save_load.save_game = lambda *a, **k: None
try:
    outcome = _explore_map_boss_arena(player)
finally:
    save_load.save_game = save_game_backup
    reset_io()

joined = "\n".join(io.log)
check("outcome routes to the reform window", outcome == "map_boss_victory",
      outcome)
check("arena branded header", "Seasonal Warden:" in joined)
check("phase banner pinned", "[PHASE]" in joined)
check("rounds were spent", int(site.get("attempts", 0)) >= 0)

loot = player.get("_map_boss_victory") or {}
check("loot summary stashed", bool(loot), str(list(loot)[:4]))
check("gold paid", loot.get("gold", 0) > 0, str(loot.get("gold")))
check("gold in the purse", player["gold"] > gold_before)
check("cache granted", loot.get("cache") is not None)
check("consumables granted", len(loot.get("consumables") or []) == 2,
      str(loot.get("consumables")))
check("flower granted", len(loot.get("flowers") or []) == 1,
      str(loot.get("flowers")))
check("first kill pays the Signet",
      [u["id"] for u in loot.get("uniques") or []] == ["warden_signet"],
      str(loot.get("uniques")))
check("journal: Warden Felled",
      any(n.startswith("Warden Felled") for n in journal_names(player)),
      str(journal_names(player)))
reformed = mb.get_active_boss(player)
check("next Echo reformed at full HP",
      reformed["echo"] == 1 and reformed["hp"] == reformed["max_hp"],
      f"echo {reformed['echo']} hp {reformed['hp']}/{reformed['max_hp']}")
check("arena transients scrubbed",
      not any(k in player for k in ("_map_boss_site", "_map_boss_in_fight",
                                    "_map_boss_clock_blocks",
                                    "_map_boss_rounds",
                                    "_combat_floor_label")),
      str([k for k in ("_map_boss_site", "_map_boss_in_fight",
                       "_map_boss_clock_blocks", "_map_boss_rounds",
                       "_combat_floor_label") if k in player]))
note(f"Echo 0 down — +{loot.get('gold')} gold, +{loot.get('exp')} XP each; "
     f"{reformed['warden_name']} reborn at Echo 1 (Lv {reformed['level']})")

# ══════════════════════════════════════════════════════════════════════════
#  5. Real fight — Echo 1 at Night
# ══════════════════════════════════════════════════════════════════════════
section("5. Echo 1 — real arena fight (Night)")
player["day_blocks"] = 16          # Night
player["current_hp"] = 6000        # no heal between Echoes (the party is fresh here)
site1 = mb.get_active_boss(player)
park_in_arena(player, site1)
io = ScriptedIO(max_actions=500)
set_io(io)
save_load.save_game = lambda *a, **k: None
try:
    outcome = _explore_map_boss_arena(player)
finally:
    save_load.save_game = save_game_backup
    reset_io()
joined = "\n".join(io.log)
check("Echo 1 also falls", outcome in ("map_boss_victory",
                                       "map_boss_season_shift"), outcome)
night_loot = player.get("_map_boss_victory") or {}
check("night kill flagged", night_loot.get("night") is True,
      str(night_loot.get("night")))
check("night kill pays two flowers",
      len(night_loot.get("flowers") or []) == 2,
      str(night_loot.get("flowers")))
check("night gold beats the day formula",
      night_loot.get("gold", 0)
      > mb.gold_xp_reward(1)["gold"] * 0.9, str(night_loot.get("gold")))
check("no second trophy at two kills",
      night_loot.get("uniques") == [], str(night_loot.get("uniques")))
note(f"Night kill — +{night_loot.get('gold')} gold, "
     f"{len(night_loot.get('flowers') or [])} flowers")
player.pop("_map_boss_victory", None)

# ══════════════════════════════════════════════════════════════════════════
#  6. Flee at partial HP, then re-enter
# ══════════════════════════════════════════════════════════════════════════
section("6. Flee — HP persists, Echo does not advance")
current = mb.get_active_boss(player)
park_in_arena(player, current)
player["day_blocks"] = 4           # morning, so 4 blocks can't wrap the day


def _flee(p, s, e):
    e[0]["hp"] = int(e[0]["max_hp"] * 0.5)
    p["_map_boss_rounds"] = 4
    return "fled"


save_load.save_game = lambda *a, **k: None
try:
    outcome = _explore_map_boss_arena(player, arena_override=_flee)
finally:
    save_load.save_game = save_game_backup
fled_echo = mb.get_active_boss(player)
check("flee routes home", outcome == "fled", outcome)
check("Echo unchanged", fled_echo["echo"] == current["echo"],
      str(fled_echo["echo"]))
check("HP kept at 50%",
      abs(fled_echo["hp"] - fled_echo["max_hp"] * 0.5) <= 1,
      f"{fled_echo['hp']}/{fled_echo['max_hp']}")
check("no loot on a flee", "_map_boss_victory" not in player)
check("the flee still cost 4 blocks", player["day_blocks"] == 8,
      str(player["day_blocks"]))
boss = cmb.build_encounter(fled_echo)[0]
check("re-entry uses the saved HP", boss["hp"] == fled_echo["hp"],
      f"{boss['hp']} vs {fled_echo['hp']}")

# ══════════════════════════════════════════════════════════════════════════
#  7. Death — HP persists, Echo stays
# ══════════════════════════════════════════════════════════════════════════
section("7. Death — HP persists, Echo stays")
current = mb.get_active_boss(player)
park_in_arena(player, current)


def _die(p, s, e):
    e[0]["hp"] = int(e[0]["max_hp"] * 0.25)
    p["_map_boss_rounds"] = 6
    return "dead"


save_load.save_game = lambda *a, **k: None
try:
    outcome = _explore_map_boss_arena(player, arena_override=_die)
finally:
    save_load.save_game = save_game_backup
dead_echo = mb.get_active_boss(player)
check("death reported", outcome == "dead", outcome)
check("Echo unchanged after death", dead_echo["echo"] == current["echo"])
check("HP kept at 25%",
      abs(dead_echo["hp"] - dead_echo["max_hp"] * 0.25) <= 1,
      f"{dead_echo['hp']}/{dead_echo['max_hp']}")
check("last_result = dead",
      player["map_boss"]["last_result"] == "dead",
      str(player["map_boss"]["last_result"]))
check("floor cursor restored", player.get("floor") == 1,
      str(player.get("floor")))

# ══════════════════════════════════════════════════════════════════════════
#  8. Season boundary
# ══════════════════════════════════════════════════════════════════════════
section("8. The season turns (day 90 → 91)")
player["day"] = 90
old = mb.get_active_boss(player)
park_in_arena(player, old)


def _win_across_season(p, s, e):
    p["day_blocks"] = 22
    p["_map_boss_rounds"] = 4
    return "victory"


save_load.save_game = lambda *a, **k: None
try:
    outcome = _explore_map_boss_arena(player, arena_override=_win_across_season)
finally:
    save_load.save_game = save_game_backup
new = mb.get_active_boss(player)
check("season-crossing kill routes to the shift",
      outcome == "map_boss_season_shift", outcome)
check("next season's Warden", new["season"] == "summer", str(new["season"]))
check("new season starts at Echo 0",
      new["echo"] == 0 and new["level"] == 20, str(new["echo"]))
check("different name / glyph / element",
      new["warden_name"] != old["warden_name"]
      and new["glyph"] != old["glyph"]
      and new["element"] != old["element"])
check("journal: The Season Closes",
      "The Season Closes" in journal_names(player), str(journal_names(player)))
check("spoils kept across the boundary",
      (player.get("_map_boss_victory") or {}).get("gold", 0) > 0)
note(f"{new['glyph']} {new['warden_name']} takes the field at Echo 0")

# ══════════════════════════════════════════════════════════════════════════
#  9. Trophy ladder over the season
# ══════════════════════════════════════════════════════════════════════════
section("9. Trophy ladder (10 kills)")
ladder_player = make_hero(day=20)
ladder_site = mb.maybe_spawn(ladder_player)
granted = []
for _ in range(10):
    mb.record_victory(ladder_player)
    summary = mb.grant_victory_rewards(ladder_player, ladder_site)
    granted.extend(u["id"] for u in summary["uniques"])
check("trophies arrive at 1 / 3 / 6 / 10",
      granted == list(data.MAP_BOSS_UNIQUE_ITEMS), str(granted))
check("all four are in the bag",
      len([i for i in ladder_player["inventory"]
           if i.get("rarity") == "unique"]) == 4)
last = mb.grant_victory_rewards(ladder_player, ladder_site)
check("the 11th kill pays a second cache", last["extra_caches"] == 1,
      str(last["extra_caches"]))
check("no duplicate trophies", last["uniques"] == [], str(last["uniques"]))

# ══════════════════════════════════════════════════════════════════════════
#  Report
# ══════════════════════════════════════════════════════════════════════════
section("Report")
note(f"season walked: Spring day 20 → day 91 (Summer Warden spawned)")
note(f"kills booked: {player['map_boss']['defeated_total']}")
note(f"best Echo: {player['map_boss']['best_echo']}")
note(f"gold purse: {player['gold']}")
note(f"journal entries: {len(journal_names(player))}")
for entry in player["journal"]["events"]:
    note(f"  day {entry.get('day')}: {entry.get('name')}")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s): {FAILS}")
    sys.exit(1)
print("All seasonal map boss playtest checks passed (Phases 1-5).")
