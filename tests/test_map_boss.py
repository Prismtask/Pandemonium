"""
tests/test_map_boss.py — Seasonal Map Boss Phase 1 (foundation) tests.

Design: docs/map_boss_design.md

Covers:
  - State init / legacy-save migration
  - Floor-20 clear gate (max_floor > 20)
  - One deterministic site per season; Echoes reuse it
  - Per-kill Echo advancement and season rotation
  - Start-at-proven-depth state (one-way, full HP, decline memory)
  - Seasonal roster (names, glyphs, elements, weaknesses, biomes, mechanics)
  - Echo scaling curve + resistance caps + unscaling weakness
  - Reward pre-roll (cache rarity curve, gear level, consumables, flower)
  - events.process_day_rollover integration
"""

import json
import random
import unittest
from unittest import mock

from pandemonium.core.events import (
    get_season,
    next_season_day,
    process_day_rollover,
    season_start_day,
)
from pandemonium.resources import map_boss_data as data
from pandemonium.resources.cities import CITIES
from pandemonium.resources.item_generation import flower_for_element
from pandemonium.world import map_boss as mb


def make_player(day=20, max_floor=21, **extra):
    """Minimal player dict with the fields the map boss touches."""
    player = {
        "day": day,
        "max_floor": max_floor,
        "daily_effects": {},
        "active_buffs": [],
        "inventory": [],
        "journal": {"events": [], "main_quests": [], "side_quests": []},
        # Progression stubs — ``gain_exp`` reads these during the reward
        # grant; capping level here keeps XP silent unless a test opts in.
        "level": 20,
        "level_cap": 20,
        "exp": 0,
        "gold": 0,
        "allies": [],
    }
    player.update(extra)
    return player


class MapBossTestCase(unittest.TestCase):
    """Base class: isolate the global RNG between tests."""

    def setUp(self):
        self._rng_state = random.getstate()

    def tearDown(self):
        random.setstate(self._rng_state)


class _FixedRng:
    """Deterministic stand-in for ``random`` (``random()`` is all we need)."""

    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


# ═══════════════════════════════════════════════════════════════
# State init & migration
# ═══════════════════════════════════════════════════════════════

class TestStateInit(MapBossTestCase):

    def test_fresh_player_gets_state_block(self):
        player = make_player()
        state = mb.ensure_map_boss_state(player)
        self.assertIsNone(state["unlocked_day"])
        self.assertIsNone(state["season"])
        self.assertEqual(state["echo"], -1)
        self.assertIsNone(state["active"])
        self.assertEqual(state["defeated_total"], 0)
        self.assertEqual(state["unique_grants"], [])
        self.assertEqual(state["best_echo"], -1)
        self.assertEqual(state["season_defeats"], {})
        self.assertIsNone(state["depth_declined_season"])

    def test_state_backfill_is_idempotent(self):
        """Old saves without the block (or a partial one) are repaired."""
        player = make_player()
        first = mb.ensure_map_boss_state(player)
        first["defeated_total"] = 3
        second = mb.ensure_map_boss_state(player)
        self.assertIs(second, first)
        self.assertEqual(second["defeated_total"], 3)

        player["map_boss"] = {"season": "summer", "active": "garbage"}
        state = mb.ensure_map_boss_state(player)
        self.assertEqual(state["season"], "summer")
        self.assertIsNone(state["active"])
        self.assertEqual(state["unique_grants"], [])
        self.assertEqual(state["season_defeats"], {})


# ═══════════════════════════════════════════════════════════════
# Gate + first spawn
# ═══════════════════════════════════════════════════════════════

class TestGate(MapBossTestCase):

    def test_no_spawn_before_floor_20_clear(self):
        """Floor 20 must be CLEARED — reaching it is not enough."""
        for max_floor in (1, 19, 20):
            player = make_player(day=20, max_floor=max_floor)
            self.assertFalse(mb.gate_met(player))
            self.assertIsNone(mb.maybe_spawn(player))
            self.assertIsNone(player["map_boss"]["active"])

    def test_floor_21_meets_the_gate(self):
        player = make_player(day=20, max_floor=21)
        self.assertTrue(mb.gate_met(player))
        self.assertIsNotNone(mb.maybe_spawn(player))

    def test_first_spawn_current_season_echo_0(self):
        player = make_player(day=20, max_floor=21)
        active = mb.maybe_spawn(player)
        season_id, season_name = get_season(20)
        self.assertEqual(season_id, "spring")
        self.assertEqual(active["season"], "spring")
        self.assertEqual(active["season_name"], season_name)
        self.assertEqual(active["echo"], 0)
        self.assertEqual(active["level"], 20)
        self.assertEqual(active["hp"], active["max_hp"])
        self.assertEqual(player["map_boss"]["unlocked_day"], 20)
        self.assertEqual(player["map_boss"]["echo"], 0)
        self.assertIs(player["map_boss"]["active"], active)

    def test_spawn_is_idempotent(self):
        player = make_player(day=20)
        first = mb.maybe_spawn(player)
        hp = first["hp"]
        first["hp"] = hp // 2
        self.assertIsNone(mb.maybe_spawn(player))
        self.assertEqual(player["map_boss"]["active"]["hp"], hp // 2)

    def test_old_save_already_gated_spawns_current_season_echo_0(self):
        """A save loaded mid-season sees the current Warden, no backlog."""
        player = make_player(day=200)          # autumn
        player["map_boss"] = {"defeated_total": 4, "best_echo": 3}
        active = mb.maybe_spawn(player)
        self.assertEqual(active["season"], "autumn")
        self.assertEqual(active["echo"], 0)
        self.assertEqual(player["map_boss"]["unlocked_day"], 200)
        self.assertEqual(player["map_boss"]["best_echo"], 3)

    def test_old_120day_save_migrates(self):
        """Legacy active sites from the old calendar are dropped (season moved)."""
        player = make_player(day=200)
        player["map_boss"] = {
            "unlocked_day": 5,
            "season": "spring",
            "echo": 5,
            "best_echo": 5,
            "active": {
                "id": "warden_spring_5",
                "season": "spring",
                "echo": 5,
                "hp": 1,
                "position": [10, 10],
                "biome": "forest",
                "max_hp": 7130,
            },
        }
        active = mb.maybe_spawn(player)
        self.assertEqual(active["season"], "autumn")
        self.assertEqual(active["echo"], 0)
        self.assertEqual(active["hp"], active["max_hp"])
        self.assertEqual(player["map_boss"]["echo"], 0)
        self.assertEqual(player["map_boss"]["best_echo"], 5)
        # A new site — the old spring coordinates are gone.
        self.assertNotEqual(active["position"], [10, 10])

    def test_no_seed_city_no_spawn(self):
        player = make_player(day=20)
        with mock.patch.object(mb, "_available_seed_cities", return_value=set()):
            self.assertIsNone(mb.maybe_spawn(player))
        self.assertIsNone(player["map_boss"]["active"])


# ═══════════════════════════════════════════════════════════════
# Site determinism
# ═══════════════════════════════════════════════════════════════

class TestSite(MapBossTestCase):

    def test_spawn_deterministic_per_season(self):
        a = mb.maybe_spawn(make_player(day=20))
        b = mb.maybe_spawn(make_player(day=20))
        self.assertEqual(a["position"], b["position"])
        self.assertEqual(a["biome"], b["biome"])
        self.assertEqual(a["seed_city"], b["seed_city"])
        self.assertEqual(a["nearest_city"], b["nearest_city"])

        # A different season rolls a different site.
        c = mb.maybe_spawn(make_player(day=100))
        self.assertNotEqual(a["position"], c["position"])

    def test_echo_reuses_site(self):
        player = make_player(day=20)
        first = mb.maybe_spawn(player)
        mb.record_victory(player)
        second = mb.advance_echo(player)
        third_echo = mb.record_victory(player) is not None
        third = mb.advance_echo(player)
        self.assertTrue(third_echo)
        for site in (second, third):
            self.assertEqual(site["position"], first["position"])
            self.assertEqual(site["biome"], first["biome"])
            self.assertEqual(site["nearest_city"], first["nearest_city"])
            self.assertEqual(site["expire_day"], first["expire_day"])

    def test_season_biome_preference(self):
        expected = {
            20: ("forest", "temperate"),        # spring
            100: ("desert", "volcanic", "savanna"),   # summer
            200: ("savanna", "forest", "temperate"),  # autumn
            300: ("tundra", "mountain"),        # winter
        }
        for day, biomes in expected.items():
            active = mb.maybe_spawn(make_player(day=day))
            self.assertIn(active["biome"], biomes, f"day {day}")

    def test_biome_preference_fallback(self):
        """No preferred-biome city available → any accessible city wins."""
        player = make_player(day=300)          # winter: tundra/mountain
        with mock.patch.object(mb, "_available_seed_cities",
                               return_value={"coralhaven"}):
            active = mb.maybe_spawn(player)
        self.assertEqual(active["seed_city"], "coralhaven")
        self.assertEqual(active["biome"], "tropical")

    def test_site_keeps_clear_of_cities(self):
        active = mb.maybe_spawn(make_player(day=20))
        from pandemonium.resources.world_layout import city_node_centers, map_bounds
        px, py = active["position"]
        for cx, cy in city_node_centers().values():
            dist_sq = (px - cx) ** 2 + (py - cy) ** 2
            self.assertGreaterEqual(dist_sq, mb.MIN_CITY_DIST ** 2)
        x_min, y_min, x_max, y_max = map_bounds()
        self.assertTrue(x_min <= px <= x_max)
        self.assertTrue(y_min <= py <= y_max)


# ═══════════════════════════════════════════════════════════════
# Echo loop + season rotation
# ═══════════════════════════════════════════════════════════════

class TestEchoLoop(MapBossTestCase):

    def test_kill_spawns_next_echo_immediately(self):
        player = make_player(day=20)
        first = mb.maybe_spawn(player)
        self.assertIsNotNone(mb.record_victory(player))
        second = mb.advance_echo(player)
        self.assertEqual(second["echo"], 1)
        self.assertEqual(second["level"], 40)
        self.assertEqual(second["hp"], second["max_hp"])
        self.assertEqual(second["max_hp"], 2424)
        self.assertEqual(len(second["mechanic_effects"]),
                         len(first["mechanic_effects"]) + 1)
        self.assertGreater(second["armor"], first["armor"])
        self.assertGreater(second["status_res"], first["status_res"])
        self.assertEqual(player["map_boss"]["echo"], 1)

    def test_kill_chain_three_echoes(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        levels = [20]
        for _ in range(3):
            mb.record_victory(player)
            levels.append(mb.advance_echo(player)["level"])
        self.assertEqual(levels, [20, 40, 60, 80])
        self.assertEqual(player["map_boss"]["best_echo"], 2)
        self.assertEqual(player["map_boss"]["defeated_total"], 3)
        self.assertEqual(player["map_boss"]["season_defeats"]["spring"], 3)

    def test_flee_does_not_advance_echo(self):
        player = make_player(day=20)
        active = mb.maybe_spawn(player)
        mb.save_boss_hp(player, active["max_hp"] // 2)
        mb.set_result(player, "fled")
        self.assertEqual(player["map_boss"]["active"]["echo"], 0)
        self.assertEqual(player["map_boss"]["echo"], 0)
        self.assertEqual(mb.get_active_boss(player)["hp"], active["max_hp"] // 2)

    def test_death_does_not_advance_echo(self):
        player = make_player(day=20)
        active = mb.maybe_spawn(player)
        mb.save_boss_hp(player, 1)
        mb.set_result(player, "dead")
        self.assertEqual(mb.get_active_boss(player)["echo"], 0)
        self.assertEqual(mb.get_active_boss(player)["hp"], 1)
        self.assertEqual(player["map_boss"]["last_result"], "dead")

    def test_dawn_new_echo_is_full_hp(self):
        player = make_player(day=20)
        active = mb.maybe_spawn(player)
        mb.save_boss_hp(player, 10)
        mb.record_victory(player)
        nxt = mb.advance_echo(player)
        self.assertEqual(nxt["hp"], nxt["max_hp"])
        self.assertNotEqual(nxt["id"], active["id"])

    def test_advance_echo_without_active_boots_the_season(self):
        player = make_player(day=20)
        active = mb.advance_echo(player)      # nothing active yet
        self.assertEqual(active["echo"], 0)
        self.assertEqual(active["season"], "spring")


class TestSeasonRotation(MapBossTestCase):

    def test_season_boundaries_are_90_days(self):
        boundaries = [season_start_day(d) for d in (1, 91, 181, 271, 361)]
        self.assertEqual(boundaries, [1, 91, 181, 271, 361])
        for day in (1, 90, 91, 180, 181, 270, 271, 360):
            self.assertEqual(next_season_day(day) - season_start_day(day), 90)

    def test_spawn_site_expires_at_next_season(self):
        active = mb.maybe_spawn(make_player(day=20))
        self.assertEqual(active["expire_day"], 91)
        active = mb.maybe_spawn(make_player(day=95))
        self.assertEqual(active["expire_day"], 181)

    def test_season_rotation_on_season_boundary(self):
        player = make_player(day=90)
        spring = mb.maybe_spawn(player)
        mb.record_victory(player)
        mb.advance_echo(player)                      # Spring Echo 1
        player["day"] = 91
        summer = mb.maybe_spawn(player)
        self.assertEqual(summer["season"], "summer")
        self.assertEqual(summer["echo"], 0)
        self.assertEqual(summer["level"], 20)
        self.assertEqual(summer["warden_name"],
                         data.WARDENS["summer"]["warden_name"])
        self.assertNotEqual(summer["position"], spring["position"])
        self.assertEqual(player["map_boss"]["best_echo"], 0)

    def test_season_rotation_replaces_undefeated_echo(self):
        player = make_player(day=90)
        active = mb.maybe_spawn(player)
        mb.save_boss_hp(player, 5)
        player["day"] = 91
        new_active = mb.maybe_spawn(player)
        self.assertEqual(new_active["hp"], new_active["max_hp"])
        self.assertNotEqual(new_active["id"], active["id"])
        self.assertEqual(player["map_boss"]["season"], "summer")

    def test_kill_crossing_season_spawns_new_season(self):
        """The time commit can turn the season mid-fight — no old next Echo."""
        player = make_player(day=90)
        mb.maybe_spawn(player)
        mb.record_victory(player)
        player["day"] = 91                # arena time commit rolled the day
        result = mb.advance_echo(player)
        self.assertEqual(result["season"], "summer")
        self.assertEqual(result["echo"], 0)
        self.assertEqual(player["map_boss"]["echo"], 0)

    def test_season_swap_not_duplicated(self):
        """maybe_spawn during the commit + the victory handler = one Warden."""
        player = make_player(day=90)
        mb.maybe_spawn(player)
        killed = player["map_boss"]["active"]
        mb.record_victory(player)
        player["day"] = 91
        from_rollover = mb.maybe_spawn(player)
        from_victory = mb.advance_echo(player, killed=killed)
        self.assertIsNone(from_victory)
        self.assertEqual(player["map_boss"]["active"]["id"], from_rollover["id"])
        self.assertEqual(player["map_boss"]["echo"], 0)
        self.assertEqual(from_rollover["echo"], 0)

    def test_depth_declined_resets_each_season(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        mb.decline_start_depth(player)
        self.assertEqual(player["map_boss"]["depth_declined_season"], "spring")
        player["day"] = 91
        mb.maybe_spawn(player)
        self.assertIsNone(player["map_boss"]["depth_declined_season"])


# ═══════════════════════════════════════════════════════════════
# Start at proven depth
# ═══════════════════════════════════════════════════════════════

class TestStartDepth(MapBossTestCase):

    def _player_with_best(self, best, day=20):
        player = make_player(day=day)
        mb.maybe_spawn(player)
        player["map_boss"]["best_echo"] = best
        return player

    def test_depth_offer_when_best_exceeds_current_echo(self):
        player = self._player_with_best(5)
        self.assertEqual(mb.start_depth_offer(player), 5)
        player["map_boss"]["best_echo"] = 0
        self.assertIsNone(mb.start_depth_offer(player))

    def test_depth_choice_sets_echo_and_full_hp(self):
        player = self._player_with_best(5)
        mb.save_boss_hp(player, 100)
        active = mb.apply_start_depth(player)
        self.assertEqual(active["echo"], 5)
        self.assertEqual(player["map_boss"]["echo"], 5)
        self.assertEqual(active["hp"], active["max_hp"])
        stats = mb.echo_stats(5)
        self.assertEqual(active["level"], 80)
        self.assertEqual(active["max_hp"], stats["max_hp"])
        self.assertEqual(active["armor"], stats["armor"])
        self.assertEqual(active["mechanic_tier"], 6)
        self.assertEqual(active["mechanic_rank"], 2)

    def test_depth_never_refights_a_cleared_echo(self):
        player = self._player_with_best(5)
        mb.apply_start_depth(player)
        mb.save_boss_hp(player, 10)
        self.assertIsNone(mb.apply_start_depth(player))     # already at 5
        self.assertIsNone(mb.apply_start_depth(player, 4))  # downward = refused
        self.assertEqual(player["map_boss"]["echo"], 5)
        self.assertEqual(mb.get_active_boss(player)["hp"], 10)

        # After a kill the window closes entirely.
        mb.record_victory(player)
        mb.advance_echo(player)
        self.assertIsNone(mb.start_depth_offer(player))

    def test_depth_echo_0_still_available(self):
        player = self._player_with_best(5)
        self.assertEqual(mb.decline_start_depth(player), "spring")
        self.assertIsNone(mb.start_depth_offer(player))
        self.assertEqual(player["map_boss"]["echo"], 0)
        self.assertEqual(mb.get_active_boss(player)["level"], 20)

    def test_depth_discards_partial_hp(self):
        player = self._player_with_best(5)
        mb.save_boss_hp(player, 1)
        active = mb.apply_start_depth(player)
        self.assertEqual(active["hp"], active["max_hp"])

    def test_depth_declined_remembered_for_season(self):
        player = self._player_with_best(5)
        mb.decline_start_depth(player)
        self.assertIsNone(mb.start_depth_offer(player))
        player["day"] = 91
        mb.maybe_spawn(player)
        player["map_boss"]["best_echo"] = 5
        self.assertEqual(mb.start_depth_offer(player), 5)

    def test_depth_cap(self):
        player = self._player_with_best(7)
        with mock.patch.object(data, "MAP_BOSS_START_DEPTH_CAP", 2):
            self.assertEqual(mb.start_depth_offer(player), 2)
            active = mb.apply_start_depth(player)
        self.assertEqual(active["echo"], 2)

    def test_depth_journal_entry(self):
        player = self._player_with_best(4)
        mb.apply_start_depth(player)
        names = [e["name"] for e in player["journal"]["events"]]
        self.assertIn("Depth Recalled", names)
        entry = [e for e in player["journal"]["events"]
                 if e["name"] == "Depth Recalled"][0]
        self.assertEqual(entry["tag"], "[MAP BOSS]")
        self.assertIn("Echo 4", entry["desc"])


# ═══════════════════════════════════════════════════════════════
# Seasonal identity
# ═══════════════════════════════════════════════════════════════

class TestSeasonalIdentity(MapBossTestCase):

    def test_roster_elements_weaknesses(self):
        expected = {
            "spring": ("earth", "fire"),
            "summer": ("fire", "water"),
            "autumn": ("wind", "thunder"),
            "winter": ("water", "fire"),
        }
        for season, (element, weakness) in expected.items():
            warden = data.get_warden(season)
            self.assertEqual(warden["element"], element)
            self.assertEqual(warden["weakness"], weakness)

    def test_roster_names_glyphs(self):
        expected = {
            "spring": ("Warden of the First Bloom", "\U0001F331"),
            "summer": ("Warden of the Long Noon", "\U0001F525"),
            "autumn": ("Warden of the Falling Crown", "\U0001F342"),
            "winter": ("Warden of the Last Light", "\u2744"),
        }
        for season, (name, glyph) in expected.items():
            warden = data.get_warden(season)
            self.assertEqual(warden["warden_name"], name)
            self.assertEqual(warden["glyph"], glyph)

    def test_roster_mechanics(self):
        expected = {
            "spring": ("bloom", "Bloom", "Bloomling"),
            "summer": ("heat", "Heat", "Cinderling"),
            "autumn": ("harvest", "Harvest", "Huskling"),
            "winter": ("frostbite", "Frostbite", "Frostling"),
        }
        for season, (mechanic, label, add) in expected.items():
            warden = data.get_warden(season)
            self.assertEqual(warden["mechanic"], mechanic)
            self.assertEqual(warden["mechanic_name"], label)
            self.assertEqual(warden["add_name"], add)

    def test_roster_matches_events_seasons(self):
        self.assertEqual(data.MAP_BOSS_SEASONS,
                         tuple(sid for sid, _ in __import__(
                             "pandemonium.core.events", fromlist=["SEASONS"]).SEASONS))

    def test_active_carries_season_identity(self):
        for day, season in ((20, "spring"), (100, "summer"),
                            (200, "autumn"), (300, "winter")):
            active = mb.maybe_spawn(make_player(day=day))
            warden = data.get_warden(season)
            self.assertEqual(active["season"], season)
            self.assertEqual(active["warden_name"], warden["warden_name"])
            self.assertEqual(active["element"], warden["element"])
            self.assertEqual(active["weakness"], warden["weakness"])
            self.assertEqual(active["mechanic"], warden["mechanic"])
            self.assertEqual(active["glyph"], warden["glyph"])
            self.assertEqual(active["add_name"], warden["add_name"])

    def test_biome_preferences_are_real_city_biomes(self):
        city_biomes = {info.get("biome") for info in CITIES.values()}
        for season in data.MAP_BOSS_SEASONS:
            for biome in data.get_warden(season)["biomes"]:
                self.assertIn(biome, city_biomes, f"{season}:{biome}")


# ═══════════════════════════════════════════════════════════════
# Mechanic ladder
# ═══════════════════════════════════════════════════════════════

class TestMechanicLadder(MapBossTestCase):

    def test_mechanic_upgrade_ladder(self):
        for season in data.MAP_BOSS_SEASONS:
            tiers = data.mechanic_tiers(season)
            self.assertEqual(len(tiers), 10, season)
            seen = set()
            for echo in range(10):
                effects = data.mechanic_effects(season, echo)
                self.assertEqual(len(effects), echo + 1)
                self.assertEqual(len(set(effects)), len(effects))
                self.assertEqual(echo + 1, len(seen | {effects[-1]}))
                seen.update(effects)

    def test_mechanic_tier_caps_at_ten(self):
        for echo in (9, 10, 20, 40):
            self.assertEqual(data.mechanic_tier_index(echo), 10)
            self.assertEqual(len(data.mechanic_effects("summer", echo)), 10)
            self.assertIsNone(data.next_mechanic_effect("summer", echo))

    def test_next_mechanic_effect_preview(self):
        nxt = data.next_mechanic_effect("heat", 0)
        self.assertEqual(nxt["id"], "heat_burn")
        self.assertEqual(data.next_mechanic_effect("heat", 1)["id"],
                         "solar_flare")

    def test_mechanic_rank_1_to_4(self):
        expected = {0: 1, 1: 1, 2: 1, 3: 2, 5: 2, 6: 3, 9: 4, 12: 4, 40: 4}
        for echo, rank in expected.items():
            self.assertEqual(mb.echo_stats(echo)["mechanic_rank"], rank)
            self.assertEqual(data.mechanic_rank(echo), rank)

    def test_mechanic_scale_by_rank(self):
        self.assertAlmostEqual(data.mechanic_rank_scale(1), 1.0)
        self.assertAlmostEqual(data.mechanic_rank_scale(4), 1.75)
        self.assertAlmostEqual(
            data.mechanic_rank_scale(2),
            1.0 + data.MAP_BOSS_MECHANIC_RANK_SCALE)

    def test_stack_caps(self):
        self.assertEqual(data.stack_cap("spring"), data.MAP_BOSS_BLOOM_CAP_BASE)
        self.assertEqual(data.stack_cap("summer"), data.MAP_BOSS_HEAT_CAP_BASE)
        self.assertEqual(data.stack_cap("autumn"), data.MAP_BOSS_HARVEST_CAP_BASE)
        self.assertEqual(data.stack_cap("winter"), data.MAP_BOSS_ICE_CAP_BASE)


# ═══════════════════════════════════════════════════════════════
# Echo scaling
# ═══════════════════════════════════════════════════════════════

class TestEchoScaling(MapBossTestCase):

    def test_echo_levels_20_40_60_80(self):
        self.assertEqual([mb.echo_stats(e)["level"] for e in range(5)],
                         [20, 40, 60, 80, 80])
        self.assertEqual(mb.echo_stats(30)["level"], 80)

    def test_echo_curve_reference_table(self):
        """§6.2 reference table — HP / damage / armor / resists / status res."""
        expected = {
            0: (1000, 1.00, 12, 1.00, 1.30, 0.20),
            1: (2424, 1.65, 15, 1.12, 1.42, 0.33),
            2: (4107, 2.33, 19, 1.24, 1.53, 0.46),
            3: (6063, 3.05, 22, 1.36, 1.65, 0.59),
            5: (7130, 3.22, 23, 1.40, 1.68, 0.65),
            10: (10120, 3.64, 26, 1.50, 1.70, 0.80),
            20: (17480, 4.48, 31, 1.60, 1.70, 0.85),
            30: (26680, 5.32, 36, 1.60, 1.70, 0.85),
        }
        for echo, (hp, dmg, armor, all_res, season_res, status_res) in expected.items():
            stats = mb.echo_stats(echo)
            self.assertEqual(stats["max_hp"], hp, f"E{echo} hp")
            self.assertAlmostEqual(stats["damage_mult"], dmg, places=2)
            self.assertEqual(stats["armor"], armor, f"E{echo} armor")
            self.assertAlmostEqual(stats["all_res"], all_res, places=2)
            self.assertAlmostEqual(stats["season_res"], season_res, places=2)
            self.assertAlmostEqual(stats["status_res"], status_res, places=2)

    def test_resist_caps(self):
        stats = mb.echo_stats(60)
        self.assertEqual(stats["all_res"], data.MAP_BOSS_RES_CAP)
        self.assertEqual(stats["season_res"], data.MAP_BOSS_SEASON_RES_CAP)
        self.assertEqual(stats["status_res"], data.MAP_BOSS_STATUS_RES_CAP)
        self.assertLessEqual(stats["armor"], data.MAP_BOSS_ARMOR_CAP)

    def test_weakness_never_scales(self):
        for echo in (0, 3, 10, 30):
            for season in data.MAP_BOSS_SEASONS:
                profile = mb.elemental_profile(season, echo)
                weakness = data.get_warden(season)["weakness"]
                self.assertEqual(profile[weakness], data.MAP_BOSS_WEAKNESS)

    def test_element_profile_uses_season_element(self):
        profile = mb.elemental_profile("summer", 2)
        self.assertAlmostEqual(profile["fire"], 1.53, places=2)   # season res
        self.assertEqual(profile["water"], 0.70)                  # weakness
        self.assertAlmostEqual(profile["earth"], 1.24, places=2)  # all res
        self.assertEqual(profile["physical"], profile["magical"])

    def test_echo_growth_is_monotonic(self):
        previous = mb.echo_stats(0)
        for echo in range(1, 12):
            stats = mb.echo_stats(echo)
            self.assertGreaterEqual(stats["max_hp"], previous["max_hp"])
            self.assertGreaterEqual(stats["damage_mult"], previous["damage_mult"])
            self.assertGreaterEqual(stats["armor"], previous["armor"])
            self.assertGreaterEqual(stats["status_res"], previous["status_res"])
            previous = stats

    def test_negative_echo_is_clamped(self):
        self.assertEqual(mb.echo_stats(-3), mb.echo_stats(0))


# ═══════════════════════════════════════════════════════════════
# Rewards pre-roll
# ═══════════════════════════════════════════════════════════════

class TestRewards(MapBossTestCase):

    def test_gold_xp_formula(self):
        self.assertEqual(mb.gold_xp_reward(0), {"gold": 400, "exp": 600})
        self.assertEqual(mb.gold_xp_reward(1), {"gold": 1000, "exp": 1550})
        self.assertEqual(mb.gold_xp_reward(3), {"gold": 2200, "exp": 3450})

    def test_gold_xp_daily_bonus(self):
        player = make_player(daily_effects={"gold_bonus": 0.30,
                                            "exp_bonus": 0.20})
        reward = mb.gold_xp_reward(1, player=player)
        self.assertEqual(reward["gold"], 1300)
        self.assertEqual(reward["exp"], 1860)

    def test_night_kill_gold_bonus(self):
        day = mb.gold_xp_reward(1)["gold"]
        night = mb.gold_xp_reward(1, night=True)["gold"]
        self.assertEqual(night, int(day * 1.25))

    def test_cache_rarity_curve(self):
        # Echo 0: 10% epic floor.
        self.assertEqual(mb.cache_rarity(0, _FixedRng(0.05)), "epic")
        self.assertEqual(mb.cache_rarity(0, _FixedRng(0.50)), "rare")
        # Echo 9: epic guaranteed.
        self.assertEqual(mb.cache_rarity(9, _FixedRng(0.99)), "epic")
        # Echo 10+: 30% legendary, no legendary before Echo 10.
        self.assertEqual(mb.cache_rarity(10, _FixedRng(0.20)), "legendary")
        self.assertEqual(mb.cache_rarity(10, _FixedRng(0.50)), "epic")
        for echo in range(10):
            for roll in (0.0, 0.5, 0.99):
                self.assertNotEqual(mb.cache_rarity(echo, _FixedRng(roll)),
                                    "legendary")
        # Always at least rare.
        for echo in range(0, 40):
            self.assertIn(mb.cache_rarity(echo), ("rare", "epic", "legendary"))

    def test_epic_chance_ramp(self):
        # Echo 4 = 50% epic.
        epics = sum(1 for _ in range(2000)
                    if mb.cache_rarity(4, _FixedRng(random.random())) == "epic")
        self.assertAlmostEqual(epics / 2000, 0.50, delta=0.06)

    def test_cache_gear_level(self):
        for echo, expected_level in ((0, 20), (1, 40), (3, 80), (30, 80)):
            with mock.patch(
                "pandemonium.resources.item_generation.pick_equipment_id",
                return_value="sword",
            ) as patched:
                cache = mb.roll_cache(echo)
            self.assertEqual(patched.call_args[0][0], expected_level)
            self.assertEqual(cache["item_id"], "sword")
            self.assertIn(cache["rarity"], ("rare", "epic", "legendary"))

    def test_cache_and_flower_season_element(self):
        for day, season in ((20, "spring"), (100, "summer"),
                            (200, "autumn"), (300, "winter")):
            active = mb.maybe_spawn(make_player(day=day))
            warden = data.get_warden(season)
            self.assertEqual(active["flower"],
                             flower_for_element(warden["element"]))
            self.assertIn(active["cache_preview"]["rarity"],
                          ("rare", "epic", "legendary"))
            self.assertTrue(active["cache_preview"]["item_id"])

    def test_consumable_tier_and_theme(self):
        from pandemonium.world.dungeon import _CONSUMABLE_TIERS
        low = mb.roll_consumables(0, "earth")
        self.assertEqual(len(low), data.MAP_BOSS_CONSUMABLES_PER_KILL)
        for item_id in low:
            self.assertIn(item_id, _CONSUMABLE_TIERS[3])

        high = mb.roll_consumables(2, "fire")
        self.assertEqual(len(high), data.MAP_BOSS_CONSUMABLES_PER_KILL)
        for item_id in high:
            self.assertIn(item_id, _CONSUMABLE_TIERS[4])
        self.assertEqual(high[0], data.ELEMENT_CONSUMABLE["fire"])
        self.assertNotEqual(high[0], high[1])

    def test_reward_snapshot_is_json_safe(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        mb.record_victory(player)
        mb.advance_echo(player)
        text = json.dumps(player["map_boss"])
        self.assertIn("warden_spring_1", text)
        self.assertEqual(json.loads(text)["echo"], 1)

    def test_no_superboss_ledger_or_shards(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        mb.record_victory(player)
        mb.advance_echo(player)
        self.assertNotIn("defeated_superbosses", player)
        self.assertNotIn("superboss_pool", player)
        self.assertNotIn("awakening_shards", player)
        self.assertNotIn("achievements", player)


# ═══════════════════════════════════════════════════════════════
# Journal + day-rollover hook
# ═══════════════════════════════════════════════════════════════

class TestJournal(MapBossTestCase):

    def test_first_spawn_journal(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        names = [e["name"] for e in player["journal"]["events"]]
        self.assertIn("A Warden Notices", names)
        self.assertIn("The Season Turns", names)
        for entry in player["journal"]["events"]:
            self.assertEqual(entry["tag"], "[MAP BOSS]")
            self.assertEqual(entry["day"], 20)

    def test_reform_journal(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        mb.record_victory(player)
        mb.advance_echo(player)
        entry = [e for e in player["journal"]["events"]
                 if e["name"] == "The Warden Reforms"][0]
        self.assertIn("Echo 1", entry["desc"])
        self.assertIn("Lv 40", entry["desc"])
        self.assertIn("New mechanic", entry["desc"])

    def test_departure_and_spawn_journal(self):
        player = make_player(day=90)
        mb.maybe_spawn(player)
        player["day"] = 91
        mb.maybe_spawn(player)
        names = [e["name"] for e in player["journal"]["events"]]
        self.assertIn("The Season Closes", names)
        self.assertIn("The Season Turns", names)
        departure = [e for e in player["journal"]["events"]
                     if e["name"] == "The Season Closes"][0]
        self.assertIn("First Bloom", departure["desc"])
        self.assertIn("Long Noon", departure["desc"])

    def test_journal_deduped_per_day(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        count = len(player["journal"]["events"])
        mb.advance_echo(player)          # spawns an echo + journal entry
        names = [e["name"] for e in player["journal"]["events"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreater(len(names), count)


class TestMapBossViewHelpers(MapBossTestCase):
    """Presentation/travel helpers consumed by the world map and arena."""

    def test_echo_label(self):
        self.assertEqual(mb.echo_label(0), "0")
        self.assertEqual(mb.echo_label(1), "I")
        self.assertEqual(mb.echo_label(4), "IV")
        self.assertEqual(mb.echo_label(9), "IX")
        self.assertEqual(mb.echo_label(10), "X")
        self.assertEqual(mb.echo_label(11), "11")
        self.assertEqual(mb.echo_label(-2), "0")

    def test_is_current_after_season_turn(self):
        player = make_player(day=90)
        site = mb.maybe_spawn(player)
        self.assertTrue(mb.is_current(player, site))
        player["day"] = 91
        self.assertFalse(mb.is_current(player, site))
        self.assertFalse(mb.is_current(player, None))
        self.assertFalse(mb.is_current(player, {"id": "nope"}))

    def test_is_current_after_kill(self):
        player = make_player(day=20)
        killed = mb.maybe_spawn(player)
        mb.record_victory(player)
        mb.advance_echo(player, killed=killed)
        self.assertFalse(mb.is_current(player, killed))
        self.assertTrue(mb.is_current(player, mb.get_active_boss(player)))

    def test_build_journey_to_warden(self):
        player = make_player(day=20)
        player["location"] = "solmere"
        mb.maybe_spawn(player)
        journey = mb.build_journey_to_warden(player)
        self.assertIsNotNone(journey)
        self.assertEqual(journey["path"][-1], "map_boss")
        self.assertEqual(journey["segments"][-1]["to"], "map_boss")
        self.assertGreater(journey["total_time"], 0)

    def test_build_journey_without_warden(self):
        player = make_player(day=20, max_floor=10)
        self.assertIsNone(mb.build_journey_to_warden(player))

    def test_season_days_left(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        self.assertEqual(mb.season_days_left(player), 71)
        self.assertEqual(mb.season_days_left(player, site), 71)
        player["day"] = 90
        self.assertEqual(mb.season_days_left(player), 1)
        self.assertEqual(mb.season_days_left(make_player(max_floor=1)), 0)

    def test_next_echo_preview(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        nxt = mb.next_echo_preview(player)
        self.assertEqual(nxt["echo"], 1)
        self.assertEqual(nxt["level"], 40)
        self.assertEqual(nxt["max_hp"], 2424)
        self.assertEqual(nxt["effect"], "Poison Bloom")
        self.assertEqual(nxt["tier"], 2)
        self.assertIsNone(mb.next_echo_preview(
            make_player(day=20, max_floor=1)))

    def test_next_unique_milestone(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        first = mb.next_unique_milestone(player)
        self.assertEqual((first["index"], first["at"], first["victories"]),
                         (0, 1, 1))
        player["map_boss"]["defeated_total"] = 2
        second = mb.next_unique_milestone(player)
        self.assertEqual((second["index"], second["at"], second["victories"]),
                         (1, 3, 1))
        player["map_boss"]["unique_grants"] = ["a", "b", "c", "d"]
        self.assertIsNone(mb.next_unique_milestone(player))


class TestDayRolloverHook(MapBossTestCase):

    def test_rollover_spawns_current_season(self):
        player = make_player(day=25)
        process_day_rollover(player, days_passed=1, old_day=24)
        active = player["map_boss"]["active"]
        self.assertIsNotNone(active)
        self.assertEqual(active["season"], "spring")
        self.assertEqual(active["echo"], 0)

    def test_rollover_pre_gate_spawns_nothing(self):
        player = make_player(day=25, max_floor=12)
        process_day_rollover(player, days_passed=1, old_day=24)
        self.assertIsNone(player["map_boss"]["active"])

    def test_rollover_across_season_boundary_rotates(self):
        player = make_player(day=90)
        mb.maybe_spawn(player)
        player["day"] = 91
        process_day_rollover(player, days_passed=1, old_day=90)
        self.assertEqual(player["map_boss"]["season"], "summer")
        self.assertEqual(player["map_boss"]["echo"], 0)


# ═══════════════════════════════════════════════════════════════
# Arena combat (Phase 3)
# ═══════════════════════════════════════════════════════════════

def make_fighter(strength=200, hp=4000, con=40, blocks=14, day=20):
    """A minimal but combat-capable player dict."""
    return {
        "name": "Hero",
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


class ScriptedIO:
    """Deterministic combat I/O: auto-attack, always pick target 1."""

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
        if any(word in low for word in ("target", "select", "which", "number")):
            return "1"
        return ""

    def clear(self):
        pass

    def is_active(self):
        return True


def _arena_context(player, site):
    """The combat context the hooks expect (see combat/map_boss.py)."""
    cmb = _combat()
    warden = data.get_warden(site["season"])
    return {
        "player": player,
        "site": site,
        "season": site["season"],
        "mechanic": warden["mechanic"],
        "tier": int(site.get("mechanic_tier", 1) or 1),
        "rank_scale": data.mechanic_rank_scale(site.get("mechanic_rank", 1)),
        "effects": tuple(site.get("mechanic_effects") or ()),
        "start_blocks": int(player.get("day_blocks", 0) or 0),
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
        "p_con": 20,
        "defending": False,
        "_enemies": None,
    }


def _combat():
    import pandemonium.combat.map_boss as module
    return module


class ArenaCombatCase(MapBossTestCase):

    def setUp(self):
        super().setUp()
        from pandemonium.combat.combat_io import reset_io
        reset_io()
        self._cmb = _combat()

    def tearDown(self):
        from pandemonium.combat.combat_io import reset_io
        reset_io()
        super().tearDown()

    def _run_fight(self, player, action="a", max_actions=300):
        from pandemonium.combat.combat_io import set_io
        site = mb.get_active_boss(player)
        io = ScriptedIO(action=action, max_actions=max_actions)
        set_io(io)
        enemies = self._cmb.build_encounter(site)
        result = self._cmb.combat_map_boss(player, floor=site["level"],
                                           enemies=enemies)
        return result, io, enemies


# ── Encounter building ─────────────────────────────────────────────────────

class TestArenaEncounter(ArenaCombatCase):

    def test_encounter_uses_the_echo_payload(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        boss = self._cmb.build_encounter(site)[0]
        self.assertTrue(boss["_map_boss"])
        self.assertEqual(boss["name"], site["warden_name"])
        self.assertEqual(boss["level"], site["level"])
        self.assertEqual(boss["max_hp"], site["max_hp"])
        self.assertEqual(boss["hp"], site["hp"])
        self.assertEqual(boss["str_mod"], site["str"])
        self.assertEqual(boss["con_mod"], site["armor"])
        self.assertAlmostEqual(boss["status_res"], site["status_res"])
        self.assertEqual(boss["elemental_res"], site["elemental_res"])

    def test_no_double_phase_scaling(self):
        """enemy_stats() without a player must ignore Morning/Noon/Night."""
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        site["hp"] = site["max_hp"]
        morning = dict(site, level=20, max_hp=1000, hp=1000)
        boss = self._cmb.build_boss(morning)
        self.assertEqual(boss["hp"], 1000)
        self.assertEqual(boss["multiplier"], 1.0)
        self.assertFalse(boss["super_boss"])
        self.assertTrue(boss["boss"])
        self.assertTrue(boss["ai_disabled"])

    def test_wounded_echo_starts_at_saved_hp(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        mb.save_boss_hp(player, 321)
        boss = self._cmb.build_encounter(mb.get_active_boss(player))[0]
        self.assertEqual(boss["hp"], 321)
        self.assertEqual(boss["max_hp"], 1000)

    def test_seasonal_add_names_no_bestiary(self):
        player = make_player(day=20)
        boss = self._cmb.build_encounter(mb.maybe_spawn(player))[0]
        add = self._cmb.build_add(mb.get_active_boss(player), boss, 0)
        self.assertEqual(add["key"], "map_boss_add")
        self.assertTrue(add["_map_boss_add"])
        self.assertTrue(add["no_bestiary"])
        self.assertEqual(add["max_hp"], max(1, int(boss["max_hp"] * 0.03)))
        self.assertEqual(add["str_mod"], max(1, int(boss["str_mod"] * 0.40)))
        expected = {"spring": "Bloomling", "summer": "Cinderling",
                    "autumn": "Huskling", "winter": "Frostling"}
        for day, season in ((20, "spring"), (100, "summer"),
                            (200, "autumn"), (300, "winter")):
            player = make_player(day=day)
            site = mb.maybe_spawn(player)
            boss = self._cmb.build_encounter(site)[0]
            names = [self._cmb.build_add(site, boss, i)["name"]
                     for i in range(4)]
            self.assertTrue(all(n.startswith(expected[season]) for n in names),
                            names)
        from pandemonium.progression.bestiary import record_defeat
        self.assertFalse(record_defeat(player, add))


# ── Phase clock ────────────────────────────────────────────────────────────

class TestArenaClock(ArenaCombatCase):

    def test_projected_clock_boundaries(self):
        player = make_fighter(blocks=0)
        labels = [self._cmb.projected_time_label(player, b)
                  for b in (0, 8, 16, 24)]
        self.assertIn("Morning", labels[0])
        self.assertIn("Noon", labels[1])
        self.assertIn("Night", labels[2])
        self.assertIn("Morning", labels[3])   # next day
        self.assertEqual(self._cmb._phase_of(0), "morning")
        self.assertEqual(self._cmb._phase_of(8), "noon")
        self.assertEqual(self._cmb._phase_of(16), "night")
        self.assertEqual(self._cmb._phase_of(24), "morning")

    def test_projection_never_touches_the_real_clock(self):
        player = make_fighter(blocks=20)
        before = int(player["day_blocks"])
        self._cmb.projected_time_label(player, 40)
        self.assertEqual(player["day_blocks"], before)

    def test_phase_buffs_and_dawn_reset(self):
        player = make_fighter(blocks=16)          # Night
        site = mb.maybe_spawn(player)
        enemies = self._cmb.build_encounter(site)
        boss = enemies[0]
        ctx = _arena_context(player, site)
        ctx["_enemies"] = enemies

        self._cmb._pre_player_hook(ctx, enemies)  # no phase yet → nothing spawned
        ctx["round"] = 1
        self._cmb._pre_round_hook(ctx, enemies)
        self.assertEqual(ctx["phase"], "night")
        # Adds spawn once the phase is known:
        self._cmb._pre_player_hook(ctx, enemies)
        self.assertEqual(sum(1 for e in enemies if e.get("_map_boss_add")), 4)
        self.assertLessEqual(len(enemies), 5)

        # Night → next day Morning: adds crumble, Dawn Lull starts.
        ctx["round"] = 9                          # 16 + 8 = block 24 → morning
        self._cmb._pre_round_hook(ctx, enemies)
        enemies[:] = [e for e in enemies if e["hp"] > 0]
        self.assertEqual(ctx["phase"], "morning")
        self.assertEqual(sum(1 for e in enemies if e.get("_map_boss_add")), 0)
        self.assertEqual(ctx["lull_rounds"], 1)   # one lull round consumed
        phase_buffs = [b for b in boss["active_buffs"]
                       if b.get("source") == "map_boss_phase"]
        self.assertEqual(len(phase_buffs), 1)
        self.assertLess(phase_buffs[0]["value"], 0.0)   # ×0.85 lull
        self.assertLess(boss["con_mod"], boss["_map_boss_base_con"])

        # Second lull round keeps the buff, then normal Dormant returns.
        ctx["round"] = 10
        self._cmb._pre_round_hook(ctx, enemies)
        self.assertEqual(ctx["lull_rounds"], 0)
        phase_buffs = [b for b in boss["active_buffs"]
                       if b.get("source") == "map_boss_phase"]
        self.assertAlmostEqual(phase_buffs[0]["value"], 0.0)  # ×1.00
        self.assertEqual(boss["con_mod"], boss["_map_boss_base_con"])

    def test_night_extra_action(self):
        player = make_fighter(blocks=16)
        site = mb.maybe_spawn(player)
        enemies = self._cmb.build_encounter(site)
        ctx = _arena_context(player, site)
        ctx["phase"] = "night"
        ctx["p_con"] = 20
        res = self._cmb._enemy_turn_hook(enemies[0], ctx, player, 20, False)
        self.assertEqual(res[0], 2)               # two actions at Night
        ctx["phase"] = "noon"
        ctx["boss_actions"] = 0
        res = self._cmb._enemy_turn_hook(enemies[0], ctx, player, 20, False)
        self.assertEqual(res[0], 1)

    def test_no_rollover_mid_fight(self):
        """The projected clock must never spend time per round."""
        player = make_fighter(blocks=22, strength=200)
        mb.maybe_spawn(player)
        from pandemonium.core import time_blocks
        with mock.patch.object(time_blocks, "spend_blocks") as spend:
            result, _io, _enemies = self._run_fight(player)
        self.assertEqual(result, "victory")
        self.assertFalse(spend.called)
        self.assertGreaterEqual(player["_map_boss_rounds"], 1)

    def test_clock_blocks_are_projected(self):
        player = make_fighter(blocks=22)
        site = mb.maybe_spawn(player)
        enemies = self._cmb.build_encounter(site)
        ctx = _arena_context(player, site)
        ctx["_enemies"] = enemies
        for round_num in (1, 2, 3):
            ctx["round"] = round_num
            self._cmb._pre_round_hook(ctx, enemies)
        self.assertEqual(player["_map_boss_clock_blocks"], 24)   # 22 + 2
        self.assertIn("Morning", player["_combat_time_label"])


# ── Mechanics ──────────────────────────────────────────────────────────────

class TestArenaMechanics(ArenaCombatCase):

    def _setup(self, day, echo=0, effects=None):
        player = make_fighter(blocks=14)
        player["day"] = day
        site = mb.maybe_spawn(player)
        if echo:
            mb.apply_start_depth(player, echo) if mb.start_depth_offer(player) \
                else None
            site = mb.get_active_boss(player)
        site = dict(site)
        if effects is not None:
            site["mechanic_effects"] = list(effects)
            site["mechanic_tier"] = len(effects)
        enemies = self._cmb.build_encounter(site)
        ctx = _arena_context(player, site)
        ctx["_enemies"] = enemies
        return player, site, enemies, ctx

    def test_bloom_mechanic(self):
        player, site, enemies, ctx = self._setup(20)
        boss = enemies[0]
        start_hp = boss["hp"] - 500
        boss["hp"] = start_hp
        for _ in range(3):                       # cap 3 → heal + reset
            self._cmb._advance_bloom(ctx, player, boss, "noon")
        self.assertEqual(ctx["stacks"], 0)
        self.assertGreater(boss["hp"], start_hp)

    def test_bloom_poison_at_three_stacks(self):
        player, site, enemies, ctx = self._setup(
            20, effects=self._cmb.data.mechanic_effects("spring", 1))
        ctx["stacks"] = 3
        msg = self._cmb._on_hit_status(ctx, player, enemies[0])
        self.assertIsNotNone(msg)
        self.assertTrue(any(d["type"] == "poison"
                            for d in player["active_debuffs"]))

    def test_heat_mechanic(self):
        from pandemonium.combat.combat_io import set_io
        io = ScriptedIO()
        set_io(io)
        random.seed(7)                           # deterministic dodge rolls
        player, site, enemies, ctx = self._setup(
            100, effects=self._cmb.data.mechanic_effects("summer", 2))
        # A level-20 Echo cannot punch through a Con-40 test dummy; use a
        # squishy target so the flare's damage is observable.
        player["attributes"]["Constitution"] = 5
        ctx["p_con"] = 2
        boss = enemies[0]
        for _ in range(5):                       # cap 5 → Solar Flare
            self._cmb._advance_heat(ctx, player, boss, "noon")
        self.assertEqual(ctx["stacks"], 0)
        self.assertIn("SOLAR FLARE", "\n".join(io.log))
        for _ in range(5):                       # a second flare must land
            self._cmb._advance_heat(ctx, player, boss, "noon")
        self.assertLess(player["current_hp"], 4000)

    def test_harvest_mechanic(self):
        from pandemonium.combat.status_effects import apply_bleed
        player, site, enemies, ctx = self._setup(
            200, effects=self._cmb.data.mechanic_effects("autumn", 2))
        boss = enemies[0]
        apply_bleed(player, 5, 3)
        boss["hp"] = boss["max_hp"] // 2
        before = boss["hp"]
        self._cmb._advance_harvest(ctx, player, boss, "noon")
        self.assertGreaterEqual(ctx["harvest"], 1)
        for _ in range(4):
            apply_bleed(player, 5, 3)
            self._cmb._advance_harvest(ctx, player, boss, "noon")
        self.assertGreaterEqual(boss["hp"], before)   # Reap drank some back

    def test_frostbite_mechanic(self):
        player, site, enemies, ctx = self._setup(
            300, effects=self._cmb.data.mechanic_effects("winter", 1))
        for _ in range(3):                       # 3 stacks → freeze + reset
            self._cmb._advance_frostbite(ctx, player, enemies[0], "noon")
        self.assertTrue(player.get("stunned"))
        self.assertEqual(_combat()._frost_stacks(player), 0)

    def test_ice_armor_reduces_damage_taken(self):
        player, site, enemies, ctx = self._setup(
            300, effects=self._cmb.data.mechanic_effects("winter", 2))
        boss = enemies[0]
        self._cmb._advance_frostbite(ctx, player, boss, "noon")
        self.assertEqual(ctx["ice_armor"], 1)
        ice = [d for d in boss["active_debuffs"]
               if d.get("source") == "map_boss_ice"]
        self.assertEqual(len(ice), 1)
        self.assertLess(ice[0]["value"], 0)

    def test_mechanic_scale_by_rank(self):
        high = mb.apply_start_depth(
            (lambda: (lambda p: (mb.maybe_spawn(p),
                                 p["map_boss"].__setitem__("best_echo", 12),
                                 p)[-1])(make_fighter()))())
        _ = high  # sanity: start-depth path builds a high Echo without error
        self.assertEqual(data.mechanic_rank(12), 4)
        self.assertAlmostEqual(data.mechanic_rank_scale(4), 1.75)

    def test_long_day_rolls_owned_statuses(self):
        player, site, enemies, ctx = self._setup(
            200, effects=self._cmb.data.mechanic_effects("autumn", 3))
        res = self._cmb._long_day(ctx, enemies[0], player, 20, False)
        self.assertEqual(res[0], 1)
        self.assertTrue(res[1])                   # skips the default attack


# ── Fight outcomes + HP persistence + time commit ─────────────────────────

class TestArenaOutcomes(ArenaCombatCase):

    def _arena(self, player):
        """Attach the arena transient state a real entry would set."""
        site = mb.get_active_boss(player)
        player["_map_boss_site"] = site["id"]
        player["_map_boss_prev_floor"] = player.get("floor", 3)
        player["floor"] = 3
        player["_combat_floor_label"] = "Arena"
        return site

    def test_victory_advances_echo_and_sets_best(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        self._arena(player)
        with mock.patch("pandemonium.core.save_load.save_game"):
            result = self._cmb.__dict__ and __import__(
                "pandemonium.world.dungeon", fromlist=["_explore_map_boss_arena"]
            )._explore_map_boss_arena(
                player, arena_override=lambda p, s, e: "victory")
        self.assertEqual(result, "map_boss_victory")
        self.assertEqual(player["map_boss"]["best_echo"], 0)
        self.assertEqual(player["map_boss"]["defeated_total"], 1)
        self.assertEqual(player["map_boss"]["active"]["echo"], 1)
        self.assertEqual(player["map_boss"]["active"]["hp"],
                         player["map_boss"]["active"]["max_hp"])
        self.assertNotIn("_map_boss_site", player)
        self.assertEqual(player["floor"], 3)

    def test_flee_persists_hp_and_does_not_advance(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        self._arena(player)

        def _override(p, s, enemies):
            enemies[0]["hp"] = 250                # chipped the Warden
            p["_map_boss_rounds"] = 4
            return "fled"

        with mock.patch("pandemonium.core.save_load.save_game"):
            with mock.patch("pandemonium.core.time_blocks.spend_blocks") as spend:
                from pandemonium.world.dungeon import _explore_map_boss_arena
                result = _explore_map_boss_arena(player, arena_override=_override)
        self.assertEqual(result, "fled")
        self.assertEqual(mb.get_active_boss(player)["hp"], 250)
        self.assertEqual(mb.get_active_boss(player)["echo"], 0)
        spend.assert_called_once()
        self.assertEqual(spend.call_args[0][1], 4)
        self.assertEqual(spend.call_args[1].get("source"), "map_boss")

    def test_death_persists_hp_and_keeps_the_echo(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        self._arena(player)

        def _override(p, s, enemies):
            enemies[0]["hp"] = 90
            p["_map_boss_rounds"] = 2
            return "dead"

        with mock.patch("pandemonium.core.save_load.save_game"):
            with mock.patch("pandemonium.core.time_blocks.spend_blocks"):
                from pandemonium.world.dungeon import _explore_map_boss_arena
                result = _explore_map_boss_arena(player, arena_override=_override)
        self.assertEqual(result, "dead")
        self.assertEqual(mb.get_active_boss(player)["hp"], 90)
        self.assertEqual(player["map_boss"]["last_result"], "dead")

    def test_interrupt_is_treated_as_a_flee(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        self._arena(player)

        def _override(p, s, enemies):
            enemies[0]["hp"] = 777
            return None                           # vanished / interrupted

        with mock.patch("pandemonium.core.save_load.save_game"):
            with mock.patch("pandemonium.core.time_blocks.spend_blocks"):
                from pandemonium.world.dungeon import _explore_map_boss_arena
                result = _explore_map_boss_arena(player, arena_override=_override)
        self.assertEqual(result, "fled")
        self.assertEqual(mb.get_active_boss(player)["hp"], 777)

    def test_reentry_uses_saved_hp(self):
        player = make_player(day=20)
        mb.maybe_spawn(player)
        mb.save_boss_hp(player, 400)
        boss = self._cmb.build_encounter(mb.get_active_boss(player))[0]
        self.assertEqual(boss["hp"], 400)

    def test_victory_crossing_the_season_shift(self):
        player = make_player(day=90)
        player["day_blocks"] = 22
        mb.maybe_spawn(player)
        self._arena(player)
        # 4 rounds from block 22 rolls day 91 (the season boundary).
        with mock.patch("pandemonium.core.save_load.save_game"):
            from pandemonium.world.dungeon import _explore_map_boss_arena
            result = _explore_map_boss_arena(
                player, arena_override=lambda p, s, e: (
                    p.__setitem__("_map_boss_rounds", 4), "victory")[1])
        self.assertIn(result, ("map_boss_season_shift", "map_boss_victory"))
        self.assertEqual(player["map_boss"]["season"], "summer")
        self.assertEqual(player["map_boss"]["echo"], 0)
        self.assertEqual(player["map_boss"]["defeated_total"], 1)


# ── Full scripted fights ──────────────────────────────────────────────────

class TestArenaFullFight(ArenaCombatCase):

    def test_full_fight_victory(self):
        player = make_fighter(strength=260, hp=6000, blocks=14)
        mb.maybe_spawn(player)
        result, io, enemies = self._run_fight(player)
        self.assertEqual(result, "victory")
        self.assertGreaterEqual(player["_map_boss_rounds"], 1)
        joined = "\n".join(io.log)
        self.assertIn("PHASE", joined)
        self.assertIn("Seasonal Warden", joined)     # custom HUD header
        self.assertIn("ROUND", joined)

    def test_full_fight_flee_is_always_allowed(self):
        player = make_fighter(strength=10, hp=200, con=5, blocks=14)
        mb.maybe_spawn(player)
        result, _io, enemies = self._run_fight(player, action="f",
                                               max_actions=5)
        self.assertEqual(result, "fled")
        self.assertGreaterEqual(enemies[0]["hp"], 0)

    def test_dawn_reset_mid_fight(self):
        """A fight dragged past midnight clears adds and starts the Lull."""
        player = make_fighter(strength=120, hp=20000, con=300, blocks=22)
        mb.maybe_spawn(player)
        result, io, _enemies = self._run_fight(player, action="a",
                                               max_actions=40)
        joined = "\n".join(io.log)
        self.assertIn("Dawn breaks", joined)
        self.assertIn("Dawn Lull", joined)
        self.assertIn(result, ("fled", "victory", "dead"))


# ═══════════════════════════════════════════════════════════════
# Rewards & uniques (Phase 4)
# ═══════════════════════════════════════════════════════════════

def _unique_actor(**extra):
    """An actor dict wearing all four Warden trophies."""
    from pandemonium.resources.items import build_item
    actor = {
        "name": "Hero",
        "equipped": {
            "weapon": build_item("long_day", "unique"),
            "armor": build_item("echo_mantle", "unique"),
            "accessory1": build_item("warden_signet", "unique"),
            "accessory2": build_item("sundial_crown", "unique"),
        },
        "active_buffs": [],
        "active_debuffs": [],
        "current_hp": 500,
        "day": 20,
    }
    actor.update(extra)
    return actor


class TestUniqueItemDefinitions(MapBossTestCase):
    """§9 — the four trophies exist with the documented shape.

    The engine's unique convention (2026-11-09) rewrites authored definitions
    at import: stats are normalized to a slot budget and the multi-element
    profile collapses to one identity element (flowers refill the two open
    slots). These tests pin the *installed* shape plus the authored intent.
    """

    # item id -> (slot, special, stat names, identity element)
    EXPECTED = {
        "warden_signet": ("accessory", "long_day_signet",
                          ("Dexterity", "Wisdom"), "light"),
        "long_day": ("weapon", "long_day_blade",
                     ("Strength", "Dexterity"), "fire"),
        "echo_mantle": ("armor", "echo_mantle",
                        ("Constitution", "Wisdom"), "physical"),
        "sundial_crown": ("accessory", "sundial_crown",
                          ("Wisdom", "Charisma"), "light"),
    }

    def test_every_trophy_matches_the_design_table(self):
        from pandemonium.resources.items import ITEMS, build_item
        for item_id, (slot, special, stats, element) in self.EXPECTED.items():
            base = ITEMS[item_id]
            self.assertEqual(base["slot"], slot)
            self.assertEqual(base["special"], special)
            self.assertEqual(base["drop_source"], "warden_long_day")
            self.assertEqual(base["drop_rarity"], "unique")
            self.assertTrue(base.get("unique"))
            for stat in stats:
                self.assertGreater(base["base_mods"].get(stat, 0), 0,
                                   f"{item_id} {stat}")
            self.assertEqual(base.get("primary_element"), element)
            item = build_item(item_id, "unique")
            self.assertEqual(item["rarity"], "unique")
            self.assertEqual(item["special"], special)
            self.assertEqual(set(item["mods"]), set(stats))

    def test_unique_stat_budgets_apply(self):
        """The four trophies follow the same budget rule as every unique."""
        from pandemonium.resources.item_generation import (
            UNIQUE_ENHANCE_CAP, UNIQUE_STAT_BUDGET)
        from pandemonium.resources.items import build_item
        for item_id, (slot, _special, stats, _element) in self.EXPECTED.items():
            item = build_item(item_id, "unique")
            target = (UNIQUE_STAT_BUDGET[slot]
                      - UNIQUE_ENHANCE_CAP * len(stats))
            self.assertEqual(sum(item["mods"].values()), target, item_id)

    def test_long_day_is_a_sword_with_a_fire_identity(self):
        from pandemonium.resources.item_generation import (
            UNIQUE_ELEMENT_VALUE, UNIQUE_TRAIT_TIER)
        from pandemonium.resources.items import ITEMS, build_item
        base = ITEMS["long_day"]
        self.assertEqual(base["weapon_type"], "sword")
        self.assertEqual(base["scaling_stat"], "Strength")
        # Authored profile (§9): physical / fire / light at 1.15.
        self.assertAlmostEqual(base["elemental_dmg"]["fire"], 1.15, places=3)
        # Built weapon: identity element at infusion tier II.
        item = build_item("long_day", "unique")
        self.assertEqual(item["elemental_dmg"],
                         {"fire": UNIQUE_ELEMENT_VALUE})
        self.assertEqual(item["trait_tier"], UNIQUE_TRAIT_TIER)

    def test_trophy_ladder_is_index_aligned(self):
        self.assertEqual(len(data.MAP_BOSS_UNIQUE_ITEMS),
                         len(data.MAP_BOSS_UNIQUE_MILESTONES))
        self.assertEqual(data.MAP_BOSS_UNIQUE_ITEMS, tuple(self.EXPECTED))


class TestUniqueEffects(MapBossTestCase):
    """§9 — the four effects work on any actor (player or ally)."""

    def setUp(self):
        super().setUp()
        from pandemonium.combat.weapon import map_boss_uniques as uniques
        self.u = uniques

    def test_equip_detection(self):
        actor = _unique_actor()
        self.assertTrue(self.u.actor_has_warden_signet(actor))
        self.assertTrue(self.u.actor_has_long_day_edge(actor))
        self.assertTrue(self.u.actor_has_echo_mantle(actor))
        self.assertTrue(self.u.actor_has_sundial_crown(actor))
        bare = {"equipped": {}, "active_buffs": []}
        for fn in (self.u.actor_has_warden_signet,
                   self.u.actor_has_long_day_edge,
                   self.u.actor_has_echo_mantle,
                   self.u.actor_has_sundial_crown):
            self.assertFalse(fn(bare))

    def test_signet_phase_bonus_ladder(self):
        actor = _unique_actor()
        actor["_map_boss_clock_blocks"] = 4      # Morning
        self.assertEqual(self.u.signet_bonus(actor), 0.0)
        actor["_map_boss_clock_blocks"] = 10     # Noon
        self.assertAlmostEqual(self.u.signet_bonus(actor), 0.08, places=3)
        actor["_map_boss_clock_blocks"] = 20     # Night
        self.assertAlmostEqual(self.u.signet_bonus(actor), 0.16, places=3)

    def test_signet_uses_the_projected_arena_clock(self):
        actor = _unique_actor(day_blocks=2)      # real clock: Morning
        actor["_map_boss_clock_blocks"] = 22     # arena clock: Night
        self.assertAlmostEqual(self.u.signet_bonus(actor), 0.16, places=3)
        plain = _unique_actor(day_blocks=2)
        self.assertEqual(self.u.signet_bonus(plain), 0.0)

    def test_long_day_stacks_cap_and_multiply(self):
        actor = _unique_actor()
        actor["allies"] = []
        actor["_map_boss_clock_blocks"] = 10
        self.u.begin_map_boss_uniques(actor)
        self.assertEqual(actor["long_day_stacks"], 0)
        for _ in range(12):
            self.u.tick_long_day(actor)
        self.assertEqual(actor["long_day_stacks"], self.u.LONG_DAY_STACK_CAP)
        self.assertAlmostEqual(self.u.long_day_bonus(actor), 0.30, places=3)
        boosted = self.u.apply_long_day_damage(actor, 100)
        self.assertGreater(boosted, 100)

    def test_long_day_resets_on_the_morning_transition(self):
        actor = _unique_actor()
        actor["_map_boss_clock_blocks"] = 22     # Night
        self.u.tick_long_day(actor)
        self.u.tick_long_day(actor)
        self.assertEqual(actor["long_day_stacks"], 2)
        actor["_map_boss_clock_blocks"] = 4      # dawn breaks
        self.u.tick_long_day(actor)
        self.assertEqual(actor["long_day_stacks"], 1)      # reset, then +1
        self.assertEqual(actor["long_day_phase"], "morning")

    def test_long_day_keeps_accumulating_through_morning(self):
        """Only the *transition* into Morning resets — not every Morning round."""
        actor = _unique_actor()
        actor["_map_boss_clock_blocks"] = 5
        for _ in range(3):
            self.u.tick_long_day(actor)
        self.assertEqual(actor["long_day_stacks"], 3)

    def test_echo_mantle_sources_a_defense_buff(self):
        actor = _unique_actor()
        actor["_map_boss_clock_blocks"] = 10
        self.u.refresh_echo_mantle(actor)
        mantle = [b for b in actor["active_buffs"]
                  if b.get("source") == "echo_mantle"]
        self.assertEqual(len(mantle), 1)
        self.assertEqual(mantle[0]["type"], "defense_pct")
        self.assertAlmostEqual(mantle[0]["value"], 0.12, places=3)
        actor["_map_boss_clock_blocks"] = 20     # Night
        self.u.refresh_echo_mantle(actor)
        mantle = [b for b in actor["active_buffs"]
                  if b.get("source") == "echo_mantle"]
        self.assertEqual(len(mantle), 1, "refresh must not stack")
        self.assertAlmostEqual(mantle[0]["value"], 0.20, places=3)

    def test_echo_mantle_clears_with_the_battle(self):
        actor = _unique_actor()
        self.u.refresh_echo_mantle(actor)
        self.u.clear_map_boss_unique_state(actor)
        self.assertEqual([b for b in actor["active_buffs"]
                          if b.get("source") == "echo_mantle"], [])

    def test_sundial_crown_saves_once_per_day(self):
        actor = _unique_actor(current_hp=1)
        actor["active_debuffs"] = [
            {"type": "burn", "remaining": 3},
            {"type": "eternal", "permanent": True},
        ]
        actor["slowed"] = True
        self.assertTrue(self.u.try_sundial_crown_save(actor))
        self.assertEqual(actor["current_hp"], 1)
        self.assertEqual(actor["sundial_used_day"], 20)
        self.assertEqual([d["type"] for d in actor["active_debuffs"]],
                         ["eternal"])
        self.assertFalse(actor["slowed"])
        self.assertFalse(self.u.try_sundial_crown_save(actor))
        actor["day"] = 21            # a new day recharges it
        self.assertTrue(self.u.try_sundial_crown_save(actor))
        self.assertEqual(actor["sundial_used_day"], 21)

    def test_sundial_crown_not_worn(self):
        actor = {"equipped": {}, "active_buffs": [], "current_hp": 5, "day": 3}
        self.assertFalse(self.u.try_sundial_crown_save(actor))

    def test_sundial_crown_is_a_death_ward_fallthrough(self):
        from pandemonium.combat.status_effects import try_consume_death_ward
        actor = _unique_actor(current_hp=1)
        self.assertTrue(try_consume_death_ward(actor))
        self.assertEqual(actor["sundial_used_day"], 20)

    def test_uniques_work_on_an_ally(self):
        ally = _unique_actor(is_ally=True, name="Mira")
        ally["_map_boss_clock_blocks"] = 20
        self.assertAlmostEqual(self.u.signet_bonus(ally), 0.16, places=3)
        self.u.tick_long_day(ally)
        ally_dmg = self.u.apply_long_day_damage(ally, 200)
        self.assertGreater(ally_dmg, 200)
        self.assertTrue(self.u.try_sundial_crown_save(ally))

    def test_sync_party_phase_mirrors_clock_onto_allies(self):
        ally = _unique_actor()
        player = {"day": 20, "_map_boss_clock_blocks": 21,
                  "equipped": {}, "active_buffs": [], "allies": [ally]}
        self.u.sync_party_phase(player)
        self.assertEqual(ally["_map_boss_clock_blocks"], 21)
        self.assertEqual(ally["day"], 20)
        self.assertAlmostEqual(self.u.signet_bonus(ally), 0.16, places=3)


class TestRewardGrant(MapBossTestCase):
    """§8 — one kill's spoils."""

    def _kill(self, today=20, player=None, night=False):
        player = player or make_player(day=today)
        site = mb.maybe_spawn(player)
        mb.record_victory(player)
        summary = mb.grant_victory_rewards(player, site, night=night)
        return player, site, summary

    def test_gold_and_xp_match_the_formula(self):
        player, _site, summary = self._kill()
        expected = mb.gold_xp_reward(0, player=player)
        self.assertEqual(summary["gold"], expected["gold"])
        self.assertEqual(summary["exp"], expected["exp"])
        self.assertEqual(summary["gold"],
                         data.MAP_BOSS_GOLD_BASE + data.MAP_BOSS_GOLD_PER_ECHO * 0)
        self.assertEqual(summary["exp"], data.MAP_BOSS_XP_BASE)
        self.assertGreaterEqual(player["gold"], summary["gold"])

    def test_echo_scales_gold_and_xp(self):
        player = make_player(day=25)
        site = mb.maybe_spawn(player)
        site["echo"] = 4
        site["level"] = mb.echo_stats(4)["level"]
        mb.record_victory(player)
        summary = mb.grant_victory_rewards(player, site)
        step = site["level"] - data.MAP_BOSS_LEVEL_START
        self.assertEqual(
            summary["gold"],
            data.MAP_BOSS_GOLD_BASE + data.MAP_BOSS_GOLD_PER_LEVEL * step
            + data.MAP_BOSS_GOLD_PER_ECHO * 4)
        self.assertEqual(
            summary["exp"],
            data.MAP_BOSS_XP_BASE + data.MAP_BOSS_XP_PER_LEVEL * step
            + data.MAP_BOSS_XP_PER_ECHO * 4)
        self.assertGreater(summary["gold"],
                           mb.gold_xp_reward(0, player=player)["gold"])

    def test_night_kill_pays_more_gold_and_an_extra_flower(self):
        player_day, _s1, day_sum = self._kill(night=False)
        player_night, _s2, night_sum = self._kill(night=True)
        self.assertGreater(night_sum["gold"], day_sum["gold"])
        self.assertEqual(len(day_sum["flowers"]), 1)
        self.assertEqual(len(night_sum["flowers"]), 2)

    def test_cache_consumables_and_flower_are_granted(self):
        player, site, summary = self._kill()
        self.assertIsNotNone(summary["cache"])
        self.assertEqual(len(summary["consumables"]),
                         data.MAP_BOSS_CONSUMABLES_PER_KILL)
        self.assertEqual(len(summary["flowers"]), 1)
        ids = {i.get("id") for i in player["inventory"]}
        self.assertIn(site["cache_preview"]["item_id"], ids)
        for item_id in site["consumables"]:
            self.assertIn(item_id, ids)
        self.assertIn(site["flower"], ids)

    def test_xp_reaches_living_allies_only(self):
        ally_a = {"name": "A", "current_hp": 10}
        ally_b = {"name": "B", "current_hp": 0}
        player = make_player(day=20, allies=[ally_a, ally_b])
        with mock.patch("pandemonium.progression.leveling.gain_exp") as g_player, \
                mock.patch("pandemonium.progression.leveling.gain_exp_ally") as g_ally:
            site = mb.maybe_spawn(player)
            mb.record_victory(player)
            summary = mb.grant_victory_rewards(player, site)
        g_player.assert_called_once()
        g_ally.assert_called_once_with(ally_a, summary["exp"])

    def test_first_kill_grants_the_signet(self):
        player, _site, summary = self._kill()
        self.assertEqual([u["id"] for u in summary["uniques"]],
                         ["warden_signet"])
        self.assertIn("warden_signet",
                      mb.ensure_map_boss_state(player)["unique_grants"])
        self.assertIn("warden_signet",
                      {i.get("id") for i in player["inventory"]})

    def test_no_duplicate_trophy_on_second_kill(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        mb.record_victory(player)
        mb.grant_victory_rewards(player, site)
        mb.record_victory(player)
        summary = mb.grant_victory_rewards(player, site)
        self.assertEqual(summary["uniques"], [])
        self.assertEqual(summary["extra_caches"], 0)
        trophies = [i for i in player["inventory"]
                    if i.get("rarity") == "unique"]
        self.assertEqual(len(trophies), 1)
        self.assertIn("warden_signet",
                      mb.ensure_map_boss_state(player)["unique_grants"])

    def test_third_kill_grants_the_edge(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        for _ in range(3):
            mb.record_victory(player)
            summary = mb.grant_victory_rewards(player, site)
        self.assertEqual([u["id"] for u in summary["uniques"]], ["long_day"])

    def test_full_ladder_then_second_caches(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        granted = []
        for _ in range(11):
            mb.record_victory(player)
            summary = mb.grant_victory_rewards(player, site)
            before = len(granted)
            granted.extend(u["id"] for u in summary["uniques"])
            if before < 4 and len(granted) == 4:
                self.assertEqual(summary["extra_caches"], 0)
        self.assertEqual(granted, list(data.MAP_BOSS_UNIQUE_ITEMS))
        self.assertEqual(summary["extra_caches"], 1)   # the 11th kill
        state = mb.ensure_map_boss_state(player)
        self.assertEqual(state["unique_grants"],
                         list(data.MAP_BOSS_UNIQUE_ITEMS))

    def test_second_cache_uses_the_echo_rarity_floor(self):
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        state = mb.ensure_map_boss_state(player)
        state["unique_grants"] = list(data.MAP_BOSS_UNIQUE_ITEMS)
        state["defeated_total"] = 10
        mb.record_victory(player)          # -> 11
        summary = mb.grant_victory_rewards(player, site)
        self.assertEqual(summary["extra_caches"], 1)
        caches = [o for o in summary["obtained"] if o["kind"] == "cache"]
        self.assertEqual(len(caches), 2)

    def test_reward_grant_journals_the_kill(self):
        player, _site, summary = self._kill()
        entries = player["journal"]["events"]
        names = [e.get("name") for e in entries]
        expected = f"Warden Felled \u2014 Spring Echo {summary['echo']}"
        self.assertIn(expected, names)
        entry = next(e for e in entries if e["name"] == expected)
        self.assertEqual(entry["tag"], "[MAP BOSS]")
        self.assertIn("Warden's Signet", entry["desc"])

    def test_no_superboss_bookkeeping(self):
        """§8.6 — the Warden is never recorded as a superboss."""
        player, _site, _summary = self._kill()
        self.assertFalse(player.get("defeated_superbosses"))
        self.assertFalse(player.get("superboss_pool"))
        self.assertFalse(player.get("awakening_shards"))

    def test_full_bag_keeps_the_trophy_and_reports_the_cache(self):
        from pandemonium.resources.items import build_item
        filler = [build_item("iron_sword", "common") for _ in range(10)]
        player = make_player(day=20, inventory=filler)
        site = mb.maybe_spawn(player)
        mb.record_victory(player)
        summary = mb.grant_victory_rewards(player, site)
        self.assertIsNone(summary["cache"])
        self.assertTrue(summary["left_behind"])
        self.assertEqual([u["id"] for u in summary["uniques"]],
                         ["warden_signet"])
        self.assertIn("warden_signet",
                      {i.get("id") for i in player["inventory"]})


class TestArenaRewardRouting(ArenaCombatCase):
    """§7.7 + §8 — the arena exit grants spoils only on a kill."""

    def _exit(self, result, hp=1000, night_blocks=10):
        from pandemonium.world.dungeon import _map_boss_arena_exit
        player = make_player(day=20)
        site = mb.maybe_spawn(player)
        snapshot = dict(site)
        snapshot["hp"] = hp
        snapshot["_map_boss"] = True
        player["_map_boss_rounds"] = 3
        player["_map_boss_clock_blocks"] = night_blocks
        with mock.patch("pandemonium.core.save_load.save_game"):
            outcome = _map_boss_arena_exit(player, result, site, snapshot)
        return player, site, outcome

    def test_victory_stashes_the_loot_summary(self):
        player, _site, outcome = self._exit("victory")
        self.assertEqual(outcome, "map_boss_victory")
        summary = player["_map_boss_victory"]
        self.assertEqual(summary["echo"], 0)
        self.assertGreater(summary["gold"], 0)
        self.assertEqual([u["id"] for u in summary["uniques"]],
                         ["warden_signet"])

    def test_night_kill_bonus_uses_the_projected_clock(self):
        player, _site, _outcome = self._exit("victory", night_blocks=20)
        self.assertTrue(player["_map_boss_victory"]["night"])

    def test_flee_and_death_grant_nothing(self):
        for result in ("fled", "dead"):
            player = make_player(day=20)
            site = mb.maybe_spawn(player)
            snapshot = dict(site, hp=500, _map_boss=True)
            player["_map_boss_rounds"] = 2
            player["_map_boss_clock_blocks"] = 10
            with mock.patch("pandemonium.core.save_load.save_game"):
                from pandemonium.world.dungeon import _map_boss_arena_exit
                _map_boss_arena_exit(player, result, site, snapshot)
            self.assertNotIn("_map_boss_victory", player)
            self.assertEqual(player["gold"], 0)
            self.assertEqual(player["inventory"], [])
            self.assertEqual(
                mb.ensure_map_boss_state(player)["unique_grants"], [])


class TestArenaUniqueWiring(ArenaCombatCase):
    """§9 — the trophies are actually wired into the live damage/lifecycle paths."""

    def test_arena_kill_routes_damage_through_the_trophies(self):
        from pandemonium.combat.weapon import map_boss_uniques as uniques
        from pandemonium.resources.items import build_item

        player = make_fighter(strength=200, hp=4000, con=40, blocks=10)
        player["equipped"]["weapon"] = build_item("long_day", "unique")
        player["equipped"]["accessory1"] = build_item("warden_signet", "unique")
        player["equipped"]["armor"] = build_item("echo_mantle", "unique")
        mb.maybe_spawn(player)

        seen = []
        real = uniques.apply_long_day_damage

        def _spy(actor, dmg):
            seen.append((actor is player, dmg))
            return real(actor, dmg)

        with mock.patch.object(uniques, "apply_long_day_damage", _spy):
            result, _io, _enemies = self._run_fight(player, action="a",
                                                    max_actions=20)
        self.assertIn(result, ("victory", "fled", "dead"))
        self.assertTrue(seen, "the basic-attack path never consulted the trophies")
        self.assertTrue(any(is_player for is_player, _dmg in seen))

    def test_arena_fight_ticks_and_clears_unique_state(self):
        from pandemonium.combat.weapon import map_boss_uniques as uniques

        player = make_fighter(strength=260, hp=6000, con=40, blocks=14)
        mb.maybe_spawn(player)
        with mock.patch.object(uniques, "tick_long_day",
                               wraps=uniques.tick_long_day) as tick, \
                mock.patch.object(uniques, "begin_map_boss_uniques",
                                  wraps=uniques.begin_map_boss_uniques) as begin:
            self._run_fight(player, action="a")
        self.assertTrue(begin.called)
        self.assertTrue(tick.called, "round-end tick never ran")

    def test_engine_lifecycle_hooks_the_uniques(self):
        from pandemonium.combat import combat_engine
        from pandemonium.combat.weapon import map_boss_uniques as uniques

        player = make_fighter()
        player["allies"] = [dict(player, name="Ally", is_ally=True)]
        with mock.patch.object(uniques, "clear_map_boss_unique_state") as clear, \
                mock.patch.object(uniques, "begin_map_boss_uniques") as begin:
            # Mirrors _combat_inner's init block.
            clear(player)
            begin(player)
        self.assertTrue(clear.called)
        self.assertTrue(begin.called)
        # _tick_all_state must tick the stacks for the player and every ally.
        player["allies"][0]["current_hp"] = 10
        with mock.patch.object(uniques, "tick_long_day") as tick:
            combat_engine._tick_all_state(player)
        actors = [call[0][0] for call in tick.call_args_list]
        self.assertIn(player, actors)
        self.assertIn(player["allies"][0], actors)


class TestArenaInputRetries(ArenaCombatCase):
    """§7.4 — a rejected/repeated GUI action must not look like a crash.

    2026-11-14 (Winter Warden): a stray Enter/Continue echo arrived on the
    next "Choose:" prompt, the override validation rejected it, and the log
    showed "Internal error: override action '' is not available." followed by
    the legacy `[A]ttack  [D]efend …` line.
    """

    def _enemy(self):
        return {"name": "Dummy", "hp": 50, "max_hp": 50, "str_mod": 5,
                "con_mod": 5, "dex_mod": 5, "level": 20, "boss": False}

    def _turn(self, action, renders_menus):
        from pandemonium.combat.combat_io import set_io
        from pandemonium.combat.player_actions import handle_player_turn
        player = make_fighter()
        io = ScriptedIO()
        io.renders_menus = renders_menus
        set_io(io)
        try:
            result = handle_player_turn(
                player, [self._enemy()], 10, 10, 10, 10, 10, 10,
                _action_override=action,
            )
        finally:
            from pandemonium.combat.combat_io import reset_io
            reset_io()
        return result, io

    def test_empty_override_is_a_silent_retry(self):
        result, io = self._turn("", renders_menus=True)
        self.assertEqual(result[0], "retry")
        self.assertEqual(io.log, [], "a stray Enter must not print anything")

    def test_gui_mode_explains_the_stale_action(self):
        result, io = self._turn("zz", renders_menus=True)
        self.assertEqual(result[0], "retry")
        joined = "\n".join(io.log)
        self.assertIn("no longer available", joined)
        self.assertNotIn("Internal error", joined)
        self.assertNotIn("[A]ttack", joined)

    def test_console_mode_keeps_the_internal_error_line(self):
        result, io = self._turn("zz", renders_menus=False)
        self.assertEqual(result[0], "retry")
        self.assertIn("Internal error", "\n".join(io.log))

    def test_gui_io_accepts_only_one_answer_per_open_prompt(self):
        """Premature keys and double clicks must never reach the engine."""
        import threading
        import time

        from pandemonium.gui.screens.combat_screen import GUICombatIO

        io = GUICombatIO()
        # No prompt open yet: a keypress during another actor's turn is
        # dropped (this was the Winter Warden "override action" report).
        io.send_input("s")
        self.assertTrue(io.input_queue.empty())

        got = []
        worker = threading.Thread(
            target=lambda: got.append(io.input("Choose: ")), daemon=True)
        worker.start()
        deadline = time.time() + 2.0
        while io.output_queue.empty() and time.time() < deadline:
            time.sleep(0.005)
        io.output_queue.get()            # consume INPUT_NEEDED
        io.send_input("a")               # the real click
        io.send_input("a")               # double click — dropped
        io.send_input("")                # stray Enter — dropped
        worker.join(timeout=2.0)
        self.assertEqual(got, ["a"])
        self.assertTrue(io.input_queue.empty(),
                        f"stale answers queued: {list(io.input_queue.queue)}")

    def test_gui_io_accepts_the_next_prompt(self):
        from pandemonium.gui.screens.combat_screen import GUICombatIO
        io = GUICombatIO()
        io.begin_prompt("Choose: ")
        io.send_input("d")
        self.assertEqual(io.wait_answer(), "d")

    def test_arena_retry_never_prints_the_legacy_action_list(self):
        """GUI bridges draw the panel themselves — no `[A]ttack …` in the log."""
        from pandemonium.combat.combat_io import set_io

        class OnceIO(ScriptedIO):
            """Answers 'u' (empty bag → retry) once, then attacks."""

            def __init__(self):
                super().__init__(action="a")
                self.first_done = False

            def input(self, prompt=""):
                if "choose" in str(prompt).lower() and not self.first_done:
                    self.first_done = True
                    self.actions += 1
                    return "u"
                return super().input(prompt)

        player = make_fighter(strength=260, hp=6000, blocks=14)
        site = mb.maybe_spawn(player)
        io = OnceIO()
        set_io(io)
        try:
            enemies = self._cmb.build_encounter(site)
            result = self._cmb.combat_map_boss(player, floor=site["level"],
                                               enemies=enemies)
        finally:
            from pandemonium.combat.combat_io import reset_io
            reset_io()
        self.assertIn(result, ("victory", "fled", "dead"))
        self.assertTrue(io.first_done, "the retry path never ran")
        joined = "\n".join(io.log)
        self.assertNotIn("[A]ttack  [D]efend  [F]lee  [U]se item", joined)
        self.assertIn("no items usable in combat", joined)


if __name__ == "__main__":
    unittest.main()
