# Seasonal Map Boss — The Wardens of the Long Day

> **Status:** ✅ **SHIPPED - Phases 1-5 complete (2026-11-13).**
> The Warden spawns, appears on the world map, travels, offers the recalled
> depth and **fights**: the projected arena clock, the three phases with a
> Dawn Lull, the seasonal adds and all four seasonal mechanics (Bloom, Heat,
> Harvest, Frostbite) with their ten-effect ladders are live. HP persists
> across flee/death, a kill reforms the next Echo, and the whole fight is
> committed as one time batch on exit. Every kill pays gold/XP, a cache, two
> consumables and flowers, and the four unique trophies land at 1/3/6/10
> lifetime victories. Docs (README + regenerated wiki), the in-game changelog
> and a scripted season playtest are in place; the numbers below §13.5 remain
> first-pass tuning targets for a live playtest.
>
> **Rev 2 (2026-11-13, superseded by Rev 3):** Floor-20 clear gate, immediate
> first spawn, monthly replacement, and +20 boss levels per Echo.
>
> **Rev 3 (2026-11-13):** player clarification — Echoes respawn on **death**
> within the same season; the monthly boundary swaps in a **new seasonal
> Warden** with its own name, element, weakness and mechanic.
>
> **Rev 4 (2026-11-13):** the calendar is now a **360-day year** (12 × 30-day
> months), so a season — and a Warden — lasts **90 days**; added **start at
> proven depth** (enter the arena at the highest Echo you have ever cleared
> instead of re-climbing from 0).
>
> **Rev 5 (2026-11-13):** Phase 1 implemented — see §13 for the shipped API.
> One addition while wiring it: `advance_echo(player, killed=…)` takes the
> site that was actually killed, so a season boundary crossed during the arena
> time commit cannot spawn two Wardens.
>
> **Rev 6 (2026-11-13):** Phase 2 implemented — world-map marker/panel/travel,
> start-depth dialog, expiry grace, arena branding and result routing (see
> §13.2). The arena's fight loop is still Phase 3: `explore_dungeon` dispatches
> to an interim guard that returns `"map_boss_locked"`, which the world map
> turns into an explanatory window and a clean return to the city.
>
> **Rev 7 (2026-11-13):** Phase 3 implemented — the arena loop (§13.3).
> `superboss_combat_loop` gained the optional `pre_round_hook(context, enemies)`
> that runs **before** the round header; every existing superboss passes `None`
> and is unchanged. The interim `"map_boss_locked"` guard is gone: entering the
> arena now fights the Warden.
>
> **Rev 8 (2026-11-13):** Phase 4 (rewards + four uniques) and Phase 5 (polish)
> shipped — see §13.4 and §13.5. Three notes for the record: the unique
> convention normalizes the four trophies' stats to the slot budget and
> collapses their authored element pairs to one identity element (flowers refill
> the other two slots); the victory journal entry is named
> `Warden Felled — {Season} Echo {n}` per §10.6; and `tests/gen_wiki_html.py`
> had stale pre-package paths, so regenerating `wiki/index.html` is part of the
> build again.
>
> **Builds on:** [`wild_dungeon_design.md`](./wild_dungeon_design.md) (world-map
> site / travel / flee structure), [`time_system_design.md`](./time_system_design.md)
> (24-block day, Morning/Noon/Night), [`item_economy_tuning_design.md`](./item_economy_tuning_design.md)
> (rarity/value), [`rarity_grade_flower_audit.md`](./rarity_grade_flower_audit.md)
> (grades + flower infusions), [`white_knight_design.md`](./white_knight_design.md)
> (boss-drop unique pattern).
>
> **Backlog link:** `Pandemonium_Open_Improvements.md` §7 — "World event layer:
> temporary special dungeon or roaming world boss."

---

## 0. Summary

A recurring **world-map boss** that uses the wild-dungeon site structure: one
marker on the world map, off-road travel, a single arena encounter, flee to the
nearest city, previewable loot, and journal entries.

- **Unlock:** the player must have **cleared Floor 20 at least once**
  (`player["max_floor"] > 20`, the same gate as the Event Horizon). The raid
  cannot spawn before that.
- **First spawn:** the **current season's Warden**, Echo 0, immediately when the
  gate is met (the next `maybe_spawn` check).
- **Echo loop within the season:** every time the Warden dies, the **next
  stronger Echo respawns immediately** at the same site — +20 levels, more HP,
  a new mechanic effect, more resistances and a stronger seasonal loop. This repeats
  as long as the season (90 days) has not changed.
- **Season rotation:** on the **first day of each season** (days 1/91/181/271 in
  the 360-day calendar), the current Warden is replaced by the **next season's
  Warden** at Echo 0 — new name, element, weakness, mechanic and site. The Echo
  cycle resets.
- **Start at proven depth:** on arrival you may begin at the highest Echo you
  have **ever defeated** instead of Echo 0 — a one-way jump that skips
  re-climbing the ladder, never a re-fight and never extra power (§5.7).
- **Four seasonal Wardens:** Spring (Bloom), Summer (Heat), Autumn (Harvest),
  Winter (Frostbite). Each has its own name, element and signature mechanic.
- **Every combat round = 1 time block.** The boss is Dormant in the Morning,
  Stirs at Noon, Rampages at Night, then resets at dawn.
- **Flee is always allowed.** The current Echo's HP is saved; the next Echo
  only appears after a kill, never after a flee.
- **One active Warden at a time.** It is an overworld-only encounter — not a
  superboss-pool member, not capturable, and not reachable during Pandemonium,
  Wonderland or Event Horizon runs.

The design tension is simple: the Warden is the one enemy that **gets stronger
with the calendar instead of with you**. Each season is a new raid; each death
within it is a new, stronger incarnation.

---

## 1. Decision log (locked 2026-11-13)

1. **Structure:** wild-dungeon-style world-map site + off-road travel + nearest
   city on flee/death. **One arena encounter, no floors.** Re-clearing trash
   between attempts would punish the flee/retry loop that the HP persistence
   exists to support.
2. **Unlock gate:** the player must have **cleared Floor 20 at least once**
   (`player["max_floor"] > 20`). Merely reaching Floor 20 is not enough — the
   same rule the Event Horizon uses.
3. **First spawn:** the **current season's Warden**, Echo 0, immediately when
   the gate is met. The first season may be partial if Floor 20 is cleared late;
   with 90-day seasons that is a minor loss of runway, not a lost raid.
4. **Death = next Echo:** within the same season, killing the Warden immediately
   spawns its next Echo at the same site — +20 levels, more HP, a new mechanic
   effect, more resistances and a stronger seasonal loop. The player does not wait for
   the season to change.
5. **Season rotation:** on the **first day of each season** — days 1/91/181/271
   of the 360-day calendar (`events.next_season_day`) — the current Warden is
   replaced by the **next season's Warden** at Echo 0 — new name, element,
   weakness, mechanic and site. The Echo cycle resets.
6. **Levels:** `level = min(80, 20 + 20 * echo)` within the season. After level
   80, HP/resists/mechanic tier/rank keep growing.
7. **HP persistence:** saved per active Echo. Flee/death keep the current Echo's
   HP; a kill spawns the next Echo at full HP; a season change resets everything.
8. **Flee is always allowed**, including at 1% HP. Fleeing saves HP progress,
   spends the elapsed time, grants no loot, and returns the party to the nearest
   city.
9. **Time model:** every round consumes **1 block (60 minutes)**. The arena
   clock is **projected** during the fight and committed in one batch on exit.
   No day-rollover side effects fire mid-combat.
10. **Phase aggression:** Morning = Dormant, Noon = Stirring, Night = Rampage,
    Morning = reset + 2-round Dawn Lull. The boss explicitly **turns back to
    normal at dawn**.
11. **Escalation:** each Echo gains levels, HP, damage, armor, elemental
    resistance, status resistance, one new mechanic effect and a higher
    mechanic rank. One seasonal weakness never scales, and all resistances cap —
    counterplay remains.
12. **Seasonal identity:** four named Wardens, each with its own element,
    weakness, biome preference and signature mechanic (§5.5/§6.6).
13. **Drops are locked** in §8: gold/XP, Warden's Cache, consumables, a
    guaranteed flower, and four uniques at 1/3/6/10 total victories. Every Echo
    kill grants the full table; the next Echo is stronger. After all four
    uniques, the unique slot becomes a second cache.
14. **No superboss rewards / ledger / pool / shards.** The Warden records a
    bestiary entry and its own defeat counter, nothing else.
15. **Overworld only.** It cannot be reached during Pandemonium, Wonderland or
    Event Horizon runs, and those modes cannot reach the world map.
16. **Start at proven depth:** the arena offers the highest Echo ever defeated
    (`best_echo`) as an entry point. It sets the season's active Echo without
    re-fighting anything; the Echo is built from its own index at full HP, and
    Echo 0 stays available as a warm-up. Never a repeatable fight (§5.7).

### Interpretation note (explicit)

The clarified request locks the following:

- **Gate:** the raid starts only after the player has **cleared Floor 20 once**
  (`max_floor > 20`).
- **"assume a new echo":** a **death inside the same season** immediately
  spawns the next, stronger Echo. The Warden keeps escalating until the season
  changes.
- **"until the new warden replaces the old":** the season deadline does not
  wait for a respawn after a kill. On the first day of the next season (every
  90 days), the **next seasonal Warden** replaces the current one at Echo 0 and
  the cycle repeats.
- **Seasonal naming:** each Warden's name, element, weakness and mechanic follow
  the season (§5.5/§6.6).

---

## 2. Fantasy & naming

**Umbrella name:** **The Wardens of the Long Day** (short: **the Wardens**).
**Event title:** **"The Season Turns — a Warden Stirs."**

| Season | Warden | Marker |
|---|---|---|
| Spring | **Warden of the First Bloom** | `🌱` |
| Summer | **Warden of the Long Noon** | `🔥` |
| Autumn | **Warden of the Falling Crown** | `🍂` |
| Winter | **Warden of the Last Light** | `❄` |

> When the first sundial was cast, something learned to drink the hours. It
> surfaces at every new season, wearing the season like a coat. Each time it
> returns it has swallowed another month — and it remembers every shape it has
> worn.

It is not a monster guarding treasure. It is an **hour the world owes**, given
a body. That is why it returns, why it gets stronger every spawn, and why
fighting it consumes real time: every round you spend is another hour it drinks.

Voice/lore lines (first pass):

- **Spawn:** "A **{warden_name}** has surfaced near **{city}**. The season turns."
- **Spring intro:** "The Warden of the First Bloom unfolds — every root is a
  finger, and the air is thick with green."
- **Summer intro:** "The Warden of the Long Noon stands in the white heat. The
  air bends around it like a held breath."
- **Autumn intro:** "The Warden of the Falling Crown walks through a storm of
  its own leaves. Each one is a year it has taken."
- **Winter intro:** "The Warden of the Last Light exhales, and the frost answers."
- **Morning:** "Dawn. The stolen hours run out of it like water — for a moment
  it is only a tired thing."
- **Noon:** "Noon. The Warden stirs, and the light bends around it."
- **Night:** "Night. The Warden rampages. The dark belongs to it."
- **Flee:** "You break away. It does not follow — it has all the time it needs."
- **Victory / reform:** "The Warden collapses into spent hours — then the hours
  run backward, and it stands again, older and stronger."
- **Season departure:** "The season turns. The old Warden steps out of the
  calendar; a new one steps in."

---

## 3. What "wild dungeon structure" means here

### 3.1 Reused

| Wild-dungeon piece | Map-boss use |
|---|---|
| World-map marker + click hit-test | Gold `⌛ E{n}` marker; city click still wins ties |
| Info panel with previewed rewards | Boss name, Echo, HP bar, mechanic name, weakness, cache preview, next trophy |
| Off-road travel segment | `wild_dungeons.build_journey_to_dungeon(..., to="map_boss")` |
| `origin_city = nearest_city` trick | Flee/death route to the nearest city for free |
| DungeonScreen branding branch | "The Long Day" / "Map Boss · Echo N" |
| `_dungeon_log` pop on entry | Prevents a previous dungeon's log bleeding into the arena |
| `player["floor"]` snapshot/restore | Never pollutes travel scaling or `max_floor`/`city_floors` |
| Journal + session log | `[MAP BOSS]` spawn/victory/departure entries |
| Expiry grace mid-journey | If the month turns while travelling, arrive at nearest city with flavor |

### 3.2 Deliberately not reused

- **No floor loop.** The site is one arena. The boss is the content; the HP bar
  is the progress bar.
- **No weekly 3–7 spawn roll.** One active seasonal Warden per season; its Echoes reuse the same site.
- **No wild `active` list.** The boss has its own state block (§4).
- **No wild reward pool generation.** Boss loot uses its own table (§8).
- **No superboss pool / ledger / shards / capture / awakening.**

### 3.3 Why a single arena

Fleeing is a first-class mechanic. If every retry required clearing 2–6 floors
again, the saved HP progress would be a trap rather than a feature. A single
arena makes the loop: **travel → chip → flee → heal → return → kill or lose the
month**.

---

## 4. Data model

### 4.1 State block — `player["map_boss"]`

```python
{
    "unlocked_day": None,      # day the Floor-20 gate was first met
    "season": None,            # "spring" | "summer" | "autumn" | "winter"
    "echo": -1,                # Echo index within the current season (0 = first)
    "active": None,            # current site dict, or None while pre-unlock
    "defeated_total": 0,       # lifetime victories (unique milestones use this)
    "unique_grants": [],       # ["warden_signet", "long_day", ...]
    "best_echo": -1,           # highest Echo ever defeated (start depth, §5.7)
    "season_defeats": {},      # {"spring": 2, "summer": 1, ...}
    "last_spawn_day": 0,       # idempotency guard
    "last_result": None,       # "victory" | "fled" | "dead"
    "depth_declined_season": None,  # season whose start-depth offer was declined
}
```

Managed by `map_boss.ensure_map_boss_state(player)` (mirrors
`wild_dungeons.ensure_wild_dungeon_state` / `quests.ensure_quest_state`). Called
from `character.build_character` and defensively at every access point, so old
saves migrate with zero work — the save system already round-trips arbitrary
JSON-safe keys.

### 4.2 Active site dict

```python
{
    "id": "warden_summer_2",        # warden_{season}_{echo}
    "season": "summer",
    "season_name": "Summer",
    "warden_name": "Warden of the Long Noon",
    "mechanic": "heat",            # seasonal mechanic id (§6.3)
    "echo": 2,                      # 0-based within this season
    "level": 60,                    # 20 + 20×Echo, cap 80
    "biome": "desert",
    "element": "fire",              # season element
    "weakness": "water",            # season weakness; never scales
    "seed_city": "cinderpeak",
    "nearest_city": "cinderpeak",   # flee destination
    "position": [412, 190],         # world-map canvas coords
    "spawn_day": 100,               # Echo 2 spawned after two kills this season
    "expire_day": 181,              # season boundary (events.next_season_day)
    "max_hp": 4107,
    "hp": 2587,                     # persisted progress within this Echo
    "armor": 19,
    "elemental_res": { ... },       # frozen snapshot for preview/debug
    "status_res": 0.46,
    "mechanic_tier": 3,             # 1..10 effects unlocked
    "mechanic_effects": ["heat_stacks", "burn", "solar_flare"],
    "mechanic_rank": 1,             # 1 + Echo // 3, cap 4
    "attempts": 1,
    "last_fought_day": 40,
    "defeated": False,

    # Pre-rolled at spawn so the map panel can preview the loot.
    "cache_preview": {"item_id": "inferno_greatsword", "rarity": "epic"},
    "consumables": ["superior_healing_potion", "ember_draught"],
    "flower": "emberbloom",
}
```

Only JSON-safe values. `max_hp` / `hp` are the authoritative values for the
preview and the next attempt; the combat module copies them onto the enemy dict.

### 4.3 Transient keys (never persisted)

| Key | Purpose |
|---|---|
| `player["_map_boss_site"]` | Active site id while inside the arena |
| `player["_map_boss_prev_floor"]` | `player["floor"]` snapshot |
| `player["_map_boss_in_fight"]` | Optional guard for button-flee paths |
| `player["_combat_time_label"]` | Projected arena clock for the combat header |
| `player["_map_boss_clock_blocks"]` | Projected block counter (unique-item synergy) |

`save_load.load_game` pops all five. `city_screen._launch_dungeon` and
`apply_death_penalty` defensively scrub them too (wild-dungeon pattern).

---

## 5. Spawn & lifecycle

### 5.1 Unlock + seasonal Echo loop

- **Gate:** `player["max_floor"] > 20` — Floor 20 must be **cleared**, not just
  reached. This is the same gate as the Event Horizon site.
- **First spawn:** the **current season's Warden**, Echo 0, as soon as the gate
  is met (the next `maybe_spawn` call).
- **Within-season Echo loop:** every time the Warden dies, the next Echo spawns
  **immediately at the same site** — +20 levels, more HP, a new mechanic effect,
  more resistances and a higher seasonal-mechanic rank. It repeats until the
  season changes.
- **Season rotation:** on the **first day of each season** (days 1/91/181/271;
  `events.next_season_day`), the current Warden is replaced by the **next
  season's Warden** at Echo 0. New name, element, weakness, mechanic and site;
  the Echo counter resets.
- **Flee/death do not advance the Echo.** Only a kill does. Fleeing or dying
  keeps the current Echo (with its saved HP) until you return or the season
  ends.
- **Level:** `level = min(80, 20 + 20 * echo)` within the season.
- **Start at proven depth:** on arrival the arena offers `best_echo` as an
  entry point (§5.7). Optional, one-way, and never a re-fight.
- **No pre-unlock spawn.** A save loaded later shows the current season's
  Warden, never a backlog of missed seasons.

The calendar (shipped 2026-11-13) is a **360-day year** of twelve 30-day
months; three months make a season. `pandemonium/core/events.py` owns it:

```python
MONTH_LENGTH_DAYS = 30
MONTHS_PER_SEASON = 3
MONTHS_PER_YEAR = 12
SEASON_LENGTH_DAYS = 90        # 3 × 30

def season_start_day(day):     # 1 / 91 / 181 / 271 / 361 …
def next_season_day(day):      # strictly the next season boundary
```

The current Warden's deadline is `events.next_season_day(day)`; the season's
Echo counter resets when the new seasonal Warden replaces it.

Example (unlock on Day 20 in Spring, with kills on Days 22, 27 and 64):

| Day | Season | Echo | Level | Note |
|---:|---|---:|---:|---|
| 20 | Spring | 0 | 20 | first Warden |
| 22 | Spring | 1 | 40 | Echo 0 killed; reforms immediately |
| 27 | Spring | 2 | 60 | Echo 1 killed; reforms immediately |
| 64 | Spring | 3 | 80 | Echo 2 killed; reforms immediately |
| 91 | Summer | 0 | 20 | season turns; Summer Warden replaces Spring at a new site |

### 5.2 Authored, deterministic spawn

The spawn is **not random per load**. Each season has a **locked arena** —
`site_city` + `site_position` in `resources/map_boss_data.py` — so the Warden
always surfaces at its most suited location; every Echo of that season reuses
it:

| Season | Anchor city (biome) | Arena position |
|---|---|---|
| Spring | **Veilholt** (forest) | `(760, 45)` |
| Summer | **Cinderpeak** (volcanic) | `(538, 286)` |
| Autumn | **Thornwall** (temperate) | `(386, 142)` |
| Winter | **Stormhold** (tundra) | `(95, 165)` |

1. Biome = the anchor city's biome; the seasonal element/weakness are fixed by
   the season, not the biome.
2. Position = the authored canvas point. It is kept fully on-canvas and clear
   of every city node, active wild-dungeon marker and the Event Horizon site.
   If a wild ruin already occupies it (spawned before the season turned), the
   site hops a short deterministic offset and returns to the authored point
   once the ruin expires.
3. Derive `nearest_city` from the final position (the anchor city for all four).

Every Echo in the season reuses the same site, position, biome and element. The
next season spawns at its own anchor. Loading the same save in the same season
always produces the same site. Saves that predate the authored layout are
repaired on the next map open (`map_boss._repair_site`), keeping the Echo, HP
and pre-rolled spoils.

The seeded ring roll (`random.Random(20260101 + season_start_day * 7919)`) is
retained only as a fallback for restricted worlds where the anchor city is
inaccessible.

### 5.3 Hook and idempotency

- `events.process_day_rollover` calls `map_boss.maybe_spawn(player)` after the
  wild-dungeon weekly cycle.
- `world_map_screen` calls `map_boss.maybe_spawn(player)` on map open, so a save
  loaded mid-season is immediately consistent.
- `maybe_spawn` is idempotent:
  1. Gate check (`max_floor > 20`); return if not met.
  2. First time only: set `unlocked_day = day`, record the unlock event, and
     spawn the current season's Warden at Echo 0.
  3. Read `current = events.get_season(day)[0]`. If `state["season"] != current`
     or `state["active"] is None`, spawn the current season's Warden at Echo 0
     at a new site; reset `state["echo"] = 0`; record the season-change journal.
     (The season only changes on days 1/91/181/271, so this branch is exact.)
  4. If the season matches and `active` exists, keep its HP/mechanic state.
- Echo advancement is **not** handled here. The victory handler (§7.7) creates
  the next Echo immediately after a kill.
- Repeated calls never reroll HP, mechanic effects, element or cache preview.

### 5.4 Old-save sync

`_sync_season(player)`:

- If `max_floor <= 20`, do nothing.
- If `state["unlocked_day"] is None`, set it to the current day and spawn the
  current season's Warden at Echo 0 immediately.
- If `state["season"]` is missing or different from `events.get_season(day)[0]`,
  discard the old active site and spawn the current season's Warden at Echo 0
  at a new site; reset `state["echo"] = 0`.
- If the season matches and `active` exists, keep its HP/mechanic state.
- Old saves from the earlier 20-day / single-Warden design are migrated to the
  current season's Echo 0; the old active site is dropped.
- **Calendar rev (2026-11-13):** the year widened from 120 to 360 days
  (seasons 30 → 90 days). `player["day"]` is untouched and the season is
  derived, so `_sync_season` simply sees a different season and respawns the
  current Warden at Echo 0. `best_echo` is preserved and drives the start-depth
  offer (§5.7).

Example: an old save loaded on Autumn 12 spawns the **Warden of the Falling
Crown** at Echo 0. Killing it that day spawns Echo 1 (level 40) on the same
autumn site; the Winter Warden replaces it on the next season boundary
(day 271).

### 5.5 Seasonal roster

Three 30-day months make a season (90 days): **Spring → Summer → Autumn →
Winter → Spring…** (`events.get_season`; M1–M3 Spring, M4–M6 Summer, M7–M9
Autumn, M10–M12 Winter). Each season has its own Warden, element, weakness,
biome preference and mechanic.

| Season | Warden | Element | Weakness | Biome preference | Mechanic | Signature status |
|---|---|---|---|---|---|---|
| Spring | **Warden of the First Bloom** | earth | fire | forest, temperate | **Bloom** | Poison |
| Summer | **Warden of the Long Noon** | fire | water | desert, volcanic, savanna | **Heat** | Burn |
| Autumn | **Warden of the Falling Crown** | wind | thunder | savanna, forest, temperate | **Harvest** | Bleed |
| Winter | **Warden of the Last Light** | water | fire | tundra, mountain | **Frostbite** | Slow / Freeze |

The arena biome is the seed city's biome, chosen from the season's preferred
list when possible. The seasonal element/weakness and mechanic do not change
with biome or Echo.

### 5.6 Season boundary

- `season_expire_day = events.next_season_day(day)` (91 / 181 / 271 / 361 …);
  every Echo in the season shares that deadline.
- At the boundary, the current Warden (any Echo) departs and the **next
  season's Warden** spawns at Echo 0 at a new site.
- If the player is mid-fight when the boundary is crossed (time commit at exit),
  the old fight resolves first, then the new seasonal Warden spawns.
- If the player kills the Warden before the boundary, the next Echo spawns
  immediately at the same site and shares the same season deadline.
- The first season may be partial if Floor 20 is cleared late; season alignment
  is strict. A 90-day season absorbs that well; the only dial left is delaying
  the first spawn to the next season boundary.

### 5.7 Start at proven depth

The season reset is the loop's only real grind: a party that reached Echo 7
last season would otherwise re-clear Echoes 0–6 every 90 days. The arena
therefore offers a **starting depth**.

**Rule** (on arrival, before the fight):

```python
start_echo = state["best_echo"]              # highest Echo ever defeated
# optional clamp: min(start_echo, MAP_BOSS_START_DEPTH_CAP)
if state["active"] is not None and start_echo > state["echo"]:
    offer_depth_choice(start_echo)           # “Call the echo you broke” / “Begin at Echo 0”
```

- Choosing the depth sets `state["echo"] = start_echo` and generates **that**
  Echo at full HP. Level, HP, armor, resistances, mechanic tier and mechanic
  rank all come from the Echo index — it is not Echo 0 wearing Echo N's stats.
- **One-way per season.** The ladder advances only by kills; a cleared Echo can
  never be re-entered. There is no menu of farmable fights.
- **No extra power, no skipped content.** The jump skips only the fights (and
  their locks); mechanic effects are cumulative, so Echo N already runs tiers
  1…N+1 at the current rank.
- **Recalling discards any partial HP** on the season's current Echo. The
  dialog says so before confirming.
- **Echo 0 is always offered** as the warm-up; players who want the low-Echo
  caches (their gear level tracks the Echo, §8.2) can still climb from the
  bottom.

**Guardrails**

- `best_echo` is lifetime, but each season's Warden has a different element and
  weakness — depth earned against Summer is not a promise against Winter. The
  dialog always prints the Warden's element and weakness, and the flee rule
  (§7.6) makes a bad opener recoverable.
- `MAP_BOSS_START_DEPTH_CAP` (default `None`) can clamp the opener if a
  level-80 start after a season turn proves too harsh in playtest.
- No Echo storage: `best_echo` already exists (§4.1) and the chosen Echo is
  just `state["echo"]`. The only new field is `depth_declined_season`, which
  suppresses the re-offer for the rest of the season.

**Voice lines**

- Offer: *“Something of it remembers you. You may call it at the height you
  last broke — Echo {n}.”*
- Chosen: *“You do not climb. You call. The {warden_name} answers already
  grown.”*
- Declined: *“You begin where it always begins — small, and hungry.”*

---

## 6. Echo escalation

Every spawn gains the following. The Echo index is the spawn number (0-based).

### 6.1 Curves

```python
level      = min(80, 20 + 20 * echo)          # 20, 40, 60, 80, 80, ...
step       = level - 20

hp_mult    = (1 + 0.06 * step) * (1 + 0.10 * echo + 0.002 * echo * echo)
damage     = (1 + 0.03 * step) * (1 + 0.03 * echo)
armor      = min(40, 12 + int(0.5 * echo + 0.15 * step))
all_res    = min(1.60, 1.0 + 0.02 * echo + 0.005 * step)
season_res = min(1.70, 1.30 + 0.015 * echo + 0.005 * step)
weakness   = 0.70                              # never changes
status_res = min(0.85, 0.20 + 0.03 * echo + 0.005 * step)
mechanic_tier = min(10, echo + 1)              # mechanic effects unlocked
mechanic_rank = min(4, 1 + echo // 3)          # numeric scaling of those effects
```

`level` is a real stat multiplier, not just a label: `step` drives HP, damage,
armor and the baseline resistance/status-resistance floor. There is **no shared
generic-buff ladder** and the boss does not gain generic buffs per Echo. Instead,
every Echo unlocks the next effect in its **seasonal mechanic** (§6.3): Echo 0
starts at tier 1, Echo 9 reaches tier 10, and Echo 10+ adds no new effect but
`mechanic_rank` scales the mechanic's numeric values by `1 + 0.25 × (rank − 1)`.

### 6.2 Reference curve

Base at Echo 0: level 20, 1,000 HP, 30 STR, 12 armor, 20% status resistance.

| Echo | Level | HP | Damage | Armor | All res | Season res | Status res | Mechanic tier | Cache floor |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 20 | 1,000 | ×1.00 | 12 | 1.00 | 1.30 | 20% | 1 | Rare+ (10% epic) |
| 1 | 40 | 2,424 | ×1.65 | 15 | 1.12 | 1.42 | 33% | 2 | Rare+ (20% epic) |
| 2 | 60 | 4,107 | ×2.33 | 19 | 1.24 | 1.53 | 46% | 3 | Rare+ (30% epic) |
| 3 | 80 | 6,063 | ×3.05 | 22 | 1.36 | 1.65 | 59% | 4 (rank 2) | Rare+ (40% epic) |
| 5 | 80 | 7,130 | ×3.22 | 23 | 1.40 | 1.68 | 65% | 6 (rank 2) | Rare+ (60% epic) |
| 10 | 80 | 10,120 | ×3.64 | 26 | 1.50 | 1.70 | 80% | 10 (rank 4) | Epic+ · 30% legendary |
| 20 | 80 | 17,480 | ×4.48 | 31 | 1.60 | 1.70 | 85% (cap) | 10 (rank 4) | Epic+ · 30% legendary |
| 30 | 80 | 26,680 | ×5.32 | 36 | 1.60 | 1.70 | 85% (cap) | 10 (rank 4) | Epic+ · 30% legendary |

> HP, damage and armor are **before** phase multipliers (Noon ×1.10 / Night
> ×1.30). The boss does not gain generic buffs; the per-Echo progression is the
> seasonal mechanic's tier in §6.3.

> **Threat hint in the panel:** "Recommended: party Lv ~{level}." The Echo's
> level is real: a level 80 Echo is a level 80 fight, not a level-20 boss with
> extra HP. A well-geared party can punch above it; an under-geared party should
> flee and return.

### 6.3 Mechanic upgrade ladder — one new effect per Echo

Each Echo unlocks the next effect in its **seasonal mechanic**. Effects are
cumulative: Echo 0 starts at tier 1 (the base loop), Echo 9 reaches tier 10,
and Echo 10+ adds no new effect but `mechanic_rank` scales numeric values. The
10-effect cap keeps the HUD readable while still giving every reachable Echo a
new toy; Echo 10+ continues through rank scaling. This is the **only** per-Echo
effect layer; the boss does not receive generic buffs.

**Spring — Bloom (Poison)**

| Echo | New effect |
|---:|---|
| 0 | Bloom stacks (cap 3): +3% damage, +2% armor per stack; at cap, consume all Bloom to heal 5% max HP. |
| 1 | At 3+ Bloom, attacks apply Poison (2 turns). |
| 2 | Cap heal becomes 10%; refresh Poison on the target. |
| 3 | Bloom gain +1 at Noon. |
| 4 | Poison also applies Weaken (−10% damage, 2 turns). |
| 5 | Cap heal becomes 15%; poison the whole party. |
| 6 | Bloom cap +1. |
| 7 | Poison damage +50%. |
| 8 | Consuming Bloom summons a Bloomling (if space). |
| 9 | **Overbloom:** cap consumption also deals AoE earth damage (0.75× STR) and poisons all. |
| 10+ | No new effect; `mechanic_rank` scales values. |

**Order:** T1's Poison check resolves before T0's cap consumption, so reaching 3
Bloom still poisons the target before the Warden heals.

**Summer — Heat (Burn)**

| Echo | New effect |
|---:|---|
| 0 | Heat stacks (cap 5): +2% damage, +2% initiative per stack; at cap, vent all Heat (no damage). |
| 1 | At 4+ Heat, attacks apply Burn. |
| 2 | At cap, **Solar Flare**: AoE fire damage (0.75× STR), then reset Heat. |
| 3 | Heat gain +1 at Noon. |
| 4 | Burn duration +1. |
| 5 | Solar Flare ignores 30% armor. |
| 6 | Heat cap +1. |
| 7 | Burn damage +50%. |
| 8 | Heat gain +1 at Night. |
| 9 | **Second Sun:** Solar Flare hits twice (second at 50% power) before reset. |
| 10+ | No new effect; `mechanic_rank` scales values. |

**Autumn — Harvest (Bleed)**

| Echo | New effect |
|---:|---|
| 0 | Attacks apply Bleed (3 turns). When a bleeding party member acts, gain 1 Harvest (cap 4); each stack: +2% damage, +1% lifesteal. |
| 1 | Bleed damage +50%. |
| 2 | At cap, **Reap**: single-target 1.5× STR; heal 50% of damage dealt; reset Harvest. |
| 3 | Reap heals 60%. |
| 4 | Bleed duration +1. |
| 5 | Reap also applies Bleed to the whole party. |
| 6 | Harvest cap +1. |
| 7 | Lifesteal +1% per stack. |
| 8 | When a bleeding target dies, gain 2 Harvest. |
| 9 | **Final Harvest:** Reap hits the whole party at 0.9× and heals 50% of total damage. |
| 10+ | No new effect; `mechanic_rank` scales values. |

**Winter — Frostbite (Slow / Freeze)**

| Echo | New effect |
|---:|---|
| 0 | Each round apply 1 Frostbite to a random party member. Frostbite: −2 DEX, 2 water damage/turn, 3 turns. |
| 1 | At 3 stacks, **Freeze** for 1 turn and reset. |
| 2 | Gain 1 Ice Armor per round (cap 3); each −3% damage taken; fire damage removes 1. |
| 3 | Frostbite targets +1 at Night. |
| 4 | Ice Armor cap +1. |
| 5 | Frozen targets take +20% damage. |
| 6 | Frostbite damage +2/turn. |
| 7 | **Shatter:** when Ice Armor is removed by fire, the attacker takes 1.0× STR water damage. |
| 8 | Freeze duration +1. |
| 9 | **Absolute Zero:** at 5 Frostbite stacks, freeze the whole party for 1 turn and reset all Frostbite. |
| 10+ | No new effect; `mechanic_rank` scales values. |

`mechanic_tier = min(10, echo + 1)` is the number of unlocked effects;
`mechanic_effects` in the active dict is the derived list for preview/HUD. The
preview shows the next effect before you travel.

### 6.4 Damage resistance in engine terms

The boss is an enemy, so its "damage resistance" is expressed through existing
mechanics:

- **Armor:** `con_mod` (flat subtraction in every player/ally damage path).
- **Elemental resistance:** `elemental_res` ratings (1.0 = neutral, >1.0 =
  resistance, <1.0 = weakness). The Warden's **season element** uses
  `season_res`; all other elements use `all_res`; the seasonal weakness stays
  0.70.
- **Status resistance:** `status_res` (global `check_status_resisted`).
- **Dodge:** none of the four base mechanics grants passive dodge; if a future
  mechanic adds one, use `dodge_cap_override` / `evasion`.
- **Do not** use `defense_pct` on the boss for incoming player damage: that
  buff is read on the **defender-player** side in `enemy_ai`, not on enemies.
  Armor + elemental resistance is the correct path.

### 6.5 Weakness rule

The seasonal weakness is **0.70** from Echo 0 through infinity. The player
always has a 1.3× damage element to exploit. This is the main answer to
high-Echo armor/resistance walls. The panel shows it prominently.

### 6.6 Mechanic hook contract

- The four mechanics live in a data-driven table in
  `resources/map_boss_data.py`: each season has `tier_effects` (10 entries) and a
  `rank_scale`.
- `pre_round_hook` advances stacks and applies phase/nocturnal modifiers;
  `enemy_turn_hook` returns extra actions and the mechanic-specific
  `extra_logic`; statuses are applied only when `damage > 0`.
- HUD tags: `BLOOM×N`, `HEAT×N`, `HARVEST×N`, `FROST×N`/`ICE×N`, plus the active
  status tags (`PSN`, `BRN`, `BLE`, `FRZ`). The tag stays visible even at tier
  10 so the player can read the current stack.
- At Night, the mechanics are more aggressive: Spring Bloom +1, Summer Heat +1,
  Autumn Harvest cap +1, Winter Frostbite targets +1.
- Status applications use the normal `status_res` check on the party; the
  Warden's own `status_res` protects it from player debuffs.
- The seasonal mechanic is the Warden's identity and the **only** per-Echo
  effect layer. There is no shared generic-buff ladder and no generic boss buffs.

---

## 7. Combat runtime

### 7.1 Encounter shape

- **Boss + up to 4 seasonal adds** (max 5 enemies, the HUD limit).
- Runtime: `pandemonium/combat/map_boss.py` uses
  `superboss_common.superboss_combat_loop` for the scripted hooks. This is a
  runtime reuse, **not** a superboss-pool membership:
  - ally cooldowns, reinforcement, and end-of-combat cleanup already tick there;
  - `enemy_turn_hook` supports `(actions, skip_atk, extra_logic, armor_mult,
    temp_str)`, which is exactly what the phase/status kit needs;
  - flee returns `"fled"` and is always available.
- Each seasonal Warden has its own YAML key — `warden_spring_bloom`,
  `warden_summer_noon`, `warden_autumn_crown`, `warden_winter_light` — with the
  same base stats, `boss: true`, `super_boss: false`, `ai_disabled: true`. The
  bestiary and death screen therefore record the seasonal name, not a generic
  "Warden." No generic `enemy_skills` AI, no capture (no `monster_girl` flag),
  no superboss ledger.
- Build the boss with `enemy_stats(BOSS_KEY)` **without a player** (so no
  Morning/Noon/Night or Full Moon multiplier), then override level, HP, STR,
  armor, resistance and status resistance with the Echo values. This avoids
  double phase scaling.
- Pass `boss_name=site["warden_name"]` and a `custom_hud_hook` that labels the
  HUD `Seasonal Warden: {warden_name}` (the shared loop's default label is
  `Superboss:`). Pass `context["season_mechanic"]` to the mechanic hooks.
  This is display-only; the loop has no superboss side effects of its own.

### 7.2 The arena clock — 1 round = 1 block

This is the defining rule. It is implemented as a **projected clock**:

1. On entry, `start_blocks = int(player.get("day_blocks", 0))`.
2. For round `n` (1-based), the arena block is:
   `cursor = start_blocks + (n - 1)`.
3. `phase = time_blocks.get_day_phase(cursor % 24)`.
4. The header gets a projected label built from `cursor % 24`
   (`☀ Morning ■■■■■■■□`). A display-only
   `player["_combat_time_label"]` is read by `combat_ui.current_time_label`.
5. `player["_map_boss_clock_blocks"] = cursor` for the Warden's Signet unique.
6. On **exit** (victory, flee, death, interrupt), commit the whole fight at once:
   `time_blocks.spend_blocks(player, rounds_fought, source="map_boss")`.

**Hook placement:** add an optional `pre_round_hook(context, enemies)` to
`superboss_combat_loop`, called after `prune_dead` and **before**
`print_round_header` (set `context["round"] = round_num` before the call). It
advances the projected clock, sets `player["_combat_time_label"]`, applies the
phase transition and increments `rounds_fought`. Existing superbosses pass
`None`, so their behavior is unchanged. Do **not** use `pre_player_hook` for
the clock — it runs after the header and would label each round with the
previous phase.

**Critical rule:** never call `advance_time(60)` or `spend_blocks(1)` per round.
That would fire day-rollover side effects (wild spawns, bills, dispatch, family
ticks, event notices) in the middle of combat. The projected clock exists
specifically to avoid that. The batch commit at exit is the only real time
advance.

Consequences at exit:

- A 10-round fight spends 10 blocks.
- Crossing midnight uses the normal `spend_blocks` overflow: it rolls the day,
  adds **+50 stress** for an unslept day, and may cross a season boundary and
  spawn the next seasonal Warden (see §7.7 ordering).
- Fatigue/stress accrued by a marathon fight is real. That is intentional: the
  Warden drinks hours.
- Hallucinations cannot trigger mid-fight; they are dungeon-room content.

### 7.3 Phase aggression table

| Phase | Name | Damage | Initiative | Behavior |
|---|---|---:|---:|---|
| **Morning** (blocks 0–7) | **Dormant** | ×1.00 | +0 | Single action. Basic/heavy only. No adds. |
| Morning, first 2 rounds | **Dawn Lull** | ×0.85 | +0 | Armor −20%; the post-Night opening. |
| **Noon** (blocks 8–15) | **Stirring** | ×1.10 | +10% | Summons 2 seasonal adds; unlocks its AoE. |
| **Night** (blocks 16–23) | **Rampage** | ×1.30 | +20% | **2 actions per turn**; summons 2 more seasonal adds; status chance +25%. |

- The boss starts in whatever phase matches the current block. A Night start is
  immediately dangerous; a Morning start gives the player the Dawn Lull opening.
- At the first Morning round of a new day (or at the start of the fight if it
  begins in Morning), the boss **clears all phase buffs**, despawns all
  seasonal adds, and begins a 2-round Dawn Lull. This is the literal "turn back
  to normal" the design asks for.
- Phase transitions print a pinned `⚙ [PHASE]` line (add `[phase]` to
  `_GIMMICK_TAGS`; or reuse `[gimmick]`).
- Phase buffs use `source="map_boss_phase"` so `_clear_phase_buffs` can remove
  them without touching mechanic effects or player-applied debuffs.

### 7.4 Boss action kit

The Warden uses one element (its seasonal element) for all attacks. The phase
changes *how hard* and *how often* it hits, not which element it uses — that
keeps the weakness meaningful. Action names are season-skinned; the shapes below
are the shared chassis (Spring: *Verdant Grasp / Pollen Weight / Bloomburst /
Nightroot / Harvest Reap / The Long Bloom*; Summer: *Censure / Weight of Noon /
Noonfire / Nightfall / Hour Reap / The Long Day*; Autumn: *Windfall / Weight of
Years / Leafstorm / Nightfall / Reap / The Last Harvest*; Winter: *Cold Censure /
Weight of Snow / Frostfall / Long Night / Last Light / The Long Winter*).

| Action | Phase | Shape | Notes |
|---|---|---|---|
| **Censure** | All | Single, 1.0× STR | Basic pressure. |
| **Weight of Hours** | All | Single, 1.2× STR | Applies the seasonal mechanic's current status on hit. |
| **Noonfire** | Noon+ | AoE, 0.75× | Applies Burn/Slow if owned. |
| **Nightfall** | Night | AoE, 0.90× | Applies Blind/Dread if owned. |
| **Hour Reap** | Night | Single, 1.6× | Ignores 30% armor. |
| **The Long Day** | Every 3rd round (2nd at Night) | AoE, 1.0× | Applies all owned statuses at 50% chance. No intent telegraph — the phase line is the only warning (enemy intent stays hidden, per the combat-design rule). |

Status application runs in `extra_logic` only when the attack dealt damage
(`damage > 0`), so a fully blocked/dodged hit never procs a status. This mirrors
the existing "no on-hit status on a fully blocked hit" convention.

### 7.5 Seasonal adds

- Display names follow the season: **Bloomling** (Spring), **Cinderling**
  (Summer), **Huskling** (Autumn), **Frostling** (Winter).
- **HP:** 3% of the Warden's max HP.
- **Damage:** 0.4× the Warden's STR.
- **Actions:** basic attack only; no statuses, no loot, no XP, no bestiary.
- Build them manually with the synthetic key `map_boss_add` (not present in
  `ENEMIES`), so `bestiary.record_defeat` returns False. Do not give them a
  real YAML key.
- **Spawn:** 2 at Noon, 2 more at Night (cap 4). Spawned in `pre_player_hook`,
  so they join the current round's initiative. At dawn they crumble.
- They are the same chassis every season; the seasonal mechanic lives on the
  Warden, not the adds.
- If the 5-enemy HUD cap is reached, no more spawn; the loop's safety cull
  should never need to fire.

### 7.6 Flee & HP persistence

- `[F]lee` is available every round, at any HP. No "you cannot flee" branch.
- On flee:
  1. `active["hp"] = boss["hp"]`
  2. `active["attempts"] += 1`
  3. `active["last_fought_day"] = player["day"]`
  4. `last_result = "fled"`
  5. Commit arena time, restore transient state, `save_game`
  6. Return to `origin_city` (nearest city)
- No loot. No boss regeneration. The HP bar on the map panel is the reward for
  the attempt.
- Re-entry uses `active["hp"]` as the starting HP. The intro line changes:
  *"The {warden_name} remembers. 63% of this Echo remains."*
- Adds, mechanic stacks and phase buffs reset on re-entry; the Echo's mechanic
  tier, armor, resistance and status resistance persist (they are part of the
  Echo, not the attempt).

### 7.7 Result ordering (important)

On fight end, resolve state **before** committing time:

1. Snapshot the active site and compute rewards from the snapshot.
2. **Victory:** `active["hp"] = 0`, `active["defeated"] = True`,
   `defeated_total += 1`, `best_echo = max(...)`,
   `season_defeats[season] += 1`, and `state["echo"] += 1`.
3. **Flee/death/interrupt:** keep `active` with the saved HP; do not advance the
   Echo.
4. Commit arena time (`spend_blocks`). This may cross a season boundary.
5. Grant rewards (victory) using the step-1 snapshot.
6. **Victory season check:**
   - **Same season:** create the next Echo **immediately at the same site** —
     full HP, `level = min(80, 20 + 20 * new_echo)`, new mechanic effect /
     resists / mechanic rank — and store it in `state["active"]`. Show the reform
     dialog (§7.10).
   - **Season changed:** discard the old-season site; spawn the current
     season's Warden at Echo 0 at a **new site**; reset `state["echo"] = 0`.
     Show the season-change dialog (§7.11). The old season's next Echo is never
     created.
7. Save, clear transients, exit.

**Idempotency:** `maybe_spawn` may already have swapped the season during the
step-4 time commit. Step 6 must re-read `state["season"]` / `state["active"]`
and only create the next Echo if the active still belongs to the killed Echo's
season. Never spawn two new Wardens for one boundary.

A kill **before** the season boundary spawns the next Echo **immediately** — no
waiting for the season to turn. A kill that crosses the boundary resolves the
old fight first, then the next seasonal Warden replaces it. The victory summary
names the season, Warden and Echo that were actually killed.

### 7.8 Death

- Standard death penalty path (`apply_death_penalty`), with the boss HP saved.
- `death_type="map_boss"`, `map_boss_echo=N`, `map_boss_season=...` and
  `map_boss_name=...` so the death screen can say:
  *"You were slain by the Warden of the First Bloom — Spring Echo II."*
- No loot. The current Echo remains until you return or the season ends.
- Time spent is committed before the death penalty, so the death screen's day
  and stress are correct.

### 7.9 Interrupt / button-flee

GUI button-flees can kill the worker thread before the in-dungeon cleanup runs
(the wild-dungeon lesson). The `_map_boss_in_fight` guard and the
`world_map_screen._on_map_boss_result` defensive branch must both persist HP,
commit time at most once, and scrub transients. A second commit is guarded by a
`_map_boss_time_committed` flag on the active site or a transient marker.

### 7.10 Post-victory reform loop

- After a **same-season kill**, the next Echo is already active at the site.
- Show a dialog:
  - Title: **"The Warden Reforms"**
  - Body: *"{warden_name} collapses — and the hours run backward. Echo {n}
    (Lv {level}) stands where it fell. Party HP: {hp}/{max}."*
  - Buttons: **Face the next Echo** / **Leave Arena**.
- **Face the next Echo:** start the next fight immediately. No travel, no free
  heal. Buffs/cooldowns tick through the normal end-of-combat cleanup; seasonal
  adds and phase buffs reset.
- **Leave Arena:** return to the nearest city. The next Echo remains active at
  the site with full HP and can be fought later.
- The standard "Leave Arena" button also works between attempts; it does not
  discard the next Echo.
- Warn if party HP is low. The risk/reward of chaining Echoes is the point.

### 7.11 Season-change dialog

- Triggered when the time commit crosses a season boundary (days
  91/181/271/361), or when `maybe_spawn` notices a new season while the player
  is in the city.
- The old Warden is gone; the next season's Warden is at Echo 0 at a new site.
- If the player is still in the arena: *"The season turns. {old_warden} is gone;
  {new_warden} stirs near {city}."* → **Return to City**. The new site is on the
  map.
- If the player is in the city/world map: journal/notice + marker refresh.
- The old season's HP progress and Echo counter are discarded.
- If the fight that crossed the boundary killed the old Warden, its rewards are
  granted; no old-season next Echo is created.

---

## 8. Rewards & drops (locked)

### 8.1 Preview at spawn

The map panel shows the actual pre-rolled loot, not just categories:

- Season, Warden name and signature mechanic.
- Current Echo, level and next-Echo preview (level/next mechanic effect/tier).
- Cache item name + rarity.
- Two consumable names.
- Flower name.
- Next unique milestone and victories remaining.
- Gold/XP range for the current Echo.

The cache is rolled at spawn and stored in `active["cache_preview"]`; item stats
are rolled at acquisition via `build_item`, matching the wild-dungeon preview
convention (name/rarity visible, exact mods hidden until acquired).

### 8.2 Every victory

| Drop | Formula / rule |
|---|---|
| **Gold** | `400 + 25 × (level − 20) + 100 × Echo`; × daily gold bonus; **+25% if the killing blow lands during Night** |
| **XP** | `600 + 40 × (level − 20) + 150 × Echo` to the player and every living ally; × daily XP bonus |
| **Warden's Cache** | 1 generated equipment item at `gear_level = clamp(level, 1, 80)`, biome = arena biome |
| **Consumables** | 2 rolls. Echo 0–1: tier 3 pool. Echo 2+: tier 4 pool. Prefer the boss's element theme (Ember Draught for fire, Frostward Tonic for water, etc.), otherwise random from the tier pool |
| **Flower** | 1 guaranteed flower of the Warden's element (`emberbloom`, `frostlotus`, `stormlily`, `galeorchid`, `stonebloom`, `sunpetal`, `nightbloom`, `manabloom`). **+1 extra flower on a Night kill** |

`gear_level` uses the existing `pick_equipment_id` grade bands. Echo 0 (level
20) is g2 gear; Echo 1 (level 40) and every later Echo is g3 gear. Worked
examples: E0 400g/600 XP · E1 1,000g/1,550 XP · E3 2,200g/3,450 XP.

Every **Echo kill** grants this table in full. The next Echo is stronger, so
this is not a same-level repeat farm. A kill that crosses the season boundary
grants the old season's loot; the new seasonal Warden starts at Echo 0.

### 8.3 Cache rarity curve

The cache starts at **Rare** and legendary only appears at **Echo 10** (30%).
There is no legendary roll before Echo 10.

| Echo | Cache rarity |
|---:|---|
| 0 | Rare+ · 10% epic |
| 1 | Rare+ · 20% epic |
| 2 | Rare+ · 30% epic |
| 3 | Rare+ · 40% epic |
| 4 | Rare+ · 50% epic |
| 5 | Rare+ · 60% epic |
| 6 | Rare+ · 70% epic |
| 7 | Rare+ · 80% epic |
| 8 | Rare+ · 90% epic |
| 9 | Epic (100%) |
| 10+ | **30% legendary / 70% epic** |

```python
if echo >= 10:
    rarity = "legendary" if rng.random() < 0.30 else "epic"
else:
    epic_chance = min(1.0, 0.10 + 0.10 * echo)
    rarity = "epic" if rng.random() < epic_chance else "rare"
```

`Rare+` means the cache never rolls common or uncommon; the formula above
selects rare or epic directly. `soften_rarity` / `cap_rarity_for_item` still
apply, so grade caps can demote an epic roll (lower effective rate at low
grade); the preview shows the **final** rarity. The cache's element bias is the **season element** (Spring earth, Summer
fire, Autumn wind, Winter water); the arena biome only flavors the site. The
guaranteed flower is the matching season flower.

### 8.4 Unique trophy ladder

Cumulative victories, one-time per save, tracked by `unique_grants`:

| Victories | Item | Slot | Effect (first pass) |
|---:|---|---|---|
| 1 | **Warden's Signet** | Accessory | **Long Day:** +8% damage at Noon, +16% at Night (0% in Morning). |
| 3 | **Long Day's Edge** | Weapon (sword) | **Hour by Hour:** +3% damage per combat round, max +30%; resets when the phase changes to Morning. |
| 6 | **Echo Mantle** | Armor | Damage taken −12%; at Night, −20% instead. |
| 10 | **Sundial Crown** | Accessory | **Rewind:** once per day, when you would fall, survive at 1 HP and clear all debuffs. |

- All four follow the **unique equipment actor-based convention** — they work
  for the player and allies, not just the MC. Names/effects are first-pass.
- No duplicate uniques. If a milestone is already granted (old save / debug),
  the unique slot converts to a second **Warden's Cache**.
- After all four are owned, every subsequent victory's unique slot becomes a
  **second cache** at the current Echo's rarity floor. This is the long-tail
  reward and needs no new material currency.
- Kills are counted across seasons. A player who chains several Echoes in one
  season will reach the unique milestones faster; the escalating Echo difficulty
  is the limiter. Milestone counts (1/3/6/10) are a playtest dial.

### 8.5 No-loot cases

| Outcome | Loot |
|---|---|
| Flee | None (HP progress saved) |
| Death | None (normal death penalty) |
| Interrupt / timeout | None (treated as flee) |
| Seasonal add kills | None (no XP, gold, bestiary, or drops) |
| Season expiry without a kill | None (the site departs) |

### 8.6 Not granted

- No `defeated_superbosses` record, no `superboss_pool` pop, no awakening
  shard/sigil, no title progress (unless a future title is added in §16).
- No Pandemonium ×2.5 gold/XP multiplier; the Warden is overworld content.
- No bounty progress.

---

## 9. Unique item implementation notes

All four are `unique: True`, `drop_rarity: "unique"`, `drop_source:
"warden_long_day"`, and live in `resources/items.py` under a "Map Boss Drops"
section.

| Item id | Name | Slot | Base mods | Elemental | Special |
|---|---|---|---|---|---|
| `warden_signet` | Warden's Signet | accessory | DEX +5, WIS +4 | dark 1.10, light 1.10 | `long_day_signet` |
| `long_day` | Long Day's Edge | weapon (`sword`) | STR +8, DEX +4 | fire 1.15, light 1.15 | `long_day_blade` |
| `echo_mantle` | Echo Mantle | armor | CON +8, WIS +4 | physical 1.12, dark 1.10, light 1.10 | `echo_mantle` |
| `sundial_crown` | Sundial Crown | accessory | WIS +6, CHA +4 | light 1.15, dark 1.15 | `sundial_crown` |

Implementation conventions (from the unique-equipment rule):

- `combat/weapon/<name>.py` with `_actor_has_<id>(actor)` and `is_player` flags.
- Wire into **both** `combat/player_actions.py` and `combat/ally.py` (basic +
  skill paths).
- Tick/clear per-actor state in `combat_engine._tick_all_state`,
  `_combat_inner`, `_end_combat_with_result` **and**
  `superboss_common`'s round loop — the map boss runs through that loop, so both
  lifecycles matter.
- `Long Day's Edge`: `long_day_stacks` per actor, +1 at each round start, max
  10, reset when the day phase **changes to Morning** (not every Morning round).
  Damage hook multiplies all four damage paths (player basic/skill, ally
  basic/skill).
- `Warden's Signet`: phase bonus read at damage time; 0% Morning, +8% Noon,
  +16% Night. Works for allies.
- `Echo Mantle`: apply a persistent `source="echo_mantle"` `defense_pct` buff at
  combat start (0.12), refresh to 0.20 at Night, back to 0.12 at Morning. On a
  player/ally wearer this is the correct path — `enemy_ai.enemy_attack` reads
  the defender's `active_buffs`. (The boss itself must not use `defense_pct`
  for incoming damage; see §6.4.)
- `Sundial Crown`: add a fallthrough at the end of
  `status_effects.try_consume_death_ward` (the Emperor pattern). Mark
  `sundial_used_day`; available again when `player["day"]` changes. Works for
  allies.
- Examine/description lore for every unique (existing convention).
- Flower infusion: uniques keep their two open flower slots; the Warden's
  element should be a natural first infusion, not a hard-coded one.

---

## 10. GUI / UX

### 10.1 World map

- **Marker:** seasonal glyph at `position` — `🌱` Spring, `🔥` Summer, `🍂`
  Autumn, `❄` Winter. Text: `🌱 E2` (Echo) and `63%` when HP is missing. Gold
  outline; distinct from wild purple `☠`.
- **Hit-testing:** city > map boss > wild. Spawn placement already avoids
  overlapping active wild markers and the Event Horizon site.
- **Info panel:**
  - `Warden of the Long Noon — Summer · Echo II · Lv 60`
  - `Mechanic: Heat (Burn)`
  - Biome, element, **weakness**, nearest city
  - HP bar: `HP 2,587 / 4,107 (63%)`
  - `Mechanic: Heat T3 — Burn · Solar Flare`
  - `Resists: All 1.24 · Fire 1.53 · Weak Water 0.70 · Status 46%`
  - `Departs: Day 181` (the season boundary)
  - `Next Echo: III — Lv 80, next Heat effect (Noon gain)`
  - `Recalled depth: Echo V available` (only when `best_echo > state["echo"]`)
  - Loot preview (cache name/rarity, consumables, flower, next trophy)
  - `Recommended: party Lv ~60` (soft hint)
  - **"Travel to the Warden"** button
- Legend entry: `🌱🔥🍂❄ Seasonal Warden — death reforms the next Echo; a new
  Warden takes over each season.`

### 10.2 Travel & arrival

- Reuse `wild_dungeons.build_journey_to_dungeon(player, site, to="map_boss")`.
- The final leg is off-road; the panel shows `≈N blocks`.
- On arrival, set `player["origin_city"] = nearest_city`, `player["location"] =
  "dungeon"`, `player["_map_boss_site"] = site["id"]`, pop `_dungeon_log`, and
  switch to DungeonScreen.
- **Start-depth offer (§5.7):** when `state["best_echo"] > state["echo"]` and
  `state["depth_declined_season"] != state["season"]`, show the depth dialog
  **before** the arena opens:
  - Title: **“Something Remembers You”**
  - Body: *“The {warden_name} waits at Echo {n} — the height your party last
    broke. It is {element}; it is weak to {weakness}. Calling it discards any
    progress on the current echo.”*
  - Buttons: **Call the echo you broke** (sets the starting Echo) / **Begin at
    Echo 0** (records `depth_declined_season`, keeps the warm-up).
  - Declining is remembered for the season, so the offer does not nag on every
    re-entry.
- **Expiry grace:** if the season turned mid-journey (the site id no longer
  matches), drop into the nearest city with *"The season has turned. A new
  Warden stirs elsewhere."* No combat, no penalty.

### 10.3 DungeonScreen

- The start-depth dialog (§10.2) resolves the Echo **before** this screen opens;
  the title, subtitle, top bar and HP bar all show the chosen Echo.
- New branding branch (wild / EH / city / **map boss**):
  - Title: `Warden of the Long Noon`
  - Subtitle: `Summer · Echo II · Lv 60 · Heat`
  - Top bar: `🔥 Summer Echo II · Day 100 · 🌤 Noon · HP 63%`
- Map widget: a single `⚔ Arena` node in the center; no movement, no floors.
- Entry log: intro + phase-aware flavor.
- Leave button: **"← Leave Arena"** (not "Flee Dungeon"). Confirm:
  *"Leave the Warden? This Echo's HP is kept. The season ends on Day {expire_day}."*
  Use `focus_no=True` so an Enter keypress cannot instantly confirm (EH lesson).
- No floor-clear windows, no post-floor menu, no save-between-floors logic.

### 10.4 CombatScreen

- Top bar: `⚔ Warden of the Long Noon | Summer Echo II | <projected phase
  track>`.
- Boss HUD tags via `_custom_tags`: `ECHO II`, `HEAT×3`, `BRN`, `FLARE`;
  standard active_buffs add `DMG+`, `CRT`.
- Phase transitions pin a `⚙ [PHASE]` line (add `[phase]` to `_GIMMICK_TAGS`).
- Adds appear as normal enemy rows (seasonal names); max 5 total.
- The projected clock is display-only; the HUD never shows a stale real clock.
- `_floor_display()` needs a map-boss branch that returns `None` / `"Arena"`,
  not `"Floor None"`.

### 10.5 Result routing

| Result | Route |
|---|---|
| `map_boss_victory` | Reward summary + **reform dialog** (§7.10): Face the next Echo / Leave Arena |
| `map_boss_season_shift` | Season-change dialog (§7.11) → CityScreen; new seasonal Warden on the map |
| `fled` | CityScreen at nearest city + log line "The Warden waits. This Echo's progress is kept." |
| `dead` | DeathScreen with `death_type="map_boss"`, season, Warden name and Echo number |
| save-exit / interrupt | Defensive scrub → CityScreen (HP already persisted) |

**Stale-callback pitfall:** the world map screen is destroyed when travel
starts. Use the wild-dungeon fix — `confirm_dialog.choice_dialog(parent=self.sm.get_top_screen()
or sm.root, ...)` with the switch on the button callback — not
`ok_dialog(self, ...)` on the dead world-map screen. Also wrap the
DungeonScreen `_handle_result` callback in `try/except` with a CityScreen
fallback, so a torn-down screen can never leave the finished arena unclickable
(the wild-dungeon TclError lesson).

### 10.6 Journal & event notices

- Unlock: `[MAP BOSS] A Warden Notices` — "Floor 20 is cleared. The {season}
  Warden stirs near {city}."
- Season spawn: `[MAP BOSS] The Season Turns` — "The {warden_name} has surfaced
  near {city}. Echo 0 (Lv 20). The season ends on Day {x}."
- Reform: `[MAP BOSS] The Warden Reforms` — "{warden_name} returns as Echo {n}
  (Lv {level}) at the same site."
- Depth recalled: `[MAP BOSS] Depth Recalled` — "{warden_name} answers at Echo
  {n} (Lv {level}) — the height your party last broke."
- Victory: `[MAP BOSS] Warden Felled — {season} Echo {n}` — loot summary.
- Season departure: `[MAP BOSS] The Season Closes` — old Warden gone; new
  seasonal Warden location.
- Use `events.record_event`; the city event-notice queue surfaces them after
  travel/time commits. No toasts.

---

## 11. Save / migration

- `ensure_map_boss_state(player)` in `character.build_character` and at every
  access point; old saves get the block on first load. No version bump.
- Missing `season`/`echo` fields are backfilled: infer the current season from
  `events.get_season(day)` and start at Echo 0. An old active site from the
  earlier 20-day design is dropped.
- `depth_declined_season` backfills to `None`; older saves simply see the
  depth offer on their first arrival in a new season.
- The season is **derived** from `player["day"]`; the 120 → 360-day calendar
  change (2026-11-13) needs no save migration and no version bump.
- `state` is JSON-safe and round-trips through the existing save system.
- `save_load.load_game` pops the five transient keys (§4.3) and does **not** run
  `ensure_player_fields` itself — tests must call `ensure_player_fields`
  explicitly (existing EH lesson).
- HP is authoritative in `state["active"]["hp"]`. Disk saves happen on
  flee/victory/death/interrupt; a crash mid-fight loses only that attempt's
  progress since the last save (acceptable).
- `apply_death_penalty` must not wipe `player["map_boss"]` (unlike wild state);
  it only scrubs transients. The boss remains for the season.
- `city_screen._launch_dungeon` scrubs `_map_boss_site` / `_map_boss_prev_floor`
  / `_combat_time_label` so a city dungeon can never inherit arena context.
- `player["floor"]` is snapshotted to `_map_boss_prev_floor` on entry and
  restored on every exit. **Never** touch `max_floor` or `city_floors`.

---

## 12. Testing

### 12.1 Unit tests — `tests/test_map_boss.py`

**State / lifecycle**

- `test_state_backfill` — old save gains the block; idempotent.
- `test_no_spawn_before_floor_20_clear` — `max_floor <= 20` spawns nothing.
- `test_first_spawn_current_season_echo_0` — current season, Echo 0, level 20,
  full HP.
- `test_kill_spawns_next_echo_immediately` — same site, Echo+1, level+20, full
  HP, new mechanic effect/resists/mechanic rank.
- `test_kill_chain_three_echoes` — levels 20/40/60/80, same site, full HP each.
- `test_flee_does_not_advance_echo`.
- `test_death_does_not_advance_echo`.
- `test_echo_reuses_site` — all same-season Echoes share position/biome.
- `test_spawn_deterministic_per_season` — same season/day → same site.
- `test_season_boundaries_are_90_days` — days 1/91/181/271/361; a season's
  `next_season_day` is the next of those.
- `test_season_rotation_on_season_boundary` — Spring Echo N → Summer Echo 0 at
  a new site on day 91.
- `test_season_rotation_replaces_undefeated_echo`.
- `test_kill_crossing_season_spawns_new_season` — no old-season next Echo.
- `test_season_swap_not_duplicated` — `maybe_spawn` during the time commit and
  the victory handler must not spawn two new seasonal Wardens.
- `test_old_save_already_gated_spawns_current_season_echo_0`.
- `test_old_120day_save_migrates` — the derived season changes, the old active
  is dropped, `best_echo` survives.
- `test_departure_and_spawn_journal`.

**Start at proven depth**

- `test_depth_offer_when_best_exceeds_current_echo` — offered only then.
- `test_depth_choice_sets_echo_and_full_hp` — the chosen Echo's own level, HP,
  armor, resists, mechanic tier and rank.
- `test_depth_never_refights_a_cleared_echo` — no re-fight path exists; the
  offer is a one-way jump, never a repeatable fight.
- `test_depth_echo_0_still_available` — warm-up keeps `state["echo"] = 0`.
- `test_depth_discards_partial_hp` — recalling overwrites the current Echo hp.
- `test_depth_declined_remembered_for_season` — no re-offer until the season
  turns.
- `test_depth_cap` — `MAP_BOSS_START_DEPTH_CAP` clamps the opener.
- `test_depth_journal_entry`.

**Seasonal identity / mechanics**

- `test_roster_elements_weaknesses` — Spring earth/fire, Summer fire/water,
  Autumn wind/thunder, Winter water/fire.
- `test_roster_names_glyphs` — four names and seasonal marker glyphs.
- `test_four_bestiary_entries` — each seasonal Warden records separately.
- `test_biome_preference_fallback` — preferred biome when available; any
  accessible city otherwise.
- `test_mechanic_rank_1_to_4` — `1 + Echo // 3`, cap 4.
- `test_bloom_mechanic` — stacks, poison threshold, consume-heal burst.
- `test_heat_mechanic` — stacks, burn threshold, Solar Flare reset.
- `test_harvest_mechanic` — bleed-driven stacks, Reap + lifesteal reset.
- `test_frostbite_mechanic` — stacks, freeze threshold, Ice Armor melt by fire.
- `test_mechanic_scale_by_rank` — stack caps/values.
- `test_seasonal_add_names_no_bestiary` — Bloomling/Cinderling/Huskling/
  Frostling, no bestiary entry, no loot/XP.

**Scaling**

- `test_echo_levels_20_40_60_80` — E0/E1/E2/E3 levels; E4+ stays 80.
- `test_echo_curve_e0_e1_e2_e3_e5_e10_e20_e30` — HP, damage, armor, resists,
  status res.
- `test_resist_caps` — all res 1.60, biome 1.70, status res 0.85.
- `test_weakness_never_scales` — seasonal weakness stays 0.70 at E30.
- `test_mechanic_upgrade_ladder` — one new mechanic effect per Echo; tier 10
  cap; rank scaling after.
- `test_no_double_phase_scaling` — `enemy_stats(BOSS_KEY)` without `player`
  ignores Morning/Noon/Night multipliers.

**Combat / time**

- `test_pre_round_hook_optional_noop` — existing superboss callers are unchanged.
- `test_projected_clock_boundaries` — Morning → Noon → Night → Morning.
- `test_dawn_reset` — phase buffs cleared, seasonal adds despawn, 2-round Dawn
  Lull.
- `test_night_extra_action` — `actions=2` only at Night.
- `test_seasonal_add_spawn_cap` — 2 at Noon, 4 total at Night, never 5.
- `test_time_commit_10_rounds` — 10 blocks spent once on exit.
- `test_time_commit_crosses_day` — +50 stress, day rolled once.
- `test_no_rollover_mid_fight` — `process_day_rollover` not called per round.
- `test_flee_always_allowed` — including at 1% HP.
- `test_hp_persists_across_flee`.
- `test_hp_persists_across_death`.
- `test_reentry_uses_saved_hp`.
- `test_new_echo_full_hp`.
- `test_victory_advances_echo_and_sets_best`.
- `test_reform_dialog_fight_or_leave` — Face starts the next fight; Leave keeps
  the next Echo active.
- `test_leave_arena_keeps_next_echo`.
- `test_result_order_season_crossing` — old Echo rewards resolve, new seasonal
  Warden spawns, no old-season next Echo.

**Rewards**

- `test_gold_xp_formula` — E0/E1/E3, daily bonuses, Night kill +25%.
- `test_cache_rarity_curve` — E0 Rare+ 10% epic; E9 100% epic; E10 30%
  legendary; no legendary before E10.
- `test_cache_gear_level` — cache gear level = boss level, capped 80.
- `test_cache_and_flower_season_element`.
- `test_consumable_tier_and_theme`.
- `test_unique_milestones_total` — 1/3/6/10 across seasons.
- `test_no_duplicate_uniques` — second milestone converts to a cache.
- `test_post_10_second_cache`.
- `test_every_echo_kill_grants_full_loot`.
- `test_no_loot_on_flee_death_interrupt`.
- `test_no_superboss_ledger_or_shards`.

**Uniques**

- `test_warden_signet_phase_bonus` — player and ally.
- `test_long_day_edge_stacks_and_dawn_reset` — player and ally.
- `test_echo_mantle_night_upgrade` — player and ally.
- `test_sundial_crown_once_per_day` — player and ally, day recharge.
- `test_unique_state_cleared_on_exit`.

### 12.2 Diagnostics

- `tests/_diag_map_boss.py` — headless runtime: seasonal spawn, four mechanics,
  3-phase fight with mocked inputs, flee, re-entry at saved HP, reform loop,
  season rotation, drop table, unique milestones. Set stdout to UTF-8 for piped
  runs (cp932 console).
- `tests/_diag_map_boss_map.py` — Tk: seasonal glyphs, hit-testing, panel HP
  bar, loot preview, travel button, expiry grace, reform/season-change dialogs.
- `tests/_diag_map_boss_gui.py` — DungeonScreen branding, projected clock,
  `[PHASE]` pin, death screen, leave confirm `focus_no`, reform-window loot lines.
- `tests/_diag_map_boss_playtest.py` — the scripted counterpart of
  `docs/map_boss_playtest_checklist.md`: walks one Spring season end to end
  (gate → spawn → panel → two **real** fights → flee → death → season turn) and
  prints the resulting journal.
- `tests/_diag_map_boss_tuning.py` — fight-length report across four gear bands
  and both day phases (§13.5).
- Use `tests/_tk_test_utils.shared_tk_root`; never create/destroy your own
  `tk.Tk()`; `unittest.SkipTest` when Tk is unavailable.

### 12.3 Manual playtest checklist

- [ ] Clearing Floor 20 spawns the current season's Warden at Echo 0, with a
  journal notice and a seasonal marker.
- [ ] Travel → arena → intro; no stale dungeon log.
- [ ] On a later season, arrival offers the recalled depth; choosing it drops
  the party straight into Echo N at full HP.
- [ ] Declining the offer keeps Echo 0 and is not re-offered that season.
- [ ] A recalled Echo cannot be re-fought after it dies — the ladder only goes
  forward.
- [ ] Kill Echo 0 → Echo 1 reforms immediately at the same site (Lv 40, full
  HP); the reform dialog offers Fight / Leave.
- [ ] "Face the next Echo" starts the next fight immediately; party HP is not
  refilled.
- [ ] "Leave Arena" returns to the city; the next Echo remains active at the
  site.
- [ ] Flee at 50% → marker shows 50% → re-enter at 50%; the Echo did not
  advance.
- [ ] Flee at 1% → can still flee; next attempt starts at 1%.
- [ ] Death at 50% → death screen names the seasonal Warden; the same Echo
  remains at 50%.
- [ ] Echo levels read 20 / 40 / 60 / 80 / 80... within one season.
- [ ] Each Echo unlocks the next seasonal-mechanic effect (tier 1→10).
- [ ] Start at Morning, Noon and Night; verify phase lines and aggression.
- [ ] Fight across a day boundary; verify dawn reset + HP/time commit.
- [ ] Kill at Night → +25% gold, +2 flowers.
- [ ] Next season boundary (day 91/181/271/361) → the **next season's**
  Warden replaces the old one at Echo 0, with a new name, glyph,
  element/weakness, mechanic and site.
- [ ] A kill that crosses a season boundary spawns the new seasonal Warden,
  not the old season's next Echo.
- [ ] All four seasonal mechanics are observable: Bloom/Poison, Heat/Burn,
  Harvest/Bleed, Frostbite/Freeze + Ice Armor.
- [ ] Kill 1/3/6/10 → unique drops; no duplicates after.
- [ ] 11th kill → second cache, no unique.
- [ ] Old save already past Floor 20 → current season's Echo 0 appears.
- [ ] `max_floor`/`city_floors` unchanged after every outcome.
- [ ] All four uniques work on an ally as well as the player.

---

## 13. Implementation order (phases)

| Phase | Work | Files | Effort |
|---|---|---|---|
| **0** | 360-day calendar: twelve 30-day months, 90-day seasons, `season_start_day` / `next_season_day` helpers, date wrap 1–12 | `core/events.py`, `docs/time_system_design.md`, `tests/_diag_season_weather.py` | ✅ done 2026-11-13 |
| **1** | Seasonal state block, `ensure_map_boss_state`, Floor-20 gate, one site per season, per-death Echo scaling, start-at-proven-depth state, reward pre-roll, journal hooks | `world/map_boss.py`, `resources/map_boss_data.py`, `core/events.py`, `core/character.py`, `tests/test_map_boss.py` | ✅ done 2026-11-13 |
| **2** | World map seasonal markers/panel/travel/arrival/start-depth dialog/expiry grace + DungeonScreen branding | `gui/screens/world_map_screen.py`, `gui/screens/dungeon_screen.py` | ✅ done 2026-11-13 |
| **3** | Combat module: encounter builder, phase clock, seasonal adds, four mechanics (Bloom/Heat/Harvest/Frostbite) with 10-tier upgrade ladders, HP persistence, reform loop, flee/death/interrupt; add optional `pre_round_hook` to the shared superboss loop | `combat/map_boss.py`, `combat/superboss/superboss_common.py`, `world/dungeon.py`, `combat/combat_ui.py` | ✅ done 2026-11-13 |
| **4** | Rewards, four uniques, item defs, unique effects, reform/season-change dialogs, victory/death/return routing | `resources/items.py`, `combat/weapon/*.py`, `gui/screens/city_screen.py`, `gui/screens/death_screen.py` | ✅ done 2026-11-13 |
| **5** | Polish: journal/notices, changelog/README/wiki, tuning, full playtest | `gui/screens/changelog_screen.py`, `README.md`, `wiki/`, tests/diags | ✅ done 2026-11-13 |

**Total estimate:** ~1,800–2,300 LOC across ~15 files, roughly one medium
work-session per phase. Phase 3 is the risky one; Phase 1 can ship dark (state
and spawn only) before the fight exists.

### 13.1 Phase 1 API (shipped 2026-11-13)

`pandemonium/resources/map_boss_data.py` — pure data, no game imports:

- `WARDENS` (four seasons: name, glyph, element, weakness, `biomes`, mechanic,
  stack tag, signature status, add name, stack cap)
- `MECHANIC_TIERS` (10-entry upgrade ladder per mechanic; `id`/`label`/`desc`)
- the §14 `MAP_BOSS_*` tuning constants
- `get_warden()` (accepts a season **or** mechanic id), `mechanic_tiers()`,
  `mechanic_tier_index()`, `mechanic_effects()`, `mechanic_labels()`,
  `next_mechanic_effect()`, `mechanic_rank()`, `mechanic_rank_scale()`,
  `stack_cap()`, `ELEMENT_CONSUMABLE`

`pandemonium/world/map_boss.py` — runtime, no GUI imports:

| Function | Purpose |
|---|---|
| `ensure_map_boss_state(player)` | Backfill/migrate `player["map_boss"]` (called from `character._ensure_time_event_fields`) |
| `gate_met(player)` | `max_floor > 20` |
| `current_season(player)` | `events.get_season` passthrough |
| `maybe_spawn(player)` / `sync_season(player)` | Idempotent spawn/rotate; returns the new site or `None` (called from `events.process_day_rollover`; Phase 2 also calls it on map open) |
| `get_active_boss(player)` | The active Echo dict or `None` (never spawns) |
| `echo_stats(echo)` | Level/HP/damage/STR/armor/resists/mechanic tier+rank for an Echo |
| `elemental_profile(season, echo)` | Per-element resist map (§6.4) |
| `cache_rarity(echo, rng=None)`, `roll_cache()`, `roll_consumables()`, `roll_flower()`, `roll_rewards()` | Pre-rolled loot preview (§8) |
| `gold_xp_reward(echo, player=None, night=False)` | Gold/XP for one kill |
| `record_victory(player)` | Counters, `best_echo`, per-season defeats, `defeated`/`hp` — call **before** the time commit |
| `advance_echo(player, killed=None)` | Next Echo at the same site; pass the killed site (dict or id) so a crossed season boundary cannot double-spawn — call **after** the time commit |
| `save_boss_hp(player, hp)` | Persist HP after a flee/death (also bumps `attempts`/`last_fought_day`) |
| `set_result(player, "victory"/"fled"/"dead")` | `last_result` bookkeeping |
| `start_depth_offer(player)` / `apply_start_depth(player, echo=None)` / `decline_start_depth(player)` | §5.7 start-at-proven-depth (upward jumps only — a cleared Echo is never re-entered) |

Journal entries are written by the runtime with the `[MAP BOSS]` tag (deduped
per day+name): *A Warden Notices*, *The Season Turns*, *The Warden Reforms*,
*The Season Closes*, *Depth Recalled*.

`tests/test_map_boss.py` — 79 tests covering the above (state/backfill, gate,
site determinism/placement, Echo loop, season rotation, start-depth, roster,
mechanic ladder, the §6.2 curve table, resist caps, reward pre-roll, journal,
the view/travel helpers and the day-rollover hook).

### 13.2 Phase 2 — world map + arena entry (shipped 2026-11-13)

Runtime additions to `world/map_boss.py` (all consumed by the GUI):

| Function | Purpose |
|---|---|
| `is_current(player, site)` | Same id + same season — used before travel and again on arrival (expiry grace) |
| `build_journey_to_warden(player)` | `build_journey_to_dungeon(..., to="map_boss")`; `None` with no live Warden |
| `next_echo_preview(player)` | Level/HP/tier/next-effect of the Echo that reforms after a kill |
| `next_unique_milestone(player)` | `{"index","at","victories"}` for the panel's trophy line |
| `season_days_left(player, site=None)` | Days until the season boundary |
| `echo_label(echo)` | `0` → `0`, `1`…`10` → `I`…`X`, else digits |

World map (`gui/screens/world_map_screen.py`):

- Marker `🌱 E0`, `· 63%` while the Echo is hurt, gold outline
  (`#d4a017`, selected `#f1c40f`) — visually distinct from violet wild ruins
  and the violet EH site. Placement is inset (`SITE_INSET_X/Y`) so the single
  marker is never half-clipped at the canvas edge.
- Hit-test order is **city → Warden → wild → EH**; hover, Escape and
  deselection all follow the same precedence.
- Panel: Warden/season/Echo/level, HP bar, mechanic name + signature status,
  biome, element, weakness, nearest city, departs, travel estimate, next Echo,
  recalled depth, spoils preview (cache name+rarity, consumables, flower, next
  trophy) and the "Travel to the Warden" button. The separate **MECHANIC**
  block (tier/effect list + resist line) was removed on request — the uncovered
  section is just `Mechanic` in the stat rows beside the phase colours.
- Travel uses the wild off-road journey to the synthetic `map_boss` node;
  cargo-overload and ferry-cost gates match the wild flow.
- Arrival sets `origin_city = nearest_city`, `location = "dungeon"`,
  `_map_boss_site`, snapshots `_map_boss_prev_floor`, sets
  `_combat_floor_label = "Arena"`, pops the previous run's `_dungeon_log` /
  `pandemonium_mode` / `_eh_in_run` / `wild_dungeon_id`, then runs the
  start-depth dialog (`focus_no` → "Begin at Echo 0") before opening the arena.
- Expiry grace: if the season turned mid-journey the party is dropped at the
  nearest city with a message; no combat, no penalty.
- Result routing: `dead` → `DeathScreen(death_type="map_boss", boss_name,
  boss_season, boss_echo)`; `map_boss_locked` (interim) → explanatory window;
  `fled`/`timeout`/`None` → defensive scrub + CityScreen; `save_exit` → menu.

Arena (`gui/screens/dungeon_screen.py`): title = Warden name, subtitle =
`Season · Echo · Lv · Mechanic`, top bar `🌱 Spring Echo 0 · HP 63% | <track>`,
left panel relabelled **Arena** with a single `⚔ ARENA` node, leave button
"← Leave Arena" and a `focus_no` confirm that names the season deadline.

Interim arena guard (`world/dungeon.py`): `explore_dungeon` dispatches on
`player["_map_boss_site"]` to `_explore_map_boss_arena`, which currently
returns `MAP_BOSS_ARENA_SEALED` (`"map_boss_locked"`) after scrubbing. **Phase 3
replaces this body** with the three-phase encounter; travel, dialog, branding
and routing are already exercised end to end.

Scrubbing: `save_load.load_game`, `utils.apply_death_penalty` and
`city_screen._launch_dungeon` all pop `_map_boss_site` / `_map_boss_prev_floor`
/ `_map_boss_in_fight` / `_map_boss_clock_blocks` / `_combat_time_label`;
`player["map_boss"]` itself always survives.

Diagnostics: `tests/_diag_map_boss_map.py` (marker/hit-test/panel/travel/
depth dialog/expiry grace/routing) and `tests/_diag_map_boss_gui.py` (arena
branding, leave confirm, death screen).

### 13.3 Phase 3 — the arena fight (shipped 2026-11-13)

`pandemonium/combat/map_boss.py` (new) runs one attempt through
`superboss_common.superboss_combat_loop` — a runtime reuse, not a
superboss-pool membership.

| Piece | Notes |
|---|---|
| `build_encounter(site)` | One boss built with `enemy_stats(KEY)` **without** a player (no time-of-day/event multiplier), then level/HP/STR/`con_mod`/`elemental_res`/`status_res` overwritten from the Echo payload |
| `build_add(site, boss, i)` | Synthetic `map_boss_add`: 3% of the boss's max HP, 0.4× its STR, `no_bestiary`, no loot — Bloomling / Cinderling / Huskling / Frostling |
| `_pre_round_hook` | Advances the **projected clock** (`start_blocks + round − 1`, never spends time), renders `_combat_time_label`, applies phase buffs (`source="map_boss_phase"`), the DawnLull, and the seasonal mechanic tick. Returns `"victory"` when the Warden is gone |
| `_pre_player_hook` | Spawns adds — 2 at Noon, 4 at Night, capped so boss+adds ≤ 5 |
| `_enemy_turn_hook` | Phase action kit: Censure / Weight of Hours / Noonfire / Nightfall / Hour Reap, plus The Long Day every 3rd action (2nd at Night). Returns `(actions, skip, extra_logic, armor_mult, temp_str)` |
| `_on_player_hit_hook` | Winter only: fire melts an Ice Armor layer; Echo 7 Shatter hits the attacker |
| `_custom_hud` | `Seasonal Warden: …` header plus `ECHO n`, phase, and `BLOOM×n` / `HEAT×n` / `HARVEST×n` / `FROST×n` / `ICE×n` tags |
| `combat_map_boss(player, floor, enemies)` | The entry point; writes `player["_map_boss_rounds"]`, clears phase/mechanic buffs before returning |

Mechanics are driven by the site's `mechanic_effects` list (the ten tiers), so
every Echo unlocks exactly the effects its tier says. Rank scaling uses
`mechanic_rank_scale()` on heal/DoT/lifesteal values.

`world/dungeon.py`:

- `_explore_map_boss_arena(player, ..., arena_override=None)` — builds the
  encounter, runs it (or hands it to the GUI via `arena_override`), then
  `_map_boss_arena_exit` applies §7.7's ordering: `record_victory` /
  `save_boss_hp` **before** the single `spend_blocks(rounds, source="map_boss")`
  commit, then `advance_echo(killed=snapshot)`. Returns `map_boss_victory`,
  `map_boss_season_shift`, `dead` or `fled` (interrupts count as flee). The
  exit saves, then scrubs every transient.
- `explore_dungeon(..., map_boss_override=)` passes the GUI hook through.

`superboss_common.superboss_combat_loop(..., pre_round_hook=None)`: the new
hook fires after `prune_dead` and **before** `print_round_header` (with
`context["round"]` set), so the projected clock labels the round it belongs
to. Existing superbosses pass nothing.

GUI: `DungeonScreen._gui_map_boss` hosts the fight in `CombatScreen`
(`combat_context="map_boss"`, `combat_func=combat_map_boss`, shared enemy
list); `CombatScreen._map_boss_top_bar` renders
`⚔ Warden | Spring Echo I | HP 63% | ☀ Morning …` using the projected label,
and `[phase]` was added to `_GIMMICK_TAGS` so phase banners stay pinned.
`current_time_label()` prefers `player["_combat_time_label"]`.

The world map routes `map_boss_victory` to the **reform window** (Face the next
Echo / Leave Arena) and `map_boss_season_shift` to the season-change window.

Tests: `tests/test_map_boss.py` grew to 106 (encounter/clock/phases/adds/four
mechanics/outcomes/HP persistence/single time commit/full scripted fights).
`tests/_diag_map_boss.py` covers the same headless end to end.

### 13.4 Phase 4 — rewards & the four uniques (shipped 2026-11-13)

Items (`resources/items.py`, section *Seasonal Map Boss Drops*): `warden_signet`,
`long_day`, `echo_mantle`, `sundial_crown` — `unique: True`,
`drop_rarity: "unique"`, `drop_source: "warden_long_day"`. The engine's unique
convention rewrites them at import (§9 note, 2026-11-09): stats are normalized
to the slot budget and the authored two-element profile collapses to one
identity element (`UNIQUE_PRIMARY_ELEMENTS` now pins light / fire / physical /
light for the four), with the two remaining slots left for flower infusion.

`combat/weapon/map_boss_uniques.py` (new) — every effect is **actor-based**, so
all four work for the player and for allies:

| Function | Purpose |
|---|---|
| `actor_has_warden_signet/long_day_edge/echo_mantle/sundial_crown(actor)` | Equipped checks (both accessory slots allowed) |
| `actor_phase(actor)` | Projected arena clock (`_map_boss_clock_blocks`) first, else the real block clock |
| `signet_bonus(actor)` / `long_day_bonus(actor)` / `apply_long_day_damage(actor, dmg)` | Damage hook — Signet phase bonus (+8% Noon / +16% Night) plus Edge stacks (+3%/round, cap +30%) |
| `tick_long_day(actor)` | +1 stack per round; resets only on the **transition** into Morning |
| `refresh_echo_mantle(actor)` | Sourced `defense_pct` buff (−12%, −20% at Night), always exactly one |
| `try_sundial_crown_save(actor)` | Once per day (`sundial_used_day`): 1 HP, clears every non-permanent debuff and the `slowed`/`blinded`/`silenced`/`dreaded`/`cursed`/`stunned` flags |
| `begin_map_boss_uniques(player)` / `sync_party_phase(player)` / `clear_map_boss_unique_state(actor)` | Lifecycle: init, mirror the projected clock onto allies, battle-end cleanup (the day stamp survives) |

Wiring: the damage hook runs in all four paths (`player_actions`, `skills`,
`ally`, `ally_skills`); `_tick_all_state` + `clear_battle_scoped_state` +
`_combat_inner` cover the standard engine and `superboss_common` mirrors the
same calls; `status_effects.try_consume_death_ward` falls through to the
Sundial after the Event Horizon Emperor attempt; `combat/map_boss._pre_round_hook`
calls `sync_party_phase(player)` whenever it advances the projected clock.

`world/map_boss.grant_victory_rewards(player, snapshot, night=None)` — §8.2's
spoils from the *killed* Warden's snapshot (gold with the daily bonus, title
gold-find and the +25% Night kill; XP to the player and every living ally; the
pre-rolled cache; two consumables; one flower, two on a Night kill) plus the
§8.4 trophy ladder (`MAP_BOSS_UNIQUE_ITEMS`, milestones 1/3/6/10). Uniques are
forced into the bag even when it is full; once all four are owned every later
kill converts the slot into a second cache at the current Echo's rarity floor.
Nothing touches superboss records, the superboss pool, shards, titles, the
Pandemonium multiplier or bounties (§8.6).

`world/dungeon._map_boss_arena_exit` calls the grant between the time commit and
`advance_echo`, reads the Night flag from the killing round's projected block,
and stashes the summary in `player["_map_boss_victory"]` (never saved —
`load_game`, `apply_death_penalty` and the GUI all treat it as transient).
`world_map_screen._map_boss_loot_lines()` renders the spoils in both the reform
window and the season-change window, and both consume the stash.

Tests: `tests/test_map_boss.py` grew to 141 (item defs/budgets, all four
effects for player *and* ally, death-ward fallthrough, reward formulas, Night
bonus and extra flower, milestone ladder with no duplicates and the post-ladder
second cache, no loot on flee/death, engine lifecycle hooks, live arena fight
hitting the damage hook). `tests/_diag_map_boss.py` section 19 and
`tests/_diag_map_boss_gui.py` section 5 cover the same ground headless.

### 13.5 Phase 5 — polish, docs and the scripted playtest (shipped 2026-11-13)

Delivered:

- **Journal names** now match §10.6 exactly; the victory entry is
  `[MAP BOSS] Warden Felled — {Season} Echo {n}` with the gold/XP/trophy
  summary in its description (`_journal` still dedupes per day+name). The
  Journal's Event tab paints `[MAP BOSS]` in the world-map marker's gold.
  *Deviation from §10.6:* the beats are **not** pushed through
  `events.record_event` / `queue_event_alerts` — that queue is the modal
  *Event Notice* popup for daily world events, which would stamp
  `[RANDOM]`/`[FIXED]` on the entry and add a meaningless "Duration: Until the
  end of the day" line. The Journal is the delivery channel, as §10.6's
  "no toasts" rule intends.
- **Full-bag handling** — a trophy is force-added and never lost; a cache that
  cannot fit is reported as `Bag full — left behind: …` in the reform window
  (`summary["left_behind"]`).
- **World-map panel** names the next trophy (`★ Next trophy: Warden's Signet —
  1 total victories (1 to go) · n/4 claimed`).
- **README** gained a full *Seasonal Map Boss* chapter (unlock, arena rules,
  the four Wardens, the four mechanics, the phase table, the Echo curve with
  gold/XP per Echo, loot, the trophy ladder) plus a TOC entry and an FAQ answer;
  `wiki/index.html` was regenerated from it. `tests/gen_wiki_html.py` had
  pre-package paths (`resources/…` instead of `pandemonium/resources/…`) and
  could not run — fixed, so the wiki is buildable again.
- **Changelog** — a *The Wardens of the Long Day* + *Loot & Trophies* block
  under the current `v0.1.9.1 — The Family We Choose` header (no version bump).
- **`docs/map_boss_playtest_checklist.md`** — eleven sections mirroring §12.3
  with the shipped numbers spelled out, plus a "known tuning targets" table.
- **`tests/_diag_map_boss_playtest.py`** — a scripted season: gate → spawn →
  panel facts → **two real fights** through `_explore_map_boss_arena` → flee →
  death → season crossing → the 1/3/6/10 trophy ladder, printing the journal.

Measured fight length (`tests/_diag_map_boss_tuning.py`, solo attacker, Noon):

| Gear band (STR / HP / CON) | Echo 0 | Echo 1 |
|---|---|---|
| fresh Floor-21 (60 / 700 / 30) | ~14–21 rounds | ~14–22 rounds |
| geared (90 / 1,000 / 35) | ~10–15 | ~10–14 |
| strong (140 / 1,600 / 40) | ~7–9 | ~6–7 |
| over-geared (220 / 6,000 / 40) | ~4–5 | ~5 |

A real party (player + allies + skills) sits two bands stronger than a solo
attacker, so a geared group lands in the intended **5–10 rounds**, i.e. one
kill costs most of a single in-game day. Night starts cost 1–2 extra rounds and
more HP — the intended risk for the +25% gold and the second flower.

No §14 constant was changed in this pass: the measured band matches the design
target, and the playtest checklist calls out the knobs to watch
(`MAP_BOSS_BASE_HP`, `MAP_BOSS_BASE_STR`, `MAP_BOSS_ARMOR_CAP`,
`MAP_BOSS_DAWN_LULL_ROUNDS`, `MAP_BOSS_NIGHT_ACTIONS`, the epic-chance ramp and
the payout constants) before a live tuning session.

---

## 14. Tuning constants (single source)

```python
# Unlock + schedule
MAP_BOSS_UNLOCK_MAX_FLOOR = 20      # gate is max_floor > 20
MAP_BOSS_MONTH_LENGTH = 30          # a game month (the billing cycle)
MAP_BOSS_MONTHS_PER_SEASON = 3      # 3 × 30 = a 90-day season
MAP_BOSS_SEASON_LENGTH_DAYS = 90    # = events.SEASON_LENGTH_DAYS
MAP_BOSS_SEASONS = ("spring", "summer", "autumn", "winter")
MAP_BOSS_LEVEL_START = 20
MAP_BOSS_LEVEL_STEP = 20
MAP_BOSS_LEVEL_CAP = 80
MAP_BOSS_MECHANIC_RANK_STEP = 3     # +1 rank every 3 Echoes
MAP_BOSS_MECHANIC_RANK_CAP = 4
MAP_BOSS_START_DEPTH_CAP = None     # None = honour best_echo; int = clamp the opener
MAP_BOSS_BLOOM_CAP_BASE = 3
MAP_BOSS_HEAT_CAP_BASE = 5
MAP_BOSS_HARVEST_CAP_BASE = 4
MAP_BOSS_ICE_CAP_BASE = 3

# Base stats (Echo 0 / level 20)
MAP_BOSS_BASE_HP = 1000
MAP_BOSS_BASE_STR = 30
MAP_BOSS_BASE_ARMOR = 12
MAP_BOSS_BASE_STATUS_RES = 0.20

# Level + Echo curves
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
MAP_BOSS_WEAKNESS = 0.70
MAP_BOSS_STATUS_RES_PER_ECHO = 0.03
MAP_BOSS_STATUS_RES_PER_LEVEL = 0.005
MAP_BOSS_STATUS_RES_CAP = 0.85
MAP_BOSS_MECHANIC_TIER_CAP = 10

# Phase aggression
MAP_BOSS_NOON_DAMAGE = 1.10
MAP_BOSS_NIGHT_DAMAGE = 1.30
MAP_BOSS_DAWN_LULL_DAMAGE = 0.85
MAP_BOSS_NIGHT_ACTIONS = 2
MAP_BOSS_DAWN_LULL_ROUNDS = 2

# Drops
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
```

All numbers are first-pass. The playtest dials, in order of likely adjustment:
level step (+20 vs +10), HP per level, Night damage/actions, status resistance
cap, cache legendary cadence, unique milestone counts.

---

## 15. Risks & mitigations

1. **Mid-combat day rollover.** Per-round `advance_time` would spawn wild
   dungeons, bills and dispatch mid-fight. **Mitigation:** projected clock +
   one batch commit on exit; test `process_day_rollover` is never called per
   round.
2. **Season-boundary result ordering.** Time commit can swap the Warden while a
   fight is resolving. **Mitigation:** resolve/clear the old active before
   committing time; grant rewards from a snapshot (§7.7). A kill before the
   boundary reforms the next Echo; a kill crossing the boundary spawns the new
   seasonal Warden and must **not** also create the old season's next Echo.
3. **HP persistence vs. save points.** A crash mid-fight loses the attempt.
   **Mitigation:** update `state["active"]["hp"]` every round; save on
   flee/victory/death/interrupt; document the acceptable loss.
4. **Superboss-loop reuse side effects.** The loop is shared with 16 superbosses.
   **Mitigation:** call it directly with a map-boss-only spec; never touch
   `superboss_pool`, `defeated_superbosses`, shards or the milestone dispatch.
5. **Phase buff leakage.** Repeated phase changes could stack buffs forever.
   **Mitigation:** all phase buffs use `source="map_boss_phase"`;
   `_clear_phase_buffs` runs before every transition and on exit.
6. **Add/HUD cap.** Four seasonal adds + boss = 5. **Mitigation:** cap spawns
   at 4; never rely on the loop's emergency cull.
7. **Unique actor parity.** New uniques could work for the player only.
   **Mitigation:** follow the actor-based convention; test player + ally for all
   four; wire both damage paths and both combat lifecycles.
8. **Economy inflation from chained Echo kills.** Every Echo kill grants a full
   cache, but the rarity curve is deliberately tight: Rare+ start, epic ramps to
   100% at Echo 9, and legendary is only **30% at Echo 10+**. **Mitigation:**
   each kill is a new, stronger Echo, not a same-level farm; the level-20 Echo
   is only available once per season. Playtest the cache cadence with 2–4 kills
   per season.
9. **Boss outscaling the player.** Echoes jump +20 levels **per kill** and grow
   forever after level 80. **Mitigation:** seasonal reset to level 20 keeps the
   entry point fresh; weakness never scales; resist/status caps; flee always
   allowed; the boss is optional; the panel shows Echo, level and mechanic before
   travel. Playtest the level-40/60/80 jumps.
10. **Marker overlap.** Wild markers are weekly and can crowd the canvas.
    **Mitigation:** deterministic placement avoids active wild positions and
    the EH site; map boss wins hit-test ties over wild.
11. **Stale world-map callback.** The victory dialog can outlive the screen.
    **Mitigation:** use the wild-dungeon `choice_dialog` pattern with
    `self.sm.get_top_screen()`.
12. **Enter-key instant confirm on flee.** **Mitigation:** `focus_no=True` on
    the leave-arena confirm (EH lesson).
13. **Stale log/context.** **Mitigation:** pop `_dungeon_log`, scrub
    `pandemonium_mode`/`_eh_in_run`/`_combat_floor_label` on entry; snapshot and
    restore `player["floor"]`; never touch `max_floor`/`city_floors`.
14. **Old-save gaps.** A save loaded after several seasons could see no boss or
    the wrong Warden. **Mitigation:** `_sync_season` on every access; infer the
    current season and spawn its Echo 0; drop the old 20-day active site.
15. **Short first season.** Clearing Floor 20 late in the season leaves a
    partial first season. **Mitigation:** 90-day seasons absorb this well;
    season alignment stays strict, and the only dial left is delaying the first
    spawn to the next season boundary (§5.6). Not a bug.
16. **Four-mechanic complexity.** Bloom/Heat/Harvest/Frostbite could drift or
    break one another. **Mitigation:** one data-driven mechanic table and one
    boss module; each mechanic has its own unit test and a shared HUD tag
    contract.
17. **Unique milestone acceleration.** Chaining Echoes can hit 1/3/6/10 quickly.
    **Mitigation:** the escalating Echo difficulty is the limiter; milestone
    counts are a playtest dial (§8.4).
18. **Tk test flakiness.** **Mitigation:** shared Tk root, skip if unavailable,
    UTF-8 stdout in diag scripts.
19. **Start-at-proven-depth opener is a trap.** Depth is lifetime, but a new
    season's Warden has a different element and weakness. **Mitigation:** the
    dialog names the element and weakness, Echo 0 stays available, flee is
    always allowed, and `MAP_BOSS_START_DEPTH_CAP` can clamp the opener.

---

## 16. Open items / future hooks

- **First-season timing:** locked as the current season's Warden immediately
  on unlock; the first season can be partial. Dial: delay to the next season
  boundary for a full first season (§5.6).
- **Level pace:** +20 per Echo (20/40/60/80) is locked. If playtest finds the
  jump too steep, change `MAP_BOSS_LEVEL_STEP` to 10 (20/30/40/50/60/70/80).
- **Season length:** 90 days (three 30-day months of the 360-day calendar);
  one seasonal Warden per season, with unlimited Echoes per season until the
  boundary (the Echo difficulty is the limiter).
- **Start depth:** honored up to `best_echo` by default. Dial:
  `MAP_BOSS_START_DEPTH_CAP` if a level-80 opener after a season turn proves too
  harsh.
- **Wound carry:** currently HP resets on each new Echo. If playtest wants a
  long-term chipping game, add a `wound_carry_pct` dial (cap 25%) rather than
  carrying exact HP; exact carry would let a patient player trivially kill every
  future Echo.
- **Echo forge / material:** not needed in v1 — the post-10 second cache covers
  the long tail. A future "Echo Core" could reforge cache rarity or add a fifth
  unique.
- **Title:** "The Season's Bane" at 10 victories / one of each seasonal Warden
  is a natural titles-system hook, deferred to avoid scope creep.
- **Leaderboard/records:** track `best_echo`, `defeated_total`, per-season
  defeats, fastest kill (fewest rounds) in the Journal or a records screen later.
- **Multi-floor variant:** explicitly out of scope; the single arena is a design
  choice, not a shortcut.
- **Playtest dials:** level step (+20 vs +10), HP per level, seasonal-mechanic
  stack caps/values, Night extra action, status resistance cap, cache legendary
  cadence, and unique milestone counts (1/3/6/10).

---

## 17. Acceptance criteria

- [ ] After Floor 20 is cleared (`max_floor > 20`), the **current season's**
  Warden spawns immediately at Echo 0.
- [ ] Killing the Warden **immediately reforms the next Echo** at the same site
  (+20 levels, more HP/resists/new mechanic effect/mechanic rank), with a
  Fight / Leave reform dialog.
- [ ] Fleeing or dying does **not** advance the Echo; the same Echo keeps its HP.
- [ ] On the first day of the next season (day 91/181/271/361), the **next
  seasonal Warden** replaces the old one at Echo 0, with a new name, glyph,
  element/weakness, mechanic and site.
- [ ] A party whose `best_echo` exceeds the season's current Echo is offered
  that depth on arrival; choosing it builds that Echo at full HP, and no cleared
  Echo can ever be re-fought.
- [ ] The four seasonal Wardens and mechanics are present: Spring Bloom/Poison,
  Summer Heat/Burn, Autumn Harvest/Bleed, Winter Frostbite/Freeze + Ice Armor.
- [ ] Travel uses the wild off-road journey; flee and death return to the
  nearest city.
- [ ] Each Echo is +20 levels (20/40/60/80 cap) and has more HP, a new
  seasonal-mechanic effect, more armor/elemental resistance and more status
  resistance than the last.
- [ ] Every round visibly advances the arena clock by one block; the boss is
  Dormant → Stirring → Rampage → reset at dawn.
- [ ] Fleeing saves HP; re-entry resumes at that HP; a new Echo resets to full.
- [ ] Time is committed once on exit; no mid-combat day-rollover side effects.
- [ ] The drop table in §8 is granted exactly once per kill; no loot on
  flee/death/interrupt. The cache starts at Rare and only rolls legendary at
  Echo 10+ (30%).
- [ ] The four uniques work for the player and allies; no duplicates.
- [ ] No superboss ledger/pool/shard changes; `max_floor`/`city_floors` are
  untouched.
- [ ] Old saves that already meet the Floor-20 gate spawn the current season's
  Warden at Echo 0 immediately.
- [ ] All tests and diags pass; the full suite remains green.
