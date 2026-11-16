# Procedural Dungeon Graph (PDG) — Design Proposal (ON HOLD UNTIL FURTHER DISCUSSION)
**Status:** Proposal — decisions 1–11 locked 2026-11-12; no code changes yet. 
**Scope:** Replace the linear 10-room city-dungeon floor with a per-floor node graph
(rooms = nodes, corridors = edges), so floors support route choice, skippable
services, and per-dungeon topology flavor while preserving the existing block-time
budget and room-handler content.
**Related docs:** [`biome_dungeon_depth_design.md`](./biome_dungeon_depth_design.md),
[`time_system_design.md`](./time_system_design.md),
[`karma_system_design.md`](./karma_system_design.md),
[`wild_dungeon_design.md`](./wild_dungeon_design.md),
[`event_horizon_design.md`](./event_horizon_design.md).

**Locked decisions (2026-11-12):**

1. **Traversal:** undirected normal dungeons, directed descent for Pandemonium, portal/one-way links for Wonderland.
2. **Time:** 0.5 block per edge + 0.5 block per destination node.
3. **Rush control:** scale floor/boss rewards and floor-clear healing with cleared nodes.
4. **Lifetime:** run-scoped, with **save-exit preserving the active dungeon**. Flee-to-city, death, and floor clear wipe it.
5. **Milestones:** compact approach graph for **all** milestones; the boss encounter remains scripted for story bosses.
6. **Reveal:** show the full node layout and edges; hide node types until the node is entered or left.
7. **Node weights:** keep the existing `ROOM_TYPE_WEIGHTS` and non-combat escalation; connector nodes are added by the graph generator.
8. **Flee:** combat flee returns to the previous node and leaves the room uncleared; flee-to-city leaves the map; death retreats to the city.
9. **Wild dungeons:** adopt PDG at a smaller scale (`N_cap = 14`).
10. **Room cap:** hard cap **24 nodes** per graph.
11. **Renderer:** Canvas is the final renderer; ASCII remains for tests/debugging.

> This document records the design discussion. Locked decisions are listed above.
> Nothing here is implemented yet. Open tuning details are in §14.

---

## 1. Summary

The current floor is a fixed line: 9 generated rooms followed by 1 boss room, in
order. PDG replaces that line with a graph the player traverses node by node.
Each floor becomes a small route-planning problem:

- Take the short route to the boss and save time, or the long route for more
  loot/XP.
- Skip a fountain or merchant and come back later (within the run).
- Face different room mixes depending on the path.
- Give every biome/dungeon its own graph behavior (branching, loops, hazards,
  one-way links, fog, etc.).

The existing room handlers, combat override, GUI log, and floor-progress model
remain the content layer. The graph only decides **what is connected to what**,
**what type each room is**, and **how the player moves**.

---

## 2. Current baseline

| Area | Current behavior |
|---|---|
| Floor generation | `dungeon.generate_floor()` creates 9 mixed rooms + 1 boss room. Non-combat chance starts at 10% and rises 5% per consecutive combat, resetting on a non-combat room. |
| Traversal | Linear. `dungeon.explore_dungeon()` walks rooms in order. |
| Time | 1 block per room (`advance_time(player, 60)`) + 1 block for floor completion → **~11 blocks per floor**. |
| Floor clear | Full heal for the player and all allies, progress sync, save. |
| Mid-floor state | `saved_dungeon_floor`, `saved_dungeon_rooms`, `saved_dungeon_room_index`; validation hard-codes exactly 10 rooms. |
| Re-entry | `city_screen._launch_dungeon()` clears `saved_dungeon_*` on every entry. `load_game()` always returns the player to a city. In the GUI, "Save and quit" therefore restarts the floor on the next entry; the resume keys are effectively unused today. **PDG changes this: save-exit preserves the graph (see §6).** |
| Floor replay | Floor selection allows any unlocked floor. A replayed floor is freshly generated. |
| Superbosses | First-time-only triggers before the normal room loop (Wonderland F10/20/30/40/50; generic every-20th with `city_prog["max_floor"] <= floor`; Pandemonium F20/F40). Victory advances the floor and returns. Replays are normal floors. |
| GUI map | `dungeon_rooms.render_ascii_map()` renders a 5×2 ASCII grid (`P`/`C`/`N`/`B`/`?`); `DungeonScreen` monkey-patches it into the Map panel. Movement/room menus already use `_tmenu` → the existing button panel. |
| Saves | `save_game()` writes pretty-printed JSON (`indent=2`). Measured 2026-11-11: `savegame_1.json` ≈ 427 KB, `savegame_4.json` ≈ 216 KB. |

---

## 3. Core model

### 3.1 Nodes and edges

- A node is a room/resolution point: combat, fountain, merchant, treasure, trap,
  stat check, connector, boss, etc.
- An edge is a logical corridor/travel link drawn between node centers.
  Traversal spends time, but edges do **not** occupy grid cells.
- Each node tracks at minimum: `id`, `type`, layout position (`layer`, `row`),
  `cleared`, and type-specific state (event key, fountain charges, merchant stock).
- The graph tracks `entry`, `boss`, `current`, `visited`, `cleared`, `revealed`,
  and the movement-time credit.

### 3.2 Traversal policy

Traversal is a per-dungeon-profile property, not a global rule:

| Profile | Behavior | Fit |
|---|---|---|
| Undirected | Backtracking allowed; cleared nodes stay cleared | Normal city dungeons |
| Directed descent | Forward-only; nodes behind may collapse | Pandemonium |
| Portal / one-way | Special edges skip layers or redirect | Wonderland |

Backtracking is what makes "skip the fountain and use it later" meaningful.
Without it, a skipped service is simply lost for that floor.

### 3.3 Node types

Keep the existing room handlers and add graph-native nodes:

- **Combat** — regular encounter.
- **Elite** — tougher encounter, better loot (optional).
- **Fountain** — healing/buff; finite charges if revisitable.
- **Merchant** — buy/sell + Karma-gated robbery/attack.
- **Treasure** — guaranteed rare+ cache.
- **Trap** — DEX/WIS avoidance.
- **Stat check** — existing narrative events.
- **Connector** — lore, small cache, shortcut, empty passage; keeps a 20-node
  route from becoming 20 full combats.
- **Boss** — terminal node; normal boss or milestone superboss depending on
  floor state.

Do **not** add dungeon sleep/camp nodes: the time design locks "no mid-dungeon
rest" (see `time_system_design.md` §3 row 6 / §6). Fountains and merchants are
the relief valves.

### 3.4 Generation invariants

Every generated graph must satisfy:

- Single entry; at least one terminal boss; boss reachable from the entry.
- Every node is reachable from the entry and can reach the boss.
- No orphan edges, no unreachable islands.
- Degree cap ~4 for readable maps.
- At least one fountain and one merchant somewhere on the graph (not necessarily
  on every route).
- No duplicate edges; no self-loops.
- Deterministic layout (`layer`, `row`) stored with the graph.
- The boss is the only floor exit; branches cannot bypass it.

A practical shape: 4–6 layers deep, 2–4 nodes per layer, 1–2 forward edges per
node, occasional cross/skip edges, then post-process for connectivity. Layout
rows should minimize edge crossings (simple barycenter ordering is enough).

### 3.5 Node mix

The exact combat/non-combat mix comes from the existing `ROOM_TYPE_WEIGHTS` and
the 10% +5% escalation (see §5.1). Connector nodes are inserted outside that
roll so a 20+ node route does not become 20 combats. A useful sanity target is
that roughly half the route is combat, with the rest split between services,
events, and connectors.

---

## 4. Time budget

Current baseline: 10 rooms × 1 block + 1 block floor completion = **~11 blocks
per floor**.

The proposed "1 block per 2 nodes" is **0.5 block per edge**. That alone does not
preserve the average:

| Model | Cost of a 10-node route | Nodes needed for ~11 blocks |
|---|---|---|
| Movement only, 0.5/edge | ~5.5 blocks | ~20 nodes |
| Movement 0.5/edge + 0.5 per node resolved | ~10.5 blocks | ~10 nodes |

**Locked:** charge **0.5 block per edge + 0.5 block per destination node
resolution**. A typical route stays around 10–12 blocks; a shortest route is
~8.5–10.5; a full clear is ~15–21. This preserves pacing without doubling
encounter count.

### 4.1 Half-block implementation

`advance_time(30)` currently costs **1 block** because `blocks_for_minutes()`
treats 16–90 minutes as one block. Do not change the global block table.

Use an accumulator (`dungeon_move_credit` / `spend_half_blocks`):

- Each edge adds 0.5 block of credit.
- Each node resolution adds 0.5 block.
- When credit reaches 1.0, call `spend_blocks(player, 1)`.
- Persist the odd half in the graph state so save/resume does not mint or lose
  whole blocks.

### 4.2 Tick semantics

The existing per-room effects were tuned to **1 room = 1 block**. In a half-block
graph, tick them by **time spent**, not by node count:

- Sleep buffs (`well_rested`, `shared_night`, `dream_blessed`, `beloved`).
- Hallucination rolls.
- Pandemonium sapping aura / Wonderland room damage.
- Arcane blessing room consumption.
- Wedding bark-shield room counter.

Otherwise a 20-node floor triggers these twice as often as today.

---

## 5. Map generation and per-dungeon identity

Make identity data-driven rather than a code fork per dungeon. A profile should
define:

- `depth` / `width` / branch factor
- `traversal`: undirected / directed / portal
- `edge_cost` (default 0.5)
- loop / cross-edge chance
- node-type weights
- reveal / fog-of-war rule
- edge hazards and special nodes

Examples:

| Dungeon | Graph identity |
|---|---|
| Temperate | Balanced branching, standard room mix |
| Coastal | Tide-locked edges; some routes close or double in cost after N moves |
| Swamp | Miasma hazard on edges; more fountains |
| Desert | Long edges, supply pressure, mirage nodes |
| Volcanic | Heat damage on traversal; high-risk shortcuts |
| Wonderland | Portals, one-way links, tea-party fountains |
| Pandemonium | Directed descent; nodes collapse behind you |
| Wild ruins | Compact graphs; can stay linear initially |

The graph profile should live in a resource/data module (e.g.
`resources/dungeon_graph_profiles.py`) with a few hooks (`can_traverse`,
`on_enter`, `on_edge`) so new dungeons do not require core changes.

### 5.1 8×8 grid and room budget

**Grid.**

- 8×8 = 64 cells.
- One node per cell; edges connect orthogonal neighbors (N/S/E/W).
- Empty cells are allowed. Avoid diagonal edges in the ASCII fallback; the
  Canvas renderer can draw them, but orthogonality keeps both views readable.
- The entry is a border cell; the boss is on the far side. Entry coordinates vary
  by profile, which makes each dungeon's map orientation distinct.

**Grid occupancy vs edge budget.** Only **nodes** occupy cells. Edges are logical
links drawn between node centers; they do not consume cells and do not count
toward the 8×8 layout. The grid is a node-position bound, not a tile map. A
24-node graph has at most 48 orthogonal edges (degree ≤ 4); typical maps use
~28–36. Diagonal/portal edges are still drawn lines and still cost no cells.

**Room budget formula.**

The budget is driven by the shortest-route time, not by the grid size:

- `spine = clamp(8 + floor // 20, 8, 10)` — edges on the intended shortest route.
- `branch = profile.branch_factor` — 0.5 (sparse) to 1.0 (dense).
- `N = clamp(1 + spine + round(spine * branch), N_min, N_cap)` — total nodes.
- `N_min = 12` for normal floors; `N_cap` is the profile cap below (18–24).
- Absolute cap: **24 nodes** (37.5% occupancy). This leaves room for corridors
  and keeps a "full" map from becoming a 40-fight slog.
- Milestone approach graphs: `N_min = 6`, `N_cap = 8–10`, `spine = 4–6`,
  `branch = 0.3–0.5`.
- Wild ruins: `N_min = 10`, `N_cap = 14`, `spine = 5–7`, random border entry.

**Quick allocation answer:** a normal floor uses **12–24 nodes** (typical
15–19), with a hard cap of **24**; milestone approaches use **6–10**; wild ruins
use **10–14**. The 8×8 grid is a layout bound, not a room target — most cells
stay empty so the map remains readable.

**Why this budget works.** A shortest route with `spine` edges and `spine + 1`
nodes costs `0.5 * spine + 0.5 * (spine + 1) = spine + 0.5` blocks when the
entry node is free. `spine = 8–10` therefore lands at **8.5–10.5 blocks**, close
to the current ~11-block floor. A full clear costs roughly `N` blocks plus
backtracking, which is the intended long-route tradeoff.

**Worked examples.**

| Floor | Profile | spine | branch | N | Shortest route | Full clear (est.) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Temperate | 8 | 0.7 | 15 | ~8.5 blocks | ~15–17 blocks |
| 20 | Coastal | 9 | 0.8 | 17 | ~9.5 blocks | ~17–19 blocks |
| 40 | Forest | 10 | 1.0 | 21 | ~10.5 blocks | ~20–24 blocks |
| milestone | any | 5 | 0.4 | 8 | ~5.5 blocks | ~8–10 blocks |

**Room allocation (locked: use the old weights).** Keep the existing generator
behavior:

- `ROOM_TYPE_WEIGHTS` stays as-is: fountain 20, merchant 15, stat_check 25,
  treasure 20, trap 20.
- Keep the current non-combat escalation: 10% base, +5% per consecutive combat,
  reset to 10% after a non-combat room.
- Combat rooms still roll `1..max_enemies` with the existing enemy-group builder.

The graph generator adds **connector nodes** outside that roll (lore, small
cache, shortcut, empty passage) so a 20-node route does not become 20 combats.
After the roll, enforce:

- At least one fountain and one merchant somewhere on the graph.
- No boss except the terminal node.
- Connector count = `N - rolled_content_nodes`; if negative, drop connectors
  first, then reroll content with the same weights.

**Entry and boss coordinates.**

- `left → right`: `entry = (0, randint(1, 6))`; `boss = (7, randint(1, 6))`,
  adjusted until Manhattan distance `>= spine`.
- `bottom → top`: `entry = (randint(1, 6), 7)`; `boss = (randint(1, 6), 0)`,
  same distance check.
- `any → farthest`: entry is a random perimeter cell; boss is the perimeter cell
  with the greatest BFS distance from entry. If the distance is below `spine`,
  reroll the entry.
- `Pandemonium`: `entry = (randint(1, 6), 0)`, `boss = (randint(1, 6), 7)`;
  traversal is directed downward.

**Profile caps.**

| Profile | Traversal | Entry → Boss | N_cap | branch |
|---|---|---|---:|---:|
| Temperate | undirected | left → right | 20 | 0.7 |
| Coastal | undirected | left → right | 22 | 0.8 |
| Swamp | undirected | left → right | 22 | 0.9 |
| Desert | undirected | left → right | 18 | 0.5 |
| Mountain | undirected + drops | bottom → top | 20 | 0.6 |
| Forest | undirected | any → farthest | 24 | 1.0 |
| Savanna | undirected | left → right | 18 | 0.5 |
| Volcanic | undirected | bottom → top | 18 | 0.6 |
| Tropical | undirected | any → farthest | 22 | 0.9 |
| Sea caves | undirected | left → right | 20 | 0.7 |
| Magical | undirected + portals | any → farthest | 22 | 0.9 |
| Celestial | undirected | bottom → top | 18 | 0.5 |
| Tundra | undirected | left → right | 18 | 0.5 |
| Pandemonium | directed | top → bottom | 20 | 0.6 |
| Wonderland | portal | any → farthest | 22 | 0.9 |

### 5.2 Generation algorithm

Candidate algorithms:

| Algorithm | Fit for an 8×8 node map |
|---|---|
| Randomized DFS maze (recursive backtracker) | **Recommended.** Guarantees connectivity, creates winding paths, O(N), easy to seed. |
| Random walk / drunkard's walk | Organic caves, but can leave isolated pockets and needs repair. |
| BSP room partitioning | Good for rectangular room layouts, not for a node graph. |
| Poisson disk + MST + extra edges | Even room spacing; more code, better for open maps. |
| Layered DAG (Slay the Spire style) | Great route choice, but less spatial; a good alternative for Pandemonium/Wonderland. |

Recommended sequence:

1. Pick entry and boss cells (see above).
2. **Carve with randomized DFS.** Start at entry; maintain a stack; choose an
   orthogonal unvisited neighbor, weighted toward the boss (`p_toward = 0.65–0.8`)
   but not always; mark visited, carve the edge, push. Stop at `N` cells or when
   the stack empties.
3. **Ensure the boss is connected.** If the boss was not carved, connect it to the
   nearest carved cell (orthogonal if possible; otherwise carve a short corridor).
4. **Add loops.** For each pair of carved orthogonal neighbors without an edge,
   add one with probability `p_loop = 0.10–0.25`. Reject a loop if it reduces the
   BFS entry→boss distance below `spine`.
5. **Grow branches.** If the DFS produced fewer than `N` nodes, grow 1–3-cell
   branches from random carved cells until `N` is reached.
6. **Assign node types.** Entry/start and boss/terminal are fixed; weighted roll
   the rest; enforce fountain/merchant and elite floors.
7. **Validate; retry** up to 8 seeds. Reject a graph if any invariant fails.

Pseudocode:

```text
generate(seed, profile, floor):
    rng = Random(seed)
    entry = pick_entry(profile, rng)
    boss  = pick_boss(profile, entry, floor, rng)
    N     = room_budget(floor, profile)

    graph = carve_dfs(entry, boss, N, profile, rng)
    connect_boss(graph, boss)
    add_loops(graph, p_loop=profile.loop_chance, min_spine=profile.min_spine)
    branch_fill(graph, N, profile, rng)
    assign_types(graph, profile, rng)
    assert_invariants(graph, profile)
    return graph
```

Validation checks:

- All nodes reachable from entry; all nodes can reach boss.
- `min_spine <= BFS(entry, boss) <= max_spine`.
- Degree <= 4; no duplicate edges; no self-loops.
- At least one fountain and one merchant.
- Boss is the only **exit** node; dead-end connector/treasure nodes are allowed.
- Room count `N` within `[N_min, N_cap]`.

### 5.3 Biome map previews

These are schematic previews, not final art. Empty cells are omitted; the
implemented map places the same nodes on an 8×8 grid. Types are shown for
illustration; in-game node types start hidden until entered or left. Glyphs:

`S` entry · `B` boss · `C` combat · `E` elite · `F` fountain · `M` merchant ·
`$` treasure · `N` event · `?` unknown · `~` hazard/tide edge · `»` portal ·
`K` key gate · `↓` one-way drop.

#### Temperate — Open Roads
*Loot identity: balanced elements; sword / greatsword / shield / bow.*
**Gimmick:** no edge hazard; reliable services; one extra connector. The baseline
map: every route is viable, and the choice is purely time vs loot.

```text
S ── C ──┬── F ── $ ──┬── B
         ├── M ── ? ──┤
         └── N ── C ──┘
```

#### Coastal — Tides
*Loot identity: Water / Wind / Thunder; rapier / crossbow / orb / harp.*
**Gimmick:** the tide flips every 4 moves. One `~` edge opens and another closes;
the map is loop-heavy, with a merchant and fountain near the shore.

```text
S ── C ~~ F ── $ ──┬── B
│         │         │
└─ N ── M ┴─ ? ── C ─┘
```

#### Swamp — Miasma
*Loot identity: Water / Earth / Dark; dagger / tongue dagger / mace / orb.*
**Gimmick:** each edge traversal adds a miasma stack. At 3 stacks, −1 DEX/WIS
until a fountain. Fountains are more common, but some are spoiled (`F~`).

```text
S ── C ──┬── F ── ? ──┐
│        │            │
└─ N ── M ┴── $ ── C ─┴─ B
```

#### Desert — Heat and Mirage
*Loot identity: Fire / Earth / Wind; axe / chakram / spear / wand / wraps / leathers.*
**Gimmick:** edges cost 1 block instead of 0.5, and mirage merchants (`m`) are
50% real, 50% ambush. Fewer fountains; long, sparse routes.

```text
S ── C ────── ? ────── B
│            │
└─ N ── $ ── m ── C ──┘
```

#### Mountain — Climb
*Loot identity: Earth / Physical / Fire; hammer / maul / shield / halberd / plate / chain / scale.*
**Gimmick:** upward edges cost 1 block, downward edges cost 0.5. One-way drops
(`↓`) skip layers; a rockslide can block an edge for 3 moves.

```text
        B
        │
   C ── ? ── F
   │         │
S ─┴─ N ── M ┴─ $
```

#### Forest — Lost Paths
*Loot identity: Earth / Wind / Water / Light; bow / spear / dagger / lute / leathers / elven mail / silk garb.*
**Gimmick:** the most tangled layout — highest branch and loop count, so the
walk to the boss is never a straight line. Forest connectors are **forage
sites** (flowers and crafting materials) instead of empty passages, and every
dead-end branch ends in a small cache. The forest charges for exploration in
time, not hazard: nothing here hurts you, but every side trail is time you do
not spend on the boss. Node types still follow the global reveal rule (hidden
until entered or left), so a branch is a commitment — you learn what it held
only by walking it.

```text
S ── C ── ? ── $ ── B
│    │    │    │
└─ N ┴─ $ ┴─ C ─┘
```

#### Savanna — Stampede
*Loot identity: Fire / Earth / Wind / Physical; spear / chakram / axe / rapier.*
**Gimmick:** few branches, but elite patrols (`E`) move one node every 3 moves.
Entering an edge beside an elite may trigger an ambush. Wide, open routes.

```text
S ── C ── E ── ? ── B
│         │
└─ N ── M ┴─ $ ── C ─┘
```

#### Volcanic — Heat Vent
*Loot identity: Fire / Earth / Dark; axe / hammer / flail / greatsword / plate / banded mail / battle harness.*
**Gimmick:** `~` heat vents deal fire damage on traversal; the safe detour is
longer. Fire resistance and cool springs (`F`) matter. Shortcuts are risky.

```text
S ── C ~~ ? ── $ ── B
│         │
└─ N ── F ┴─ E ── C ─┘
```

#### Tropical — Canopy
*Loot identity: Water / Earth / Fire / Wind; dagger / bow / chakram / bell / silk garb / wraps.*
**Gimmick:** two layers. `^` climbs to a canopy route that skips ground hazards
but hides loot; the ground route is richer but riskier.

```text
S ── C ──^── ? ── F ── B
│    │         │
└─ N ┴─ $ ── ? ─┘
```

#### Sea Caves — Flooded Tunnels
*Loot identity: Water / Dark / Thunder; spear / dagger / orb / wand.*
**Gimmick:** `~` flooded edges cost 1 block and may require a CON check or
water-breathing. Low tide reveals a shortcut; underwater caches sit off the main
route.

```text
S ── C ~~ ? ── $ ── B
│         │
└─ N ── F ┴─ M ── C ─┘
```

#### Magical — Arcane Flux
*Loot identity: Magical / Light / Dark / Thunder; staff / greatstaff / grimoire / orb / robes / vestments / runic plate / tome / crown.*
**Gimmick:** `»»` portals link non-adjacent nodes; the destination changes after
use. Arcane event nodes can teleport the party to another branch.

```text
S ── C ── ? »» F ── B
│         │
└─ N ── M ┴─ $ ── C ─┘
```

#### Celestial — Gates of Light
*Loot identity: Light / Wind / Magical / Thunder; staff / greatstaff / grimoire / crown / regalia / vestments / robes / monocle.*
**Gimmick:** `K` key gates open a direct route if you find the Sigil on a side
branch. A judgment shrine offers a Karma choice; high Karma gets a small blessing.

```text
S ── C ──[K]── F ── B
│         │
└─ N ── M ┴─ $ ── C ─┘
```

#### Tundra — Frostbite
*Loot identity: Water / Wind / Earth; spear / crossbow / greatstaff / harp.*
**Gimmick:** each edge adds cold; at 4 stacks, −1 all stats until a warm spring
(`F`). Blizzards hide edges or add 1 block. Fewer, longer routes.

```text
S ── C ────── ? ────── B
│            │
└─ N ── F ── M ── $ ───┘
```

#### Pandemonium — Collapse
*Loot identity: Dark / Fire / Magical; tongue dagger / axe / flail / grimoire / runic plate / regalia.*
**Gimmick:** directed descent. Nodes behind you collapse after leaving; there is
no backtracking. Curses can hide the boss or invert a branch.

```text
S ── C ── ? ── F
     ↓    ↓
     M ── ? ── E
          ↓
          B
```

#### Wonderland — Nonsense Logic
*Loot identity: Magical / Light / Dark / Wind; rapier / wand / lute / bell / regalia / crown / monocle.*
**Gimmick:** one-way portals (`»`), rotating nodes, and false connections. Some
nodes rotate every 3 moves, swapping their edges; tea-party fountains give random
buffs. Entry is on a random border cell.

```text
S ── C ── ? »» F ── B
│         │
└─ N ── M ┴─ $ ── C ─┘
```

Event Horizon is not a PDG dungeon; it keeps its endless-room loop. Wild ruins
adopt PDG at a smaller scale (`N_cap = 14`, `spine = 5–7`) once the city version
is stable.

---

## 6. Revisiting and floor lifetime

"Revisiting" means different things. They now have separate rules.

| Event | Behavior |
|---|---|
| **Backtrack within one floor run** | Allowed for undirected profiles. Cleared nodes stay cleared and give no rewards again; movement still costs time. Fountain charges and merchant state persist for the run. |
| **Combat flee** | Returns to the previous node. The room stays uncleared and its type is revealed (`C`); you can take another route. |
| **Flee to city** | Ends the run. The graph is wiped; re-entering starts a fresh graph. |
| **Death** | Normal death penalty; the player retreats to the origin city; graph is wiped. |
| **Save-exit** | Preserves the active graph, current node, cleared/visited state, and half-block credit in the save. Loading can resume the dungeon. |
| **Replay an already-cleared floor** | Fresh graph; first-time-only superbosses do not respawn. |
| **Floor-to-floor stairs** | Not supported in v1. One `explore_dungeon()` call = one floor. |

Combat flee and flee-to-city are separate actions. Combat flee resolves the
fight and returns to the previous node; flee-to-city is a movement/post-room
menu option that ends the run and returns the player to the origin city.

### 6.1 Lifetime: run-scoped + save-exit persistence (locked)

- Graph lives in `player["dungeon_graph"]` for the active run.
- `save_game()` stores the graph, `current`, `visited`, `cleared`,
  fountain/merchant state, `move_credit`, `floor`, and `graph_version`.
- **Save-exit preserves** the graph. On load, offer **Resume Dungeon (Floor N,
  node X/Y)** vs **Abandon Run** (or auto-resume; UX to tune). Starting a
  different dungeon/floor, fleeing to city, death, or clearing the floor wipes
  the preserved graph.
- **Flee-to-city, death, and floor clear wipe** the graph. Re-entering or
  replaying a floor generates a fresh graph.
- Current code clears `saved_dungeon_*` in `_launch_dungeon()` and `load_game()`
  always returns to a city. PDG must add an explicit resume path instead of
  relying on the old implicit keys.

### 6.2 Not included: persistence across voluntary city visits

Save-exit persistence is the only cross-session carry-over. Leaving the dungeon
to shop or rest and returning later starts a fresh graph. Supporting that would
need:

- keeping graph state across city visits until floor clear,
- a "Resume Floor N" vs "Restart Floor N" floor-selection choice,
- a decision on fountain/merchant parking,
- a `run_id` to avoid stale collisions.

---

## 7. Rewards and rush control

A full heal on every floor clear is the main exploit risk. A shortest route
(~8.5–10.5 blocks) full-heals the party more often than the current ~11-block
floor, and boss rewards per block rise.

**Locked: scale floor rewards with cleared nodes.** The shortest route stays
open, but the floor/boss completion reward and floor-clear healing scale with
how much of the graph was cleared.

- `cleared_ratio = cleared_nodes / max(1, N - 2)` (0.0 = boss rush; 1.0 = full
  clear; entry and boss are excluded).
- `reward_mult = 0.5 + 0.5 * cleared_ratio` (initial tuning; full clear = 1.0,
  bare rush ≈ 0.5).
- Apply to the boss/floor-completion gold and XP. Per-node loot/XP is already
  paid at node resolution.
- Floor-clear heal: full heal at `cleared_ratio >= 0.75`; otherwise
  `25% + 50% * cleared_ratio` of max HP (or another tuned curve).
- Show the expected multiplier on the boss node or floor header, so the choice
  is informed.

A boss seal / minimum path length is not used in v1; reward scaling is the
chosen lever. Revisiting cleared nodes must not re-award loot/XP or re-roll
events. A fountain must not be an unlimited heal; give it charges (1–2) or a
once-per-floor effect. A killed merchant stays gone for the run.

---

## 8. Superbosses and milestone floors

### 8.1 Current behavior

- Wonderland F10/20/30/40/50 and generic every-20th floors trigger **before** the
  normal room loop, first time only.
- Victory advances the floor and returns; no normal rooms happen on that visit.
- Replays after `max_floor` advances are normal floors.
- Generic superbosses require `city_prog["max_floor"] <= floor`. Because biome
  depth is shared, entering floor 20 from a second city after the biome is
  already at 30 **skips** the floor-20 superboss. This is a pre-existing issue.

### 8.2 Floor-type taxonomy

Do not keep the pre-floor trigger and also add a graph boss on the same floor —
that either wastes the graph or creates two bosses. Pick one terminal encounter
per floor.

**Locked: every milestone floor gets a compact approach graph.** The boss
encounter itself remains the existing scripted fight for story bosses.

| Floor type | Graph | Terminal encounter |
|---|---|---|
| Normal floor | Full graph | Normal boss |
| Milestone first clear (generic every-20th, WL F10–F50, Pande F20/F40) | Compact approach graph (6–10 nodes; spine 4–6) | Superboss or scripted milestone boss |
| Replay of a defeated milestone | Full graph | Normal boss |

Recommended:

- Use **explicit per-floor/per-boss flags** for milestone defeats, not
  `max_floor <= floor`. This fixes the shared-depth skip and lets the graph
  generator choose the right profile at entry.
- Compact approach profile: `N_cap = 8–10`, `spine = 4–6`, `branch = 0.3–0.5`;
  guarantee a fountain near the boss.
- The boss node is the only exit. Defeat advances the floor; death uses the
  normal death path. Combat flee from a normal boss returns to the previous node
  (boss room stays uncleared); superbosses remain no-flee.
- Do not double-charge time: the current superboss loops call `advance_time(60)`
  before an attempt. If the boss becomes a node, the node-entry cost replaces
  it.

---

## 9. Save data and storage

Measured against real saves (2026-11-11):

| Item | Size |
|---|---|
| `savegame_1.json` | ~427 KB |
| `savegame_4.json` | ~216 KB |
| Active-floor snapshot (10 rooms, pre-rolled enemies, pretty JSON) | 0.7–1.6 KB |
| 24-node / 29-edge graph + visited/cleared/current state | ~2 KB compact, ~4 KB pretty |
| Same graph with pre-rolled enemies (estimate) | ~6–12 KB |
| Event Horizon state in `savegame_1` | ~61 KB |

**One active graph is negligible** — roughly 1–3% of a typical save. The bloat risk
is persisting a graph for every floor or entrance. Do not do that.

Recommended save model:

- Persist only the active graph: `player["dungeon_graph"]`.
- Store topology, node types, `visited`, `cleared`, `current`, fountain charges,
  merchant state, and the half-block credit.
- Include `run_id` and `graph_version` so code changes cannot silently
  reinterpret old maps.
- **Preserve on save-exit**; include `floor`, `current`, `visited`, `cleared`,
  fountain/merchant state, `move_credit`, and resume metadata.
- Wipe on floor clear, flee-to-city, and death.
- Do **not** persist per-floor history or regenerate-and-store cleared floors.
- A seed-only save (seed + mutable state) is tiny but brittle: a generator change
  mid-run alters the map. A compact snapshot is stable and cheap; prefer it.
- Pre-roll enemy groups on node entry, not for every node, if size matters; the
  map only needs node types.

`save_game()` uses `indent=2`, so disk size is roughly 2× the compact size. The
graph is still noise compared with inventory, Event Horizon state, and the
persisted dungeon log.

---

## 10. GUI and navigation

The current Map panel is a 5×2 ASCII grid, not a general graph renderer. Reuse the
panel and `_tmenu` buttons, but add a new renderer.

### 10.1 Layout budget and party capacity

The current screen spends too much space on overhead and gives the log roughly
75–80% of the width. The map then gets about 460×160 px, which cannot hold a
336 px Canvas plus node info. The revision below is a **space budget**, not a
pixel-perfect spec — tune the numbers in playtest.

**Recommended wireframe — Map left; Log + Party right; Actions full-width bottom.**

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TOP HEADER — DUNGEON NAME · Floor 7 · Coastal · time · fatigue · [Flee] ⚙  │
├───────────────────────────────┬──────────────────────────────────────────────┤
│ MAP CANVAS                    │ DUNGEON LOG                                  │
│ (~600 px wide at 1917)        │ (~1313 px wide; ~459 px before party shrink) │
│                               │                                              │
│                               │                                              │
│                               ├──────────────────────────────────────────────┤
│                               │ PARTY STATUS — 4 cols × 2 rows (~150 px)     │
│                               │ [P ] [A1] [A2] [A3]                          │
│                               │ [A4] [A5] [A6] [A7]                          │
├───────────────────────────────┴──────────────────────────────────────────────┤
│ ACTION GRID — constant 3 rows (~190 px incl. prompt)                        │
│ [Node A · 1b] [Node B · 0.5b] [Back · 0.5b]                                 │
│ [ ... ] [ ... ] [ ... ]                                                     │
│ [ ... ] [ ... ] [ ... ]                                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

The map panel's node-info/route/reward line sits inside the left column, under
the Canvas. **Flee lives in the top header's right corner**, not the action grid.

**Budget.**

| Region | Target (1917×992 reference) | Rule |
|---|---|---|
| Top header | ~36 px | Name/floor/region + time/fatigue + Flee + gear |
| Main row | ~700 px | map left; log + party right |
| Columns | left ~600 px (~31%), right ~1313 px (~69%) | left min ~400 px |
| Map panel | left, full main-row height | canvas width-limited to ~590 px; info panel below |
| Dungeon log | right top | ~459 px before party shrink; ~549 px after |
| Party panel | right bottom, content-sized ~140–150 px | 4 columns × 2 rows; no separator labels |
| Action grid | full-width bottom, constant ~190 px | 3 rows; prompt fixed; overflow scrolls |

**Worked budget (1917×992 reference).** Map column ~600×700; log ~1313×459
before the party strip shrinks, ~1313×549 after it drops from ~239 to ~150;
party ~1313×150; action grid ~190. The 8×8 canvas is width-limited to ~590 px
(cell ≈70), leaving ~80 px below for node info/routes/reward. Cap the node
radius at 18–20 px and let the spacing grow.

**Overhead trims.**

- The 3-line header repeats the top bar and reprints the craft hint already in
  the log. Move the name/floor/region into the top bar and remove the separate
  header. The craft hint goes into the first log line or the node-info status
  line.
- The button panel currently reserves a fixed `height=180` canvas even for one
  button. Replace it with a **constant 3-row action grid**: the prompt stays in
  the same spot, normal menus use 3 rows, and long menus (merchant lists)
  scroll. This prevents the map from resizing/redrawing whenever the menu
  height changes.
- Put **Flee to City** in the top header's right corner and keep the `f` key.
  It ends the run and wipes the graph, so it should not move between menus.
- The current button panel replaces the text-input row, which changes the
  available map height. Unify the prompt/input/button area into the fixed
  action grid so the middle band never jumps.

**Party capacity (important).** Stat checks can select **all 8 units** (player +
7 allies), not just the 3 front-row cards shown in the old mock. The Party
Status panel must support the full roster:

- Use 4 columns × 2 rows: row 1 = player + front, row 2 = back/bench. At the
  maximum 4+4 split this carries the grouping without FRONT/BACK separator
  labels.
- Size the strip to its content (~140–150 px for two rows), not the ~239 px in
  the sketch; give the spare ~90 px to the log.
- Stretch each HP bar to the card width (~300–330 px at 1917); the current
  fixed 130 px bar wastes the card.
- Keep the vertical scrollbar for smaller rosters / small windows.
- The stat-check button menu should use the same 8-unit roster in the 3-row
  action grid, with overflow scrolling.

**Why the log keeps its width.** The map is not too big: at 1917×992 the
left column is ~600 px and the canvas is ~590 px square. The log keeps its
~1313 px width and gains height when the party strip shrinks to content. The
left column should still have a **min width (~400 px)** so the Canvas does not
collapse on smaller windows.

**Wide graphs and small windows.** Seven of the 15 profiles run left→right and
may use fewer than 8 rows. Do not center the canvas in a large empty box; top-
align it and give the remaining height to the info panel (routes from P, reward
multiplier, node details). At ~1280×720 the map column is ~400 px (cell ≈45) and
only a line or two fits underneath, so move the legend to a hover/status line.
For smaller windows, give the header, party strip, and action grid `weight=0`
(content-sized) and let only the middle band stretch.

#### Header integration comparison

**A — Separate dungeon header.**

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR — time · fatigue · [Flee] · settings                                │ 28
├──────────────────────────────────────────────────────────────────────────────┤
│ DUNGEON HEADER — name · region/floor · craft hint                            │ 28–60
├───────────────────────────────┬──────────────────────────────────────────────┤
│ MAP CANVAS                    │ DUNGEON LOG                                  │
│                               │                                              │
│                               ├──────────────────────────────────────────────┤
│                               │ PARTY STATUS — 4 cols × 2                    │
│                               │ [P ] [A1] [A2] [A3]                          │
│                               │ [A4] [A5] [A6] [A7]                          │
├───────────────────────────────┴──────────────────────────────────────────────┤
│ ACTION GRID — constant 3 rows                                              │
│ [Node A] [Node B] [Back]                                                    │
│ [ ... ] [ ... ] [ ... ]                                                     │
│ [ ... ] [ ... ] [ ... ]                                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

**B — Dungeon header integrated into the top bar (preferred).**

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TOP HEADER — DUNGEON NAME · Floor 7 · Coastal · time · fatigue · [Flee] ⚙  │ 36
├───────────────────────────────┬──────────────────────────────────────────────┤
│ MAP CANVAS                    │ DUNGEON LOG                                  │
│                               │                                              │
│                               │                                              │
│                               ├──────────────────────────────────────────────┤
│                               │ PARTY STATUS — 4 cols × 2                    │
│                               │ [P ] [A1] [A2] [A3]                          │
│                               │ [A4] [A5] [A6] [A7]                          │
├───────────────────────────────┴──────────────────────────────────────────────┤
│ ACTION GRID — constant 3 rows                                              │
│ [Node A] [Node B] [Back]                                                    │
│ [ ... ] [ ... ] [ ... ]                                                     │
│ [ ... ] [ ... ] [ ... ]                                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Comparison.**

| | A: separate header | B: integrated header |
|---|---|---|
| Top bar/header | ~28 px + 28–60 px | ~36 px total |
| Main row | ~700 px | ~720–760 px |
| Map canvas height | ~700 px | ~720–760 px |
| Log height | ~549 px | ~570–600 px |
| Party strip (right) | ~150 px | ~150 px |
| Action grid (full width) | ~190 px | ~190 px |
| Log width | ~69% | ~69% |
| Party | 4×2 cards | 4×2 cards |

**Opinion.** Use B. The separate header duplicates the top bar (dungeon name,
floor) and repeats the craft hint already in the log. Integrating it is a modest
vertical win — about 20 px versus a one-line header, 50–60 px versus the current
three-line header — but it is free information-wise.

The full-width action grid matches the current format and should keep a
constant 3-row height so the map never resizes between menus. Flee belongs in
the header's right corner — it ends the run and wipes the graph, so it should
not move. The party strip is 4×2 and content-sized (~150 px), not the ~239 px
sketch; stretch the HP bars to the card width. At 1917×992 the map column is
~600 px and the canvas ~590 px square, which is a good size, not too big.

For wide graphs, top-align the canvas and give the leftover height to the info
panel. At ~1280×720 the map column is ~400 px (cell ≈45); move the legend to a
hover/status line and keep the header/party/action grid content-sized so only
the middle band stretches.

**Top-bar plumbing.** `DungeonScreen.build_ui` already sets the shared top line
and `_update_top_bar` refreshes it with the time track. Remove `header_frame`,
and make `_set_subtitle` update the top line (or a compact second segment) so
wild/EH floor changes still refresh. Put the craft hint in the first log line or
the map status line.

### 10.2 Example map

```text
        FLOOR 7 — COASTAL

   S ── P ─┬── F ── $ ──┬── B
           ├── M ── ? ──┤
           └── n ── ? ── C ─┘

   [P] You      [S] Entry     [n] Cleared
   [C] Combat   [F] Fountain  [M] Merchant
   [$] Treasure [B] Boss      [?] Unknown
   Next: S — 0.5b (cleared) · F/M/n — 1b (new)
   Routes from P:  M → ? → B (3b) · F → $ → B (3b)
                   n → ? → C → B (4b)
```

`P` can backtrack to the entry (`S`), take the fountain route (`F → $`), push
straight through the merchant route (`M → ?`), or take the longer cleared-event
route (`n → ? → C`). All three routes terminate at the boss; the map never
creates a bypass. Types are shown here for illustration; in-game unvisited nodes
start as `?` until entered or left.

The current Map panel is 24×7 characters, so the final graph view uses an
expanded Canvas panel. The ASCII form remains the test/debug renderer; clickable
Canvas nodes are the shipping UI.

- Render layered nodes with glyphs (`?`, `C`, `N`, `$`, `M`, `F`, `B`) and edge
  lines; highlight the current node; distinguish cleared/visited/unknown.
- Store `layer` and `row` in the graph data so rendering is deterministic.
- Movement buttons: one per adjacent node, labelled with type and cost, e.g.
  `Combat · 0.5 block`, `Fountain · 0.5 block`. Include visited nodes for
  backtracking.
- Output-panel feedback after each move: time spent, node entered, result.
- Show the full node layout and edges from the start, but hide node types.
  Unvisited nodes render as `?`; reveal the type when the node is entered or
  left, and keep it visible for the rest of the run.
- Canvas is the final renderer; keep the ASCII map for tests/debugging. Buttons
  remain the canonical input; clicks are a shortcut.
- Combat's `Room x/y` label needs to become `Node x/y` or hide the denominator.
- Event Horizon keeps its "Rift" status panel; wild dungeons keep their current
  branding.

### 10.3 Canvas renderer

A `tk.Canvas` is the right widget for the graph: it draws lines, shapes, text,
and hitboxes in one 2D coordinate system. The world map already uses this pattern
in `world_map_screen.py`:

- `create_line()` for routes
- `create_rectangle()` / `create_text()` for nodes and labels
- `canvasx()` / `canvasy()` for hit-testing after panning
- `scrollregion` for drag-panning
- `itemconfig()` / `tag_raise()` for cheap state updates

The dungeon map is smaller than the world map and does not need panning at 8×8,
but the same mechanics apply.

**Widget and layout.**

- Use a `GraphMapView` container that can show either a `tk.Text` or a
  `tk.Canvas`. PDG floors use the Canvas; Event Horizon keeps its Text status
  panel; the linear fallback (wild dungeons until Phase 5) keeps the ASCII Text
  map. Do not delete the Text path.
- The current `DungeonScreen._run_facility` monkey-patches
  `dungeon_rooms.render_ascii_map`; add a parallel `render_graph_map(graph,
  player)` hook or call a screen callback from the graph loop. Keep the same
  `after(0, ...)` marshalling.
- Use a fixed/min-width left column (~600 px at 1917, min ~400 px) and let the
  log/party column take the rest (~1313 px at 1917); see §10.1.
- Put the legend, route costs, and node info in a flexible info panel **below**
  the Canvas, not inside it. Top-align the Canvas; for wide graphs that use
  fewer than 8 rows, give the leftover height to the info panel instead of
  centering the map in empty space.
- Below a minimum cell size (~28 px), open an expand-map overlay
  (`push_overlay`, same pattern as combat) or enable world-map style drag-pan.
  Do not shrink the glyphs into illegibility.

**Coordinate formula.** Use the bounding box of occupied cells, not the full
8×8:

```text
MARGIN = 16

cols = max_col - min_col + 1
rows = max_row - min_row + 1
CELL = clamp(min((w - 2*MARGIN) / cols,
                 (h - 2*MARGIN) / rows), 28, 70)
R    = min(20, max(12, CELL * 0.28))

center(col, row):
    x = MARGIN + (col - min_col) * CELL + CELL / 2
    y = MARGIN + (row - min_row) * CELL + CELL / 2

cell_at(x, y):
    col = min_col + floor((x - MARGIN) / CELL)
    row = min_row + floor((y - MARGIN) / CELL)
```

At 1917×992 the map column is ~600 px, so the canvas is width-limited to
~590 px and `CELL ≈ 70`; at 1280×720 it is ~400 px and `CELL ≈ 45`. Do not
scale the node radius with the cell — cap it at 18–20 px and let the spacing
grow. At most 24 of 64 cells are used, so fitting the occupied bbox gives much
larger cells than dividing by 8. Keep the debounced `<Configure>` event
(~50 ms). At small widths move the legend to a hover/status line; if
`CELL < 28`, use the overlay/pan fallback above.

**Drawing order.**

1. Background grid (optional; subtle lines every `CELL` pixels).
2. Edges (`create_line`) — draw before nodes so nodes cover the endpoints.
3. Nodes (`create_oval` or `create_rectangle`) plus glyph (`create_text`).
4. Current-player ring (gold outline).
5. Reachable-node highlight (outer glow or brighter outline).
6. Legend and tooltip text.

Use tags for cheap updates:

- `tags=("node", f"node:{node_id}")` on both the shape and the glyph.
- `tags=("edge", f"edge:{a}:{b}")` on each edge.
- `tags=("player",)` on the current ring.

**Node styling.**

| Type | Fill | Glyph |
|---|---|---|
| Combat | `#c0392b` | `C` |
| Elite | `#8e44ad` | `E` |
| Fountain | `#16a085` | `F` |
| Merchant | `#f1c40f` | `M` |
| Treasure | `#9b59b6` | `$` |
| Event | `#3498db` | `N` |
| Connector | `#7f8c8d` | `·` |
| Boss | `#e94560` | `B` |
| Unknown | `#2d3436` outline | `?` |

Cleared nodes use a desaturated fill and a thin outline; unknown nodes use a
dashed outline; the current node gets a thick gold outline; the boss is slightly
larger (`R + 4`).

**Input and redraw flow.**

- The dungeon runs in a background thread; the Canvas lives on the main thread.
  Never call Canvas methods from the dungeon thread. Schedule updates with
  `self.after(0, ...)` exactly like the current `_update_map()`.
- Snapshot `visited`, `cleared`, `current`, and node types before `after(0, ...)`,
  like `_update_party` does. Never pass the live graph dict to the main thread.
- On click: `x = canvas.canvasx(event.x)`, `y = canvas.canvasy(event.y)`; compute
  `col/row`; look up the node id. If it is adjacent to the current node, call the
  same handler as the movement button (`_on_button_choice(index)`) rather than
  the dungeon logic directly.
- On hover: highlight the node and set `cursor="hand2"`; show its type/known
  info in the output panel or a small tooltip.
- Keyboard: the existing number-key button handler keeps working; Canvas clicks
  are an optional shortcut.
- Redraw strategy: full redraw on floor generation; after a move, use
  `itemconfig()` to update fills/outlines and move the player ring. Keep
  `node_items` / `edge_items` maps so updates do not rebuild the whole canvas.

**Minimal pseudocode.**

```python
CELL, MARGIN, R = 70, 16, 20  # production: CELL from bbox; R capped at 20

def center(col, row):
    return (MARGIN + col * CELL + CELL // 2,
            MARGIN + row * CELL + CELL // 2)

def draw_graph(canvas, graph, current):
    canvas.delete("all")
    for a, b in graph["edges"]:
        x1, y1 = center(*graph["nodes"][a]["cell"])
        x2, y2 = center(*graph["nodes"][b]["cell"])
        canvas.create_line(x1, y1, x2, y2, fill="#4a5568", width=2,
                           tags=("edge", f"edge:{a}:{b}"))
    for nid, node in graph["nodes"].items():
        x, y = center(*node["cell"])
        canvas.create_oval(x - R, y - R, x + R, y + R,
                           fill=NODE_COLORS[node["type"]],
                           outline="#2d3436", width=2,
                           tags=("node", f"node:{nid}"))
        canvas.create_text(x, y, text=NODE_GLYPHS[node["type"]],
                           fill="#111", font=(Theme.FONT_FAMILY, 10, "bold"),
                           tags=("node", f"node:{nid}"))
    x, y = center(*graph["nodes"][current]["cell"])
    canvas.create_oval(x - R - 4, y - R - 4, x + R + 4, y + R + 4,
                       outline="#f1c40f", width=3, tags=("player",))

def on_click(event):
    x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
    col = int((x - MARGIN) // CELL)
    row = int((y - MARGIN) // CELL)
    node_id = graph["cell_index"].get((col, row))
    if node_id in graph["reachable"]:
        screen._on_graph_move(node_id)   # maps to the active button index
```

---

## 11. Existing hooks and code anchors

These must be re-anchored explicitly. Recommended: first entry only, and tick
by time rather than node count.

| Hook | Current anchor | PDG rule |
|---|---|---|
| Pandemonium sapping aura | Room entry | First entry per node, scaled to block time |
| Wonderland curiosity/shadow effects | Room entry | First entry per node |
| Arcane blessing consumption | Room entry | Per block or per 2 nodes |
| Hallucination roll | Per room | Per block / per 2 nodes |
| Sleep buffs | Per room clear | Per block |
| Wedding bark-shield counter | Per room clear | Per block / normalized |
| Bounty counters | Per enemy kill | Unchanged (kill-driven) |
| Quest room counters | Per room | Normalize to block time if the quest is time-tuned |
| Curse / quirk / shadow choice | Floor entry | Floor entry |
| Normal boss "Empowered" buff | `combat_engine` when `room_num == total_rooms` | Pass equal values when entering the boss node, or add an explicit boss flag |
| Floor advance | Boss room / superboss victory | Boss terminal node |

Other code anchors:

- `pandemonium/world/dungeon.py` — `generate_floor()`, `explore_dungeon()`,
  `saved_dungeon_*`, superboss blocks.
- `pandemonium/world/dungeon_rooms.py` — room handlers, `render_ascii_map()`,
  `handle_fountain_room()`, `handle_merchant_room()`.
- `pandemonium/gui/screens/dungeon_screen.py` — Map panel, `_gui_render`,
  `_tmenu` button panel, combat override.
- `pandemonium/gui/screens/city_screen.py` — `_launch_dungeon()` clears
  `saved_dungeon_*`; floor selection.
- `pandemonium/combat/combat_engine.py` — floor-boss empowerment.
- `pandemonium/core/time_blocks.py` — `advance_time()`, `blocks_for_minutes()`,
  `spend_blocks()`.
- `pandemonium/progression/karma.py` — `is_enabled()`, `change_karma()`.
- `pandemonium/facilities/travel_events.py` — merchant pricing helpers.
- `pandemonium/core/save_load.py` — load always resumes in a city.

Wild dungeons and Event Horizon have their own loops and state (`_explore_wild_dungeon`,
`_explore_event_horizon`). Leave them on their current paths until Phase 5; wild
dungeons adopt the compact PDG profile, while Event Horizon remains separate.
Do not swap `generate_floor()` globally.

---

## 12. Implementation phases

| Phase | Scope |
|---|---|
| 0 | This design doc; decisions locked 2026-11-12. |
| 1 | `dungeon_graph.py`: generator, invariants, traversal loop for city dungeons only, behind a flag; reward scaling; keep the linear path as fallback. |
| 2 | Layout revision (integrated header + Flee, constant 3-row action grid, ~600 px left column, content-sized 4×2 party strip) + save-exit persistence + Canvas renderer (ASCII test renderer) + movement buttons + resume flow. |
| 3 | Node content expansion: connector nodes, fountain charges, Karma merchant robbery/attack. |
| 4 | Per-biome profiles + compact approach graphs for all milestones + explicit milestone flags. |
| 5 | Wild dungeon adoption at smaller scale (`N_cap = 14`); Event Horizon remains separate. |

Suggested new modules:

- `pandemonium/world/dungeon_graph.py` — generation, traversal, profile hooks.
- `pandemonium/world/dungeon_graph_render.py` — ASCII test renderer + Canvas widget helper.
- `pandemonium/resources/dungeon_graph_profiles.py` — data-driven profiles.

Keep the existing `dungeon_rooms` handlers as the content layer. Keep
`generate_floor()` as the linear fallback (and for wild dungeons until Phase 5).

---

## 13. Testing plan

- **Generator invariants:** hundreds of seeds × each profile: connected, boss
  reachable, every node can reach boss, degree bounds, no duplicates, guaranteed
  fountain/merchant, node count within `[N_min, N_cap]`.
- **Grid occupancy:** confirm edges do not consume cells; only nodes occupy the
  8×8 layout; edge count stays within the degree bound.
- **Time budget:** Monte Carlo shortest/median/longest path cost; assert the
  average is within the target band (~10–12 blocks for normal floors).
- **Reveal rules:** layout/edges visible from the start; types hidden until
  entered or left; combat flee reveals `C` and leaves the room uncleared;
  revealed types stay visible.
- **Revisit/flee:** cleared node gives no reward; movement still costs; fountain
  charges deplete; merchant stays dead for the run; combat flee returns to the
  previous node; flee-to-city wipes; death wipes.
- **Reward scaling:** `cleared_ratio` drives boss gold/XP and floor-clear healing;
  a rush route pays less than a full clear; per-node rewards are not double-paid.
- **Boss terminal:** entering boss is the only exit; normal boss empowerment
  applies; reward scaling works.
- **Superboss:** milestone flags, first-time vs replay, shared-depth no longer
  skips, compact approach graph on every milestone, no double time charge.
- **Wild:** smaller-scale graph (`N_cap = 14`) uses the same invariants and
  reward rules.
- **Karma:** steal/attack choices apply Karma on commit, not on success; Karma-off
  hides the moral options.
- **Save round-trip:** save-exit preserves graph + cleared/visited/current +
  half-block credit and resumes the same node; flee/death/floor-clear wipe it;
  old saves with `saved_dungeon_*` do not crash.
- **GUI smoke:** Canvas renders a branched graph with hidden types; movement
  buttons work; ASCII test renderer matches the same graph; combat label is
  correct.
- **Regression:** full pytest suite; old-save smoke test read-only.

---

## 14. Decision log and remaining tuning

### 14.1 Locked 2026-11-12

1. **Traversal:** undirected normal, directed Pandemonium, portal Wonderland.
2. **Time:** 0.5 edge + 0.5 node.
3. **Rush control:** scale floor/boss rewards and floor-clear healing with
   cleared nodes; no boss seal in v1.
4. **Lifetime:** run-scoped + save-exit persistence; flee-to-city, death, and
   floor clear wipe.
5. **Milestones:** compact approach graph for all milestones; scripted boss
   encounter for story bosses.
6. **Reveal:** show layout/edges; hide node types until entered or left.
7. **Node weights:** keep existing `ROOM_TYPE_WEIGHTS` and non-combat
   escalation; connectors added by the generator.
8. **Flee:** combat flee returns to the previous node; flee-to-city leaves the
   map; death retreats to the city.
9. **Wild:** adopt PDG at smaller scale (`N_cap = 14`).
10. **Room cap:** hard cap 24 nodes.
11. **Renderer:** Canvas final; ASCII for tests/debugging.

### 14.2 Remaining tuning details

- Exact `reward_mult` curve and floor-clear heal curve.
- Exact layout proportions, left-column min width (~400 px), and the 4-column
  party breakpoint.
- Header placement: integrated top bar (preferred) vs one-line header.
- Flee placement: top header right corner (preferred) vs action grid.
- Action grid: constant 3-row height (~190 px) with overflow scrolling.
- Party strip: content-sized ~140–150 px, stretched HP bars, and whether
  FRONT/BACK separator labels remain at the 4+4 split.
- Party placement: under the log in the right column (default) vs a 2×4 grid
  or scrollbar in the same panel for narrow windows.
- Stat-check button grid for the full 8-unit roster.
- Save-exit resume UX: explicit Resume/Abandon prompt vs auto-resume.
- Reveal timing: type shown on entry, on leaving, or both; whether combat flee
  reveals it immediately.
- Edge rendering: straight orthogonal lines vs curved portal/diagonal links.
- Connector-node insertion order and whether connectors can be combat-free.
- Wild dungeon graph profile: entry/boss rule and boss-floor integration.

---

## 15. Non-goals

- Floor-to-floor stairs / multi-floor graph runs.
- Persistent graphs across voluntary city visits; save-exit is the only
  persistence.
- Replacing Event Horizon's endless-room loop.
- Reworking combat, loot tables, or enemy scaling as part of this change.
- Changing the global block-cost table.
