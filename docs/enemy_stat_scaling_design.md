# Enemy Stat Scaling — Early / Mid / Late

Status: implemented 2026-11-24
Code: `pandemonium/combat/enemy_scaling.py`
Audit: `.venv\Scripts\python.exe tests/_diag_enemy_stat_scaling.py`
Tests: `tests/test_enemy_scaling.py`

## 1. The six stats

Every enemy template carries six attributes. Race mods and personal `mods`
are added together, then `combat.stats.enemy_stats` applies the time-of-day
multiplier (Morning 1.0 / Noon 1.1 / Night 1.25, capped 2.2; Pandemonium and
Event Horizon freeze at 1.25 × 1.7).

| Stat | Template key | Drives | Exported as |
|---|---|---|---|
| **STR** | `Strength` | basic-attack and skill damage | `str_mod` |
| **DEX** | `Dexterity` | accuracy / dodging incoming attacks | `dex_mod` |
| **CON** | `Constitution` | armor (flat damage reduction) | `con_mod` |
| **WIS** | `Wisdom` | **healing** (support kits) and **anti-dodge** | `wis_mod` |
| **LER** | `Learning` | **how often the enemy uses its skill / AoE** | `ler_mod` |
| **CHA** | `Charisma` | **how often its rider debuff / racial proc lands** | `cha_mod` |

Before this change WIS / LER / CHA were authored in the YAML but dropped by
`enemy_stats`, so they were pure flavor. They are now exported and wired:

```
heal amount      = max_hp × heal_pct × (1 + 0.04 × WIS)        cap ×2.00
skill / AoE odds = base chance × level tier × (1 + 0.03 × LER) cap ×1.35
rider debuff     = base chance × (1 + 0.04 × CHA)              cap ×1.60, final 0.90
player dodge     = (defender DEX − attacker DEX) × 0.03
                 + (defender WIS − attacker WIS) × 0.02
```

Consequences worth knowing:

* A late enemy with WIS 6–9 shaves 12–18% off a DEX-only dodge build. The
  80% dodge cap is still reachable, but no longer free.
* A healer with WIS 12 heals ~48% more than its `heal_pct` suggests.
* A skill-heavy enemy with LER 9 uses its kit ~27% more often, capped +35%.
* A debuffer with CHA 9 lands its rider ~36% more often, capped +60% and a
  hard 90% ceiling so no enemy can lock the party out.

Event Horizon room scaling and Boss Rush scaling apply WIS to the `def`
axis and LER/CHA to the `dmg` axis **for regular enemies only**. Superboss
modules read these fields as bespoke constants (Chrysalis adds LER to every
dark hit), so scaling them would double-dip on top of `str_mod`; bosses keep
their authored values.

## 2. The curve

```
value(level) = base + growth × level
```

| Stat | Base | Growth | L1 | L20 | L40 | L60 |
|---|---|---|---|---|---|---|
| STR | 2.0 | 0.17 | 2 | 5 | 9 | 12 |
| DEX | 3.0 | 0.07 | 3 | 4 | 6 | 7 |
| CON | 2.0 | 0.12 | 2 | 4 | 7 | 9 |
| WIS | 1.0 | 0.12 | 1 | 3 | 6 | 8 |
| LER | 1.0 | 0.08 | 1 | 3 | 4 | 6 |
| CHA | 1.0 | 0.09 | 1 | 3 | 5 | 6 |

The curve is a **guideline**, not a runtime override — templates stay
hand-authored. The audit script reports where the roster sits against it.

## 3. Early / mid / late targets

Floor → enemy-level windows come from `world/dungeon.get_random_enemy_key`
(`floor - 6 - floor//10` to `floor + 3`), so a run sees roughly:

| Phase | Floors | Enemy levels | AI tier | Room shape |
|---|---|---|---|---|
| Early | 1–9 | 1–12 | Instinctive → Trained | 1–2 enemies, basic attacks |
| Mid | 10–29 | 13–32 | Coordinated → Tactical | 3–4 enemies, skills + AoE + healers |
| Late | 30–60 | 33–60 | Calculating | 4–5 enemies, full kits, frequent debuffs |

Targets at each phase's sample level:

| Phase (sample) | Role | STR | DEX | CON | WIS | LER | CHA |
|---|---|---|---|---|---|---|---|
| **Early (L6)** | attacker | 3 | 3 | 3 | 1 | 1 | 2 |
| | supporter | 2 | 3 | 2 | 3 | 2 | 2 |
| **Mid (L21)** | attacker | 6 | 4 | 5 | 3 | 3 | 3 |
| | supporter | 3 | 4 | 4 | 5 | 3 | 3 |
| **Late (L45)** | attacker | 10 | 6 | 7 | 5 | 5 | 5 |
| | supporter | 6 | 5 | 7 | 10 | 6 | 6 |
| **Cap (L60)** | attacker | 12 | 7 | 9 | 7 | 6 | 6 |
| | supporter | 7 | 6 | 8 | 12 | 7 | 7 |

Role multipliers (on top of the curve):

| Role | STR | DEX | CON | WIS | LER | CHA |
|---|---|---|---|---|---|---|
| attacker | 1.00 | 1.00 | 1.00 | 0.80 | 1.00 | 1.00 |
| supporter | 0.60 | 0.85 | 0.90 | 1.50 | 1.25 | 1.10 |

Supporters trade muscle for healing and a cheaper kit. Anything that heals
should sit at or above the supporter WIS line; anything that only attacks
can sit at 0.8× the WIS line without losing much.

## 4. Current roster fit

Medians from `tests/_diag_enemy_stat_scaling.py` (regular enemies only —
superbosses, minions, city guards, heroines and shadow copies excluded):

| Phase | n | STR | DEX | CON | WIS | LER | CHA |
|---|---|---|---|---|---|---|---|
| Early | 234 | 3 | 3 | 3 | 1 | 2 | 2 |
| Mid | 242 | 7 | 5 | 7 | 3 | 3 | 3 |
| Late | 106 | 9 | 6 | 10 | 5 | 6 | 5 |

The roster already tracks the curve closely. The deliberate deviations:

* Late **CON 10 vs target 7** — late templates are armored elites; the
  player's damage growth absorbs it.
* Early **LER 2 vs target 1** — early kits are authored one level early but
  the Instinctive tier (L1–4) still suppresses damage skills entirely.
* Supporter WIS is the weakest column early (`goblin_shaman`/`cultist` were
  WIS 2 before this pass; both are now 4).

### Healer outliers fixed in this pass

| Template | Level | WIS before → after | Effective after |
|---|---|---|---|
| `goblin_shaman` | 3 | 2 → 4 | 4 |
| `cultist` | 5 | 2 → 4 | 4 |
| `gnome_potion_thrower` | 4 | 2 → 3 | 3 |
| `gnome_alchemist` | 7 | 2 → 4 | 4 |
| `infernal_priest` | 11 | 2 → 4 | 3 (Demon −1 WIS) |
| `vampire_matriarch` | 25 | 4 → 6 | 5 (Vampire −1 WIS) |

Early absolute numbers are tiny (a L3 shaman heals 20% of 20 HP), so these
bumps only make the support role legible; they do not move early balance.

## 5. Authoring guide

When adding an enemy:

1. **Pick the phase** from the floor it spawns in, not its level alone.
2. **Start at the attacker line** for STR/DEX/CON.
3. **If it heals** (`role: supporter`, a heal `abilities:` entry, or a name
   keyword such as Shaman/Priest/Chaplain/Alchemist), move 40% of STR into
   WIS and sit at the supporter WIS line. Give it LER ≥ its level's attacker
   line so the heal comes up often enough.
4. **If it inflicts a debuff** (rider status, racial proc), push CHA to the
   supporter/attacker line. CHA is the *only* thing that scales proc chance
   besides the hard-coded base.
5. **Don't stack all three** — a high-WIS healer with high-CHA control and
   high-STR damage is a boss, not a regular enemy. Pick one role.
6. Bosses may exceed the line; that is what `boss: true` is for. Superbosses
   are re-budgeted separately (see `docs/*superboss*` and the bracket code in
   `world/dungeon.py`).

## 6. Example — Everlong crew (2026-11-24)

The crew were level 18–20 with effective stats below the F40 pool. They now
sit at L34–36, in line with the Late band, and the Chaplain adds the support
slot the encounter was missing.

| Crew | Lv | HP | STR | DEX | CON | WIS | LER | CHA | Role |
|---|---|---|---|---|---|---|---|---|---|
| Seaman | 34 | 360 | 8 | 6 | 9 | 3 | 4 | 2 | attacker |
| Gunner | 35 | 320 | 9 | 9 | 7 | 2 | 4 | 2 | attacker |
| Brawler | 36 | 400 | 11 | 5 | 10 | 2 | 3 | 3 | attacker |
| Boatswain | 35 | 350 | 8 | 6 | 9 | 5 | 6 | 5 | attacker |
| Lookout | 34 | 330 | 7 | 10 | 7 | 4 | 6 | 3 | attacker |
| **Chaplain** | 35 | 340 | 6 | 6 | 8 | **12** | **9** | **9** | **supporter** |

The Chaplain is guaranteed in the opening boarding party (three fighters +
one support, the 5-enemy arena cap), heals the most wounded crew every 3
turns (16% max HP × WIS 1.48 ≈ 23.7%), and otherwise has a 35% chance to
chant +1 STR / +1 DEX over the crew for 2 turns. It never heals the Captain,
so the Ghostly Hull phase is not extended.

## 7. Verification

```
.venv\Scripts\python.exe tests/_diag_enemy_stat_scaling.py
.venv\Scripts\python.exe -m pytest -q tests/test_enemy_scaling.py
```

The audit is a report (always exits 0). The pytest file asserts the curve is
monotonic, the caps hold, `enemy_stats` exports all six stats, enemy WIS
reduces player dodge, and the Everlong crew meets the Late band.
