# Architecture Reference

## Entry Points

| File | Role |
|---|---|
| `./launcher.py` | **Entry point** (PyInstaller target). Sets up threading exception hook, calls `gui.app.run_gui()`. |
| `./Pandemonium.spec` | PyInstaller build spec for GUI executable. |
| `./make_exe.py` | PyInstaller build script. |

## Core Files

| File | Role |
|---|---|
| `./pandemonium/core/character.py` | Creation, `ensure_player_fields()`, `player_max_hp()` |
| `./pandemonium/progression/leveling.py` | XP, level-up rewards |
| `./pandemonium/world/dungeon.py` | Dungeon crawl, floor gen, combat triggers, superboss milestones |
| `./pandemonium/inventory/inventory.py` / `./pandemonium/inventory/inventory_ui.py` | Inventory & equipment |
| `./pandemonium/progression/karma.py` | Single global standing score — tiers, daily cap, gate responses, atonement helpers; City Favor is gone |
| `./pandemonium/progression/karma_dialogue.py` | Karma-tier NPC/shop/guard/inn lines (Blackwake variants; non-Blackwake inns and Wonderland stay neutral) |
| `./pandemonium/core/save_load.py` | Save/load |
| `./pandemonium/world/city.py` / `./pandemonium/world/city_dialogue.py` | City hub, NPC dialogue |
| `./pandemonium/core/events.py` | Date-based event system, time tracking |
| `./pandemonium/core/utils.py` | `_tprint`/`_tpause`/`_tinput`, `advance_time()`, `apply_death_penalty()`, `clear_screen()`, `format_time()`, `get_time_period()`, `get_difficulty_multiplier_from_time()`, `strip_ansi()` (GUI-only runtime; `_t*` console fallbacks are for headless tests) |

## Combat Module

| File | Role |
|---|---|
| `./pandemonium/combat/combat_engine.py` | Combat loop, initiative, turn order |
| `./pandemonium/combat/combat_ui.py` | ASCII combat HUD (68-char width, 2-row entity layout) |
| `./pandemonium/combat/player_actions.py` | Player turn: attack, skills, items, flee, capture |
| `./pandemonium/combat/ally.py` | Ally creation, turn actions |
| `./pandemonium/combat/skills.py` | Class skills: definitions, cooldowns, mastery |
| `./pandemonium/combat/ally_skills.py` | Ally innate/learnable skill execution |
| `./pandemonium/combat/superboss/superboss_common.py` | Shared superboss combat loop |
| `./pandemonium/combat/capture.py` | Monster-girl capture |
| `./pandemonium/combat/city_guards.py` | Non-lethal city-gate guard squads, jail outcome, gate cooldowns |
| `./pandemonium/combat/stats.py` | Effective stats (base+eq+buffs), 1.7× Pandemonium multiplier |
| `./pandemonium/combat/status_effects.py` | Poison, burn, bleed, curse, dread, silence, fear, etc. |
| `./pandemonium/combat/stat_milestones.py` | Every 5 base-attr: STR→+dmg, CON→-dmg, DEX→dodge%, WIS→init/flee+heal%, CHA→capture%, LRN→skill% |
| `./pandemonium/combat/elemental.py` | 8-element damage/resist system |
| `./pandemonium/combat/enemy_ai.py` | Enemy attacks, mitigation (def buffs, divine shield, dodge, passives) |
| `./pandemonium/combat/combat_io.py` | Thread-safe I/O: `c_print`/`c_input`/`c_clear` |
| `./pandemonium/combat/action_menu.py` | Conditional action menus (ally menus differ from player) |
| `./pandemonium/combat/wedding_specials.py` | Bonded effects, soulbound, post-combat rewards |
| `./pandemonium/combat/elemental_debuffs.py` | Elemental debuff application: `try_apply_elemental_debuff()`, proc chance calc |
| `./pandemonium/combat/elemental_traits.py` | Weapon elemental traits: `get_primary_element()`, `apply_trait()`, on-kill procs |
| `./pandemonium/combat/helpers.py` | Formatting helpers: `format_damage_msg()`, `_player_has_tarnished_jade()` |
| `./pandemonium/combat/vileheart_venom.py` | Vileheart Venom pendant proc system |

## Superboss Files

| File | Boss |
|---|---|
| `./pandemonium/combat/abyss_fang.py` | Abyss Fang (multi-phase superboss), Abyssal Tempo stacks |
| `./pandemonium/combat/superboss/black_silence.py` | Black Silence |
| `./pandemonium/combat/black_silence_gloves.py` | Black Silence Gloves |
| `./pandemonium/combat/superboss/broodmother.py` | Broodmother |
| `./pandemonium/combat/captain_cutlass.py` | Captain Cutlass (high tide, rally, riposte) |
| `./pandemonium/combat/superboss/entangled_chrysalis.py` | Entangled Chrysalis (Pandemonium F20, 3 Temporal Aspects, Paradox Fracture) |
| `./pandemonium/combat/superboss/everlong_ship.py` | Everlong Ship |
| `./pandemonium/combat/superboss/ignis.py` | Ignis |
| `./pandemonium/combat/superboss/jabberwock.py` | Jabberwock (Wonderland F40) |
| `./pandemonium/combat/superboss/mary_sue.py` / `./pandemonium/combat/superboss/mary_sue_shadows.py` | Mary Sue (Wonderland F50, 5-phase, Plot Armor) |
| `./pandemonium/combat/superboss/queen_of_hearts.py` | Queen of Hearts (Wonderland F10) |
| `./pandemonium/combat/superboss/rientrante.py` | Rientrante |
| `./pandemonium/combat/superboss/slitcurrent.py` | Slitcurrent |
| `./pandemonium/combat/superboss/sylvana.py` | Sylvana |
| `./pandemonium/combat/tarnished_jade.py` | Tarnished Jade |
| `./pandemonium/combat/superboss/wicked_witch.py` | Wicked Witch (Wonderland F30) |
| `./pandemonium/combat/superboss/wl_floor_bosses.py` | Wonderland floor bosses |
| `./pandemonium/combat/superboss/yinglong.py` | Yinglong |
| `./pandemonium/combat/dummy.py` | Training dummy |

## Non-Combat

| File | Role |
|---|---|
| `./pandemonium/world/dungeon_rooms.py` | Non-combat rooms: fountain, merchant, trap, treasure, stat-check (10% chance) |
| `./pandemonium/world/curse_pandemonium.py` | Pandemonium curses: 10 types, 4 corruption tiers (1.0×–2.5×) |
| `./pandemonium/world/wonderland_curses.py` | Wonderland quirks + Shadow system (Floor 40+) |

## Facilities

| File | Role |
|---|---|
| `./pandemonium/facilities/house/` | Monster girl housing package: `menu.py`, `lounge.py`, `storage.py`, `rest.py`, `management.py`, `dispatch_board.py`, `family_menu.py`, `core.py`, `constants.py` |
| `./pandemonium/heroine_quests/` | Heroine quest rules/actions launched from any hub (e.g. `sylvana_mirror.py`); quest content lives in the heroine's YAML entry |
| `./pandemonium/facilities/shop.py` | Item shop |
| `./pandemonium/facilities/inn.py` | Rest/HP recovery |
| `./pandemonium/facilities/blacksmith.py` | Equipment crafting/upgrading |
| `./pandemonium/facilities/temple.py` | Blessings, curse removal |
| `./pandemonium/facilities/guild.py` | Level cap increases, biome clearing |
| `./pandemonium/facilities/barracks.py` | Ally skill training (`learning` dict) |
| `./pandemonium/facilities/gift_shop.py` | Gifts, wedding rings |
| `./pandemonium/facilities/travel.py` / `./pandemonium/facilities/travel_events.py` | World travel + events |
| `./pandemonium/facilities/arcane_tower.py` | Arcane tower facility |
| `./pandemonium/facilities/black_market.py` | Black market |
| `./pandemonium/facilities/herbalist.py` | Herbalist |
| `./pandemonium/facilities/port.py` | Port facility |
| `./pandemonium/facilities/shipyard.py` | Shipyard |
| `./pandemonium/facilities/skill_book.py` | Skill book management |
| `./pandemonium/facilities/trade_hall.py` | Trading |
| `./pandemonium/facilities/pathfinding.py` | Pathfinding utility |

## Resources

### Top-Level Data Files
| File | Role |
|---|---|
| `./pandemonium/resources/__init__.py` | Package init |
| `./pandemonium/resources/cities.py` | City definitions/data |
| `./pandemonium/resources/city_maps.py` | City map layouts |
| `./pandemonium/resources/constants.py` | Game constants |
| `./pandemonium/resources/items.py` | Item definitions |
| `./pandemonium/resources/mounts.py` | Mount definitions |
| `./pandemonium/resources/races_classes.py` | Race/class data (RACES, CLASSES, ATTRIBUTES) |
| `./pandemonium/resources/skill_loader.py` | Skill loading from YAML |

### Enemy Data (`./pandemonium/resources/enemies/`)
| File | Role |
|---|---|
| `./pandemonium/resources/enemies/enemy_loader.py` | YAML enemy loading (old `enemies.py` removed) |
| `./pandemonium/resources/enemies/biome_races.py` | Biome-to-enemy-race mappings |
| `./pandemonium/resources/enemies/enemy_races.py` | Enemy race definitions |
| `./pandemonium/resources/enemies/enemies_data/` | 24 YAML files: `all_enemies.yaml`, `monster_girls.yaml`, `superbosses.yaml`, `wonderland.yaml`, + per-race files |

### Dialogues (`./pandemonium/resources/dialogues/`)
21 city dialogue files: `ashkara.py`, `blackwake.py`, `brinewatch.py`, `cinderpeak.py`, `coralhaven.py`, `dunemar.py`, `elderfen.py`, `greyharbor.py`, `irondeep.py`, `isle_of_glass.py`, `mirefall.py`, `saltmarsh.py`, `skylume.py`, `solmere.py`, `stormhold.py`, `sunreach.py`, `thornwall.py`, `tidebreak.py`, `veilholt.py`, `wonderland.py`

### Skill Book (`./pandemonium/resources/skill_book/`)
| File | Role |
|---|---|
| `./pandemonium/resources/skill_book/innate_skills.yaml` | Innate ally/monster-girl skill definitions |
| `./pandemonium/resources/skill_book/skill_list.yaml` | Master skill list with race passives |

## GUI Module

### Core GUI
| File | Role |
|---|---|
| `./pandemonium/gui/__init__.py` | Package init |
| `./pandemonium/gui/app.py` | tkinter main window, `PandemoniumApp`, `run_gui()` entry |
| `./pandemonium/gui/theme.py` | Dark theme: bg `#1a1a2e`, accent `#e94560`, monospace |
| `./pandemonium/gui/screen_manager.py` | Screen router, back-stack, game clock (1min/2s), top/bottom bars |
| `./pandemonium/gui/terminal.py` | Thread-safe facility I/O bridge |
| `./pandemonium/gui/io_redirector.py` | stdout/stderr redirect for tkinter |
| `./pandemonium/gui/notification_queue.py` | Notification queuing system |
| `./pandemonium/gui/settings.py` | GUI settings management |

### GUI Screens (`./pandemonium/gui/screens/`)
| File | Role |
|---|---|
| `base_screen.py` | Base screen class for all screens |
| `changelog_screen.py` | Changelog display |
| `char_create_screen.py` | Character creation screen |
| `city_screen.py` | City hub screen |
| `combat_screen.py` | Combat UI screen |
| `death_screen.py` | Death/game-over screen |
| `dungeon_screen.py` | Dungeon crawl screen |
| `facility_screen.py` | Facility interaction screen |
| `inventory_screen.py` | Inventory/equipment screen |
| `main_menu_screen.py` | Main menu screen |
| `post_floor_screen.py` | Post-floor rewards/choices |
| `settings_screen.py` | Settings screen |
| `splash_screen.py` | Splash/loading screen |
| `world_map_screen.py` | Unified world map / travel hub |

### GUI Widgets (`./pandemonium/gui/widgets/`)
| File | Role |
|---|---|
| `city_map.py` | City map widget |
| `confirm_dialog.py` | Confirmation dialog |
| `hp_bar.py` | HP bar display |
| `item_card.py` | Item card display |
| `log_window.py` | Log/message window |
| `notification_toast.py` | Toast notifications |
| `stat_display.py` | Stats display panel |

### GUI Combat (`./pandemonium/gui/combat/`)
| File | Role |
|---|---|
| `combat_renderer.py` | ASCII combat HUD in tkinter text widget |
| `action_panel.py` | Action button panel for combat |

### Savefile (`./savefile/`)
| File | Role |
|---|---|
| `gui_settings.json` | GUI settings persistence |
| `savegame_1.json` through `savegame_4.json` | Player save slots |

## Tests

Naming convention (authoritative): `./tests/README.md`. pytest collects only
`test_*.py`; config lives in `./pyproject.toml` (`testpaths = ["tests"]`,
`pythonpath = ["."]`).

| File | Role |
|---|---|
| `./tests/test_*.py` | pytest suite — health checks, phase 2/3/4/19, bestiary, event horizon, wild dungeons, house routing, party reinforcement, gloves rework |
| `./tests/_smoke_phase0.py` / `./tests/_smoke_phase1.py` | Manual import/instantiation smoke scripts (not collected; were `test_phase0/1.py`) |
| `./tests/_diag_*.py` | Manual diagnostic scripts, one system each (`_diag_casino`, `_diag_karma`, `_diag_family`, …) |
| `./tests/_temp_*.py` / `./tests/_repro_*.py` | Throwaway one-change checks / bug reproductions — safe to delete |
| `./tests/_fix_*.py` | One-off savefile surgery scripts |
| `./tests/_tk_test_utils.py` | `shared_tk_root()` — one withdrawn Tk root for all GUI tests; never `root.destroy()` |
| `./tests/enemy_audit.py`, `./tests/gen_wiki_html.py` | Project tools, not tests |

## Dev Utilities

| File | Role |
|---|---|
| `./clean_pycache.ps1` | Clear Python bytecode cache |
| `./verify_phase2.py` | Phase 2 verification/QA script |
| `./result.txt` | Output/log artifact |
