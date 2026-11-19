"""
resources/map_boss_data.py — Seasonal map boss data (docs/map_boss_design.md).

Pure data + tiny helpers:

  * the four seasonal Wardens — name, glyph, element, weakness, biome
    preference, signature mechanic and signature status;
  * the ten-tier mechanic ladder per season (one new effect per Echo);
  * the §14 tuning constants, single-sourced here so the runtime, combat
    module and GUI panel all read the same numbers.

No game-system imports — safe to import from ``world/map_boss.py``, combat
modules, the GUI and tests.
"""

# ── Unlock + schedule (docs/map_boss_design.md §14) ────────────────────────
MAP_BOSS_UNLOCK_MAX_FLOOR = 20      # gate is max_floor > 20 (Floor 20 CLEARED)
MAP_BOSS_MONTH_LENGTH = 30          # a game month (the billing cycle)
MAP_BOSS_MONTHS_PER_SEASON = 3      # 3 × 30 = a 90-day season
MAP_BOSS_SEASON_LENGTH_DAYS = 90    # = events.SEASON_LENGTH_DAYS
MAP_BOSS_SEASONS = ("spring", "summer", "autumn", "winter")

# ── Echo curve ─────────────────────────────────────────────────────────────
MAP_BOSS_LEVEL_START = 20
MAP_BOSS_LEVEL_STEP = 20
MAP_BOSS_LEVEL_CAP = 80
MAP_BOSS_MECHANIC_RANK_STEP = 3     # +1 rank every 3 Echoes
MAP_BOSS_MECHANIC_RANK_CAP = 4
MAP_BOSS_START_DEPTH_CAP = None     # None = honour best_echo; int = clamp opener

# Stack caps (rank scaling does not move the cap; Echo tiers do)
MAP_BOSS_BLOOM_CAP_BASE = 3
MAP_BOSS_HEAT_CAP_BASE = 5
MAP_BOSS_HARVEST_CAP_BASE = 4
MAP_BOSS_ICE_CAP_BASE = 3

# ── Base stats (Echo 0 / level 20) ─────────────────────────────────────────
MAP_BOSS_BASE_HP = 1000
MAP_BOSS_BASE_STR = 30
MAP_BOSS_BASE_ARMOR = 12
MAP_BOSS_BASE_STATUS_RES = 0.20

# ── Level + Echo curves ────────────────────────────────────────────────────
MAP_BOSS_HP_PER_LEVEL = 0.06
MAP_BOSS_HP_PER_ECHO = 0.10
MAP_BOSS_HP_ECHO_QUADRATIC = 0.002
MAP_BOSS_DAMAGE_PER_LEVEL = 0.03
MAP_BOSS_DAMAGE_PER_ECHO = 0.03
MAP_BOSS_ARMOR_PER_ECHO = 0.5
MAP_BOSS_ARMOR_PER_LEVEL = 0.15
MAP_BOSS_ARMOR_CAP = 40
MAP_BOSS_RES_PER_ECHO = 0.02
MAP_BOSS_RES_PER_LEVEL = 0.005
MAP_BOSS_RES_CAP = 1.60
MAP_BOSS_SEASON_RES_BASE = 1.30
MAP_BOSS_SEASON_RES_PER_ECHO = 0.015
MAP_BOSS_SEASON_RES_PER_LEVEL = 0.005
MAP_BOSS_SEASON_RES_CAP = 1.70
MAP_BOSS_WEAKNESS = 0.70            # never scales
MAP_BOSS_STATUS_RES_PER_ECHO = 0.03
MAP_BOSS_STATUS_RES_PER_LEVEL = 0.005
MAP_BOSS_STATUS_RES_CAP = 0.85
MAP_BOSS_MECHANIC_TIER_CAP = 10
MAP_BOSS_MECHANIC_RANK_SCALE = 0.25  # +25% mechanic values per rank step

# ── Phase aggression ───────────────────────────────────────────────────────
MAP_BOSS_NOON_DAMAGE = 1.10
MAP_BOSS_NIGHT_DAMAGE = 1.30
MAP_BOSS_DAWN_LULL_DAMAGE = 0.85
MAP_BOSS_NIGHT_ACTIONS = 2
MAP_BOSS_DAWN_LULL_ROUNDS = 2

# ── Drops ──────────────────────────────────────────────────────────────────
MAP_BOSS_GOLD_BASE = 400
MAP_BOSS_GOLD_PER_LEVEL = 25
MAP_BOSS_GOLD_PER_ECHO = 100
MAP_BOSS_XP_BASE = 600
MAP_BOSS_XP_PER_LEVEL = 40
MAP_BOSS_XP_PER_ECHO = 150
MAP_BOSS_NIGHT_GOLD_BONUS = 0.25
MAP_BOSS_CACHE_GEAR_CAP = 80
MAP_BOSS_EPIC_CHANCE_BASE = 0.10
MAP_BOSS_EPIC_CHANCE_PER_ECHO = 0.10
MAP_BOSS_EPIC_CHANCE_CAP = 1.0
MAP_BOSS_LEGENDARY_FROM_ECHO = 10
MAP_BOSS_LEGENDARY_CHANCE = 0.30
MAP_BOSS_CONSUMABLES_PER_KILL = 2
MAP_BOSS_UNIQUE_MILESTONES = (1, 3, 6, 10)   # cumulative victories -> unique
# Trophy ladder (§8.4 / §9) — index-aligned with the milestones above.
MAP_BOSS_UNIQUE_ITEMS = ("warden_signet", "long_day", "echo_mantle",
                         "sundial_crown")


# ── Seasonal roster (§5.5 / §6.6) ──────────────────────────────────────────
#
# ``biomes`` is the season's biome preference for the arena site; the
# season element/weakness/mechanic never change with biome or Echo.
# ``site_city`` / ``site_position`` lock each Warden's arena to its most
# suited location (docs/map_boss_design.md §5.2) — the position is a fixed
# canvas point that already clears every city node, wild marker and the
# Event Horizon site.
WARDENS = {
    "spring": {
        "season_name": "Spring",
        "warden_name": "Warden of the First Bloom",
        "glyph": "\U0001F331",                      # 🌱
        "element": "earth",
        "weakness": "fire",
        "biomes": ("forest", "temperate"),
        "site_city": "veilholt",               # the blooming forest
        "site_position": (760, 45),            # north of Veilholt
        "mechanic": "bloom",
        "mechanic_name": "Bloom",
        "stack_tag": "BLOOM",
        "signature_status": "poison",
        "status_code": "PSN",
        "add_name": "Bloomling",
        "stack_cap": MAP_BOSS_BLOOM_CAP_BASE,
    },
    "summer": {
        "season_name": "Summer",
        "warden_name": "Warden of the Long Noon",
        "glyph": "\U0001F525",                      # 🔥
        "element": "fire",
        "weakness": "water",
        "biomes": ("desert", "volcanic", "savanna"),
        "site_city": "cinderpeak",             # the volcanic noon
        "site_position": (538, 286),           # south-west of Cinderpeak
        "mechanic": "heat",
        "mechanic_name": "Heat",
        "stack_tag": "HEAT",
        "signature_status": "burn",
        "status_code": "BRN",
        "add_name": "Cinderling",
        "stack_cap": MAP_BOSS_HEAT_CAP_BASE,
    },
    "autumn": {
        "season_name": "Autumn",
        "warden_name": "Warden of the Falling Crown",
        "glyph": "\U0001F342",                      # 🍂
        "element": "wind",
        "weakness": "thunder",
        "biomes": ("savanna", "forest", "temperate"),
        "site_city": "thornwall",              # the harvest frontier
        "site_position": (386, 142),           # north-east of Thornwall
        "mechanic": "harvest",
        "mechanic_name": "Harvest",
        "stack_tag": "HARVEST",
        "signature_status": "bleed",
        "status_code": "BLE",
        "add_name": "Huskling",
        "stack_cap": MAP_BOSS_HARVEST_CAP_BASE,
    },
    "winter": {
        "season_name": "Winter",
        "warden_name": "Warden of the Last Light",
        "glyph": "\u2744",                          # ❄
        "element": "water",
        "weakness": "fire",
        "biomes": ("tundra", "mountain"),
        "site_city": "stormhold",              # the frozen north
        "site_position": (95, 165),            # south-west of Stormhold
        "mechanic": "frostbite",
        "mechanic_name": "Frostbite",
        "stack_tag": "FROST",
        "signature_status": "slow",
        "status_code": "FRZ",
        "add_name": "Frostling",
        "stack_cap": MAP_BOSS_ICE_CAP_BASE,
    },
}


# ── Mechanic upgrade ladders (§6.3) — one new effect per Echo ──────────────
#
# Each entry: ``id`` (stable key used by combat), ``label`` (short HUD/panel
# text) and ``desc`` (panel tooltip). Echo N unlocks tier N+1; Echo 10+ adds
# no new effect and scales the numeric values through ``mechanic_rank``.
MECHANIC_TIERS = {
    "bloom": (
        {"id": "bloom_stacks", "label": "Bloom",
         "desc": "Bloom stacks (cap 3): +3% damage, +2% armor per stack; at "
                 "cap, consume all Bloom to heal 5% max HP."},
        {"id": "bloom_poison", "label": "Poison Bloom",
         "desc": "At 3+ Bloom, attacks apply Poison (2 turns)."},
        {"id": "bloom_cap_heal_10", "label": "Deeper Bloom",
         "desc": "Cap heal becomes 10%; refresh Poison on the target."},
        {"id": "bloom_noon_gain", "label": "Noon Bloom",
         "desc": "Bloom gain +1 at Noon."},
        {"id": "bloom_poison_weaken", "label": "Sapping Pollen",
         "desc": "Poison also applies Weaken (-10% damage, 2 turns)."},
        {"id": "bloom_cap_heal_15", "label": "Overgrown",
         "desc": "Cap heal becomes 15%; poison the whole party."},
        {"id": "bloom_cap_up", "label": "Bloom Cap +1",
         "desc": "Bloom cap +1."},
        {"id": "bloom_poison_amp", "label": "Thick Poison",
         "desc": "Poison damage +50%."},
        {"id": "bloom_summon", "label": "Bloomling",
         "desc": "Consuming Bloom summons a Bloomling (if space)."},
        {"id": "bloom_overbloom", "label": "Overbloom",
         "desc": "Overbloom: cap consumption also deals AoE earth damage "
                 "(0.75x STR) and poisons all."},
    ),
    "heat": (
        {"id": "heat_stacks", "label": "Heat",
         "desc": "Heat stacks (cap 5): +2% damage, +2% initiative per stack; "
                 "at cap, vent all Heat (no damage)."},
        {"id": "heat_burn", "label": "Smoulder",
         "desc": "At 4+ Heat, attacks apply Burn."},
        {"id": "solar_flare", "label": "Solar Flare",
         "desc": "At cap, Solar Flare: AoE fire damage (0.75x STR), then "
                 "reset Heat."},
        {"id": "heat_noon_gain", "label": "Noon Heat",
         "desc": "Heat gain +1 at Noon."},
        {"id": "burn_duration", "label": "Lingering Burn",
         "desc": "Burn duration +1."},
        {"id": "flare_armor_pierce", "label": "Piercing Flare",
         "desc": "Solar Flare ignores 30% armor."},
        {"id": "heat_cap_up", "label": "Heat Cap +1",
         "desc": "Heat cap +1."},
        {"id": "burn_amp", "label": "White Burn",
         "desc": "Burn damage +50%."},
        {"id": "heat_night_gain", "label": "Night Heat",
         "desc": "Heat gain +1 at Night."},
        {"id": "second_sun", "label": "Second Sun",
         "desc": "Second Sun: Solar Flare hits twice (second at 50% power) "
                 "before reset."},
    ),
    "harvest": (
        {"id": "harvest_stacks", "label": "Harvest",
         "desc": "Attacks apply Bleed (3 turns). When a bleeding party member "
                 "acts, gain 1 Harvest (cap 4); each stack: +2% damage, "
                 "+1% lifesteal."},
        {"id": "bleed_amp", "label": "Deep Cut",
         "desc": "Bleed damage +50%."},
        {"id": "reap", "label": "Reap",
         "desc": "At cap, Reap: single-target 1.5x STR; heal 50% of damage "
                 "dealt; reset Harvest."},
        {"id": "reap_heal_60", "label": "Rich Reap",
         "desc": "Reap heals 60%."},
        {"id": "bleed_duration", "label": "Lingering Cut",
         "desc": "Bleed duration +1."},
        {"id": "reap_party_bleed", "label": "Bloody Reap",
         "desc": "Reap also applies Bleed to the whole party."},
        {"id": "harvest_cap_up", "label": "Harvest Cap +1",
         "desc": "Harvest cap +1."},
        {"id": "lifesteal_up", "label": "Thirsty Harvest",
         "desc": "Lifesteal +1% per stack."},
        {"id": "reap_on_death", "label": "Fallen Harvest",
         "desc": "When a bleeding target dies, gain 2 Harvest."},
        {"id": "final_harvest", "label": "Final Harvest",
         "desc": "Final Harvest: Reap hits the whole party at 0.9x and heals "
                 "50% of total damage."},
    ),
    "frostbite": (
        {"id": "frostbite_round", "label": "Frostbite",
         "desc": "Each round apply 1 Frostbite to a random party member. "
                 "Frostbite: -2 DEX, 2 water damage/turn, 3 turns."},
        {"id": "frost_freeze", "label": "Freeze",
         "desc": "At 3 stacks, Freeze for 1 turn and reset."},
        {"id": "ice_armor", "label": "Ice Armor",
         "desc": "Gain 1 Ice Armor per round (cap 3); each -3% damage taken; "
                 "fire damage removes 1."},
        {"id": "night_extra_target", "label": "Night Chills",
         "desc": "Frostbite targets +1 at Night."},
        {"id": "ice_cap_up", "label": "Ice Armor Cap +1",
         "desc": "Ice Armor cap +1."},
        {"id": "frozen_vuln", "label": "Brittle",
         "desc": "Frozen targets take +20% damage."},
        {"id": "frost_damage_up", "label": "Bitter Cold",
         "desc": "Frostbite damage +2/turn."},
        {"id": "shatter", "label": "Shatter",
         "desc": "Shatter: when Ice Armor is removed by fire, the attacker "
                 "takes 1.0x STR water damage."},
        {"id": "freeze_duration", "label": "Long Freeze",
         "desc": "Freeze duration +1."},
        {"id": "absolute_zero", "label": "Absolute Zero",
         "desc": "Absolute Zero: at 5 Frostbite stacks, freeze the whole "
                 "party for 1 turn and reset all Frostbite."},
    ),
}

# Element-themed tier-4 consumables the Warden's cache prefers (§8.2).
ELEMENT_CONSUMABLE = {
    "fire": "ember_draught",
    "water": "frostward_tonic",
    "thunder": "thunderbrew",
    "wind": "gale_cordial",
    "earth": "stoneblood_vial",
    "light": "blessed_water",
    "dark": "shadow_essence",
    "magical": "mana_philter",
}


# ── Lookups ────────────────────────────────────────────────────────────────

# Mechanic id -> season id (lets callers pass either spelling).
_MECHANIC_SEASONS = {rec["mechanic"]: season for season, rec in WARDENS.items()}


def get_warden(season_id):
    """Warden record for a season id (or mechanic id); Spring on unknown."""
    season_id = _MECHANIC_SEASONS.get(season_id, season_id)
    return WARDENS.get(season_id, WARDENS["spring"])


def mechanic_tiers(season_id):
    """The 10-entry upgrade ladder for a season."""
    return MECHANIC_TIERS.get(get_warden(season_id)["mechanic"], MECHANIC_TIERS["bloom"])


def mechanic_tier_index(echo):
    """Unlocked effect count for an Echo (1..10)."""
    try:
        echo = int(echo)
    except (TypeError, ValueError):
        echo = 0
    return max(1, min(MAP_BOSS_MECHANIC_TIER_CAP, echo + 1))


def mechanic_effects(season_id, echo):
    """The cumulative list of effect ids unlocked by ``echo``."""
    tiers = mechanic_tiers(season_id)
    return [entry["id"] for entry in tiers[:mechanic_tier_index(echo)]]


def mechanic_labels(season_id, echo):
    """The cumulative list of effect labels unlocked by ``echo``."""
    tiers = mechanic_tiers(season_id)
    return [entry["label"] for entry in tiers[:mechanic_tier_index(echo)]]


def next_mechanic_effect(season_id, echo):
    """The effect the NEXT Echo unlocks, or None once the ladder is done."""
    tiers = mechanic_tiers(season_id)
    index = mechanic_tier_index(echo)      # next tier = index (0-based)
    if index >= len(tiers):
        return None
    return dict(tiers[index])


def mechanic_rank(echo):
    """Numeric scaling rank for the mechanic (1..4; +1 every 3 Echoes)."""
    try:
        echo = max(0, int(echo))
    except (TypeError, ValueError):
        echo = 0
    return min(MAP_BOSS_MECHANIC_RANK_CAP,
               1 + echo // MAP_BOSS_MECHANIC_RANK_STEP)


def mechanic_rank_scale(rank):
    """Multiplier applied to the mechanic's numeric values for a rank."""
    try:
        rank = max(1, int(rank))
    except (TypeError, ValueError):
        rank = 1
    return 1.0 + MAP_BOSS_MECHANIC_RANK_SCALE * (rank - 1)


def stack_cap(season_id):
    """Base stack cap for the season's mechanic."""
    return get_warden(season_id)["stack_cap"]
