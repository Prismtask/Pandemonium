# Pandemonium Code Health Check — 2026-11-11

**Version:** v0.1.9.0 "The Family We Choose" (beta)
**Scope:** 231 Python source files, 97,665 LOC (`pandemonium/`, `launcher.py`, `make_exe.py`)
**Method:** byte-compile, pytest, import smoke test, Pylance workspace diagnostics, Ruff (`F401`/`F811`/`F821`), AST scans (unused imports, unreferenced definitions, duplicate bodies, mutable defaults, bare excepts, function length), manual verification of findings.

> This report supersedes the 2026-07-28 audit.

---

## 📊 Dashboard

| Check | Result |
|---|---|
| Syntax / byte-compile (`compileall`) | ✅ OK — 0 errors |
| Test suite (`pytest -q`) | ✅ **279 passed**, 105 subtests, 6.7 s |
| Import smoke (every module imported) | ✅ **210 / 210 modules** |
| Pylance (workspace diagnostics) | ✅ 0 errors · 0 game warnings |
| Ruff `F401` / `F811` / `F821` | ✅ All checks passed (excluding intentional `__init__.py` re-exports) |
| Mutable default arguments | ✅ 0 |
| TODO / FIXME / HACK markers | ✅ 0 |
| Bare `except:` | ⚠️ 1 |
| Unused imports | ✅ **0** in game modules (141 removed) |
| Unreferenced top-level functions | 🟡 **6** — documented planned APIs only (58 at baseline) |
| Identical duplicate function bodies | ✅ **0** (6 groups consolidated) |
| Functions ≥ 150 lines | ⚠️ **60** (down from 62; see plan) |

The codebase is in **good structural health**: the test suite is green, every module imports cleanly, there are no syntax errors, no mutable-default traps, and Pylance/Ruff report no undefined names or unused imports. Remaining debt is concentrated in a small number of **very long combat/GUI functions** and a few open consistency items.

---

## ✅ FIXED — Confirmed Runtime Bug (2026-11-11)

| # | File | Line | Issue |
|---|---|:---:|---|
| 1 | `pandemonium/facilities/barracks.py` | 378 | **`NameError: name 'DEFAULT_DUMMY_CONFIG' is not defined`** when the player selects **"Reset to Defaults"** in the training-dummy configuration menu. |

**Cause:** `DEFAULT_DUMMY_CONFIG` was imported *inside* `_dummy_spar_flow()`, so the sibling function `_dummy_config_menu()` could not see it.

**Reproduced:** mocked `term.menu` to return choice `5` → `NameError` at `barracks.py:378`.

**Applied fix:**
- Added `copy_default_dummy_config()` to `combat/dummy.py` — a copy with an independent `elemental_res` dict.
- `_dummy_config_menu()` now imports and uses that helper on reset (no more undefined name).
- `_dummy_spar_flow()` also starts from the helper, fixing a latent aliasing bug where resistance edits polluted the module-level defaults.

**Regression coverage:** `tests/test_barracks_dummy.py` — 3 tests (reset restores defaults, reset does not pollute defaults, copies are independent). Full suite: **279 passed**.

---

## 🧹 Cleanup Applied (2026-11-11)

| Area | Before | After | Action |
|---|---:|---:|---|
| Unused imports (game modules) | 141 | **0** | Ruff `F401 --fix` across non-`__init__.py` files; re-export modules untouched |
| Unreferenced top-level functions | 58 | **6** | Removed 56 superseded helpers; kept the 6 documented planned APIs |
| Identical duplicate function bodies | 6 groups | **0** | Consolidated into shared helpers (see below) |
| Functions ≥ 150 lines | 62 | **60** | Split `ensure_player_fields` and `_get_entity_buff_tags` |
| Net source change | — | **−658 LOC** | 243 insertions · 901 deletions in tracked source/tests (excludes new utility modules and the regression test file) |

**Duplicate helpers consolidated:**
- `superboss_common.get_boss(elist, key)` — replaced 4 local `_get_boss()` copies.
- `combat/ally.get_living_party(player)` — replaced 4 `_get_alive_party()` and 4 `_get_living_targets()` copies (8 call sites in 8 modules).
- `gui/widgets/dialog_utils.py` — shared `safe_toplevel()`, `has_gui()`, `is_main_thread()` for event/level-up dialogs.
- `facilities/intro_utils.py` — shared `print_header()` for archivist/tutorial intros.

**Behavioral fix included:** `wicked_witch._get_living_targets()` previously iterated every ally, including the bench; it now uses `get_living_party()` (active front-row allies only), matching every other boss.

**Verification:** `compileall` OK · `pytest` 279 passed · import smoke 210/210 · Ruff `F401/F811/F821` all passed · duplicate-body scan 0.

---

## 🟠 HIGH — Correctness / Consistency Risks

### 2. `_actor_max_hp()` is implemented 4× with different rules

| Location | Ally detection | Fallback |
|---|---|---|
| `combat/weapon/chronoweave.py:32` | `actor.get("race")` | `max_hp` → `current_hp` → 1 |
| `combat/weapon/decaying_aegis.py:33` | `actor.get("is_ally")` | `max_hp` → `current_hp` → 1, clamped |
| `combat/weapon/prescript_ledger.py:71` | `actor.get("is_ally")` | `max_hp` default **1** |
| `world/event_horizon.py:1076` | `actor.get("is_ally")` | `max_hp` default **100** |

The actor-based convention says both `is_ally` and `race` identify allies. `chronoweave` uses only `race`; the other three use only `is_ally`, and the default HP differs by two orders of magnitude. This is a latent wrong-HP-clamp bug.

**Recommendation:** add one shared `actor_max_hp(actor)` to `combat/helpers.py` (or `combat/stats.py`) and import it everywhere. Same treatment for the duplicated `_owner_name()` helpers in `authors_pen.py`, `chronoweave.py`, `decaying_aegis.py`.

### 3. ✅ `_get_alive_party()` duplicates — resolved

All four copies (`combat_engine`, `big_bad_wolf`, `broodmother`, `entangled_chrysalis`) and the four `_get_living_targets()` copies (`mary_sue`, `mary_sue_shadows`, `jabberwock`, `wicked_witch`) now call one helper:

```python
# combat/ally.py
def get_living_party(player):
    """Return [player] + active allies, excluding anyone at 0 HP."""
    party = [player] if player.get("current_hp", 0) > 0 else []
    party.extend(get_active_allies(player))
    return party
```

`get_active_allies()` already filters dead/defeated/stress-sit-out allies; the helper now also filters a dead player consistently. `wicked_witch` previously looped over every ally (including the bench) — fixed to active allies only.

### 4. `_player_has_*` equipment predicates still duplicated

| Function | Copies | Note |
|---|---|---|
| `_player_has_tarnished_jade` | `combat/helpers.py:65`, `combat/weapon/tarnished_jade.py:15` | `helpers.py` returns `None` when absent, the weapon copy returns `False` |
| `_player_has_black_silence_gloves` | `combat/action_menu.py:10`, `combat/weapon/black_silence_gloves.py:77` | identical logic |

All `_actor_has_*` implementations follow the same shape. A generic `actor_has_equipped(actor, slot, item_id)` in `combat/helpers.py` would collapse these.

---

## 🟡 MEDIUM — Cleanup & Maintainability

### 5. ✅ Unused imports — resolved (141 → 0)

Ruff `F401 --fix` removed 150 findings across non-`__init__.py` files (141
AST-verified plus 9 additional). The largest cleanup was `world/dungeon.py`
(26 stale Wonderland-curse imports). `__init__.py` re-export modules were
deliberately excluded. Ruff `F401` now reports nothing outside those
re-exports.

### 6. ✅ Unreferenced functions — resolved (58 → 6 intentional)

Removed 56 superseded/obsolete helpers, including `prepare_dummy_for_gui`,
`swap_party_member`, `trigger_heroine_permanent_unlock`, the unused
status-effect query helpers, superboss leftovers, and
`remove_item_from_inventory`. Six functions remain intentionally because
design docs name them as future wiring points:

| Function | Doc |
|---|---|
| `quests.has_quest`, `quests.notify_objective`, `quests.offer_side_quest`, `quests.decline_quest` | `docs/quest_system_design.md` |
| `combat/ally.dismiss_allies_back_to_house` | `docs/dispatch_system_design.md` |
| `facilities/travel.embark_multi_leg_journey` | `docs/quest_system_design.md`, `docs/wild_dungeon_design.md` |

> These are feature gaps, not stale code. Wire them when the side-quest /
> dispatch / multi-leg travel flows ship, or delete them then.

### 7. ✅ Identical duplicate bodies — resolved (6 → 0)

| Function | Resolution |
|---|---|
| `_get_boss` | `superboss_common.get_boss(elist, key)` |
| `_get_living_targets` | `combat/ally.get_living_party(player)` |
| `_safe_toplevel` / `_has_gui` / `_is_main_thread` | `gui/widgets/dialog_utils.py` |
| `_header` | `facilities/intro_utils.py` |

The duplicate-body scan now reports **0** groups. Same-name/different-body
helpers remain intentional (e.g. `advance_time` compatibility shim,
`_sell_price` city vs road merchant, `stress_band` scales).

### 8. Long functions — 60 remain

Two safe refactors landed: `ensure_player_fields` (302 → 6 helpers of 25–86
lines) and `_get_entity_buff_tags` (233 → 5 pure collectors + orchestrator,
verified byte-identical output across a branch-coverage fixture). 60
functions remain ≥ 150 lines; they are concentrated in deeply stateful
combat/GUI code:

| Lines | Function | Type |
|--:|---|---|
| 2,106 | `gui/screens/changelog_screen.py:92` `_insert_changelog()` | data table — leave as-is |
| 2,022 | `combat/skills.py:455` `_execute_skill_core()` | **logic hotspot** |
| 1,287 | `combat/ally_skills.py:596` `execute_ally_skill()` | **logic hotspot** |
| 1,018 | `combat/player_actions.py:23` `handle_player_turn()` | **logic hotspot** |
| 883 | `world/dungeon.py:1752` `explore_dungeon()` | room loop |
| 824 | `combat/ally.py:1204` `handle_ally_turn()` | turn loop |
| 746 | `combat/superboss/mary_sue.py:537` `combat_mary_sue()` | boss AI |
| 701 | `facilities/house/lounge.py:147` `_house_lounge()` | menu loop |
| 562 | `combat/combat_engine.py:384` `_combat_inner()` | round loop |
| 539 | `facilities/inn.py:391` `_heroine_interaction()` | menu loop |
| 531 | `combat/superboss/superboss_common.py:87` `superboss_combat_loop()` | boss loop |

**Plan:** split one hotspot only when its area is next modified, starting
with `_execute_skill_core` (extract per-skill handlers behind a dispatch
table) and `execute_ally_skill`, with combat regression tests before and
after. Do not refactor boss AI or long GUI layout functions in a general
cleanup pass — they are high-risk and low immediate value.

### 9. Minor findings

| # | Finding | Location |
|---|---|---|
| 9a | Bare `except:` should be `except ValueError:` (only catches `int()` conversion) | `combat/player_actions.py:1008` |
| 9b | UTF-8 BOM at start of file (imports fine, but `utf-8` parsers fail) | `pandemonium/resources/family_scenes.py` |
| 9c | Import-time `print("Total enemies loaded: …")` noise | `resources/enemies/enemy_loader.py` (5 prints) |
| 9d | ✅ Resolved — unused `_tclear()` removed | `core/utils.py` |
| 9e | Ruff/Pylance hints remain for unused callback args (`e`, `a`, `k`, `kwargs`, `player`, `dmg`) — expected in game code, not worth a mass edit | — |

---

## ✅ Follow-up on the 2026-07-28 report

Fixed since the last audit:

- `HEROINE_SHADOW_FLOOR50_DIALOGUE` is now defined (`world/wonderland_curses.py:658`).
- `_tprint` / `_tpause` / `_tinput` / `_tmenu` centralized in `core/utils.py`; the unused `_tclear` was removed during this cleanup.
- `_update_top_bar` duplication resolved via the screen-manager top bar.
- `prune_dead`, `roll_initiative`, `_int_to_roman`, `get_effective_charisma`, `_get_wonderland_max_floor`, `_danger_tag`, `ELEMENT_TAGS`, `styled_button` no longer duplicated.
- Empty `gui/screens/facilities/` directory and stub `main.py` removed.
- `ItemCard` / `StatDisplay` widgets are now referenced (not dead).

Still open from the previous report:

- `_player_has_tarnished_jade` (2) and `_player_has_black_silence_gloves` (2) still duplicate; `_sell_price` remains intentionally different per merchant type.
- `_actor_max_hp()` still has four implementations with inconsistent ally detection (see HIGH #2).
- 60 functions remain ≥150 lines (see MEDIUM #8).

---

## 🏆 Recommended order of work

1. ✅ **DONE — `barracks.py` `DEFAULT_DUMMY_CONFIG`** — fixed, plus independent default-state copies; regression tests added (`tests/test_barracks_dummy.py`).
2. ✅ **DONE — unused import sweep** — Ruff `F401` across non-`__init__.py` files.
3. **Consolidate `actor_max_hp()`** — removes a real inconsistency and four copies.
4. **Consolidate `_player_has_*` predicates** into `combat/helpers.py`.
5. ✅ **DONE — dead functions** — 56 removed; 6 documented planned APIs kept.
6. ✅ **DONE — GUI dialog helpers** — `gui/widgets/dialog_utils.py`.
7. **Split `skills._execute_skill_core()` / `ally_skills.execute_ally_skill()`** only when they are next modified — they are high-risk to refactor wholesale.
8. **Fix the bare except, strip the BOM, guard the import-time print** — quick polish.

---

## Appendix A — Unused imports at baseline (141; now resolved)

```
26  pandemonium\world\dungeon.py: ITEM_RARITY, player_biome, _tclear, clear_screen, format_time, ROOM_LABELS, STAT_CHECK_EVENTS, WL_ROOM_LABELS, WL_STAT_CHECK_EVENTS, is_flee_blocked, format_mary_sue_shadow_intro, get_caterpillars_insight_reduction, get_cheshire_dodge_chance, get_jabberwock_bane_multiplier, get_looking_glass_reroll_chance, get_mary_sue_shadow_modifiers, get_painting_roses_reduction, get_player_shadows, get_shadow_accuracy_penalty, get_shadow_bleed_poison_extension, get_shadow_damage_taken_multiplier, get_shadow_initiative_bonus, get_shadow_skip_chance, get_shadow_stat_check_dc_increase, get_white_rabbit_cooldown_reduction, get_wl_quirk
7   pandemonium\combat\superboss\mary_sue.py: format_enemy_status_line, print_superboss_header, apply_bleed, compute_ally_stats, ALL_ELEMENT_TYPES, try_strip_plot_armor, get_heroine_in_party
7   pandemonium\combat\superboss\everlong_ship.py: compute_player_stats, handle_player_turn, format_enemy_status_line, print_superboss_header, get_alive_allies, player_max_hp, c_clear
7   pandemonium\world\dungeon_rooms.py: _tclear, _tinput, advance_time, clear_screen, ITEMS, ITEM_RARITY, add_item_to_inventory
6   pandemonium\combat\superboss\yinglong.py: compute_player_stats, handle_player_turn, format_enemy_status_line, print_superboss_header, format_player_status_line, c_clear
5   pandemonium\combat\superboss\jabberwock.py: compute_player_stats, handle_player_turn, format_enemy_status_line, print_superboss_header, compute_ally_stats
5   pandemonium\combat\superboss\wl_floor_bosses.py: c_clear, c_input, apply_poison, ELEMENTS, calculate_elemental_damage
5   pandemonium\combat\superboss\queen_of_hearts.py: random, compute_player_stats, handle_player_turn, format_enemy_status_line, print_superboss_header
5   pandemonium\combat\superboss\wicked_witch.py: compute_player_stats, handle_player_turn, format_enemy_status_line, print_superboss_header, get_heroine_in_party
5   pandemonium\combat\player_actions.py: c_clear, format_player_status_line, format_enemy_status_line, is_monster_girl, get_passive_skill
4   pandemonium\combat\superboss\big_bad_wolf.py: compute_player_stats, handle_player_turn, format_enemy_status_line, print_superboss_header
4   pandemonium\combat\superboss\entangled_chrysalis.py: compute_player_stats, apply_burn, apply_weaken, get_alive_allies
4   pandemonium\inventory\core.py: random, ITEMS, ITEM_RARITY, build_item
3   pandemonium\combat\weapon\tarnished_jade.py: c_clear, c_input, random
3   pandemonium\inventory\legacy_ui.py: _tclear, _tmenu, _tpause
3   pandemonium\combat\ally.py: c_clear, ENEMY_RACES, player_max_hp
3   pandemonium\combat\weapon\wedding_specials.py: c_clear, c_input, prune_dead
3   pandemonium\gui\screens\world_map_screen.py: ITEM_RARITY, get_effective_attribute, textwrap
3   pandemonium\combat\weapon\black_silence_gloves.py: c_print, ELEMENT_TAGS, is_monster_girl
3   pandemonium\combat\combat_engine.py: print_combat_hud, can_switch, swap_party_member
3   pandemonium\combat\combat_ui.py: clear_screen, c_clear, c_input
3   pandemonium\combat\superboss\superboss_common.py: clear_abyss_fang_state, format_enemy_status_line, print_superboss_header
3   pandemonium\combat\superboss\black_silence.py: handle_player_turn, format_enemy_status_line, print_superboss_header
2   pandemonium\facilities\skill_book.py: PASSIVE_SKILLS, get_class_capstone_id
2   pandemonium\resources\enemies\enemy_loader.py: ENEMY_RACES, BIOME_RACES
2   pandemonium\gui\screens\city_screen.py: service_dialogue, get_city_map
1   pandemonium\gui\screens\inventory_screen.py: get_skill_mastery_level
1   pandemonium\combat\superboss\rientrante.py: c_clear
1   pandemonium\progression\leveling.py: _tpause
1   pandemonium\world\city.py: house_menu
1   pandemonium\combat\ally_skills.py: absorb_damage
1   pandemonium\gui\screens\dungeon_screen.py: threading
1   pandemonium\facilities\black_market.py: ITEM_RARITY
1   pandemonium\facilities\gift_shop.py: random
1   pandemonium\combat\weapon\authors_pen.py: c_input
1   pandemonium\facilities\arcane_tower.py: remove_item_by_reference
1   pandemonium\facilities\inn.py: swap_alice_to_vorpal_skills
1   pandemonium\combat\weapon\blank_canvas_shawl.py: c_print
1   pandemonium\gui\screens\combat_screen.py: get_io
1   pandemonium\facilities\shop.py: ITEM_RARITY
1   pandemonium\facilities\travel_events.py: advance_time
```

## Appendix B — Largest modules

| Lines | Module |
|--:|---|
| 2,975 | `gui/screens/world_map_screen.py` |
| 2,656 | `world/dungeon.py` |
| 2,530 | `combat/ally.py` |
| 2,483 | `combat/skills.py` |
| 2,241 | `gui/screens/inventory_screen.py` |
| 2,223 | `gui/screens/changelog_screen.py` |
| 2,188 | `world/event_horizon.py` |
| 2,085 | `gui/screens/combat_screen.py` |
| 2,076 | `combat/ally_skills.py` |
| 1,826 | `combat/status_effects.py` |

---

*Updated 2026-11-11 after cleanup. Analysis is static (AST + Ruff + Pylance); the only runtime repro was the barracks reset path and the buff-tag equivalence fixture.*
