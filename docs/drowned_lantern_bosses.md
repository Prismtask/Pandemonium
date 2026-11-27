# The Drowned Lantern — Boss Roster & Encounters

Status: **proposal / for review** — no code yet.
Companion docs: `lantern_isle_design.md` (mechanics/quests) · `drowned_lantern_dialogue.md`
(scene script) · `map_boss_design.md` (Seasonal Warden — the difficulty yardstick) ·
`enemy_ai_behaviors_design.md` (race kits) · `modding_design.md` (delivery).

Everything here is tuned for the pack's **level 40–60** band. The optional night raids are
the exception: after the arc ends they escalate to **Seasonal Warden parity** (level 80
and beyond, Echo-style).

---

## 0. Conventions

| Rule | Value |
|---|---|
| **Arc level band** | 40–60. Act 1 = 42, Act 2 = 46–50, Act 3 = 52–56, Act 4 = 58–60 |
| **Enemy slots** | Max 5 (boss + 4 adds) — same cap as the Warden arena |
| **Boss runtime** | Arena encounter, not a floor loop. Reuse the arena shape of `combat/map_boss.py` / `superboss_common.superboss_combat_loop`; do **not** add a DLC-specific screen |
| **Phases** | HP thresholds with a one-line **telegraph** printed a round before any heavy move |
| **Status scale** | Boss `status_res` 0.30–0.55 inside the arc; night raids follow Warden caps |
| **Solo rule** | Acts 1 and 3 run solo. `lantern_solo_ward` adds +30% max HP, +20% damage, and a free camp heal per act; without it the solo bosses are not shippable |
| **Party rule** | Acts 2 and 4 assume the player + Marian (2 actors), tuned as a 3-actor group |
| **Flags** | Every kill sets `lantern_boss:<id>`; quests read flags only (`lantern_boss:anchor_warden`), never boss internals |
| **Loot split** | **Arc bosses** give uniques/keys/materials. **Night wardens give materials only** + gold/XP — never uniques, lore, or codex |
| **Immunities** | No boss is immune to everything. Every boss has one exploitable element (≤ 0.70 taken) and one resisted element (≥ 1.40 taken) |

**Damage language.** A boss ability written `1.2×` means 1.2 × the boss's expected
auto-attack damage at its level. The night-raid table's `dmg ×` column is the Warden's
`damage_mult` (applies to all outgoing damage), so tuning matches `echo_stats()` exactly.

---

## 1. Difficulty ladder

| # | Boss | Act | Level | Max HP | Actors | Role |
|---|---|---|---|---|---|---|
| 1 | **The Market Granary** (scripted) | 1 | 42 | 3 × 180 | Solo | First combat trigger; teaches the granary |
| 2 | **Drowned Quartermaster** | 2 | 46 | 1,400 | Player + Marian | The Wreck mini-boss; drops the beacon lens |
| 3 | **The Dream-Warden** | 2 | 50 | 3,000 | Player + Marian | Act finale; its death resets into Act 3 |
| 4 | **The Archivist** | 3 | 52 | 2,600 | Solo | Sanctum wing 1; first lamp |
| 5 | **The Cantor** | 3 | 54 | 2,900 | Solo | Sanctum wing 2; second lamp |
| 6 | **The Anchor Warden** | 3 | 56 | 4,200 | Solo | Sanctum wing 3; Lantern Anchor |
| 7 | **Drowned Sailor** | 4 | 58 | 3,600 | Player + Marian | Harbor shrine |
| 8 | **Hollow Merchant** | 4 | 58 | 3,600 | Player + Marian | Market shrine |
| 9 | **Weeping Mother** | 4 | 58 | 3,600 | Player + Marian | Residential shrine |
| 10 | **The Choir** | 4 | 58 | 3 × 1,200 | Player + Marian | Temple shrine (trio) |
| 11 | **The Keeper** | 4 | 60 | 5,400 | Player + Marian | Finale; ends in the choice, not a kill |
| 12 | **Night Wardens ×4** | post | 40 → 80+ | 2,424 → 10,773+ | Player + Marian | Optional repeatable; Warden parity |

**Curve check.** Act 4 shrine bosses (3,600 HP) sit just under Warden Echo I (level 40,
2,424 HP but 1.65× damage) in threat and well under Echo II (4,107 HP, 2.33× damage at
level 60). The Keeper is deliberately the arc ceiling at 60.

---

## 2. Act 1 — The Market Granary (scripted encounter)

Not a boss, but it is the pack's combat gate and the first thing that must feel right.

| | |
|---|---|
| **Where** | Market district, the chandler's granary (single room) |
| **Trigger** | Accept the wick task; the chandler refuses until the rats are gone |
| **Enemies** | `cave_rat` ×1 + `shadow_rat` ×2 (level 42, **180 HP** each, 1.0× damage) |
| **Rules** | No adds, no phases. Rats use the Beast kit (Feral Pounce rider: `bleed` T1) |
| **Solo ward** | +20% max HP only (the fight should be won at ~60% HP) |
| **Reward** | `festival_wick`, `market_granary_cleared` |
| **Act 2 echo** | Same room, `shadow_rat` ×3 (level 46, 220 HP), no carcass loot — the memory refuses to pay |

**Design intent:** the party learns that the island's combat is normal combat before it
meets anything that lies to it. No mechanics, no telegraphs, no phase text.

---

## 3. Act 2

### 3.1 The Drowned Quartermaster — The Wreck

> *"Cargo manifest. One lens. One crew. One tide."*

| | |
|---|---|
| **Level / HP** | 46 / **1,400** |
| **Armor / status res** | 14 / 0.30 |
| **Element** | water — resists water **1.45**, takes **1.30** from lightning |
| **Actors** | Player + Marian |
| **Arena** | The Wreck's flooded hold: 2 crates (destructible, absorb 120 damage each) |

**Phases**

| Phase | HP | Behaviour |
|---|---|---|
| **Manifest** | 100–60% | One action. Alternates `Manifest Strike` / `Cargo Chain` |
| **Overload** | 60–30% | Two actions from 60%; summons 2 drowned deckhands at the phase break |
| **Jetty** | < 30% | Two actions; `Undertow` becomes available |

**Abilities**

- **Manifest Strike** — 1.3× single, physical. *"The Quartermaster unhooks a manifest board."*
- **Cargo Chain** — 0.9× single + `slow` 2 turns. *"A chain of cargo hooks drags across the deck."*
- **Bilge Spray** — 0.8× AoE (all actors) + `poison` 3 turns. Water.
- **Overload** (60%) — summons **2 × Drowned Deckhand** (level 45, 260 HP). While any
  deckhand lives the Quartermaster gains **+25% damage**.
- **Undertow** (< 30%, every 3rd round) — 1.6× AoE + `stun` 1 turn unless the actor
  dodges. *"The water under the deck pulls the wrong way."*

**Exploit:** destroying a crate deals 120 damage to the Quartermaster through the hold.
**Solo/party note:** with Marian the fight is about holding the deckhands; without her
(debug only) the encounter is not balanced.

**Drops:** `beacon_lens` (quest), 2 × `wreck_salt`, gold/XP for level 46.
**Flag:** `lantern_boss:drowned_quartermaster`.

---

### 3.2 The Dream-Warden — Act 2 epilogue

> *"The day is not finished."*

| | |
|---|---|
| **Level / HP** | 50 / **3,000** |
| **Armor / status res** | 16 / 0.35 |
| **Element** | dark/light — resists dark **1.50**, takes **1.30** from light |
| **Actors** | Player + Marian |
| **Arena** | The festival square at dusk; three **face-lanterns** hang above it |

**The core mechanic — the Reset Meter**

The Warden gains **+1 Reset** at the end of each round (displayed in the boss line, like
the Warden's mechanic stacks). At **5 Reset** it casts **Reset the Day**:

- 2.0× AoE to all actors, heals the Warden 10% of max HP, summons 2 memory-echoes,
  resets Reset to 0.

Reset can be **drained** three ways, and the fight is about choosing one:

1. **Strike a face-lantern** — each lantern has 200 HP; breaking one drains 2 Reset and
   cancels the next `Correction`.
2. **Marian's Memory Flare** — once per fight, drains 3 Reset (`hymn` cooldown 4 rounds).
3. **Eat the cast** — take the AoE and start over. Valid, expensive.

**Phases**

| Phase | HP | Behaviour |
|---|---|---|
| **Remembrance** | 100–66% | One action; opens with `Face of the Mother` |
| **Correction** | 66–33% | Two actions; `Correction` once at the break (dispels buffs, `silence` 2) |
| **Reset** | < 33% | Two actions; Reset gains **+2 per round** instead of +1 |

**Abilities**

- **Face of the Mother** — 1.2× magical + `weaken` 2 turns.
- **Face of the Father** — 1.2× physical + `blind` 2 turns.
- **Chorus of the Town** — 0.9× AoE + `slow` 2 turns.
- **Correction** (66% break, then every 5 rounds) — dispels all actor buffs, `silence` 2.
- **Reset the Day** — as above. *"Every bell in the town rings at once."*

**Adds:** 2 × **Memory Echo** (level 48, 300 HP). Echoes do not attack; they **feed Reset
+1 per round while alive**. Killing them is always correct.

**Script hook:** at 0 HP the fight does **not** end — the epilogue scene plays, the island
collapses, and the Act 3 reset fires. The boss module sets `dream_warden_defeated` and
hands control to the mod's `loop.py`.

**Drops:** `dream_shard` (material, 1), 2 × `beacon_glass`, gold/XP for level 50.
**Flag:** `lantern_boss:dream_warden`.

---

## 4. Act 3 — The Drowned Sanctum (solo)

All three Act 3 bosses assume `lantern_solo_ward` (+30% max HP, +20% damage, one camp heal
per act). Truth-map echo encounters are separate and stay at **2 enemies**.

### 4.1 The Archivist — wing 1, first lamp

> *"Every name. Every ship. Every morning."*

| | |
|---|---|
| **Level / HP** | 52 / **2,600** |
| **Armor / status res** | 15 / 0.40 |
| **Element** | dark — resists dark **1.50**, takes **1.35** from fire |
| **Arena** | The Archive: knee-deep water, 4 shelving rows (cover) |

**The core mechanic — The Name Wall**

At the end of each round the Archivist **writes one of your memories** onto the wall.
Each entry applies a stacking debuff to the player (`blind` → `slow` → `weaken`, one per
round, max 3). At **3 entries** it casts **Final Entry**. The player can interrupt the
writing by dealing **≥ 15% of the Archivist's max HP in one round** (600+), which erases
the current entry.

**Phases**

| Phase | HP | Behaviour |
|---|---|---|
| **Cataloguing** | 100–60% | One action; writes every round |
| **Errata** | 60–25% | Two actions; `Redaction`; spawns 2 ink blots at the break |
| **Final Entry** | < 25% | Two actions; `Final Entry` every 3rd round while entries ≥ 2 |

**Abilities**

- **Ink Lash** — 1.3× magical (dark) + `blind` 2 turns.
- **Redaction** — strips one player buff and heals itself 6% max HP.
- **Errata** (60% break) — 2 × **Ink Blot** (level 50, 220 HP); each living blot gives the
  Archivist **+10% damage**.
- **Final Entry** — 2.2× single, and if the player is below 35% HP it also `stun`s for 1
  turn. *"He underlines your name."*

**Drops:** **first lamp**, `ledger_page` (material, 2), gold/XP for level 52.
**Flag:** `lantern_boss:archivist`, `sanctum_lamp_1`.

---

### 4.2 The Cantor — wing 2, second lamp

> *"Sleep. Sleep. The morning is warm."*

| | |
|---|---|
| **Level / HP** | 54 / **2,900** |
| **Armor / status res** | 16 / 0.40 |
| **Element** | light — resists light **1.45**, takes **1.35** from dark |
| **Arena** | The Choir: no roof, no floor, one **Bell** on a chain at the centre |

**The core mechanic — Hymn stacks**

The Cantor gains **+1 Hymn** at the end of each round it is not interrupted. At **5 Hymn**
it casts **Lullaby** (`sleep` 2 turns + heals itself 10%). Hymn can be cleared by:

- **Ringing the Bell** (once per phase, player action) — clears all Hymn, `daze`s the Cantor 1 turn.
- **Landing a light-element hit** — removes 1 Hymn.
- **Interrupting** (≥ 500 damage in one round) — removes 2 Hymn.

**Phases**

| Phase | HP | Behaviour |
|---|---|---|
| **Versicle** | 100–50% | One action; Hymn +1/round |
| **Antiphon** | 50–20% | Two actions; opens with `Antiphon` |
| **Crescendo** | < 20% | Two actions; damage ramps **+15% per round** until dead |

**Abilities**

- **Versicle** — 1.2× magical (light) + `slow` 2 turns.
- **Antiphon** — 0.9× AoE + `silence` 2 turns. *The song answers itself.*
- **Descant** — grants itself **haste** (extra action next round, once per phase).
- **Lullaby** — at 5 Hymn: `sleep` 2 turns + heal 10% max HP + resets Hymn.
- **Crescendo** (< 20%) — each round gains +15% damage, stacking; the fight becomes a race.

**Solo note:** the Bell is mandatory. Without it, a bad Hymn cycle is an unavoidable sleep
into a crescendo death. The bell's tag must be visible in the room description.

**Drops:** **second lamp**, `hymn_page` (material, 2), gold/XP for level 54.
**Flag:** `lantern_boss:cantor`, `sanctum_lamp_2`.

---

### 4.3 The Anchor Warden — wing 3, Act 3 final

> *"Eight lights went dark. The ninth kept its promise."*

| | |
|---|---|
| **Level / HP** | 56 / **4,200** (3 lamps: **3,360**) |
| **Armor / status res** | 20 / 0.45 |
| **Element** | water — resists water **1.55**, takes **1.30** from light |
| **Arena** | The Anchor Chamber: a ring of nine lamps, a chain going up into the dark |

**The core mechanic — lamps weaken it**

Each Sanctum lamp the player lit before the fight changes the encounter:

| Lamps lit | Phases | Adds | Max HP | Armor | Salt Skin reflect |
|---|---|---|---|---|---|
| 0 | 3 | 2 | 4,200 | 20 | 10% melee |
| 1 | 2 | 1 | 3,780 | 16 | 8% melee |
| 2 | 2 | 1 | 3,570 | 12 | 6% melee |
| 3 | 1 | 0 | 3,360 | 8 | 5% melee |

The lamps are also **checkpoint heals** before the fight. A player who skipped a wing can
still win, but the Warden is a real wall.

**Phases** (as lamp count allows)

| Phase | HP | Behaviour |
|---|---|---|
| **The Door** | 100–70% | One action; `Anchor Swing` / `Chain Shot` |
| **The Promise** | 70–40% | Two actions; adds; `Hold the Door` shield |
| **The Ninth** | < 40% | Two actions; `Ninth Tide` every 3rd round (telegraphed) |

**Abilities**

- **Anchor Swing** — 1.5× single physical, 25% `stun` 1 turn.
- **Chain Shot** — 1.1× ranged + `slow` 2 turns.
- **Hold the Door** — absorbs 10% max HP as a shield while any add lives.
- **Salt Skin** (passive) — reflects a share of melee damage (table above).
- **Ninth Tide** — 2.0× AoE water; telegraphed one full round; the player can dive behind
  the Vault Door to halve it. *"The floor becomes the sea."*

**Adds:** **Drowned Keeper** (level 54, 420 HP) — `Anchor Swing` only.

**Script hook:** on death the Warden **sinks**, the anchor frees, and the Lantern Anchor is
granted by the scene, not by loot. The third lamp is part of the kill, so an interrupted
fight cannot lose it.

**Drops:** `lantern_anchor`, third lamp, 3 × `salt_iron`, gold/XP for level 56.
**Flag:** `lantern_boss:anchor_warden`.

---

## 5. Act 4 — the four shrines (player + Marian)

All four are level **58**, **3,600 HP**, armor **18**, status res **0.40**, and are
**free order**. Each has one district element, one party-facing mechanic, and one
"the memory fights back" moment at 25%.

| Boss | District | Element (res / weak) | Mechanic | Memory moment |
|---|---|---|---|---|
| **Drowned Sailor** | Harbor | water 1.45 / lightning 1.30 | **Broadside** every 3rd round | *Last Orders* — all hands attack |
| **Hollow Merchant** | Market | dark 1.45 / light 1.30 | **Debt** stacks → Foreclosure | *Going Out of Business* — sells his own adds |
| **Weeping Mother** | Residential | water 1.40 / fire 1.30 | **Grief** stacks → Wail | *Let Them Go* — huge AoE, then self-stun |
| **The Choir** | Temple | light 1.50 / dark 1.35 | **Three bodies**, shared death | *Requiem* — the last voice sings |

### 5.1 Drowned Sailor

- **Phases:** Watch (100–60) → All Hands (60–25, 2 actions) → Last Orders (< 25%, 2 actions + 1 add).
- **Abilities:** `Cutlass Flurry` (3 × 0.55×), `Rigging Snare` (0.8× + `slow` + `daze` 1),
  `Bosun's Whistle` (summons **2 × Drowned Hand**, level 56, 300 HP),
  `Broadside` (1.8× AoE water, every 3rd round, telegraphed).
- **At 25%:** *Last Orders* — all living hands act immediately, then the Sailor gains
  **+20% damage** for the rest of the fight.
- **Weakness exploit:** lightning attacks chain to one add for 50% damage.

### 5.2 Hollow Merchant

- **Phases:** Open Stall (100–60) → Clearance (60–25, 2 actions) → Foreclosure (< 25%).
- **Mechanic — Debt:** +1 Debt on the party per round (max 4). At **4 Debt** it casts
  **Foreclosure**: 15% max HP drain from each actor, heals itself for the total, resets.
  Killing a **Hollow Customer** removes 1 Debt.
- **Abilities:** `Price Cut` (1.4× single, ignores 25% armor), `Bait and Switch` (taunt;
  redirects the next attack to an add), `Clearance` (0.9× AoE), `Counterfeit` (summons
  **2 × Hollow Customer**, level 56, 280 HP).
- **At 25%:** *Going Out of Business* — sacrifices all adds, healing 8% per add, then
  fights alone with **+25% damage**.

### 5.3 Weeping Mother

- **Phases:** The Window (100–60) → The Lane (60–25, 2 actions) → Let Them Go (< 25%).
- **Mechanic — Grief:** +1 Grief per round on each actor (max 3). At **3 Grief** the actor
  gets `weaken` 2 turns. Cleansed by **Marian's hymn** (1 round, once per 4 rounds).
- **Abilities:** `Wail` (0.9× AoE + `dread`), `Cradle` (heals herself 8% + shield 5%),
  `Memorial Flame` (1.2× fire + `burn` 3), `The Lane Remembers` (summons **2 × Weeping
  Echo**, level 56, 260 HP, they only apply Grief).
- **At 25%:** *Let Them Go* — 2.5× AoE, then **self-stun 1 round**. That stun is the
  intended kill window; skipping it makes the fight unfair, so it is not optional.

### 5.4 The Choir (trio)

- **Structure:** three bodies — **Voice** (leader), **Antiphon**, **Descant** — each
  **1,200 HP**, level 58, armor 18. The encounter ends when all three are dead.
- **Shared rule:** each death grants the survivors **+25% damage** and heals them 10%.
- **Abilities:** `Round` (chain lightning, 1.0× to two targets), `Fugue` (haste an ally),
  `Dissonance` (0.9× AoE + `silence` 2), `Requiem` (only the last survivor; 2.0× AoE,
  telegraphed one round).
- **Target order matters:** killing Voice first removes `Fugue`; killing Antiphon first
  removes `Dissonance`; killing Descant first removes `Round`. The fight is a puzzle, not
  a DPS check.

---

## 6. Act 4 finale — The Keeper

> *"I only wanted the morning to last."*

| | |
|---|---|
| **Level / HP** | 60 / **5,400** |
| **Armor / status res** | 20 / 0.50 |
| **Element** | fire/light — resists fire **1.45**, takes **1.30** from water |
| **Actors** | Player + Marian |
| **Arena** | The lighthouse lamp room; the lens; a stair going down |

**Phases**

| Phase | HP | Behaviour |
|---|---|---|
| **The Host** | 100–75% | One action; polite, apologetic, `Lamp Hook` / `Lens Flash` |
| **The Hand** | 75–40% | Two actions; `Keeper's Command` adds; *The Morning* at the break |
| **The Edge** | < 40% | Two actions; `Anchor Chain`; damage ramps +10% per round |

**Abilities**

- **Lamp Hook** — 1.3× single fire + `burn` 3 turns.
- **Lens Flash** — 0.9× AoE light + `blind` 2 turns.
- **Keeper's Command** (75% break, then every 5 rounds) — **2 × Drowned Keeper** (level 58, 420 HP).
- **The Morning** (75% break) — heals himself 10% and gains **+15% damage** for the rest of
  the fight. *"Outside, the town begins the same morning again."*
- **Anchor Chain** (< 40%, once) — **binds Marian**: she cannot act until the chain takes
  **800 damage** or 2 rounds pass. This is the only time the game disables the companion;
  the scene around it must tell the player what to do.
- **Last Light** (< 15%) — scripted: he stops attacking, the lens turns, and the **choice
  screen** opens. The Keeper cannot be killed by damage.

**The rule that must not break:** every ending breaks him. The fight never awards a
"spared" state; the choice changes what his death anchors, not whether it happens.

**Drops:** none. The finale scene grants the ending item (`marian_keepsake` on Release,
the hub on Keep, Marian's permanence on Bind).

---

## 7. Post-arc night raids — the Night Wardens

Unlocked only after Q8 (the arc is finished). The lit inn offers a day/night toggle;
at night the four districts host **Night Echoes** of their shrine wardens. They are the
hardest repeatable content in the pack and are built to the **Seasonal Warden's own
numbers**.

### 7.1 Parity model (no new tuning constants)

The base game already publishes the Warden's curves in
`pandemonium/resources/map_boss_data.py` and computes them in
`pandemonium/world/map_boss.py::echo_stats()`. Night Echo `n` is simply:

```
seasonal_echo = n + 1                        # Night I == Warden Echo I
level  = min(80, 20 + 20 * seasonal_echo)    # 40, 60, 80, 80, …
stats  = echo_stats(seasonal_echo)           # HP, damage, armor, res, status res
rank   = min(4, 1 + n // 3)                  # +25% mechanic values per rank
tier   = min(10, n + 1)                      # one new Tide effect per Echo
```

That gives exact difficulty parity with the current season's Warden at the same Echo, and
the same infinite escalation above level 80. Flee is always allowed, HP persists per Echo,
a kill immediately reforms the next Echo, and every district tracks its own `n`.

**The only island substitution:** the Warden's Noon/Night/Dawn phase multipliers are
renamed to the island's tide, with **identical numbers**.

| Island phase | Warden equivalent | Effect |
|---|---|---|
| **Ebb** | Noon | damage **1.10×** |
| **Flood** | Night | damage **1.30×** and **2 actions** |
| **Slack Water** | Dawn lull | damage **0.85×** for **2 rounds** |

### 7.2 Night Echo scaling table

| Night Echo | Level | Max HP | Damage × | Armor | Elemental res | Water res | Status res | Mechanic rank | Tide tier |
|---|---|---|---|---|---|---|---|---|---|
| **I** | 40 | 2,424 | 1.65× | 15 | 1.12 | 1.42 | 0.33 | 1 | 1 |
| **II** | 60 | 4,107 | 2.33× | 19 | 1.24 | 1.53 | 0.46 | 1 | 2 |
| **III** | 80 | 6,063 | 3.05× | 22 | 1.36 | 1.65 | 0.59 | 2 | 3 |
| **IV** | 80 | 6,587 | 3.14× | 23 | 1.38 | 1.66 | 0.62 | 2 | 4 |
| **V** | 80 | 7,130 | 3.22× | 23 | 1.40 | 1.68 | 0.65 | 2 | 5 |
| **VI** | 80 | 7,691 | 3.30× | 24 | 1.42 | 1.69 | 0.68 | 3 | 6 |
| **VII** | 80 | 8,271 | 3.39× | 24 | 1.44 | 1.70 | 0.71 | 3 | 7 |
| **VIII** | 80 | 8,869 | 3.47× | 25 | 1.46 | 1.70 | 0.74 | 3 | 8 |
| **IX** | 80 | 9,485 | 3.56× | 25 | 1.48 | 1.70 | 0.77 | 4 | 9 |
| **X** | 80 | 10,120 | 3.64× | 26 | 1.50 | 1.70 | 0.80 | 4 | 10 |
| **XI+** | 80 | +6.4%/Echo | +3%/Echo | +0.5/Echo | +0.02/Echo (cap 1.60) | cap | +0.03/Echo (cap 0.85) | 4 | 10 |

Every figure above is `echo_stats(n + 1)` — do not retune them, assert them in a test.

### 7.3 The Tide mechanic ladder (one new effect per Echo)

Island-themed, same structure as the seasonal ladder (tier = Echo, rank = mechanic power).

| Tier | Effect | Rule |
|---|---|---|
| 1 | **Salt** | Attacks apply 1 Salt; at 5 Salt → `poison` 3 turns |
| 2 | **Fog** | Party attacks have a 10% miss chance |
| 3 | **Undertow** | Every 3rd round applies `slow` 2 turns |
| 4 | **Hymn** | Boss heals 5% at round start if nobody dealt light damage last round |
| 5 | **Drowned Echo** | Summons 1 echo of a district add (max 1 alive) |
| 6 | **Barnacle** | +6 armor; melee attackers take 6 flat damage |
| 7 | **Lantern Gutter** | Light damage −20%; light skills cost +1 AP |
| 8 | **Riptide** | Flood phase gains a third action |
| 9 | **The Ninth** | One-time, at 25% HP: 1.5× AoE (telegraphed) |
| 10 | **Slack Water** | Slack Water heals 8% instead of 4% and lasts 1 round |

Rank scales the *values* (+25% per rank step, cap rank 4); the caps never move. This
mirrors `MAP_BOSS_MECHANIC_RANK_SCALE`.

### 7.4 The four Night Wardens

| Night warden | District | Phase kit (inherits its Act 4 boss) | Night-only additions |
|---|---|---|---|
| **The Sailor at the Gate** | Harbor | Cutlass Flurry, Rigging Snare, Bosun's Whistle, Broadside | Broadside every **2nd** round at rank 2+; at tier 5 the Drowned Echo is a **Drowned Hand** |
| **The Merchant of Nothing** | Market | Price Cut, Bait and Switch, Clearance, Counterfeit | Debt cap drops **4 → 3** at rank 2; Foreclosure also **steals one buff** |
| **The Mother at the Window** | Residential | Wail, Cradle, Memorial Flame, The Lane Remembers | Grief triggers at **2** stacks at rank 2+; Wail gains `dread` |
| **The Choir of the Ninth** | Temple | Round, Fugue, Dissonance, Requiem | At tier 6+ a **fourth voice** (Descant echo) joins with 40% HP |

Each keeps its Act 4 element resistance and weakness — the raid is the same fight, grown.

### 7.5 Rewards (materials only)

Warden-rate gold and XP, island materials, nothing else:

```
gold = 400 + 25 * level + 100 * echo      # echo = n + 1
xp   = 600 + 40 * level + 150 * echo
materials = 2 + echo // 3                 # one district material
```

| District | Material |
|---|---|
| Harbor | `salt_iron` |
| Market | `wreck_salt` |
| Residential | `siren_pearl` |
| Temple | `beacon_glass` |

**Hard rule:** no uniques, no lore, no codex, no memory scenes at **any** Echo. The story
is finished; the raids are a farm and a mood piece. A test must assert this at Echo X.

---

## 8. State, flags, and registry keys

```python
player["lantern"]["bosses"] = []          # defeated arc boss ids
player["lantern"]["night_echoes"] = {     # per-district Echo index (0 = Night I)
    "harbor": 0, "market": 0, "residential": 0, "temple": 0,
}
player["lantern"]["night_hp"] = {}        # {"harbor": 812, ...} persisted per Echo
player["lantern"]["night_best"] = 0       # highest Night Echo cleared anywhere
```

| Boss id | Flag | Quest objective |
|---|---|---|
| `market_granary` | `market_granary_cleared` | Q1b wick |
| `drowned_quartermaster` | `lantern_boss:drowned_quartermaster` | `lantern_raid:wreck` |
| `dream_warden` | `lantern_boss:dream_warden` | `lantern_boss:dream_warden` → Act 3 reset |
| `archivist` | `lantern_boss:archivist` | `lantern_wing:1` |
| `cantor` | `lantern_boss:cantor` | `lantern_wing:2` |
| `anchor_warden` | `lantern_boss:anchor_warden` | `lantern_boss:anchor_warden` |
| `drowned_sailor` | `lantern_boss:drowned_sailor` | `lantern_shrine:harbor` |
| `hollow_merchant` | `lantern_boss:hollow_merchant` | `lantern_shrine:market` |
| `weeping_mother` | `lantern_boss:weeping_mother` | `lantern_shrine:residential` |
| `the_choir` | `lantern_boss:the_choir` | `lantern_shrine:temple` |
| `the_keeper` | `lantern_boss:the_keeper` | `lantern_choice` |

**Enemy ids** (YAML, race groups): `lantern_drowned_deckhand`, `lantern_memory_echo`,
`lantern_ink_blot`, `lantern_drowned_keeper`, `lantern_drowned_hand`,
`lantern_hollow_customer`, `lantern_weeping_echo`. All are pack-tagged
(`pack: drowned_lantern`) so the containment test can prove they never appear on the
mainland.

---

## 9. Implementation notes

- **One module per boss** under `mods/drowned_lantern/scripts/bosses/`: `quartermaster.py`,
  `dream_warden.py`, `archivist.py`, `cantor.py`, `anchor_warden.py`, `shrine.py`
  (four shrine bosses share the module with a data table), `keeper.py`, `night.py`.
- **Arena shape:** reuse the map-boss arena contract (one site, no floors, HP persistence
  only for night raids). Do not build a DLC dungeon screen; if the base game needs a
  generic arena hook, add it generically (`register_boss`).
- **Telegraphs** print one round ahead using `c_print`, never `print`.
- **Phase transitions** are HP-threshold checks at end of round, stored in the boss dict —
  no reliance on message ordering.
- **Solo ward** is applied in the arena entry path, not inside each boss, so all three Act 3
  bosses inherit it.
- **Lamp weaken** is read from `player["lantern"]["sanctum_lamps"]` at arena entry; the
  Anchor Warden never re-reads it mid-fight.
- **Night parity** calls `echo_stats(n + 1)` — import it from
  `pandemonium.world.map_boss` at module level in `night.py` (base game, no cycle).
- **Drops** go through the normal loot path. Night wardens must be marked
  `no_unique: true` in their drop table.

## 10. Verification

- `tests/_diag_lantern_bosses.py`:
  - phase thresholds fire once each, in order, and never rewind;
  - Dream-Warden Reset Meter: 5 stacks casts, lanterns drain 2, Marian drains 3, echoes add 1;
  - Archivist writing interrupts at ≥ 600 damage in one round;
  - Cantor Hymn clears via Bell, light hit, and interrupt (1/1/2);
  - Anchor Warden: each lamp count yields the exact HP/armor/add table in §4.3;
  - Keeper: cannot drop below 1 HP; choice screen opens at 15%;
  - shrine bosses: 25% "memory moment" always fires; Choir death buffs stack correctly.
- **Night parity test:** for n in 0–12, `night_stats(n)` equals
  `map_boss.echo_stats(n + 1)` field-by-field (level, max_hp, damage_mult, armor, resists).
- **Night rewards test:** at Echo X, drops contain only the district material + gold/XP;
  no uniques, no lore flags, no codex ids.
- **Solo test:** every Act 3 boss is beatable at the act-entry level with the ward active
  and the recommended lamp state; a scripted "skip a wing" run is hard but winnable.
- **Containment test:** no boss enemy id or drop appears outside `pack: drowned_lantern`.

## 11. Open

- Whether the Temple Choir boss keeps the name **The Choir** or gets a named warden
  (currently the Sanctum wing and the Act 4 boss share the word).
- Whether Night Echoes should cap at a fixed number (e.g. X) or run forever with the
  Warden's curves. Current proposal: **forever**, level-capped at 80 like the Warden.
