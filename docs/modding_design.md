# Pandemonium — Modding System (v1 design)

Status: **proposal / for review** — no code yet.
Purpose: prove moddability by shipping **The Drowned Lantern** as the first content-pack mod.

Companion docs: `lantern_isle_design.md` (the reference mod) · `improvement_planning_guide.md`
(phase discipline) · `save-system-architecture.md` counterpart in `/memories/repo/`.

---

## 1. Goals

- Drop a folder into `mods/` and get new items, enemies, quests, cities, dialogues, maps,
  trade goods, wild themes, and content-pack toggles without rebuilding the exe.
- Optional Python hooks for custom logic (state checks, services, story beats, boss
  modules, city gates) through a small, stable API.
- Saves never crash when a mod is missing or updated.
- The Drowned Lantern ships as the reference mod, so the modding path is tested by real
  content rather than a toy example.

**Non-goals for v1:** sandboxing untrusted Python, hot-reloading mods mid-save, a Steam
Workshop-style browser/downloader, and modding core combat math without an explicit hook.

---

## 2. Why the architecture supports this

The content registries are module-level dicts:

| Registry | Module |
|---|---|
| `ITEMS` | `resources/items.py` |
| `ENEMIES`, `ENEMY_RACES`, `BIOME_RACES` | `resources/enemies/` |
| `QUESTS` | `resources/quests.py` |
| `CITIES` | `resources/cities.py` |
| `CITY_MAPS`, `CITY_SERVICE_POSITIONS` | `resources/city_maps.py` |
| `CITY_DIALOGUES` | `world/city_dialogue.py` |
| `CITY_POSITIONS`, `REGIONS` | `resources/world_layout.py` |
| `TRADE_GOODS`, `CITY_DEMAND` | `resources/trade_goods.py` |
| `WILD_DUNGEON_THEMES` | `resources/wild_dungeon_themes.py` |

A module that does `from pandemonium.resources.quests import QUESTS` holds the **same dict
object**, so merging into the dict before the GUI starts is visible everywhere. That is the
cheap, reliable first mechanism.

**Critical startup change.** `launcher.py` currently imports
`pandemonium.gui.app` at module scope, and the GUI imports screens (and therefore resource
modules) at import time. The loader must run first:

```python
def main():
    _setup_thread_excepthook()
    from pandemonium.mods import init_mods
    init_mods()
    from pandemonium.gui.app import run_gui
    run_gui()
```

Move the `gui.app` import inside `main()`; do the same for any other import that pulls in
resource modules before `init_mods()`.

PyInstaller one-folder builds (`Pandemonium.spec` / `make_exe.py`) can ship a `mods/`
folder next to `Pandemonium.exe`, outside `_internal`, so users can add or remove mods
without touching the bundle.

---

## 3. Mod package format

```
mods/
  README.md
  drowned_lantern/
    mod.yaml
    data/
      items.yaml
      enemies.yaml
      quests.yaml
      cities.yaml
      dialogues.yaml
      maps.yaml
    scripts/
      __init__.py
      content.py
    assets/
```

`mod.yaml`:

```yaml
id: drowned_lantern
name: The Drowned Lantern
version: 0.1.0
api: 1
game_min: 0.1.9.1
game_max: null
content_pack: true          # shows a per-save Game Rules row
default_new: false
default_old: false
trusted_scripts: true       # required to run scripts/
requires: []
load_after: []
entry: scripts.content:register
data:
  - data/items.yaml
  - data/enemies.yaml
  - data/quests.yaml
  - data/cities.yaml
  - data/dialogues.yaml
  - data/maps.yaml
```

Rules:

- `id` is lowercase `[a-z0-9_]+` and must be unique.
- `api` is the modding API version; incompatible majors refuse to load with a clear error.
- `content_pack: true` adds a per-save toggle to the Game Rules registry. The pack is
  final once the save starts its content (same consent model as Karma/Family).
- `trusted_scripts: true` is required for `entry`; data-only mods omit it.
- Content IDs are namespaced or prefixed: the DLC uses `drowned_lantern`-specific IDs
  (`sq_lantern_*`, `lantern_*`, `lantern_isle`) to avoid collisions. Third-party mods
  should use `modid_contentid` or a `mod` field on every entry.

### 3.1 Example mod (data-only) — `mods/hello_isle/`

A complete, copy-pasteable example. It adds one accessory, one enemy race, and one shop
line. No Python, no `trusted_scripts`, no load order.

```
mods/
  README.md
  hello_isle/
    mod.yaml
    data/
      items.yaml
      enemies.yaml
      dialogues.yaml
```

`mods/hello_isle/mod.yaml`

```yaml
id: hello_isle
name: Hello Isle (example)
version: 0.1.0
api: 1
game_min: 0.1.9.1
game_max: null
content_pack: false       # no Game Rules row; always on
default_new: null
default_old: null
requires: []
load_after: []
data:
  - data/items.yaml
  - data/enemies.yaml
  - data/dialogues.yaml
# no entry: + no trusted_scripts => data-only mod
```

`mods/hello_isle/data/items.yaml` — a `dict` merged into `ITEMS`

```yaml
hello_isle_lantern:
  name: Hello Lantern
  type: equipment
  slot: accessory          # weapon | armor | accessory
  unique: true
  base_mods:
    Wisdom: 4
  elemental_dmg:
    light: 1.1
```

`mods/hello_isle/data/enemies.yaml` — race-grouped, merged into `ENEMIES`

```yaml
Hello:                     # new race, auto-added to ENEMY_RACES
  hello_isle_crab:
    name: Hello Crab
    race: Hello
    level: 1
    base_hp: 12
    mods:
      Strength: 2
      Constitution: 2
      Dexterity: 1
      Wisdom: 1
      Learning: 1
      Charisma: 1
    boss: false
    super_boss: false
```

`mods/hello_isle/data/dialogues.yaml` — merged into `CITY_DIALOGUES`

```yaml
hello_isle_city:
  shop:
    enter:
      - "Everything here is a little bit damp. You get used to it."
    leave:
      - "Mind the step. It used to be a boat."
```

**Filename → registry** (v1 contract). The loader maps the file name to the registry, so a
data-only mod never needs a parser:

| File | Merges into |
|---|---|
| `items.yaml` | `ITEMS` |
| `enemies.yaml` | `ENEMIES`, `ENEMY_RACES`, `BIOME_RACES` |
| `quests.yaml` | `QUESTS` |
| `cities.yaml` | `CITIES`, `CITY_MAPS`, `CITY_SERVICE_POSITIONS`, `CITY_STORY_POSITIONS`, `CITY_DIALOGUES` |
| `layout.yaml` | `CITY_POSITIONS`, `REGIONS` |
| `trade.yaml` | `TRADE_GOODS`, `CITY_DEMAND` |
| `themes.yaml` | `WILD_DUNGEON_THEMES` |

A file may instead start with `registry: <name>` to target a registry explicitly.

**What the player sees:** the startup log prints

```
[mods] 1 loaded (hello_isle 0.1.0, data-only)
[mods] +1 item, +1 enemy, +1 dialogue city
```

Nothing appears in-game until content references it — that is the point of the fixture:
loading must be provable without changing the base game.

---

## 4. Loader lifecycle

1. `launcher.py` calls `init_mods()` before importing the GUI.
2. Discover `mods/*/mod.yaml` from the search paths (§7).
3. Parse and validate manifests: id, API version, game version, required mods, entry
   syntax.
4. Topologically sort by `requires` / `load_after`; detect cycles and refuse the cycle.
5. Import the base resource modules and merge data:
   - items → `ITEMS`
   - enemies → `ENEMIES` (+ `ENEMY_RACES` / `BIOME_RACES` for new races)
   - quests → `QUESTS`
   - cities → `CITIES`, `CITY_MAPS`, `CITY_SERVICE_POSITIONS`, `CITY_STORY_POSITIONS`,
     `CITY_DIALOGUES`
   - layout → `CITY_POSITIONS`, `REGIONS`
   - trade goods → `TRADE_GOODS`, `CITY_DEMAND`
   - wild themes → `WILD_DUNGEON_THEMES`
   - content packs → a `GAME_RULES` row
6. Run each mod's `entry` function (if trusted), passing the `pandemonium.mods.api`
   facade.
7. Freeze the registries, write a load summary to the startup log, and let the GUI start.

**Duplicate IDs:** reject by default with a clear error naming the mod and the ID. An
entry may set `override: true` to replace an existing ID explicitly; never override
silently. Load order is base game → mods in dependency order; later mods override earlier
mods only with `override: true`.

**Derived tables:** some systems build derived data at import (item-generation weights,
biome pools, quest chains, city layouts). Late additions may not appear in those tables.
v1 should either (a) restrict mod content to entries the existing tables already support,
or (b) expose explicit rebuild hooks (e.g. `rebuild_item_generation()`,
`rebuild_biome_pools()`). The Drowned Lantern needs the latter for its island biome and
materials; plan that hook before shipping the mod.

---

## 5. Mod API v1

### Data merges (no code)
- items (including simple unique items with static stats)
- enemies + races/biomes
- quests (existing objective types only)
- cities, city maps, service positions, story positions, dialogues
- trade goods, city demand, wild dungeon themes
- content-pack Game Rules rows

### Code hooks (trusted scripts)
- `register_state_check(obj_type, fn)` — new quest objective checks
- `register_quest_hook(quest_id, event, fn)` — start / complete / update callbacks
- `register_player_state(key, default_factory)` — mod-owned save state seeded by
  `ensure_player_fields()`
- `register_service(name, handler)` — new city facility handlers
- `register_story_beat(beat_id, fn)` — StoryScreen beats
- `register_item_effect(item_id, module_or_fn)` — unique equipment behavior
- `register_boss(key, factory)` — superboss module registration
- `register_city_hook(city_id, hook, fn)` — arrival guards, service gates, map variants,
  death routing
- `register_content_pack(...)` — explicit pack registration when the manifest is not enough
- `log(message)` — startup/session log

API versioning: additive changes keep `api: 1`; breaking changes bump the major and
refuse old mods with a readable message.

### The Drowned Lantern's API use
- state checks: `lantern_*`
- services: `lantern_ferry`, `beacon`
- city hooks: act gate, dream/truth map variant, `dock_daughter` / shrine story tags
- story beats: the loop reset, memories, the broken reset
- bosses: Dream-Warden, the Keeper
- content pack: `drowned_lantern`

---

## 6. Save compatibility and content packs

`player["mods"]` is added via `ensure_player_fields()`:

```python
player["mods"] = {
    "enabled": [],              # mod ids chosen for this save
    "versions": {},             # mod id -> version at enable time
    "missing": [],              # mods referenced by the save but not installed
    "quarantine": [],           # item instances whose mod is missing
}
```

- **Load:** compare the save's enabled mods to the installed set. Missing mods are
  reported once on load and added to `missing`.
- **Unknown items:** keep the instance but mark it `unavailable`; it cannot be equipped,
  used, sold, or discarded; the tooltip says "Requires mod X." This prevents item loss and
  crashes.
- **Unknown quests/cities:** hide them from the Journal/map; do not delete state.
- **Enabling a mod on an existing save:** only through the content-pack opt-in; final per
  save. No mid-arc disable.
- **Save backup:** write a `savegame_<slot>.backup_...` before enabling a content pack,
  reusing the save-system backup helper.
- **Removing a mod mid-save:** refuse while the pack is active; allow only if the pack was
  never enabled or its content is fully resolved.

---

## 7. Packaging and paths

Search order for the mods folder:

1. `PANDEMONIUM_MODS` environment variable (tests and development).
2. `Path(sys.executable).parent / "mods"` (packaged build).
3. `Path.cwd() / "mods"` (repo root / development).
4. A bundled read-only `mods/` under `sys._MEIPASS` (sample/docs only).

`make_exe.py` / `Pandemonium.spec`: copy `mods/` next to the exe, **not** inside
`_internal`. The loader must tolerate a missing folder, an empty folder, and a malformed
manifest without crashing the game.

**Security:** Python mods run arbitrary local code. Ship data-only mods by default;
require `trusted_scripts: true` for scripts; document "only install mods you trust." Do not
add remote downloads or auto-updates in v1.

**Frozen-build import:** load each script entry with
`importlib.util.spec_from_file_location` under a namespaced module name, and add the mod
folder to `sys.path` only while the entry runs. Test this in a real PyInstaller build; a
data-only mod is the safe fallback.

---

## 8. Testing the modding capability

- **Fixture mod:** `tests/fixtures/mods/hello_mod/` — one item, one enemy, one dialogue
  line, a data-only manifest.
- **`tests/_diag_mods.py`:** set `PANDEMONIUM_MODS`, load the fixture, assert registry
  merges, duplicate-ID rejection, API mismatch, missing dependency, malformed YAML, and
  idempotent reload.
- **`tests/_diag_mod_dlc.py`:** load `mods/drowned_lantern/`, assert the quests/city/
  state checks/services register, run the loop reset and chase smoke paths.
- **Frozen smoke test:** build with `make_exe.py`, drop a data-only mod next to the exe,
  verify the item appears in a new game.
- **Save safety:** load a save that references a missing mod; verify the warning,
  quarantine, and no crash.
- **No-mod smoke:** the base game must start and pass the existing suite with an empty
  `mods/` folder.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| GUI imports resources before mods load | Move the `gui.app` import inside `main()` after `init_mods()`; add an import-order test |
| `GAME_RULES` is an immutable tuple imported by `char_create_screen` | Register pack rows before that import, or convert the registry to a mutable list / dynamic getter |
| Derived tables miss late content | Restrict v1 content to existing tables; add explicit rebuild hooks for the DLC |
| Duplicate IDs / conflicts | Reject by default; `override: true` only |
| Missing mod in a save | Warn, quarantine unknown items, hide unknown quests/cities |
| Python mod security | Data-only default; `trusted_scripts` opt-in; no remote downloads |
| PyInstaller dynamic imports | Namespaced `importlib` loading; frozen-build smoke test |
| Startup performance | Load data lazily where possible; log load time; fail soft |
| Mod updates change IDs | Version the manifest; keep old IDs as aliases or quarantine |

---

## 10. The Drowned Lantern as the first mod

**Base game (generic, no DLC names):**
- `pandemonium/mods/` loader, registry, API facade, manifest validation, save/mod state.
- `launcher.py` init order.
- Generic city hooks: service gates, map variants, story tags.
- Generic state-check/service/story-beat/boss registration.
- Generic quest/player-state/death hooks (the loop reset needs a quest-complete callback).
- Game Rules content-pack row support.
- Tests and `mods/README.md`.

**Mod (`mods/drowned_lantern/`):**
- `mod.yaml` + `data/` (items, enemies, quests, city, dialogues, maps).
- `scripts/content.py` (entry) plus `loop.py`, `services.py`, `chase.py`, `bosses.py`, and
  `weapons.py` for the lantern-specific logic.
- Assets (if any).

**The chase:** implement it with the existing `StoryScreen`, `choice_dialog`, and combat
APIs. If it needs a dedicated screen, add a generic "scripted sequence" facility hook to
the base game first — do not put a DLC-specific screen in the base game.

This split keeps the base game free of Drowned Lantern identifiers and makes the mod the
proof of the modding API.

---

## 11. Locked policy (2026-11-20)

The open calls are resolved; these are decisions, not options:

1. **Data-only first, hybrid second.** Ship the loader + registry merge + the `hello_isle`
   example, prove a data-only mod loads in a frozen build, then add the Python hook API
   and move The Drowned Lantern in as the reference hybrid mod.
2. **Scripts are opt-in.** `trusted_scripts: true` is required for `entry`; anything else
   runs data-only. The loader warns on load and the mods list shows a "runs code" badge.
3. **Missing mods are quarantined.** A save referencing an absent mod loads with a clear
   warning; unknown items are quarantined and unknown quests/cities are hidden — never a
   refusal to load the save.
4. **Prefixed IDs + origin field.** New content uses `modid_contentid`; every entry also
   carries `mod: <id>` for provenance and for the quarantine scan. Base-game IDs are
   never renamed.
5. **UI scope for v1:** startup log summary plus a read-only mods list (id, name, version,
   API, content-pack flag, "runs code") in Settings. Enable/disable and load-order UI come
   later.
6. **Content packs are per-save.** Same consent model as Karma/Family: chosen at character
   creation or once at the ferryman for old saves; never toggled mid-arc.
7. **Loading order is deterministic:** base game → dependency order → manifest id
   (alphabetical) as the tie-break. Same folder, same order, every launch.

### Still open
- Whether mods may register **new GUI screens** (needs a generic screen hook first) or are
  limited to existing screens in v1.
- Whether `mods/` gets a checksum/hash list for the mods list display.
