"""Regression: enemy kills must actually credit gold.

Bug history (2026-11-12): `add_gold_drop()` was truncated during the package
restructure — it computed the gold, then returned without adding it to the
player or printing it. Item drops still worked, so rooms looked normal but
the purse never moved.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pandemonium.world.dungeon import add_gold_drop, roll_gold_drop, ENEMIES  # noqa: E402
from pandemonium.resources.items import kill_gold_offset  # noqa: E402


def make_player(level=30, max_floor=30, gold=0):
    return {
        "gold": gold,
        "level": level,
        "max_floor": max_floor,
        "city_floors": {},
        "daily_effects": {},
        "equipped_title": None,
    }


def normal_enemy_near(level):
    """A non-boss enemy close to the requested level."""
    candidates = [k for k, v in ENEMIES.items()
                  if not v.get("boss") and v.get("level", 1) > 0]
    return min(candidates, key=lambda k: abs(ENEMIES[k]["level"] - level))


class GoldDropTests(unittest.TestCase):
    def test_roll_returns_positive_gold(self):
        player = make_player()
        gold = roll_gold_drop(normal_enemy_near(30), player=player)
        self.assertGreater(gold, 0)

    def test_add_gold_drop_credits_the_player(self):
        player = make_player()
        add_gold_drop(player, normal_enemy_near(30), pandemonium=False)
        self.assertGreater(player["gold"], 0)
        self.assertLess(player["gold"], 500)

    def test_offset_never_zeroes_level_30_gold(self):
        player = make_player(level=30, max_floor=30)
        self.assertGreater(kill_gold_offset(30), 0)
        gold = roll_gold_drop(normal_enemy_near(30), player=player)
        self.assertGreaterEqual(gold, 8)

    def test_existing_gold_is_preserved(self):
        player = make_player(gold=1234)
        add_gold_drop(player, normal_enemy_near(30), pandemonium=False)
        self.assertGreater(player["gold"], 1234)


if __name__ == "__main__":
    unittest.main()
