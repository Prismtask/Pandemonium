"""Procedural Dungeon Graph (PDG) — demo implementation.

Implements docs/dungeon_graph_design.md for the temperate wild-ruin demo:

* 8x8 node layout with orthogonal corridor edges (long straight corridors are
  allowed for the rare boss-connection fallback).
* Randomized DFS carving biased toward the boss, loop edges, branch fill.
* Room-type assignment reuses the existing ``ROOM_TYPE_WEIGHTS`` and the
  10% + 5% non-combat escalation; connector passages are added outside the
  roll so a graph route is not a wall of combats.
* Movement costs 0.5 block per edge + 0.5 block per newly resolved node,
  accumulated in ``graph["credit"]`` so half blocks survive a save.
* Node types are hidden until a node is entered or left; layout and edges are
  visible from the start.
* Floor rewards and the floor-clear heal scale with the cleared ratio
  (boss rush pays less than a full clear).
* Save-exit preserves the active graph; flee, death, and floor clear wipe it.

The GUI uses the existing DungeonScreen Map panel (section 10.1 is not
implemented here). City floors and Event Horizon keep their current paths;
only wild ruins in the temperate biome use this module for now.
"""

import copy
import random
from collections import Counter, deque

import pandemonium.progression.karma as karma
import pandemonium.world.dungeon_rooms as dungeon_rooms
from pandemonium.combat.boss_styles import is_solo_boss
from pandemonium.combat.combat_engine import combat
from pandemonium.core.character import player_max_hp
from pandemonium.core.utils import _term, _tmenu, _tpause, _tprint, advance_time
from pandemonium.progression.leveling import gain_exp, gain_exp_ally
from pandemonium.resources.dungeon_graph_profiles import get_profile
from pandemonium.resources.enemies import ENEMIES

GRAPH_VERSION = 1
GRID = 8

# Demo gate: only wild ruins in these biomes run PDG. Add entries as more
# profiles are implemented.
PDG_DEMO_ENABLED = True
PDG_WILD_PROFILES = {"temperate": "temperate"}

_DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))

_NODE_GLYPHS = {
    "entry": "S",
    "combat": "C",
    "boss": "B",
    "fountain": "F",
    "merchant": "M",
    "treasure": "$",
    "trap": "T",
    "stat_check": "N",
    "connector": "·",
    "unknown": "?",
}

_NODE_LABELS = {
    "entry": "Entry",
    "combat": "Combat",
    "boss": "Boss",
    "fountain": "Fountain",
    "merchant": "Merchant",
    "treasure": "Treasure",
    "trap": "Trap",
    "stat_check": "Event",
    "connector": "Passage",
    "unknown": "Unknown",
}

_NODE_HEADERS = {
    "combat": "--- Combat Chamber ---",
    "fountain": "✨  Fountain Chamber",
    "merchant": "🏺  Merchant's Corner",
    "stat_check": "📜  Mysterious Scene",
    "treasure": "💎  Treasure Vault",
    "trap": "⚠️   Suspicious Passage",
    "connector": "·   Quiet Passage",
    "boss": "*** BOSS CHAMBER ***",
}

_CONNECTOR_SCENES = (
    ("A collapsed corridor, empty but quiet.",
     "You catch your breath in the still air.", None),
    ("An old supply cache, picked clean long ago.",
     "A few coins still glint in the dust.", "gold"),
    ("A mossy alcove with a trickle of clean water.",
     "The water is cold and clean.", "heal"),
    ("Faded carvings line the passage.",
     "Old road signs point deeper into the ruin.", None),
)


class GraphError(RuntimeError):
    """Raised when the generator cannot satisfy every invariant."""


# ═══════════════════════════════════════════════════════════════════
# Public entry points
# ═══════════════════════════════════════════════════════════════════

def pdg_profile_for_wild(region):
    """Return the graph profile id for a wild biome, or None.

    The PDG integration is intentionally demo-scoped: only the temperate
    wild ruin runs the graph loop.
    """
    if not PDG_DEMO_ENABLED:
        return None
    return PDG_WILD_PROFILES.get(region)


def generate_graph(floor, profile_id="temperate", region="temperate",
                   player=None, wild=True, seed=None, floor_index=None,
                   generate_content=True):
    """Generate one floor graph satisfying docs §3.4.

    ``floor`` is the content/scaling floor (the ruin's level for wild runs);
    ``floor_index`` is the display floor index used for the spine budget and
    defaults to ``floor``.
    """
    profile = get_profile(profile_id, wild=wild)
    rng = random.Random(seed) if seed is not None else random
    spine_floor = floor_index if floor_index is not None else floor
    spine = _spine_for(spine_floor, profile)
    n_target = _node_budget(spine, profile)

    for _attempt in range(16):
        entry, boss = _pick_entry_boss(profile, spine, rng)
        carved, edges, boss_reached = _carve_graph(
            entry, boss, n_target, profile, rng)
        if not boss_reached:
            _connect_boss(carved, edges, boss, int(profile["node_cap"]))
        if boss not in carved:
            continue
        _grow_branches(carved, edges, boss, n_target, rng)
        _add_loops(carved, edges, boss, profile, rng)

        graph = _build_topology_graph(
            carved, edges, entry, boss, floor, region, profile, spine, n_target)
        if not validate_graph(graph, require_types=False):
            continue

        _assign_types(graph, floor, region, profile, rng, player,
                      generate_content=generate_content)
        if validate_graph(graph):
            return graph

    raise GraphError(
        f"failed to generate a valid {profile_id} graph for floor {floor}")


def normalize_graph(graph):
    """Normalize a graph loaded from JSON (string ids, tuple edges).

    Mutates nothing in place: returns a JSON-round-tripped copy with the
    runtime representations the traversal loop expects.
    """
    out = copy.deepcopy(graph)
    nodes = out.get("nodes") or {}
    out["nodes"] = {str(nid): node for nid, node in nodes.items()}
    out["edges"] = [tuple(edge) for edge in (out.get("edges") or [])
                    if isinstance(edge, (list, tuple)) and len(edge) == 2]
    for key in ("visited", "revealed", "cleared"):
        out[key] = [str(nid) for nid in (out.get(key) or [])]
    for key in ("entry", "boss", "current"):
        if out.get(key) is not None:
            out[key] = str(out[key])
    out["credit"] = float(out.get("credit", 0.0) or 0.0)
    out.setdefault("profile", "temperate")
    out.setdefault("region", "temperate")
    out.setdefault("wild", True)
    out.setdefault("spine", 0)
    out.setdefault("node_min", 0)
    out.setdefault("node_cap", 24)
    out.setdefault("boss_defeated", False)
    for node in out["nodes"].values():
        node.setdefault("type", "unknown")
        node.setdefault("cleared", False)
        cell = node.get("cell") or [0, 0]
        node["cell"] = [int(cell[0]), int(cell[1])]
    if not out.get("entry") and out["nodes"]:
        out["entry"] = next(iter(out["nodes"]))
    if not out.get("current"):
        out["current"] = out.get("entry")
    return out


def validate_graph(graph, require_types=True):
    """Return True when the graph satisfies the generation invariants.

    ``require_types=False`` validates topology only (used before node types
    are assigned); the public/default check also requires exactly one entry
    and boss plus at least one fountain and merchant.
    """
    try:
        nodes = graph["nodes"]
        entry = graph["entry"]
        boss = graph["boss"]
        if entry not in nodes or boss not in nodes or entry == boss:
            return False
        if len(nodes) < int(graph.get("node_min", 1) or 1):
            return False
        if len(nodes) > int(graph.get("node_cap", 24) or 24):
            return False

        seen_cells = set()
        for node in nodes.values():
            cell = node.get("cell")
            if not cell or len(cell) != 2:
                return False
            c, r = int(cell[0]), int(cell[1])
            if not (0 <= c < GRID and 0 <= r < GRID):
                return False
            if (c, r) in seen_cells:
                return False
            seen_cells.add((c, r))

        adjacency = {nid: [] for nid in nodes}
        degree = {nid: 0 for nid in nodes}
        seen_edges = set()
        for edge in graph.get("edges") or []:
            if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                return False
            a, b = str(edge[0]), str(edge[1])
            if a not in nodes or b not in nodes or a == b:
                return False
            key = _edge(a, b)
            if key in seen_edges:
                return False
            seen_edges.add(key)
            ca = nodes[a]["cell"]
            cb = nodes[b]["cell"]
            if ca[0] != cb[0] and ca[1] != cb[1]:
                return False  # diagonal edges are not supported
            adjacency[a].append(b)
            adjacency[b].append(a)
            degree[a] += 1
            degree[b] += 1

        if any(value > 4 for value in degree.values()):
            return False
        if degree.get(boss, 0) != 1:
            return False

        from_entry = _bfs_from(adjacency, entry)
        if len(from_entry) != len(nodes):
            return False
        if boss not in from_entry:
            return False
        if from_entry[boss] < int(graph.get("spine", 0) or 0):
            return False
        from_boss = _bfs_from(adjacency, boss)
        if len(from_boss) != len(nodes):
            return False

        if not require_types:
            return True

        types = Counter(node.get("type", "unknown") for node in nodes.values())
        if types.get("entry") != 1 or types.get("boss") != 1:
            return False
        if types.get("fountain", 0) < 1 or types.get("merchant", 0) < 1:
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def move_cost(graph, node_id):
    """Block cost to move onto *node_id* from the current node.

    A newly resolved node costs edge + node (1.0 block by default); a cleared
    node or the entry only costs the edge (0.5). Revisiting a revealed but
    uncleared room costs the full amount.
    """
    profile = get_profile(graph.get("profile", "temperate"),
                          wild=bool(graph.get("wild", True)))
    edge_cost = float(profile.get("edge_cost", 0.5))
    node_cost = float(profile.get("node_cost", 0.5))
    node_id = str(node_id)
    if node_id == graph.get("entry") or node_id in (graph.get("cleared") or []):
        return edge_cost
    return edge_cost + node_cost


def cleared_ratio(graph):
    """Cleared middle nodes / all middle nodes (entry and boss excluded)."""
    nodes = graph.get("nodes") or {}
    included = [nid for nid in nodes
                if nid not in (graph.get("entry"), graph.get("boss"))]
    if not included:
        return 0.0
    cleared = sum(1 for nid in included if nid in (graph.get("cleared") or []))
    return min(1.0, cleared / len(included))


def reward_multiplier(graph):
    """Return ``(multiplier, cleared_ratio)`` — 0.5 rush, 1.0 full clear."""
    ratio = cleared_ratio(graph)
    return 0.5 + 0.5 * ratio, ratio


def adjacent_nodes(graph, node_id):
    """Return the node ids directly connected to *node_id*."""
    node_id = str(node_id)
    result = []
    for edge in graph.get("edges") or []:
        a, b = str(edge[0]), str(edge[1])
        if a == node_id:
            result.append(b)
        elif b == node_id:
            result.append(a)
    return result


def bfs_distance(graph, start, target):
    """BFS edge distance from *start* to *target*, or None when unreachable."""
    if start is None or target is None:
        return None
    adjacency = {}
    for nid in (graph.get("nodes") or {}):
        adjacency[nid] = []
    for edge in graph.get("edges") or []:
        a, b = str(edge[0]), str(edge[1])
        if a in adjacency and b in adjacency:
            adjacency[a].append(b)
            adjacency[b].append(a)
    distances = _bfs_from(adjacency, str(start))
    return distances.get(str(target))


def summarize_graph(graph):
    """Small metrics block for diagnostics and the demo script."""
    nodes = graph.get("nodes") or {}
    types = Counter(node.get("type", "unknown") for node in nodes.values())
    distance = bfs_distance(graph, graph.get("entry"), graph.get("boss"))
    return {
        "nodes": len(nodes),
        "edges": len(graph.get("edges") or []),
        "spine": int(graph.get("spine", 0) or 0),
        "shortest_edges": distance,
        "route_blocks": float(distance) if distance is not None else None,
        "full_clear_blocks": float(max(0, len(nodes) - 1)),
        "types": dict(types),
    }


# ═══════════════════════════════════════════════════════════════════
# Step 1 — topology
# ═══════════════════════════════════════════════════════════════════

def _spine_for(floor_index, profile):
    try:
        floor_index = int(floor_index)
    except (TypeError, ValueError):
        floor_index = 1
    if profile.get("wild"):
        base = 5 + max(0, floor_index - 1) // 2
    else:
        base = 8 + max(0, floor_index) // 20
    return max(int(profile["spine_min"]),
               min(int(profile["spine_max"]), base))


def _node_budget(spine, profile):
    branch = float(profile.get("branch_factor", 0.7))
    target = 1 + spine + int(round(spine * branch))
    # Reserve a few slots for the boss-connection path so a wandering DFS
    # can still reach a far boss without a long bypass edge.
    ceiling = max(int(profile["node_min"]),
                  int(profile["node_cap"]) - 4)
    return max(int(profile["node_min"]), min(ceiling, target))


def _pick_entry_boss(profile, spine, rng):
    side = profile.get("entry_side", "left")
    if side == "left":
        for _ in range(200):
            entry_y = rng.randint(1, GRID - 2)
            boss_y = rng.randint(1, GRID - 2)
            if (GRID - 1) + abs(boss_y - entry_y) >= spine:
                return (0, entry_y), (GRID - 1, boss_y)
        return (0, 1), (GRID - 1, GRID - 2)

    perimeter = []
    for c in range(GRID):
        perimeter.append((c, 0))
        perimeter.append((c, GRID - 1))
    for r in range(1, GRID - 1):
        perimeter.append((0, r))
        perimeter.append((GRID - 1, r))
    for _ in range(400):
        entry = rng.choice(perimeter)
        boss = rng.choice(perimeter)
        if entry != boss and _manhattan(entry, boss) >= spine:
            return entry, boss
    return (0, 1), (GRID - 1, GRID - 2)


def _choose_next(candidates, boss, toward_boss, rng):
    if rng.random() < toward_boss:
        distances = [_manhattan(cell, boss) for cell in candidates]
        best = min(distances)
        closest = [cell for cell, dist in zip(candidates, distances)
                   if dist == best]
        return rng.choice(closest)
    return rng.choice(candidates)


def _carve_graph(entry, boss, n_target, profile, rng):
    """Randomized DFS carve biased toward the boss."""
    carved = {entry}
    edges = set()
    stack = [entry]
    boss_reached = False
    toward_boss = float(profile.get("toward_boss", 0.72))

    while stack and len(carved) < n_target:
        current = stack[-1]
        candidates = []
        for dc, dr in _DIRECTIONS:
            neighbor = (current[0] + dc, current[1] + dr)
            if _in_bounds(neighbor) and neighbor not in carved:
                candidates.append(neighbor)
        if not candidates:
            stack.pop()
            continue

        if boss in candidates:
            # Reach the boss when the floor already has some substance; if
            # the route is still short, take a side step first.
            if len(carved) >= max(3, n_target - 2) or rng.random() < 0.55:
                nxt = boss
            else:
                others = [cell for cell in candidates if cell != boss]
                nxt = (_choose_next(others, boss, toward_boss, rng)
                       if others else boss)
        else:
            nxt = _choose_next(candidates, boss, toward_boss, rng)

        carved.add(nxt)
        edges.add(_edge(current, nxt))
        if nxt == boss:
            boss_reached = True
            stack.pop()  # boss is terminal — never carve through it
        else:
            stack.append(nxt)

    return carved, edges, boss_reached


def _connect_boss(carved, edges, boss, node_cap):
    """Carve a route to an unvisited boss, respecting the node cap."""
    if boss in carved:
        return True
    aligned = [cell for cell in carved
               if cell[0] == boss[0] or cell[1] == boss[1]]
    current = min(aligned or carved,
                  key=lambda cell: _manhattan(cell, boss))

    while current != boss:
        # Keep one slot free for the boss itself.
        if len(carved) >= max(1, node_cap - 1):
            carved.add(boss)
            edges.add(_edge(current, boss))
            return True
        dx = boss[0] - current[0]
        dy = boss[1] - current[1]
        if dx:
            step = (current[0] + (1 if dx > 0 else -1), current[1])
        else:
            step = (current[0], current[1] + (1 if dy > 0 else -1))
        if step not in carved:
            carved.add(step)
        edges.add(_edge(current, step))
        current = step

    carved.add(boss)
    return True


def _grow_branches(carved, edges, boss, n_target, rng):
    """Fill the graph to the node target with one-cell side branches."""
    while len(carved) < n_target:
        choices = []
        for cell in carved:
            if cell == boss:
                continue
            for dc, dr in _DIRECTIONS:
                neighbor = (cell[0] + dc, cell[1] + dr)
                if (neighbor not in carved and neighbor != boss
                        and _in_bounds(neighbor)):
                    choices.append((cell, neighbor))
        if not choices:
            return
        parent, child = rng.choice(choices)
        carved.add(child)
        edges.add(_edge(parent, child))


def _add_loops(carved, edges, boss, profile, rng):
    """Add a few orthogonal loop edges; the boss never gains a second edge."""
    chance = float(profile.get("loop_chance", 0.16))
    for cell in list(carved):
        if cell == boss:
            continue
        for dc, dr in _DIRECTIONS:
            neighbor = (cell[0] + dc, cell[1] + dr)
            if (neighbor not in carved or neighbor == boss
                    or _edge(cell, neighbor) in edges):
                continue
            if _degree(edges, cell) >= 4 or _degree(edges, neighbor) >= 4:
                continue
            if rng.random() < chance:
                edges.add(_edge(cell, neighbor))


def _build_topology_graph(carved, edges, entry, boss, floor, region,
                          profile, spine, n_target):
    ordered = [entry]
    ordered.extend(cell for cell in carved if cell not in (entry, boss))
    ordered.append(boss)
    id_map = {cell: f"n{i}" for i, cell in enumerate(ordered)}

    nodes = {}
    for cell in ordered:
        nodes[id_map[cell]] = {
            "type": "unknown",
            "cell": [int(cell[0]), int(cell[1])],
            "cleared": False,
        }

    edge_list = []
    for a, b in sorted(edges):
        left, right = id_map.get(a), id_map.get(b)
        if left and right and left != right:
            edge_list.append([left, right])

    entry_id = id_map[entry]
    boss_id = id_map[boss]
    return {
        "version": GRAPH_VERSION,
        "profile": profile["id"],
        "wild": bool(profile.get("wild")),
        "floor": int(floor),
        "region": region,
        "nodes": nodes,
        "edges": edge_list,
        "entry": entry_id,
        "boss": boss_id,
        "current": entry_id,
        "visited": [entry_id],
        # The boss lair is the floor objective — reveal its terminal node
        # from the start. Other node types stay hidden until entered/left.
        "revealed": [entry_id, boss_id],
        "cleared": [],
        "credit": 0.0,
        "spine": int(spine),
        "node_min": int(profile["node_min"]),
        "node_cap": int(profile["node_cap"]),
        "n_target": int(n_target),
        "boss_defeated": False,
    }


# ═══════════════════════════════════════════════════════════════════
# Step 2 — node types and room content
# ═══════════════════════════════════════════════════════════════════

def _assign_types(graph, floor, region, profile, rng, player,
                  generate_content=True):
    nodes = graph["nodes"]
    entry = graph["entry"]
    boss = graph["boss"]
    nodes[entry]["type"] = "entry"
    nodes[entry].pop("room", None)
    nodes[boss]["type"] = "boss"
    nodes[boss]["room"] = (
        _generate_boss_room(floor, region, player) if generate_content
        else {"type": "combat", "enemies": [], "is_boss": True}
    )

    middle = [nid for nid in nodes if nid not in (entry, boss)]
    rng.shuffle(middle)
    ratio = float(profile.get("connector_ratio", 0.30))
    connector_count = min(
        len(middle),
        max(1, int(round(len(middle) * ratio))))
    content_ids = middle[:len(middle) - connector_count]
    connector_ids = middle[len(middle) - connector_count:]

    chance = 0.10
    consecutive = 0
    for nid in content_ids:
        if rng.random() < chance:
            room_type = _roll_noncombat_type(rng)
            chance = 0.10
            consecutive = 0
        else:
            room_type = "combat"
            consecutive += 1
            chance = min(0.10 + 0.05 * consecutive, 0.80)
        _set_node_type(nodes[nid], room_type, floor, region, rng, player,
                       generate_content)

    for nid in connector_ids:
        _set_node_type(nodes[nid], "connector", floor, region, rng, player,
                       generate_content)

    _ensure_service(nodes, "fountain", rng, floor, region, player,
                    generate_content)
    _ensure_service(nodes, "merchant", rng, floor, region, player,
                    generate_content)


def _roll_noncombat_type(rng):
    weights = dungeon_rooms.ROOM_TYPE_WEIGHTS
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _set_node_type(node, room_type, floor, region, rng, player,
                   generate_content):
    for key in ("room", "event", "difficulty", "flavor", "cache", "detail"):
        node.pop(key, None)
    node["type"] = room_type
    node["cleared"] = False
    if not generate_content:
        return

    if room_type == "combat":
        node["room"] = _generate_combat_room(floor, region, player)
    elif room_type == "stat_check":
        events = dungeon_rooms.get_stat_check_events(region)
        if not karma.is_enabled(player):
            events = {key: value for key, value in events.items()
                      if not value.get("karma_only")}
        if events:
            node["event"] = rng.choice(list(events))
        else:
            node["type"] = "treasure"
    elif room_type == "trap":
        node["difficulty"] = int(10 + floor * 1.5)
    elif room_type == "connector":
        flavor, detail, cache = rng.choice(_CONNECTOR_SCENES)
        node["flavor"] = flavor
        node["detail"] = detail
        node["cache"] = cache


def _ensure_service(nodes, service, rng, floor, region, player,
                    generate_content):
    if any(node.get("type") == service for node in nodes.values()):
        return
    candidates = [nid for nid, node in nodes.items()
                  if node.get("type") == "connector"]
    if not candidates:
        candidates = [nid for nid, node in nodes.items()
                      if node.get("type") == "combat"]
    if not candidates:
        return
    _set_node_type(nodes[rng.choice(candidates)], service, floor, region, rng,
                   player, generate_content)


def _generate_combat_room(floor, region, player):
    # Local import: dungeon imports this module at top level (cycle).
    from pandemonium.world.dungeon import (
        _attach_room_suffix,
        _encounter_party_size,
        _roll_encounter_size,
        build_enemy_group,
    )
    party_size = _encounter_party_size(player)
    count = _roll_encounter_size(floor, party_size)
    if player and player.get("daily_effects", {}).get("monster_surge"):
        count = min(5, count + 1)
    enemies = build_enemy_group(floor, count, region=region, player=player)
    room = {"type": "combat", "enemies": enemies}
    _attach_room_suffix(room, floor)
    return room


def _generate_boss_room(floor, region, player):
    # Local import: dungeon imports this module at top level (cycle).
    from pandemonium.world.dungeon import (
        _encounter_party_size,
        _roll_encounter_size,
        build_enemy_group,
        get_random_enemy_key,
    )
    boss_key = get_random_enemy_key(floor, boss=True, region=region,
                                    player=player)
    enemies = [boss_key]
    if not is_solo_boss(boss_key, ENEMIES[boss_key]):
        total = _roll_encounter_size(floor, _encounter_party_size(player),
                                     boss_room=True)
        minions = min(3, max(1, total - 1))
        enemies.extend(build_enemy_group(floor, minions, region=region,
                                         player=player))
    return {"type": "combat", "enemies": enemies, "is_boss": True}


# ═══════════════════════════════════════════════════════════════════
# Step 3 — traversal loop
# ═══════════════════════════════════════════════════════════════════

def run_pdg_floor(player, level, region, name, floor_num, total_floors,
                  combat_override=None, saved_graph=None,
                  room_reward_fn=None, profile_id="temperate",
                  dungeon_id=None):
    """Run one PDG floor.

    Returns ``"floor_clear"`` on boss victory, ``"save_exit"`` when the player
    saves at a movement prompt, ``"fled"`` when they leave for the city, and
    ``"dead"`` / ``"timeout"`` for combat failures. The caller owns the wild
    dungeon exit helpers.
    """
    graph = None
    if isinstance(saved_graph, dict):
        try:
            candidate = normalize_graph(saved_graph)
            if (int(candidate.get("floor", 0) or 0) == int(level)
                    and not candidate.get("boss_defeated")
                    and validate_graph(candidate)):
                graph = candidate
        except (TypeError, ValueError, KeyError):
            graph = None

    resumed = graph is not None
    if graph is None:
        graph = generate_graph(
            level, profile_id=profile_id, region=region, player=player,
            wild=True, floor_index=floor_num)

    profile = get_profile(profile_id, wild=True)
    shortest = bfs_distance(graph, graph["entry"], graph["boss"])
    _tprint("\n" + "=" * 58)
    _tprint(f"  {name.upper()} — FLOOR {floor_num}/{total_floors}  ·  PDG DEMO")
    _tprint(f"  {profile.get('name', profile_id)} profile · "
            f"{len(graph['nodes'])} chambers · "
            f"shortest route {shortest if shortest is not None else '?'} blocks")
    _tprint("=" * 58)
    if resumed:
        _tprint("  (resumed from the saved graph)")
    _tprint("  Corridors branch in every direction. The boss waits beyond.")
    _render_all(graph, player)
    _tpause("Press Enter to explore the branching floor...")

    while True:
        options, actions = _movement_options(graph)
        current_label = _node_label(graph, graph["current"])
        choice = _tmenu(options, prompt=f"Travel from {current_label}:",
                        allow_cancel=False)
        if not (0 <= choice < len(actions)):
            continue
        action, payload = actions[choice]

        if action == "inventory":
            terminal = _term()
            if terminal:
                terminal.open_inventory()
            _render_all(graph, player)
            continue
        if action == "save":
            player["saved_wild_graph"] = {
                "floor": int(floor_num),
                "dungeon_id": dungeon_id,
                "graph": _graph_snapshot(graph),
            }
            _tprint("  Progress saved. Exit to the menu to resume later.")
            return "save_exit"
        if action == "flee":
            _tprint("  You abandon the ruin and make for the surface...")
            return "fled"

        status = _move_to_node(player, graph, payload, level,
                               combat_override, room_reward_fn)
        if status == "dead":
            return "dead"
        if status == "timeout":
            return "timeout"
        if status == "run_fled":
            return "fled"
        if status == "boss_victory":
            _apply_floor_bonus(player, graph, level)
            _mult, ratio = reward_multiplier(graph)
            apply_floor_clear_heal(player, ratio)
            _render_all(graph, player)
            return "floor_clear"

        _render_all(graph, player)


def apply_floor_clear_heal(player, ratio):
    """Locked rush-control heal: full at >=75% cleared, otherwise 25–62%."""
    fraction = 1.0 if ratio >= 0.75 else 0.25 + 0.5 * ratio
    healed = 0

    max_hp = player_max_hp(player)
    old_hp = int(player.get("current_hp", 0) or 0)
    player["current_hp"] = min(max_hp, old_hp + int(max_hp * fraction))
    healed += player["current_hp"] - old_hp

    for ally in player.get("allies", []):
        if int(ally.get("current_hp", 0) or 0) <= 0:
            continue
        ally_max = int(ally.get("max_hp", 1) or 1)
        ally_old = int(ally.get("current_hp", 0) or 0)
        ally["current_hp"] = min(ally_max, ally_old + int(ally_max * fraction))
        healed += ally["current_hp"] - ally_old

    _tprint(f"\n  The floor's calm restores {healed} HP across the party "
            f"({fraction:.0%} heal).")
    return healed


def _apply_floor_bonus(player, graph, level):
    mult, ratio = reward_multiplier(graph)
    base_gold = max(10, int(level) * 6 + random.randint(5, 15))
    base_exp = max(10, int(level) * 8)
    gold = int(round(base_gold * mult))
    exp = int(round(base_exp * mult))

    player["gold"] = player.get("gold", 0) + gold
    gain_exp(player, exp)
    for ally in player.get("allies", []):
        if int(ally.get("current_hp", 0) or 0) > 0:
            gain_exp_ally(ally, exp)

    player.setdefault("_pdg_multipliers", []).append(mult)
    _tprint(f"\n  Floor bonus: +{gold} gold, +{exp} XP")
    _tprint(f"  Reward multiplier x{mult:.2f} "
            f"({ratio:.0%} of the floor cleared)")
    return gold, exp


def _move_to_node(player, graph, node_id, level, combat_override,
                  room_reward_fn):
    node_id = str(node_id)
    previous = graph["current"]
    if node_id not in adjacent_nodes(graph, previous):
        return "continue"

    cost = move_cost(graph, node_id)
    graph["current"] = node_id
    _reveal(graph, node_id)
    if node_id not in graph["visited"]:
        graph["visited"].append(node_id)
    _pay_move(player, graph, cost)

    node = graph["nodes"][node_id]
    node_type = node.get("type", "unknown")

    if node_type == "entry" or node_id in graph["cleared"]:
        _tprint(f"\n  You return to {_node_label(graph, node_id)}. "
                f"Nothing remains here.")
        return "continue"

    _tprint("\n" + "═" * 50)
    _tprint(f"  {_NODE_HEADERS.get(node_type, '--- Chamber ---')}")
    _tprint("═" * 50)

    if node_type == "boss":
        result = _run_combat(player, node.get("room") or {}, level,
                             _room_numbers(graph, node_id), combat_override)
        if result == "victory":
            if room_reward_fn:
                room_reward_fn(player, node.get("room") or {})
            graph["boss_defeated"] = True
            return "boss_victory"
        if result == "fled":
            graph["current"] = previous
            _pay_move(player, graph, move_cost(graph, previous))
            _tprint("\n  You retreat from the boss's chamber. "
                    "It remains uncleared.")
            return "continue"
        return "dead" if result == "dead" else "timeout"

    if node_type == "combat":
        result = _run_combat(player, node.get("room") or {}, level,
                             _room_numbers(graph, node_id), combat_override)
        if result == "victory":
            if room_reward_fn:
                room_reward_fn(player, node.get("room") or {})
            _mark_cleared(graph, node_id)
            return "continue"
        if result == "fled":
            graph["current"] = previous
            _pay_move(player, graph, move_cost(graph, previous))
            _tprint("\n  You fall back to the previous chamber. "
                    "This room stays uncleared.")
            return "continue"
        return "dead" if result == "dead" else "timeout"

    result = "continue"
    if node_type == "fountain":
        result = dungeon_rooms.handle_fountain_room(player, level)
    elif node_type == "merchant":
        result = dungeon_rooms.handle_merchant_room(player, level)
    elif node_type == "treasure":
        result = dungeon_rooms.handle_treasure_room(player, level)
    elif node_type == "trap":
        result = dungeon_rooms.handle_trap_room(player, level)
    elif node_type == "stat_check":
        result = dungeon_rooms.handle_stat_check_room(
            player, level, node.get("event"), combat_override=combat_override)
    elif node_type == "connector":
        _resolve_connector(player, node, level)

    if result == "dead":
        return "dead"
    if result == "fled":
        graph["current"] = previous
        _pay_move(player, graph, move_cost(graph, previous))
        _tprint("\n  You retreat to the previous chamber.")
        return "continue"
    if result not in ("continue", None):
        return "timeout"

    _mark_cleared(graph, node_id)
    return "continue"


def _run_combat(player, room, level, numbers, combat_override):
    room_num, total_rooms = numbers
    enemies = room.get("enemies") or []
    if combat_override:
        return combat_override(
            player, enemies, floor=level, room_num=room_num,
            total_rooms=total_rooms, suffixes=room.get("suffixes"))
    return combat(
        player, enemies, floor=level, room_num=room_num,
        total_rooms=total_rooms, suffixes=room.get("suffixes"))


def _room_numbers(graph, node_id):
    total = max(1, len(graph["nodes"]) - 1)  # entry excluded, boss included
    cleared = sum(1 for nid in (graph.get("cleared") or [])
                  if nid not in (graph["entry"], graph["boss"]))
    if node_id == graph["boss"]:
        return total, total
    return min(total, cleared + 1), total


def _resolve_connector(player, node, level):
    _tprint(f"  {node.get('flavor', 'An empty passage.')}")
    detail = node.get("detail")
    if detail:
        _tprint(f"  {detail}")
    cache = node.get("cache")
    if cache == "gold":
        gold = max(3, int(level) * 2 + random.randint(2, 8))
        player["gold"] = player.get("gold", 0) + gold
        _tprint(f"  You gather {gold} gold from the dust.")
    elif cache == "heal":
        max_hp = player_max_hp(player)
        old_hp = int(player.get("current_hp", 0) or 0)
        player["current_hp"] = min(max_hp, old_hp + max(2, int(max_hp * 0.05)))
        _tprint(f"  You recover {player['current_hp'] - old_hp} HP.")


def _pay_move(player, graph, cost):
    graph["credit"] = float(graph.get("credit", 0.0) or 0.0) + float(cost)
    whole_blocks = int(graph["credit"] + 1e-9)
    if whole_blocks <= 0:
        return
    graph["credit"] = max(0.0, graph["credit"] - whole_blocks)
    advance_time(player, 60 * whole_blocks)
    suffix = "s" if whole_blocks != 1 else ""
    _tprint(f"  Time passes: {whole_blocks} block{suffix}.")


def _movement_options(graph):
    current = graph["current"]
    revealed = set(graph.get("revealed") or [])
    visited = set(graph.get("visited") or [])
    cleared = set(graph.get("cleared") or [])

    neighbors = sorted(
        adjacent_nodes(graph, current),
        key=lambda nid: tuple(graph["nodes"][nid]["cell"]))
    options = []
    actions = []
    for nid in neighbors:
        node = graph["nodes"][nid]
        known = nid in revealed or nid in visited or nid == graph["boss"]
        label = _NODE_LABELS.get(node.get("type", "unknown"), "Unknown") \
            if known else "Unknown"
        suffix = " (cleared)" if nid in cleared else ""
        options.append(f"{label}{suffix} · {move_cost(graph, nid):.1f} blocks")
        actions.append(("move", nid))

    options.extend(["Inventory / Stats", "Save and quit", "Flee to city"])
    actions.extend([("inventory", None), ("save", None), ("flee", None)])
    return options, actions


def _node_label(graph, node_id):
    node = graph["nodes"].get(str(node_id)) or {}
    label = _NODE_LABELS.get(node.get("type", "unknown"), "Unknown")
    if str(node_id) in (graph.get("cleared") or []):
        label += " (cleared)"
    return label


def _reveal(graph, node_id):
    graph.setdefault("revealed", [])
    if node_id not in graph["revealed"]:
        graph["revealed"].append(node_id)


def _mark_cleared(graph, node_id):
    graph.setdefault("cleared", [])
    if node_id not in graph["cleared"]:
        graph["cleared"].append(node_id)
    node = graph["nodes"].get(node_id)
    if node is not None:
        node["cleared"] = True


# ═══════════════════════════════════════════════════════════════════
# ASCII renderer (the current DungeonScreen Map panel)
# ═══════════════════════════════════════════════════════════════════

def render_map(graph, player=None, force_reveal=False):
    """Render the 8x8 graph into the existing 24-char Map panel.

    Layout and edges are always visible; node types stay hidden (``?``) until
    the node is entered or left. ``force_reveal`` is for the offline demo
    script only.
    """
    nodes = graph.get("nodes") or {}
    by_cell = {}
    for nid, node in nodes.items():
        cell = node.get("cell") or [0, 0]
        c, r = int(cell[0]), int(cell[1])
        if 0 <= c < GRID and 0 <= r < GRID:
            by_cell[(c, r)] = nid

    if by_cell:
        min_col = min(c for c, _r in by_cell)
        max_col = max(c for c, _r in by_cell)
        min_row = min(r for _c, r in by_cell)
        max_row = max(r for _c, r in by_cell)
    else:
        min_col = min_row = 0
        max_col = max_row = GRID - 1
    cols = max_col - min_col + 1
    rows = max_row - min_row + 1

    def _x(col):
        return 3 * (col - min_col)

    def _y(row):
        return 2 * (row - min_row)

    # Glyph rows separated by connector rows, cropped to the occupied bbox.
    # Cell layout is [glyph][pad][gap]: the gap column carries horizontal
    # corridor dashes so node glyphs can never overwrite an edge.
    grid = [[" "] * (cols * 3) for _ in range(rows * 2 - 1)]

    revealed = set(graph.get("revealed") or [])
    visited = set(graph.get("visited") or [])
    cleared = set(graph.get("cleared") or [])
    current = str(graph.get("current"))

    for (c, r), nid in by_cell.items():
        node = nodes[nid]
        known = (force_reveal or nid in revealed or nid in visited
                 or nid == current or nid == graph.get("boss"))
        glyph = _NODE_GLYPHS.get(node.get("type", "unknown"), "?") \
            if known else "?"
        if known and nid in cleared:
            glyph = glyph.lower() if glyph.isalpha() else glyph
        row = grid[_y(r)]
        x = _x(c)
        row[x] = glyph
        if nid == current:
            row[x + 1] = "+"

    for edge in graph.get("edges") or []:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            continue
        a, b = str(edge[0]), str(edge[1])
        if a not in nodes or b not in nodes:
            continue
        ca, cb = nodes[a]["cell"], nodes[b]["cell"]
        c1, r1 = int(ca[0]), int(ca[1])
        c2, r2 = int(cb[0]), int(cb[1])
        if r1 == r2:
            lo, hi = sorted((c1, c2))
            row = grid[_y(r1)]
            for c in range(lo, hi):
                pad = _x(c) + 1
                gap = _x(c) + 2
                if 0 <= pad < len(row) and row[pad] != "+":
                    row[pad] = "─"
                if 0 <= gap < len(row):
                    row[gap] = "─"
                if c + 1 < hi and (c + 1, r1) not in by_cell:
                    row[_x(c + 1)] = "─"
                    if _x(c + 1) + 1 < len(row):
                        row[_x(c + 1) + 1] = "─"
        elif c1 == c2:
            lo, hi = sorted((r1, r2))
            for r in range(lo, hi):
                grid[_y(r) + 1][_x(c1)] = "│"
                if r + 1 < hi and (c1, r + 1) not in by_cell:
                    grid[_y(r + 1)][_x(c1)] = "│"

    lines = [f"=== FLOOR {graph.get('floor', '?')} MAP ==="]
    lines.extend("".join(row).rstrip() for row in grid)
    lines.append("")

    mult, _ratio = reward_multiplier(graph)
    ratio = cleared_ratio(graph)
    lines.append(f"Cleared {ratio:.0%} · x{mult:.2f}")
    lines.append("S entry C+ you B boss")
    lines.append("C combat  F fountain")
    lines.append("M merchant N event")
    lines.append("$ loot T trap · passage")
    lines.append("? unknown  lower=cleared")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════

def _render_all(graph, player):
    map_text = render_map(graph, player=player)
    if map_text:
        _tprint(map_text)
    party_text = dungeon_rooms.render_party_status(player)
    if party_text:
        _tprint(party_text)


def _graph_snapshot(graph):
    snapshot = copy.deepcopy(graph)
    snapshot["edges"] = [list(edge) for edge in snapshot.get("edges") or []]
    return snapshot


def _edge(a, b):
    return (a, b) if str(a) <= str(b) else (b, a)


def _in_bounds(cell):
    return 0 <= cell[0] < GRID and 0 <= cell[1] < GRID


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _degree(edges, cell):
    count = 0
    for a, b in edges:
        if a == cell or b == cell:
            count += 1
    return count


def _bfs_from(adjacency, start):
    distances = {str(start): 0}
    queue = deque([str(start)])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, []):
            if neighbor not in distances:
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances
