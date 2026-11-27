"""Enemy attribute scaling — early / mid / late targets and role multipliers.

Every enemy template carries six attributes. Three of them used to *matter*:

    STR — basic-attack and skill damage
    DEX — accuracy, and defence against being dodged
    CON — armor (flat damage reduction)

The other three were authored in the YAML but never exported by
``combat.stats.enemy_stats``, so they were pure flavor:

    WIS — healing (support kits) and anti-dodge (``stats.get_dodge_chance``)
    LER — how often an enemy reaches for its skill / AoE
    CHA — how often its rider debuff (skill status, racial proc) lands

This module is the single source for:

  1. ``TARGET_STATS`` — the campaign curve (see ``docs/enemy_stat_scaling_design.md``).
  2. ``PHASES`` — the early / mid / late floor bands.
  3. ``target_enemy_stats()`` — what an enemy of a given level *should* look
     like, before race mods. Used by the audit script and authoring docs.
  4. Role multipliers for WIS / LER / CHA (``heal_multiplier`` etc.), consumed
     by ``combat/enemy_skills.py`` and ``combat/enemy_ai.py``.

The curve is a **guideline**, not a runtime override: templates stay
hand-authored, and the audit script (``tests/_diag_enemy_stat_scaling.py``)
reports outliers instead of silently rewriting 600+ enemies.
"""

# ── The six combat attributes ───────────────────────────────────────────────
STAT_KEYS = ("STR", "DEX", "CON", "WIS", "LER", "CHA")

# Growth curve: value(level) = base + growth × level (after race + personal
# mods). Anchored to the existing roster so most enemies already fit:
# L1 ≈ 2/3/2/1/1/1, L40 ≈ 9/6/7/5/4/5, L60 ≈ 12/7/9/6/6/6.
TARGET_STATS = {
    "STR": (2.0, 0.17),
    "DEX": (3.0, 0.07),
    "CON": (2.0, 0.12),
    "WIS": (1.0, 0.12),
    "LER": (1.0, 0.08),
    "CHA": (1.0, 0.09),
}

# Role multipliers applied on top of the level curve. Attackers are the
# baseline; supporters trade muscle for WIS (healing) and LER (cheaper kit).
ROLE_MULTIPLIERS = {
    "attacker": {
        "STR": 1.00, "DEX": 1.00, "CON": 1.00,
        "WIS": 0.80, "LER": 1.00, "CHA": 1.00,
    },
    "supporter": {
        "STR": 0.60, "DEX": 0.85, "CON": 0.90,
        "WIS": 1.50, "LER": 1.25, "CHA": 1.10,
    },
}

# Floor bands. The normal spawn pool at floor F is roughly
# ``F - 6 - F//10 .. F + 3`` (see ``world/dungeon.get_random_enemy_key``),
# so the level column is the pool an actual run sees.
PHASES = (
    {
        "name": "Early",
        "floors": (1, 9),
        "levels": (1, 12),
        "sample_level": 6,
        "summary": "Instinctive AI: basic attacks only, at most a cheap heal.",
    },
    {
        "name": "Mid",
        "floors": (10, 29),
        "levels": (13, 32),
        "sample_level": 21,
        "summary": "Trained → Tactical: single-target skills, then AoE, healers appear.",
    },
    {
        "name": "Late",
        "floors": (30, 60),
        "levels": (33, 60),
        "sample_level": 45,
        "summary": "Calculating AI: full kits, frequent debuffs, 4–5 enemy rooms.",
    },
)

# ── Role-stat → behaviour conversion ────────────────────────────────────────
# Each point of the role stat is worth this much; caps stop a single outlier
# template from turning a heal into a full restore or a debuff into a lock.

HEAL_WIS_PER_POINT = 0.04      # +4% healing per WIS
HEAL_WIS_CAP = 2.00            # at most double (WIS 25)
SKILL_LER_PER_POINT = 0.03     # +3% skill / AoE chance per Learning
SKILL_LER_CAP = 1.35           # at most +35% (LER 12)
DEBUFF_CHA_PER_POINT = 0.04    # +4% rider-debuff chance per Charisma
DEBUFF_CHA_CAP = 1.60          # at most +60% (CHA 15)


def _attr(entity, key):
    """Read a non-negative integer attribute from a dict-like enemy."""
    if not entity:
        return 0
    try:
        value = int(entity.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _multiplier(entity, stat_key, per_point, cap):
    return min(cap, 1.0 + _attr(entity, stat_key) * per_point)


def heal_multiplier(enemy):
    """WIS scaling for an enemy's heal actions (supporters)."""
    return _multiplier(enemy, "wis_mod", HEAL_WIS_PER_POINT, HEAL_WIS_CAP)


def skill_multiplier(enemy):
    """Learning scaling for skill / AoE selection chance."""
    return _multiplier(enemy, "ler_mod", SKILL_LER_PER_POINT, SKILL_LER_CAP)


def debuff_multiplier(enemy):
    """Charisma scaling for rider-debuff and racial-proc chance."""
    return _multiplier(enemy, "cha_mod", DEBUFF_CHA_PER_POINT, DEBUFF_CHA_CAP)


def debuff_chance(enemy, base_chance):
    """Apply CHA to a base debuff/proc chance, clamp to a sane 0–0.90."""
    try:
        base = float(base_chance)
    except (TypeError, ValueError):
        base = 0.0
    return max(0.0, min(0.90, base * debuff_multiplier(enemy)))


# ── Target curve helpers ────────────────────────────────────────────────────

def phase_for_level(level):
    """Return the PHASES entry that covers *level* (clamped at both ends)."""
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 1
    if level <= PHASES[0]["levels"][1]:
        return PHASES[0]
    for phase in PHASES[1:]:
        if level <= phase["levels"][1]:
            return phase
    return PHASES[-1]


def phase_for_floor(floor):
    """Return the PHASES entry that covers *floor* (clamped at both ends)."""
    try:
        floor = int(floor)
    except (TypeError, ValueError):
        floor = 1
    for phase in PHASES:
        if floor <= phase["floors"][1]:
            return phase
    return PHASES[-1]


def target_enemy_stats(level, role="attacker"):
    """Target attributes for an enemy of *level* (post race mods, pre time).

    Returns ``{"STR": int, "DEX": int, "CON": int, "WIS": int, "LER": int,
    "CHA": int}``. Used by the audit script and the design doc; it is not
    applied automatically because templates are hand-authored.
    """
    try:
        level = max(1, int(level))
    except (TypeError, ValueError):
        level = 1
    mult = ROLE_MULTIPLIERS.get(role, ROLE_MULTIPLIERS["attacker"])
    values = {}
    for key in STAT_KEYS:
        base, growth = TARGET_STATS[key]
        values[key] = max(1, int(round((base + growth * level) * mult[key])))
    return values


def target_band_table():
    """``{role: {phase_name: {stat: value}}}`` at each phase's sample level."""
    table = {}
    for role in ROLE_MULTIPLIERS:
        table[role] = {
            phase["name"]: target_enemy_stats(phase["sample_level"], role)
            for phase in PHASES
        }
    return table
