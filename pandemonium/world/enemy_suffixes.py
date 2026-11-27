"""Spawn-time enemy suffixes (replaces the old "Empowered" final-room buff).

A suffix is a rank modifier on a **normal** enemy: a name tag plus a small
stat budget. It is rolled once per combat room, weighted by the floor and the
room size, and applied when the enemy instance is created — so the HUD, the
combat engine and the floor preview all see the same numbers.

Design rules:
  * one suffix per room, one per enemy;
  * bosses, superbosses, minions, monster girls, city guards, heroines,
    shadows and scripted/dummy enemies can never roll one;
  * both the chance and the strength scale with floor depth;
  * suffixes never change rewards — they are a combat twist, not extra loot.

The old ``Empowered`` block in ``combat_engine`` (flat +30% HP / +20% stats on
the first enemy of the last room) is retired; the ``veteran`` suffix is its
spiritual successor.
"""

import random

# Suffixes only appear from floor 10 onward. Earlier floors are the clean
# tutorial + first descent; the room chance then ramps gradually.
SUFFIX_START_FLOOR = 10

# Chance that a *combat room* contains one suffixed enemy, by floor. Rows are
# interpolated linearly; bigger rooms get a small bonus (see roll_room_suffix).
SUFFIX_CHANCE_BANDS = (
    (9, 0.00),    # floors 1-9: no suffixes
    (10, 0.05),
    (19, 0.09),
    (34, 0.13),
    (49, 0.17),
    (60, 0.20),
    (999, 0.20),
)

# Budget curve: 60% of the table at floor 10, doubling to 200% at floor 60.
# The early elite is deliberately soft; the late one is a real spike.
SUFFIX_POWER_START = 0.60
SUFFIX_POWER_PER_FLOOR = 0.028
SUFFIX_POWER_CAP = 2.00

SUFFIX_CHANCE_PER_EXTRA_ENEMY = 0.015
SUFFIX_CHANCE_CAP = 0.35

# Enemy HUD column is 33 characters. A suffixed name must fit, and a suffix
# whose label already appears in the base name is skipped (no "Ancient
# Ancient Golem", no "Veteran Veteran Swordsman").
SUFFIX_NAME_MAX = 33

_SUFFIX_BLOCKED_FLAGS = (
    "boss", "super_boss", "minion_only", "city_only", "_heroine", "_shadow",
    "monster_girl", "ai_disabled", "is_dummy", "captured",
)

_STAT_FIELDS = {
    "str": "str_mod",
    "con": "con_mod",
    "dex": "dex_mod",
    "wis": "wis_mod",
    "ler": "ler_mod",
    "cha": "cha_mod",
}

# label = name prefix; weight = pick weight; min_floor = unlock depth.
# Every suffix unlocks at SUFFIX_START_FLOOR (floor 10); the weights keep the
# simple stat suffixes common and the exotic ones rare. hp/str/... are
# percentage multipliers at full power (scaled by suffix_power_for_floor).
SUFFIXES = {
    "veteran": {
        "label": "Veteran", "weight": 10, "min_floor": 10,
        "hp": 0.30, "str": 0.10, "con": 0.10, "dex": 0.10,
    },
    "frenzied": {
        "label": "Frenzied", "weight": 7, "min_floor": 10,
        "str": 0.30, "dex": 0.10, "con": -0.15,
    },
    "armored": {
        "label": "Armored", "weight": 7, "min_floor": 10,
        "hp": 0.10, "con": 0.35, "dex": -0.10,
    },
    "swift": {
        "label": "Swift", "weight": 6, "min_floor": 10,
        "hp": 0.10, "dex": 0.30,
    },
    "warded": {
        "label": "Warded", "weight": 5, "min_floor": 10,
        "hp": 0.10, "wis": 0.20, "status_res": 0.20,
    },
    "arcane": {
        "label": "Arcane", "weight": 4, "min_floor": 10,
        "ler": 0.25, "elemental": True,
    },
    "ancient": {
        "label": "Ancient", "weight": 3, "min_floor": 10,
        "hp": 0.60, "str": -0.10, "con": 0.15,
    },
}


def _lerp(a, b, t):
    return a + (b - a) * t


def suffix_chance_for_floor(floor):
    """Base chance for one suffix in a room at *floor* (0.0-1.0)."""
    try:
        floor = max(1, int(floor))
    except (TypeError, ValueError):
        floor = 1
    bands = SUFFIX_CHANCE_BANDS
    if floor <= bands[0][0]:
        return bands[0][1]
    for (f0, c0), (f1, c1) in zip(bands, bands[1:]):
        if floor <= f1:
            t = (floor - f0) / max(1, f1 - f0)
            return _lerp(c0, c1, t)
    return bands[-1][1]


def suffix_power_for_floor(floor):
    """Strength multiplier applied to a suffix's bonuses.

    F10 = 0.60 (60% of the table), F60 = 2.00 (200%). Below F10 suffixes
    cannot roll; ``apply_suffix`` also refuses them.
    """
    try:
        floor = max(1, int(floor))
    except (TypeError, ValueError):
        floor = 1
    if floor < SUFFIX_START_FLOOR:
        return 0.0
    if floor == SUFFIX_START_FLOOR:
        return SUFFIX_POWER_START
    return min(SUFFIX_POWER_CAP,
               SUFFIX_POWER_START + (floor - SUFFIX_START_FLOOR) * SUFFIX_POWER_PER_FLOOR)


def can_suffix(enemy):
    """True when this enemy instance may receive a suffix."""
    if not isinstance(enemy, dict):
        return False
    return not any(enemy.get(flag) for flag in _SUFFIX_BLOCKED_FLAGS)


def eligible_suffixes(floor):
    """Suffix ids unlocked at *floor*, with their pick weights."""
    try:
        floor = int(floor)
    except (TypeError, ValueError):
        floor = 1
    return [
        (sid, data["weight"])
        for sid, data in SUFFIXES.items()
        if floor >= data["min_floor"]
    ]


def suffix_fits_name(name, label):
    """True when *label* can prefix *name* without redundancy or overflow."""
    name = str(name or "")
    label = str(label or "")
    if not name or not label:
        return False
    if label.lower() in name.lower():
        return False
    return len(label) + 1 + len(name) <= SUFFIX_NAME_MAX


def roll_room_suffix(floor, enemy_count, rng=None, names=None):
    """Roll one suffix for a room.

    Returns ``{"index": int, "id": str}`` or ``None``. ``index`` is the slot
    in the room's enemy list that receives the suffix. When ``names`` is
    supplied, the roll only considers slots whose name can carry the label
    (no duplicate words like "Ancient Ancient Golem", no 34+ char names).
    """
    if enemy_count <= 0:
        return None
    rng = rng or random
    try:
        count = int(enemy_count)
        floor = int(floor)
    except (TypeError, ValueError):
        return None
    chance = suffix_chance_for_floor(floor)
    if chance <= 0:
        return None
    chance += SUFFIX_CHANCE_PER_EXTRA_ENEMY * max(0, count - 1)
    chance = min(SUFFIX_CHANCE_CAP, chance)
    if chance <= 0 or rng.random() >= chance:
        return None
    options = eligible_suffixes(floor)
    if not options:
        return None

    if names is not None:
        count = min(count, len(names))
        valid = []
        for idx in range(count):
            name = str(names[idx] or "")
            fits = [
                (sid, weight) for sid, weight in options
                if suffix_fits_name(name, SUFFIXES[sid]["label"])
            ]
            if fits:
                valid.append((idx, fits))
        if not valid:
            return None
        idx, fits = rng.choice(valid)
        ids = [sid for sid, _ in fits]
        weights = [weight for _, weight in fits]
        return {"index": idx, "id": rng.choices(ids, weights=weights, k=1)[0]}

    idx = rng.randrange(count)
    ids = [sid for sid, _ in options]
    weights = [w for _, w in options]
    return {"index": idx, "id": rng.choices(ids, weights=weights, k=1)[0]}


def apply_suffix(enemy, suffix_id, floor):
    """Apply *suffix_id* to an enemy instance in place. Returns the enemy."""
    data = SUFFIXES.get(suffix_id)
    if not data or not can_suffix(enemy):
        return enemy
    try:
        floor = int(floor)
    except (TypeError, ValueError):
        floor = SUFFIX_START_FLOOR
    if floor < SUFFIX_START_FLOOR:
        return enemy
    power = suffix_power_for_floor(floor)
    label = data["label"]

    if not suffix_fits_name(enemy.get("name", ""), label):
        return enemy

    enemy["name"] = f"{label} {enemy.get('name', 'Enemy')}"
    hp_bonus = data.get("hp", 0.0) * power
    if hp_bonus:
        enemy["max_hp"] = max(1, int(enemy.get("max_hp", 1) * (1.0 + hp_bonus)))
        enemy["hp"] = enemy["max_hp"]
    for key, field in _STAT_FIELDS.items():
        bonus = data.get(key, 0.0) * power
        if bonus and field in enemy:
            enemy[field] = max(0, int(enemy[field] * (1.0 + bonus)))
    status_bonus = data.get("status_res", 0.0)
    if status_bonus:
        enemy["status_res"] = min(1.0, enemy.get("status_res", 0.0) + status_bonus)
    if data.get("elemental"):
        enemy["elemental_dmg"] = {"magical": 1.3}
        enemy["elemental_res"] = {}
    enemy["suffix"] = suffix_id
    enemy["suffix_label"] = label
    return enemy


def apply_room_suffixes(enemies, suffixes, floor):
    """Apply a room's ``{index: suffix_id}`` map to spawned enemy dicts."""
    if not suffixes or not enemies:
        return enemies
    for idx, suffix_id in suffixes.items():
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(enemies):
            apply_suffix(enemies[idx], suffix_id, floor)
    return enemies
