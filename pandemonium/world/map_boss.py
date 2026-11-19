"""
map_boss.py — Seasonal Map Boss runtime (docs/map_boss_design.md).

Phase 1 (this module): the ``player["map_boss"]`` state block, the Floor-20
clear gate, one deterministic site per season, per-Echo scaling (levels,
HP, damage, armor, resistances, mechanic tier/rank), the start-at-proven-depth
offer state, reward pre-rolls and the ``[MAP BOSS]`` journal hooks.

Combat (``combat/map_boss.py``), the world-map marker/travel (Phase 2) and the
drop grant/unique milestones (Phase 4) build on these facts:

  * ``state["active"]`` is the single source of truth for the current Echo
    (level, max_hp, hp, resists, mechanic tier/rank, reward preview).
  * A kill snapshots the site, calls :func:`record_victory` **before** the
    arena time commit, then :func:`advance_echo` **after** it — passing the
    killed site so a crossed season boundary cannot spawn two Wardens. A flee
    or death only persists ``active["hp"]`` via :func:`save_boss_hp`.
  * The season (and therefore the Warden) is derived from ``player["day"]``
    — no separate clock, no save version bump.

No GUI imports — safe to import from events, character, combat and tests.
"""

import math
import random

from pandemonium.resources import map_boss_data as data
from pandemonium.resources.cities import CITIES
from pandemonium.resources.world_layout import (
    EVENT_HORIZON_MARKER_H,
    EVENT_HORIZON_MARKER_W,
    MAP_BOSS_MARKER_H,
    MAP_BOSS_MARKER_W,
    NODE_H,
    NODE_W,
    WILD_MARKER_H,
    WILD_MARKER_W,
    city_node_centers,
    map_bounds,
    markers_clear,
)
from pandemonium.core.events import get_season
from pandemonium.core.events import next_season_day
from pandemonium.resources.item_generation import pick_equipment_id
from pandemonium.resources.items import cap_rarity_for_item, soften_rarity
from pandemonium.resources.item_generation import flower_for_element
from pandemonium.core.events import get_daily_bonus_multiplier
from pandemonium.progression.titles import apply_gold_find
from pandemonium.resources.items import build_item
from pandemonium.core.events import ensure_journal

# ── Placement tuning (wild-dungeon site rules) ─────────────────────────────
MIN_CITY_DIST = 90              # px from city node centers (squared compare)
MIN_SITE_DIST = 70              # px from wild markers / the Event Horizon site
POSITION_RING_MIN = 90          # off-road ring around the seed city
POSITION_RING_MAX = 260
POSITION_ATTEMPTS = 300

# The world-map marker is ~120x32 px. Unlike the many wild ruins, the Warden
# is a single once-per-season marker, so its centre is inset to keep the whole
# marker on the canvas (a marker at y=0 is half-clipped and awkward to click).
SITE_INSET_X = 60
SITE_INSET_Y = 20

# Realms that never host a Warden (special-entry cities, not overworld).
_EXCLUDED_SEED_BIOMES = frozenset({"celestial", "pandemonium", "wonderland"})

# Deterministic nudges tried, in order, when a transient marker (a wild ruin)
# currently sits on an authored arena position.
_LOCKED_NUDGES = ((0, 0), (40, 0), (-40, 0), (0, 40), (0, -40),
                  (40, 40), (-40, 40), (40, -40), (-40, -40),
                  (80, 0), (-80, 0), (0, 80), (0, -80))

_SITE_KEYS = ("biome", "seed_city", "nearest_city", "position", "expire_day")


# ── Small safe helpers ─────────────────────────────────────────────────────

def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _day(player):
    return max(1, _int(player.get("day", 1), 1))


def _city_name(city_id):
    return CITIES.get(city_id, {}).get("name", city_id)


# ── State ──────────────────────────────────────────────────────────────────

def _default_state():
    return {
        "unlocked_day": None,      # day the Floor-20 gate was first met
        "season": None,            # "spring" | "summer" | "autumn" | "winter"
        "echo": -1,                # Echo index within the current season (0 = first)
        "active": None,            # current site dict, or None pre-unlock
        "defeated_total": 0,       # lifetime victories (unique milestones)
        "unique_grants": [],       # ["warden_signet", "long_day", ...]
        "best_echo": -1,           # highest Echo ever defeated (start depth)
        "season_defeats": {},      # {"spring": 2, "summer": 1, ...}
        "last_spawn_day": 0,       # idempotency guard
        "last_result": None,       # "victory" | "fled" | "dead"
        "depth_declined_season": None,  # season whose depth offer was declined
    }


def ensure_map_boss_state(player):
    """Initialize/migrate the map boss state block on a player dict.

    Mirrors ``wild_dungeons.ensure_wild_dungeon_state`` — safe for old saves,
    idempotent, and every key is backfilled.
    """
    state = player.get("map_boss")
    if not isinstance(state, dict):
        state = {}
        player["map_boss"] = state
    for key, default in _default_state().items():
        if key not in state:
            state[key] = type(default)() if isinstance(default, (list, dict)) else default
    if not isinstance(state.get("unique_grants"), list):
        state["unique_grants"] = []
    if not isinstance(state.get("season_defeats"), dict):
        state["season_defeats"] = {}
    if state.get("active") is not None and not isinstance(state["active"], dict):
        state["active"] = None
    return state


def gate_met(player):
    """True once Floor 20 has been CLEARED (``max_floor > 20``).

    The same gate the Event Horizon uses — merely *reaching* Floor 20 is not
    enough.
    """
    return _int(player.get("max_floor", 1), 1) > data.MAP_BOSS_UNLOCK_MAX_FLOOR


def current_season(player):
    """``(season_id, season_name)`` for the player's current day."""
    return get_season(player)


def get_active_boss(player):
    """The active Echo dict, or None. Never triggers a spawn."""
    state = ensure_map_boss_state(player)
    active = state.get("active")
    return active if isinstance(active, dict) else None


def echo_label(echo):
    """Display label for an Echo index — ``0``, then ``I``…``X``, then digits."""
    from pandemonium.core.utils import _int_to_roman
    number = max(0, _int(echo, 0))
    if 1 <= number <= 10:
        return _int_to_roman(number)
    return str(number)


def is_current(player, site):
    """True when *site* is still the live Warden (same id, same season).

    The world map uses this before travelling and again on arrival: a season
    can turn mid-journey, which retires the site the player set out for.
    """
    if not isinstance(site, dict):
        return False
    active = get_active_boss(player)
    if active is None or active.get("id") != site.get("id"):
        return False
    return active.get("season") == current_season(player)[0]


def season_days_left(player, site=None):
    """Days until the season (and this Warden) closes. 0 on the last day."""
    site = site if isinstance(site, dict) else get_active_boss(player)
    if not site:
        return 0
    return max(0, next_season_day(_day(player)) - _day(player))


def next_unique_milestone(player):
    """The next unique-trophy milestone, or None once every one is reached.

    Returns ``{"index", "at", "victories"}`` where ``victories`` is how many
    more kills are needed. Milestones already passed by the kill count are
    skipped, so the preview never advertises a trophy that is due now.
    """
    state = ensure_map_boss_state(player)
    kills = _int(state.get("defeated_total"), 0)
    granted = len(state.get("unique_grants") or [])
    milestones = data.MAP_BOSS_UNIQUE_MILESTONES
    for index, need in enumerate(milestones):
        if index < granted:
            continue
        if need > kills:
            return {"index": index, "at": need, "victories": need - kills}
    return None


def build_journey_to_warden(player):
    """Route to the arena: city route + the off-road leg (``to="map_boss"``).

    Returns a ``find_shortest_path``-shaped dict, or None when there is no
    live Warden or no route.
    """
    from pandemonium.world.wild_dungeons import build_journey_to_dungeon
    site = get_active_boss(player)
    if site is None:
        return None
    return build_journey_to_dungeon(player, site, to="map_boss")


def next_echo_preview(player):
    """Facts about the Echo that reforms after a kill (None when unknown).

    The world-map panel shows this before the player commits to the fight.
    """
    site = get_active_boss(player)
    if site is None:
        return None
    echo = max(0, _int(site.get("echo"), 0)) + 1
    season_id = site.get("season") or "spring"
    stats = echo_stats(echo)
    effect = data.next_mechanic_effect(season_id, echo - 1)
    return {
        "echo": echo,
        "level": stats["level"],
        "max_hp": stats["max_hp"],
        "armor": stats["armor"],
        "tier": stats["mechanic_tier"],
        "effect": effect["label"] if effect else None,
    }


# ── Site generation (§5.2) ─────────────────────────────────────────────────

def _city_accessible(player, city_id):
    """Item-locked cities only seed sites once their entry item is carried."""
    item_id = CITIES.get(city_id, {}).get("entry_item")
    if not item_id:
        return True
    return any(item.get("id") == item_id
               for item in player.get("inventory", []))


def _available_seed_cities(player):
    """Overworld cities that may currently seed the Warden's arena."""
    offered = city_node_centers()
    return {
        cid for cid, info in CITIES.items()
        if cid in offered
        and info.get("biome") not in _EXCLUDED_SEED_BIOMES
        and _city_accessible(player, cid)
    }


def _occupied_positions(player):
    """Marker rects the Warden must stay clear of: ``(x, y, w, h)``.

    Rectangles (not bare centre points) so the 116x30 Warden marker cannot
    overlap a 96x30 ruin marker or the 150x30 Event Horizon marker — the old
    70px centre rule still allowed a mostly-horizontal overlap.
    """
    taken = []
    wild = player.get("wild_dungeons")
    if isinstance(wild, dict):
        for site in wild.get("active", []) or []:
            pos = site.get("position") if isinstance(site, dict) else None
            if pos:
                taken.append((pos[0], pos[1],
                              WILD_MARKER_W, WILD_MARKER_H))
    try:
        from pandemonium.world.event_horizon import EVENT_HORIZON_POSITION
        taken.append((EVENT_HORIZON_POSITION[0], EVENT_HORIZON_POSITION[1],
                      EVENT_HORIZON_MARKER_W, EVENT_HORIZON_MARKER_H))
    except Exception:
        pass
    return taken


def _locked_spot_is_clear(x, y, centers, taken):
    """Marker-only clearance for an authored site.

    Authored arenas sit deliberately near their anchor city, so the 90px
    centre rule used by random ring rolls does not apply — the drawn marker
    rectangles are the real requirement. Also keeps the whole Warden marker
    on the canvas.
    """
    x_min, y_min, x_max, y_max = map_bounds()
    x_min += SITE_INSET_X
    x_max -= SITE_INSET_X
    y_min += SITE_INSET_Y
    y_max -= SITE_INSET_Y
    if not (x_min <= x <= x_max and y_min <= y <= y_max):
        return False
    for cx, cy in centers.values():
        if not markers_clear(x, y, MAP_BOSS_MARKER_W, MAP_BOSS_MARKER_H,
                             cx, cy, NODE_W, NODE_H):
            return False
    for tx, ty, tw, th in taken:
        if not markers_clear(x, y, MAP_BOSS_MARKER_W, MAP_BOSS_MARKER_H,
                             tx, ty, tw, th):
            return False
    return True


def _locked_position(player, base):
    """The authored position, nudged when a wild marker occupies it.

    Only transient occupants matter here: wild spawns reserve the Warden's
    site, so a ruin can sit on it only when it spawned before this season's
    site appeared. All nudges stay a short hop from the authored spot.
    """
    centers = city_node_centers()
    taken = _occupied_positions(player)
    x0, y0 = base
    for dx, dy in _LOCKED_NUDGES:
        x, y = x0 + dx, y0 + dy
        if _locked_spot_is_clear(x, y, centers, taken):
            return [x, y]
    return [x0, y0]


def _spot_is_clear(x, y, centers, taken):
    """Random-roll clearance: centre-distance minima + marker rectangles."""
    for cx, cy in centers.values():
        if (x - cx) ** 2 + (y - cy) ** 2 < MIN_CITY_DIST ** 2:
            return False
    for tx, ty, _tw, _th in taken:
        if (x - tx) ** 2 + (y - ty) ** 2 < MIN_SITE_DIST ** 2:
            return False
    return _locked_spot_is_clear(x, y, centers, taken)


def _pick_position(rng, taken, near_city=None):
    """A point on an off-road ring around ``near_city``, clear of markers.

    ``taken`` entries are ``(x, y, width, height)`` marker rectangles. A
    deterministic grid sweep backs the random attempts so a densely packed
    map can never fall back to an overlapping point.
    """
    x_min, y_min, x_max, y_max = map_bounds()
    x_min += SITE_INSET_X
    x_max -= SITE_INSET_X
    y_min += SITE_INSET_Y
    y_max -= SITE_INSET_Y
    centers = city_node_centers()
    for _ in range(POSITION_ATTEMPTS):
        if near_city and near_city in centers:
            cx0, cy0 = centers[near_city]
            radius = rng.randint(POSITION_RING_MIN, POSITION_RING_MAX)
            angle = rng.uniform(0, 2 * math.pi)
            x = int(cx0 + radius * math.cos(angle))
            y = int(cy0 + radius * math.sin(angle))
        else:
            x = rng.randint(x_min, x_max)
            y = rng.randint(y_min, y_max)
        # Reject off-canvas proposals. Clamping used to pile every site whose
        # ring fell off the west/south edge onto the canvas border.
        if not (x_min <= x <= x_max and y_min <= y <= y_max):
            continue
        if _spot_is_clear(x, y, centers, taken):
            return [x, y]
    # Deterministic fallback: sweep a coarse grid for any clear point.
    for gy in range(y_min, y_max + 1, 20):
        for gx in range(x_min, x_max + 1, 20):
            if _spot_is_clear(gx, gy, centers, taken):
                return [gx, gy]
    return [x_min, y_min]


def _season_site(player, season_id, day):
    """The season's arena site — locked to the Warden's authored location.

    Each season has a ``site_city`` / ``site_position`` in
    ``resources/map_boss_data.py`` (docs/map_boss_design.md §5.2), so the
    Warden always surfaces at its most suited location (Winter → Stormhold,
    Spring → Veilholt, …). The seeded ring roll remains as a fallback for
    restricted worlds where the anchor city is inaccessible.

    Every Echo in the season reuses this site (position, biome, gateway).
    Returns None when no overworld city can currently seed a site.
    """
    from pandemonium.core.events import next_season_day, season_start_day
    from pandemonium.world.wild_dungeons import find_nearest_city

    warden = data.get_warden(season_id)

    available = _available_seed_cities(player)
    if not available:
        return None

    anchor = warden.get("site_city")
    locked = warden.get("site_position")
    if anchor in available and locked:
        seed_city = anchor
        position = _locked_position(player, locked)
    else:
        # Fallback: seeded ring roll around a biome-preferred city.
        rng = random.Random(20260101 + season_start_day(day) * 7919)
        preferred = [cid for cid in sorted(available)
                     if CITIES.get(cid, {}).get("biome") in warden["biomes"]]
        pool = preferred or sorted(available)
        seed_city = pool[rng.randrange(len(pool))]
        position = _pick_position(rng, _occupied_positions(player),
                                  near_city=seed_city)

    biome = CITIES.get(seed_city, {}).get("biome", "temperate")
    return {
        "biome": biome,
        "seed_city": seed_city,
        "nearest_city": find_nearest_city(position, allowed=available or None),
        "position": position,
        "expire_day": next_season_day(day),
    }


# ── Echo scaling (§6.1) ────────────────────────────────────────────────────

def echo_stats(echo):
    """Level/HP/damage/armor/resistance/mechanic figures for an Echo.

    ``echo`` is 0-based within the season: level 20 / 40 / 60 / 80 then a
    flat 80 with HP, resistances and the mechanic rank still growing.
    """
    echo = max(0, _int(echo, 0))
    level = min(data.MAP_BOSS_LEVEL_CAP,
                data.MAP_BOSS_LEVEL_START + data.MAP_BOSS_LEVEL_STEP * echo)
    step = level - data.MAP_BOSS_LEVEL_START

    hp_mult = ((1 + data.MAP_BOSS_HP_PER_LEVEL * step)
               * (1 + data.MAP_BOSS_HP_PER_ECHO * echo
                  + data.MAP_BOSS_HP_ECHO_QUADRATIC * echo * echo))
    damage_mult = ((1 + data.MAP_BOSS_DAMAGE_PER_LEVEL * step)
                   * (1 + data.MAP_BOSS_DAMAGE_PER_ECHO * echo))

    armor = min(data.MAP_BOSS_ARMOR_CAP,
                data.MAP_BOSS_BASE_ARMOR
                + int(data.MAP_BOSS_ARMOR_PER_ECHO * echo
                      + data.MAP_BOSS_ARMOR_PER_LEVEL * step))
    all_res = min(data.MAP_BOSS_RES_CAP,
                  data.MAP_BOSS_RES_PER_ECHO * echo
                  + data.MAP_BOSS_RES_PER_LEVEL * step + 1.0)
    season_res = min(data.MAP_BOSS_SEASON_RES_CAP,
                     data.MAP_BOSS_SEASON_RES_BASE
                     + data.MAP_BOSS_SEASON_RES_PER_ECHO * echo
                     + data.MAP_BOSS_SEASON_RES_PER_LEVEL * step)
    status_res = min(data.MAP_BOSS_STATUS_RES_CAP,
                     data.MAP_BOSS_BASE_STATUS_RES
                     + data.MAP_BOSS_STATUS_RES_PER_ECHO * echo
                     + data.MAP_BOSS_STATUS_RES_PER_LEVEL * step)

    return {
        "level": level,
        "step": step,
        "max_hp": int(round(data.MAP_BOSS_BASE_HP * hp_mult)),
        "hp_mult": hp_mult,
        "damage_mult": damage_mult,
        "str": int(round(data.MAP_BOSS_BASE_STR * damage_mult)),
        "armor": armor,
        "all_res": all_res,
        "season_res": season_res,
        "status_res": status_res,
        "weakness_res": data.MAP_BOSS_WEAKNESS,
        "mechanic_tier": data.mechanic_tier_index(echo),
        "mechanic_rank": data.mechanic_rank(echo),
    }


def elemental_profile(season_id, echo):
    """Per-element resistance profile for the Echo (§6.4).

    The seasonal element uses ``season_res``, the seasonal weakness stays at
    the fixed 0.70, and every other element uses ``all_res``.
    """
    from pandemonium.combat.elemental import ELEMENTS

    warden = data.get_warden(season_id)
    stats = echo_stats(echo)
    profile = {}
    for element in ELEMENTS:
        if element == warden["element"]:
            profile[element] = round(stats["season_res"], 4)
        elif element == warden["weakness"]:
            profile[element] = data.MAP_BOSS_WEAKNESS
        else:
            profile[element] = round(stats["all_res"], 4)
    return profile


# ── Reward pre-roll (§8.1 / §8.3) ──────────────────────────────────────────

def cache_rarity(echo, rng=None):
    """Cache rarity: Rare+ with a ramping epic chance, legendary from Echo 10."""
    rng = rng or random
    echo = max(0, _int(echo, 0))
    if echo >= data.MAP_BOSS_LEGENDARY_FROM_ECHO:
        return ("legendary"
                if rng.random() < data.MAP_BOSS_LEGENDARY_CHANCE
                else "epic")
    epic_chance = min(data.MAP_BOSS_EPIC_CHANCE_CAP,
                      data.MAP_BOSS_EPIC_CHANCE_BASE
                      + data.MAP_BOSS_EPIC_CHANCE_PER_ECHO * echo)
    return "epic" if rng.random() < epic_chance else "rare"


def roll_cache(echo, biome=None, rng=None):
    """Pre-roll the Warden's Cache: an equipment id + its final rarity.

    Item stats stay unrolled until acquisition (``build_item``), matching the
    wild-dungeon preview convention.
    """

    rng = rng or random
    level = max(1, min(data.MAP_BOSS_CACHE_GEAR_CAP, echo_stats(echo)["level"]))
    item_id = pick_equipment_id(level, biome, rng=rng)
    rarity = cache_rarity(echo, rng=rng)
    rarity = cap_rarity_for_item(item_id, rarity)
    rarity = soften_rarity(item_id, rarity, rng=rng)
    return {"item_id": item_id, "rarity": rarity}


def roll_consumables(echo, element, rng=None):
    """Pre-roll the kill's consumables — element-themed when possible."""
    from pandemonium.world.dungeon import _CONSUMABLE_TIERS

    rng = rng or random
    tier = 3 if _int(echo, 0) < 2 else 4
    pool = list(_CONSUMABLE_TIERS.get(tier) or [])
    if not pool:
        return []
    themed = data.ELEMENT_CONSUMABLE.get(element)
    picks = []
    for index in range(data.MAP_BOSS_CONSUMABLES_PER_KILL):
        if index == 0 and themed in pool:
            picks.append(themed)
            continue
        choices = [iid for iid in pool if iid not in picks] or pool
        picks.append(rng.choice(choices))
    return picks


def roll_flower(element):
    """The guaranteed flower — always the Warden's own element."""
    return flower_for_element(element)


def roll_rewards(echo, season_id, biome=None, rng=None):
    """Pre-roll everything the panel previews at spawn (§8.1)."""
    warden = data.get_warden(season_id)
    return {
        "cache": roll_cache(echo, biome, rng=rng),
        "consumables": roll_consumables(echo, warden["element"], rng=rng),
        "flower": roll_flower(warden["element"]),
    }


def gold_xp_reward(echo, player=None, night=False):
    """Gold/XP for one kill — daily bonus plus the Night-kill gold bonus."""
    stats = echo_stats(echo)
    echo = max(0, _int(echo, 0))
    step = stats["level"] - data.MAP_BOSS_LEVEL_START
    gold = (data.MAP_BOSS_GOLD_BASE
            + data.MAP_BOSS_GOLD_PER_LEVEL * step
            + data.MAP_BOSS_GOLD_PER_ECHO * echo)
    exp = (data.MAP_BOSS_XP_BASE
           + data.MAP_BOSS_XP_PER_LEVEL * step
           + data.MAP_BOSS_XP_PER_ECHO * echo)
    if player is not None:
        gold = int(gold * get_daily_bonus_multiplier(player, "gold_bonus"))
        exp = int(exp * get_daily_bonus_multiplier(player, "exp_bonus"))
    if night:
        gold = int(gold * (1 + data.MAP_BOSS_NIGHT_GOLD_BONUS))
    return {"gold": int(gold), "exp": int(exp)}


# ── Victory rewards (§8.2 – §8.6) ─────────────────────────────────────────

def grant_victory_rewards(player, snapshot, night=None):
    """Hand out one kill's spoils (§8.2 – §8.6). Returns a GUI summary.

    Called by :func:`pandemonium.world.dungeon._map_boss_arena_exit` right
    after :func:`record_victory` and the single arena time commit, with the
    ``snapshot`` of the Warden that actually died (its dict survives the Echo
    advance, so every fact — Echo, level, element, pre-rolled drops — is the
    killed one, not the reformed one).

    Nothing here touches ``defeated_superbosses``, ``superboss_pool``,
    awakening shards, title progress, the Pandemonium ×2.5 multiplier or
    bounty progress — the Warden is not a superboss (§8.6).

    Items are added straight to the bag rather than through
    ``prompt_acquire_item``: the victory/reform window already itemises the
    haul, and four nested pickup prompts would bury it.
    """
    from pandemonium.inventory.core import add_item_to_inventory
    from pandemonium.progression.leveling import gain_exp, gain_exp_ally

    snapshot = snapshot if isinstance(snapshot, dict) else {}
    state = ensure_map_boss_state(player)
    echo = max(0, _int(snapshot.get("echo"), _int(state.get("echo"), 0)))
    level = max(data.MAP_BOSS_LEVEL_START, _int(snapshot.get("level"), 20))
    biome = snapshot.get("biome")
    night = bool(night)

    # ── Gold + XP ───────────────────────────────────────────────────────
    money = gold_xp_reward(echo, player=player, night=night)
    gold = apply_gold_find(player, money["gold"])
    exp = money["exp"]
    player["gold"] = _int(player.get("gold"), 0) + gold
    gain_exp(player, exp)
    for ally in player.get("allies", []):
        if _int(ally.get("current_hp"), 0) > 0:
            gain_exp_ally(ally, exp)

    obtained = []
    left_behind = []

    def _grant_cache(cache):
        item_id = (cache or {}).get("item_id")
        rarity = (cache or {}).get("rarity", "rare")
        if not item_id:
            return None
        item = build_item(item_id, rarity)
        if not item:
            return None
        if not add_item_to_inventory(player, item):
            left_behind.append(item.get("name", item_id))
            return None
        entry = {"name": item.get("name", item_id), "rarity": rarity,
                 "kind": "cache"}
        obtained.append(entry)
        return entry

    # ── Warden's Cache ─────────────────────────────────────────────────
    base_cache = snapshot.get("cache_preview") or roll_cache(echo, biome)
    cache_entry = _grant_cache(base_cache)

    # ── Consumables ────────────────────────────────────────────────────
    consumables = []
    for item_id in (snapshot.get("consumables") or []):
        item = build_item(item_id, "common")
        if not item or not add_item_to_inventory(player, item):
            continue
        entry = {"name": item.get("name", item_id), "rarity": "common",
                 "kind": "consumable"}
        obtained.append(entry)
        consumables.append(entry)

    # ── Flowers (the Night kill yields a second) ───────────────────────
    flower_ids = []
    if snapshot.get("flower"):
        flower_ids.append(snapshot["flower"])
        if night:
            flower_ids.append(snapshot["flower"])
    flowers = []
    for flower_id in flower_ids:
        item = build_item(flower_id, "common")
        if not item or not add_item_to_inventory(player, item):
            continue
        entry = {"name": item.get("name", flower_id), "rarity": "common",
                 "kind": "flower"}
        obtained.append(entry)
        flowers.append(entry)

    # ── Unique trophy ladder (§8.4) ────────────────────────────────────
    kills = _int(state.get("defeated_total"), 0)
    grants = list(state.get("unique_grants") or [])
    milestones = data.MAP_BOSS_UNIQUE_MILESTONES
    uniques = []
    extra_caches = 0
    for index, need in enumerate(milestones):
        if kills < need or index < len(grants):
            continue
        item_id = data.MAP_BOSS_UNIQUE_ITEMS[index]
        if item_id in grants:
            extra_caches += 1
            continue
        grants.append(item_id)
        item = build_item(item_id, "unique")
        if item:
            # A trophy is never lost to a full bag — force it in.
            if not add_item_to_inventory(player, item):
                player.setdefault("inventory", []).append(item)
            entry = {"name": item.get("name", item_id), "rarity": "unique",
                     "kind": "unique", "id": item_id}
            obtained.append(entry)
            uniques.append(entry)
    if len(grants) >= len(milestones) and not uniques:
        # Every trophy is owned — the unique slot pays out as a second cache.
        extra_caches += 1
    state["unique_grants"] = grants
    for _ in range(extra_caches):
        _grant_cache(roll_cache(echo, biome))

    # ── Journal ────────────────────────────────────────────────────────
    season_id = snapshot.get("season") or current_season(player)[0]
    season_name = snapshot.get("season_name") or data.get_warden(season_id)["season_name"]
    warden_name = (snapshot.get("warden_name")
                   or data.get_warden(season_id)["warden_name"])
    bonus = ""
    if uniques:
        bonus = " Trophy: " + ", ".join(u["name"] for u in uniques) + "."
    _journal(
        player, f"Warden Felled \u2014 {season_name} Echo {echo}",
        f"{warden_name} broken at Echo {echo} (Lv {level}). "
        f"+{gold} gold, +{exp} XP per hero.{bonus}",
    )

    return {
        "warden_name": warden_name,
        "season": season_id,
        "season_name": snapshot.get("season_name"),
        "echo": echo,
        "level": level,
        "night": night,
        "gold": gold,
        "exp": exp,
        "obtained": obtained,
        "cache": cache_entry,
        "consumables": consumables,
        "flowers": flowers,
        "uniques": uniques,
        "extra_caches": extra_caches,
        "left_behind": left_behind,
        "victories": kills,
        "unique_grants": list(grants),
    }


# ── Spawn / season lifecycle (§5.1, §5.3, §5.4) ───────────────────────────

def _build_active(player, season_id, echo, day, site):
    """Assemble the active Echo dict from a season site + Echo index."""
    warden = data.get_warden(season_id)
    stats = echo_stats(echo)
    rewards = roll_rewards(echo, season_id, biome=site.get("biome"))
    return {
        "id": f"warden_{season_id}_{echo}",
        "season": season_id,
        "season_name": warden["season_name"],
        "warden_name": warden["warden_name"],
        "glyph": warden["glyph"],
        "mechanic": warden["mechanic"],
        "mechanic_name": warden["mechanic_name"],
        "stack_tag": warden["stack_tag"],
        "signature_status": warden["signature_status"],
        "add_name": warden["add_name"],
        "echo": echo,
        "level": stats["level"],
        "biome": site.get("biome"),
        "element": warden["element"],
        "weakness": warden["weakness"],
        "seed_city": site.get("seed_city"),
        "nearest_city": site.get("nearest_city"),
        "position": list(site.get("position") or (0, 0)),
        "spawn_day": day,
        "expire_day": site.get("expire_day"),
        "max_hp": stats["max_hp"],
        "hp": stats["max_hp"],
        "str": stats["str"],
        "armor": stats["armor"],
        "elemental_res": elemental_profile(season_id, echo),
        "status_res": round(stats["status_res"], 4),
        "mechanic_tier": stats["mechanic_tier"],
        "mechanic_rank": stats["mechanic_rank"],
        "mechanic_effects": data.mechanic_effects(season_id, echo),
        "mechanic_labels": data.mechanic_labels(season_id, echo),
        "attempts": 0,
        "last_fought_day": None,
        "defeated": False,
        # Pre-rolled at spawn so the world-map panel can preview the loot.
        "cache_preview": rewards["cache"],
        "consumables": rewards["consumables"],
        "flower": rewards["flower"],
    }


def _site_from_active(active):
    """Extract the reusable geographic keys from an active dict."""
    if not isinstance(active, dict):
        return None
    site = {key: active.get(key) for key in _SITE_KEYS}
    if not site["position"] or not site["biome"]:
        return None
    return site


def _repair_site(player, state):
    """Move a stored site that does not match the authored arena layout.

    Saves that predate the locked anchors (or a site whose authored spot is
    currently occupied by a wild ruin) are re-rolled to the season's authored
    location. Only the geography moves: the season's Echo, HP and pre-rolled
    spoils are kept. Idempotent — an authored site left in place.
    """
    active = state.get("active")
    if not isinstance(active, dict):
        return
    season_id = state.get("season")
    if not season_id:
        return
    warden = data.get_warden(season_id)
    locked = warden.get("site_position")
    pos = active.get("position")
    centers = city_node_centers()
    if locked:
        if (pos and list(pos) == list(locked)
                and _locked_spot_is_clear(pos[0], pos[1], centers,
                                          _occupied_positions(player))):
            return
    elif pos and _locked_spot_is_clear(
            pos[0], pos[1], centers, _occupied_positions(player)):
        return
    fresh = _season_site(player, season_id, _day(player))
    if fresh is None:
        return
    for key in _SITE_KEYS:
        if key in fresh:
            active[key] = fresh[key]


def maybe_spawn(player):
    """Ensure the current season's Warden exists. Idempotent.

    Returns the active site dict when a Warden was (re)spawned this call,
    otherwise None. Hooked from ``events.process_day_rollover`` and from the
    world map when it opens.
    """
    state = ensure_map_boss_state(player)
    if not gate_met(player):
        return None

    day = _day(player)
    season_id, _season_name = current_season(player)
    active = state.get("active")
    if isinstance(active, dict) and state.get("season") == season_id:
        # Same-season sites persist across Echoes, but repair one saved
        # before (or since overlapped by) marker-rectangle placement.
        _repair_site(player, state)
        return None

    first_unlock = state.get("unlocked_day") is None
    old_season = state.get("season")
    site = _season_site(player, season_id, day)
    if site is None:
        return None

    if first_unlock:
        state["unlocked_day"] = day

    new_active = _build_active(player, season_id, echo=0, day=day, site=site)
    state["season"] = season_id
    state["echo"] = 0
    state["active"] = new_active
    state["last_spawn_day"] = day
    state["depth_declined_season"] = None

    warden = data.get_warden(season_id)
    city = _city_name(site["nearest_city"])
    if first_unlock:
        _journal(
            player, "A Warden Notices",
            f"Floor {data.MAP_BOSS_UNLOCK_MAX_FLOOR} is cleared. The "
            f"{warden['season_name']} Warden stirs near {city}.",
        )
    if old_season and old_season != season_id:
        _journal(
            player, "The Season Closes",
            f"The {data.get_warden(old_season)['warden_name']} steps out of the "
            f"calendar. The {warden['warden_name']} takes its place near {city}.",
        )
    _journal(
        player, "The Season Turns",
        f"The {warden['warden_name']} has surfaced near {city}. Echo 0 "
        f"(Lv {new_active['level']}). The season ends on Day "
        f"{new_active['expire_day']}.",
    )
    return new_active


def sync_season(player):
    """Alias for :func:`maybe_spawn` — old-save / map-open consistency pass."""
    return maybe_spawn(player)


# ── Echo advancement (§7.7 helper) ─────────────────────────────────────────

def record_victory(player):
    """Book a kill: counters, best Echo, season defeats. Returns the Echo."""
    state = ensure_map_boss_state(player)
    active = state.get("active")
    if not isinstance(active, dict):
        return None
    echo = max(0, _int(active.get("echo"), 0))
    state["defeated_total"] = _int(state.get("defeated_total"), 0) + 1
    state["best_echo"] = max(_int(state.get("best_echo"), -1), echo)
    season = active.get("season") or state.get("season")
    defeats = state.setdefault("season_defeats", {})
    defeats[season] = _int(defeats.get(season), 0) + 1
    state["last_result"] = "victory"
    active["hp"] = 0
    active["defeated"] = True
    return echo


def advance_echo(player, killed=None):
    """Create the next Echo of the current season at the same site.

    Called by the victory handler *after* :func:`record_victory` and after the
    arena time commit. Pass the site that was actually killed (its dict or its
    id): if the Warden on the map is no longer that site — because the time
    commit already rolled the season over — no next Echo is created. That
    guard is what keeps one season boundary from spawning two Wardens.
    """
    state = ensure_map_boss_state(player)
    active = state.get("active")
    season_id, _season_name = current_season(player)
    if killed is not None:
        killed_id = killed.get("id") if isinstance(killed, dict) else killed
        if not isinstance(active, dict) or active.get("id") != killed_id:
            return None
    if not isinstance(active, dict) or active.get("season") != season_id:
        return maybe_spawn(player)

    echo = max(0, _int(active.get("echo"), 0)) + 1
    day = _day(player)
    site = _site_from_active(active) or _season_site(player, season_id, day)
    if site is None:
        return None

    new_active = _build_active(player, season_id, echo=echo, day=day, site=site)
    state["season"] = season_id
    state["echo"] = echo
    state["active"] = new_active
    new_effect = data.next_mechanic_effect(season_id, echo - 1)
    effect_text = f" New mechanic: {new_effect['label']}." if new_effect else ""
    _journal(
        player, "The Warden Reforms",
        f"{new_active['warden_name']} returns as Echo {echo} "
        f"(Lv {new_active['level']}) at the same site.{effect_text}",
    )
    return new_active


def set_result(player, result):
    """Record the last arena outcome: ``"victory"``/``"fled"``/``"dead"``."""
    state = ensure_map_boss_state(player)
    state["last_result"] = result
    return state["last_result"]


def save_boss_hp(player, hp):
    """Persist the current Echo's HP after a flee or a death."""
    state = ensure_map_boss_state(player)
    active = state.get("active")
    if not isinstance(active, dict):
        return None
    max_hp = max(1, _int(active.get("max_hp"), 1))
    active["hp"] = max(0, min(max_hp, _int(hp, max_hp)))
    active["attempts"] = _int(active.get("attempts"), 0) + 1
    active["last_fought_day"] = _day(player)
    return active["hp"]


# ── Start at proven depth (§5.7) ───────────────────────────────────────────

def start_depth_offer(player):
    """The Echo the arena may recall, or None when no offer applies."""
    state = ensure_map_boss_state(player)
    active = state.get("active")
    if not isinstance(active, dict):
        return None
    current_echo = _int(active.get("echo"), 0)
    if state.get("depth_declined_season") == state.get("season"):
        return None
    best = _int(state.get("best_echo"), -1)
    cap = data.MAP_BOSS_START_DEPTH_CAP
    if cap is not None:
        best = min(best, _int(cap, best))
    return best if best > current_echo else None


def apply_start_depth(player, echo=None):
    """Jump the season's ladder to a proven depth (one way, full HP).

    Discards any partial HP on the season's current Echo — the dialog says so
    before confirming.
    """
    state = ensure_map_boss_state(player)
    active = state.get("active")
    if not isinstance(active, dict):
        return None
    current_echo = max(0, _int(active.get("echo"), 0))
    target = start_depth_offer(player) if echo is None else max(0, _int(echo, 0))
    # One-way per season: the ladder only ever jumps upward, so a cleared
    # Echo can never be re-entered (no repeatable fight, no free heal).
    if target is None or target <= current_echo:
        return None

    season_id = active.get("season") or state.get("season")
    day = _day(player)
    site = _site_from_active(active) or _season_site(player, season_id, day)
    if site is None:
        return None

    new_active = _build_active(player, season_id, echo=target, day=day, site=site)
    state["echo"] = target
    state["active"] = new_active
    _journal(
        player, "Depth Recalled",
        f"{new_active['warden_name']} answers at Echo {target} "
        f"(Lv {new_active['level']}) — the height your party last broke.",
    )
    return new_active


def decline_start_depth(player):
    """Remember that the season's depth offer was declined (no re-offering)."""
    state = ensure_map_boss_state(player)
    state["depth_declined_season"] = state.get("season")
    return state["depth_declined_season"]


# ── Journal ────────────────────────────────────────────────────────────────

def _journal(player, name, desc):
    """Append a ``[MAP BOSS]`` entry to the Journal's Event tab (deduped)."""
    ensure_journal(player)
    day = _day(player)
    entries = player["journal"]["events"]
    for existing in entries:
        if existing.get("day") == day and existing.get("name") == name:
            return
    entries.append({
        "day": day,
        "name": name,
        "desc": desc,
        "tag": "[MAP BOSS]",
        "fixed": False,
    })
