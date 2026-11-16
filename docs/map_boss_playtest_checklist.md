# Seasonal Map Boss — Playtest Checklist (Phase 5)

Design: [`map_boss_design.md`](./map_boss_design.md) §12.3.
Expected values come from the shipped constants — `resources/map_boss_data.py`
§14 is the single source. A "❌" or a mismatch anywhere = bug to report.

Fastest route to a valid save: play to **Floor 21** in any biome (the gate is
`max_floor > 20`, i.e. Floor 20 *cleared*), or use the dev console if your
build has one.

---

## 1. Unlock & first spawn

- [ ] With `max_floor ≤ 20`, **no** Warden marker exists anywhere on the world
      map (test in every season).
- [ ] Clear Floor 20 → return to a city / open the world map → the current
      season's Warden appears at **Echo 0, Lv 20, 1,000 HP**.
- [ ] Journal (Events tab) shows **`[MAP BOSS] A Warden Notices`** — "Floor 20
      is cleared. The {season} Warden stirs near {city}." — and
      **`The Season Turns`** naming the Warden, Echo 0, Lv 20 and the
      season's last day.
- [ ] Reload the save: the marker, Echo and journal stay put (no double spawn,
      no duplicate journal entry for the same day).

## 2. Marker & panel

- [ ] Marker reads `🌱 E0` in Spring, `🔥`, `🍂`, `❄` in the other seasons, with
      a gold outline; it becomes `#f1c40f` when selected.
- [ ] Marker sits **inside** the map bounds (never half-clipped) and does not
      overlap a city, a wild ruin or the Event Horizon site.
- [ ] Clicking it (not the city / wild ruin / EH behind it) opens the panel:
      Warden name, `[glyph Season · Echo 0 · Lv 20]`, HP bar 100%, Mechanic
      `Bloom (Poison)`, Biome, Element **Earth**, Weakness **Fire**,
      Nearest city, `Departs Day 91 (in N day(s))`, `Est. travel ≈N blocks`.
- [ ] The panel has **no** separate `MECHANIC` block (no tier/effect list and
      no resist line) — the mechanic is only named in the stat rows.
- [ ] Spoils block shows the cache name with a rarity tag, the two consumables
      and the element flower, then `★ Next trophy: Warden's Signet — 1 total
      victories (1 to go)`.
- [ ] Hovering then moving off the marker deselects it (and Escape closes).

## 3. Travel & arrival

- [ ] "Travel to the Warden" starts the off-road journey; the ETA matches the
      panel's estimate.
- [ ] Arriving opens the **start-depth dialog** only if you have beaten an Echo
      before (`best_echo > current echo`); a first visit goes straight in.
- [ ] After any kill, the next arrival **offers the recalled depth**; choosing
      it drops you at `Echo N` **at full HP** and the journal records
      `Depth Recalled`.
- [ ] Declining (`Begin at Echo 0`, the default focused button) is remembered
      for the season — no second offer that season.
- [ ] A cleared Echo can **never** be re-entered: with `best_echo = 3` and the
      current Echo 3, no offer appears; killing Echo 3 offers `best_echo`
      only into Echo 4.
- [ ] Travel while the season boundary passes → **expiry grace**: you land in
      the nearest city, the log says the season turned, no fight, no penalty.

## 4. Arena branding

- [ ] DungeonScreen title = Warden name; subtitle
      `Spring · Echo 0 · Lv 20 · Bloom`.
- [ ] Top bar `🌱 Spring Echo 0 · HP 100% | <time track>`.
- [ ] Left panel is labelled **Arena** with a single `⚔ ARENA` node; no
      `Floor N`, no craft hint, no floor-clear button.
- [ ] "← Leave Arena" opens a confirm that names the season deadline and
      focuses **No** (Enter must not confirm it).

## 5. The fight

- [ ] Combat top bar reads `⚔ <Warden> | Spring Echo 0 | <projected phase>`.
- [ ] Start at **Morning (blocks 0–7)**: the Warden is Dormant (reduced
      damage), no adds.
- [ ] **Noon (8–15)**: `⚙ [PHASE] Noon` banner, ×1.10 damage, **2 adds**
      (Bloomling) join.
- [ ] **Night (16–23)**: `[PHASE] Night`, ×1.30 damage, **the Warden acts
      twice per round** and **4 adds** join (cap: boss + adds = 5).
- [ ] Cross into the next day → `Dawn breaks` + **Dawn Lull** for 2 rounds
      (×0.85 damage, −20% armour) and the adds are cleared.
- [ ] Bloom mechanic: watch `BLOOM×n` in the boss HUD climb to 3, the Warden
      heal on consumption, and Poison (`PSN`) appear on a hero from Echo 1.
- [ ] Each round the HUD clock advances **one block** while the real clock in
      the top bar does **not** move.
- [ ] One fight should cost `rounds` blocks in total — check the day/`Day
      blocks` after leaving (one batched commit, no mid-fight rollover).
- [ ] Flee from the combat menu at any HP: allowed even at 1%.

## 6. Flee / death / interrupt

- [ ] Flee at ~50% → log "The Warden waits. This Echo's progress is kept.",
      return to the nearest city; marker shows the same Echo at ~50%.
- [ ] Re-enter → the fight starts with the Warden at the **saved HP** (same
      Echo number).
- [ ] Die → DeathScreen says **"You were slain by the Warden of the First
      Bloom — Spring Echo 0."**; the Echo stays at its pre-fight HP.
- [ ] Close the window / force-quit mid-fight, reload → no arena transients
      (`_map_boss_*`), the Echo HP is whatever it was, party is in the city.
- [ ] `max_floor` and `city_floors` are unchanged after every outcome.

## 7. Victory & loot

- [ ] Kill Echo 0 at Noon/`Day` → reform window **"THE WARDEN REFORMS"**:
      "…collapses — and the hours run backward. Echo I (Lv 40) stands where it
      fell. Party HP: x/y (z%)." plus **Spoils:** gold, XP, cache, 2
      consumables, 1 flower, and (first kill) `★ Trophy: Warden's Signet`.
- [ ] Gold/XP match the formula: Echo 0 = **400 gold / 600 XP**; Echo 1 =
      **1,000 / 1,550**; Echo 3 = **2,200 / 3,450** (before daily bonus, title
      gold-find and the Night bonus).
- [ ] Night kill (killing blow at blocks 16–23) → **+25% gold** and **2
      flowers**; the window shows `(Night kill)`.
- [ ] Cache: rarity is rare-or-better and the panel preview matches the item
      you receive; at Echo 9+ it is always epic, and from Echo 10 there is a
      30% legendary.
- [ ] The two consumables are tier 3 (Echo 0–1) or tier 4 (Echo 2+), and the
      first is the element-themed one (`ember_draught` for Summer, etc.).
- [ ] The flower is always the Warden's element.
- [ ] XP lands on the player **and every living ally**; a fallen ally gets
      none.
- [ ] Journal shows **`[MAP BOSS] Warden Felled — Spring Echo 0`** with the
      gold/XP summary.
- [ ] Bag is full → the **trophy is still added**; a cache that cannot fit is
      reported (not silently duplicated).

## 8. Reform loop

- [ ] "Face the next Echo" re-enters the arena **immediately** with **no
      heal** — party HP carries over, the new Echo is at full HP.
- [ ] "Leave Arena" returns to the city; the next Echo is still on the map at
      the same site.
- [ ] Repeat until Echo 3: levels read **20 / 40 / 60 / 80**, then stay 80
      while HP/STR/resists keep climbing.
- [ ] Echo N unlocks exactly **N+1** mechanic effects (check the panel's
      mechanic line each time).

## 9. Season rotation

- [ ] Sleep/travel until day **91** → the old Warden is replaced by
      **Warden of the Long Noon** at Echo 0: new glyph 🔥, Fire element, weak
      to Water, Heat mechanic, new site near a desert/volcanic/savanna city.
- [ ] Journal shows `The Season Closes` and a fresh `The Season Turns`.
- [ ] Echo counters reset (`echo 0`), `best_echo` **persists** — the new
      season offers the recalled depth again.
- [ ] Repeat at days **181** (Autumn/wind/Harvest) and **271**
      (Winter/water/Frostbite), and at **361 → day 1** (Spring again).
- [ ] A kill that crosses a season boundary spawns the **new season's** Warden
      (§7.7 order) and still pays the killed Echo's loot.

## 10. The four trophies

- [ ] Kill 1 → **Warden's Signet**; 3 → **Long Day's Edge**; 6 →
      **Echo Mantle**; 10 → **Sundial Crown**; no duplicates ever.
- [ ] 11th kill → **second Warden's Cache** instead of a trophy (the panel
      reads "All four trophies claimed — the cache doubles.").
- [ ] Signet: damage is flat in the Morning, **+8%** at Noon, **+16%** at
      Night (compare one attack per phase).
- [ ] Long Day's Edge: +3% per round up to **+30%**; crossing dawn resets it.
- [ ] Echo Mantle: **−12%** damage taken by day, **−20%** at Night (check the
      `DEF12%` / `DEF20%` tag and the damage numbers).
- [ ] Sundial Crown: once per day, a killing blow leaves you at **1 HP** with
      every debuff cleared; it does **not** trigger twice the same day, and it
      recharges on the next day.
- [ ] All four work on an **ally**: equip one and confirm the tag/behaviour
      follows the wearer in both normal dungeons and the arena.

## 11. Boundaries

- [ ] The Warden never appears during **Pandemonium**, **Wonderland** or an
      **Event Horizon** run, and cannot be captured.
- [ ] Killing it adds **no** `defeated_superbosses` entry, no superboss pool
      slot, no awakening shards, no bounty/quest/title progress, and no
      Pandemonium ×2.5 pay-out.
- [ ] After a Warden kill, a **normal** dungeon fight is unchanged (no leaked
      `defense_pct`, no stale `long_day_stacks`, no arena clock label).

---

## Known tuning targets (first pass)

These are the numbers most likely to move after the first real playtest:

| Knob | Now | Watch for |
|---|---|---|
| `MAP_BOSS_BASE_HP` / `MAP_BOSS_HP_PER_ECHO` | 1,000 / +10% (+0.2%·E²) | Echo 1–3 fight length (target 6–10 rounds) |
| `MAP_BOSS_BASE_STR` | 30 | Echo 0 hitting too hard for a fresh Floor-21 party |
| `MAP_BOSS_ARMOR_CAP` | 40 | armour blunting weapon builds past Echo 10 |
| `MAP_BOSS_DAWN_LULL_ROUNDS` | 2 | long fights stacking Lulls |
| `MAP_BOSS_NIGHT_ACTIONS` | 2 | Night feeling mandatory-skip |
| `MAP_BOSS_EPIC_CHANCE_BASE` / `PER_ECHO` | 10% / +10% | cache generosity across a season |
| `MAP_BOSS_GOLD_BASE` / `XP_BASE` | 400 / 600 | payout vs a Floor-21 dungeon clear |
| `MAP_BOSS_UNIQUE_MILESTONES` | 1 / 3 / 6 / 10 | time-to-first-trophy |
