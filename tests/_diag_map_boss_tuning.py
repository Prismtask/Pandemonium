# -*- coding: utf-8 -*-
"""Tuning probe — arena fight length by party strength (run directly, not pytest).

    c:/Code/Pandemonium/.venv/Scripts/python.exe tests/_diag_map_boss_tuning.py

Design target (docs/map_boss_design.md §13.5): a **solo attacker** should clear
Echo 0–1 in roughly 5–22 rounds across the Floor-21 gear band, so a real party
(player + 3–7 allies, skills, buffs) lands in the 5–10 round band and a kill
costs most of one in-game day. Night starts run slightly longer and cost more
HP, which is the intended risk.

The checks are deliberately loose — this script reports numbers for humans to
judge; it only fails when a fight is absurd (0 rounds, or a 40+ round slog that
would burn two days on one attempt).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FAILS = []


def check(label, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(label)


from pandemonium.combat.combat_io import reset_io, set_io  # noqa: E402
from pandemonium.combat import map_boss as cmb  # noqa: E402
from pandemonium.world import map_boss as mb  # noqa: E402
from tests._diag_map_boss_playtest import ScriptedIO, make_hero  # noqa: E402

# (label, strength, hp, con) — roughly Floor-21 fresh → well-geared solo
BANDS = (
    ("fresh Floor-21", 60, 700, 30),
    ("geared", 90, 1000, 35),
    ("strong", 140, 1600, 40),
    ("over-geared", 220, 6000, 40),
)


def run(strength, hp, con, echo, blocks):
    player = make_hero(day=20, blocks=blocks, strength=strength, hp=hp, con=con)
    player["level"] = 21
    site = mb.maybe_spawn(player)
    site["echo"] = echo
    boss = cmb.build_boss(site)
    boss["hp"] = boss["max_hp"]
    set_io(ScriptedIO(max_actions=800))
    try:
        result = cmb.combat_map_boss(player, floor=site["level"], enemies=[boss])
    except KeyboardInterrupt:
        result = "CAP"
    finally:
        reset_io()
    rounds = int(player.get("_map_boss_rounds") or 0)
    pct = 100 * boss["hp"] // boss["max_hp"]
    print(f"       STR {strength:>3} HP {hp:>5} CON {con:>3} blocks {blocks:>2} "
          f"E{echo}: {result:<8} rounds={rounds:<3} boss_left={pct}%")
    return result, rounds


print("=" * 70)
print("  Noon starts (blocks = 10)")
print("=" * 70)
for label, strength, hp, con in BANDS:
    for echo in (0, 1):
        result, rounds = run(strength, hp, con, echo, 10)
        check(f"{label} E{echo}: fight resolves", result in ("victory", "fled",
                                                             "dead"), result)
        check(f"{label} E{echo}: 2–30 rounds", 2 <= rounds <= 30, str(rounds))

print()
print("=" * 70)
print("  Night starts (blocks = 16) — more boss actions, same HP")
print("=" * 70)
for label, strength, hp, con in (("geared", 90, 1000, 35),
                                 ("strong", 140, 1600, 40)):
    result, rounds = run(strength, hp, con, 1, 16)
    check(f"night {label} E1: 2–30 rounds", 2 <= rounds <= 30, str(rounds))

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s): {FAILS}")
    sys.exit(1)
print("Arena length is inside the tuning band — see the table above.")
