# Boss Styles, Final Rooms and Enemy Suffixes

Status: implemented 2026-11-26
Code: `pandemonium/combat/boss_styles.py`, `pandemonium/world/enemy_suffixes.py`
Spawn wiring: `pandemonium/world/dungeon.py` (`generate_floor`)
Combat wiring: `pandemonium/combat/combat_engine.py`, `pandemonium/gui/screens/combat_screen.py`
Tests: `tests/test_final_room_and_suffixes.py`, `tests/test_boss_pool.py`

## 1. Final room rules

Every floor is 9 mixed rooms + a guaranteed combat room.

| Floor | 10th room | Reward flag |
|---|---|---|
| `floor % 5 == 0` | **True boss** (`boss: true`) — solo or escort | `is_boss: true` |
| every other floor | **ordinary combat room** (same encounter-size curve as rooms 1–9) | none |
| Wonderland boss floor | fixed Wonderland floor boss + escort curve (unchanged) | `is_boss: true` |

The old `Empowered` prefix (+30% HP / +20% STR/CON/DEX on the first enemy of
the last room) is retired. Normal rooms, including the 10th, can roll a
suffix instead.

The boss level band is `floor .. floor+3` (it used to be `floor+1 .. floor+3`),
so floor 60 can spawn a level-60 boss instead of falling through to the
any-level emergency fallback.

## 2. Boss styles

`boss_styles.py` owns the curated `SOLO_BOSS_KEYS` set (34 bosses across every
band). A template may override it with `boss_style: solo` or
`boss_style: escort` in the enemy YAML.

| Style | Board | Budget |
|---|---|---|
| **solo** | boss alone | HP ×2.20, STR/CON/DEX/WIS/LER/CHA ×1.15, `status_res` +0.30, **2 actions/round** once the party fields 3+ actors |
| **escort** | boss + 1–3 normal enemies | template stats |

The solo budget is applied in `enemy_stats()` at spawn, so the HUD, bestiary
preview and combat all see the same numbers. `combat_engine._combat_inner`
runs the second action with `skip_turn_start=True`, so DoTs, stuns and kit
cooldowns tick once per round, not once per action.

Escort rooms use the boss-room encounter curve: `num_escorts =
min(3, max(1, boss_total - 1))` — an escort boss always has at least one ally.

## 3. Suffixes

A suffix is a spawn-time rank modifier on a **normal** enemy. One suffix per
combat room, one enemy per room, never on bosses/superbosses/minions/monster
girls/city guards/heroines/shadows/scripted enemies.

| Suffix | Unlock | Weight | Budget at full power (scales with floor) |
|---|---|---|---|
| Veteran | F10 | 10 | HP +30%, STR/CON/DEX +10% |
| Frenzied | F10 | 7 | STR +30%, DEX +10%, CON −15% |
| Armored | F10 | 7 | HP +10%, CON +35%, DEX −10% |
| Swift | F10 | 6 | HP +10%, DEX +30% |
| Warded | F10 | 5 | HP +10%, WIS +20%, `status_res` +0.20 |
| Arcane | F10 | 4 | LER +25%, attack element becomes magical |
| Ancient | F10 | 3 | HP +60%, STR −10%, CON +15% |

Every suffix unlocks on floor 10. The weights keep the plain stat suffixes
common and the exotic ones rare.

**Chance (per combat room)** interpolates:

| Floor | 1–9 | 10 | 19 | 34 | 49 | 60+ |
|---|---|---|---|---|---|---|
| Base | 0% | 5% | 9% | 13% | 17% | 20% |

+1.5% per enemy above the first, capped at 35%. **Power** starts at **0.60×**
the table on floor 10 and rises to **2.00×** on floor 60 — the early elite is
deliberately soft, the late one is a real spike. A Veteran's HP bonus is +18%
at F10, +30% at F35 and +60% at F60.

The roll happens in `generate_floor` and is stored on the room as
`{"suffixes": {index: suffix_id}}`; `combat()` and `CombatScreen` apply it to
the enemy instances before the opening HUD. The room's key list is unchanged,
so rewards/bounties/floor previews keep working.

**Name guard.** A suffix is skipped when its label already appears in the
enemy's name (`Ancient Golem`, `Ancient Construct Sentinel`, `Veteran
Swordsman`, `Arcane Clockwork`, ...) or when the prefixed name would exceed
the 33-character enemy HUD column. The roll is name-aware: it picks a slot
that can carry at least one suffix, then picks a suffix that fits. If no slot
fits, the room goes without a suffix. `apply_suffix()` enforces the same
rule, so a direct call cannot produce `Ancient Ancient Golem`.

## 4. Rewards

- Suffixes do not change XP/gold/drops (combat twist only).
- Solo bosses trade their minions for the budget; boss gold remains 2.5×.
- The 10th room on non-boss floors is a normal room, so no boss reward.

## 5. Verification

```
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe tests/_diag_boss_pool.py --region celestial
.venv\Scripts\python.exe scripts/check_module_imports.py
```

`_diag_boss_pool.py` reports `SPREAD` (boss HP max/min ≥2× at a floor),
`FLAT` (boss median <1.5× normal median) and `AI-DISABLED` leaks. Suffix
chance is covered by `tests/test_final_room_and_suffixes.py`.
