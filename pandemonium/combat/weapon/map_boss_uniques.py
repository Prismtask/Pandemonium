"""
combat/weapon/map_boss_uniques.py — the Warden of the Long Day's four uniques.

Docs: `docs/map_boss_design.md` §9. Every effect is **actor-based** (the
unique-equipment convention): it works identically on the player and on any
ally, and never hardcodes the player dict.

| Item | Slot | Effect |
|---|---|---|
| Warden's Signet | accessory | +8% damage at Noon, +16% at Night (0% in the Morning) |
| Long Day's Edge | sword | +3% damage per combat round (max +30%), reset when the phase turns to Morning |
| Echo Mantle | armor | −12% damage taken (−20% at Night) via a sourced `defense_pct` buff |
| Sundial Crown | accessory | once per day, survive a fatal blow at 1 HP and clear every debuff |

The phase is read from the arena's **projected clock**
(``actor["_map_boss_clock_blocks"]``) when it is mirrored, otherwise from the
real block clock — so the Signet and the Edge also behave sensibly outside the
arena (they just follow the day the way everything else does).

Lifecycle (mirrors Moonlight Greatsword):
  * ``begin_map_boss_uniques(player)`` — combat start (both engines)
  * ``tick_long_day(actor)`` — end of round (both engines)
  * ``clear_map_boss_unique_state(actor)`` — battle end / defensive scrub
  * ``sync_party_phase(player)`` — arena phase change (allies mirror the clock)
"""

from pandemonium.combat.combat_io import c_print
from pandemonium.core.time_blocks import get_day_phase

# ── Tunables (docs/map_boss_design.md §9) ──────────────────────────────────
SIGNET_SPECIAL = "long_day_signet"
LONG_DAY_SPECIAL = "long_day_blade"
ECHO_MANTLE_SPECIAL = "echo_mantle"
SUNDIAL_SPECIAL = "sundial_crown"

SIGNET_NOON_BONUS = 0.08
SIGNET_NIGHT_BONUS = 0.16

LONG_DAY_PER_ROUND = 0.03
LONG_DAY_STACK_CAP = 10

ECHO_MANTLE_BASE = 0.12
ECHO_MANTLE_NIGHT = 0.20
ECHO_MANTLE_SOURCE = "echo_mantle"

SUNDIAL_DEBUFF_FLAGS = ("slowed", "blinded", "silenced", "dreaded", "cursed",
                        "stunned")


# ── Equipped checks ───────────────────────────────────────────────────────

def _accessory_specials(actor):
    equipment = actor.get("equipped") or {}
    if not isinstance(equipment, dict):
        return ()
    specials = []
    for slot in ("accessory1", "accessory2", "accessory"):
        item = equipment.get(slot)
        if item and item.get("special"):
            specials.append(item["special"])
    return tuple(specials)


def actor_has_warden_signet(actor):
    return SIGNET_SPECIAL in _accessory_specials(actor)


def actor_has_sundial_crown(actor):
    return SUNDIAL_SPECIAL in _accessory_specials(actor)


def actor_has_echo_mantle(actor):
    equipment = actor.get("equipped") or {}
    if not isinstance(equipment, dict):
        return False
    armor = equipment.get("armor")
    return bool(armor and armor.get("special") == ECHO_MANTLE_SPECIAL)


def actor_has_long_day_edge(actor):
    equipment = actor.get("equipped") or {}
    if not isinstance(equipment, dict):
        return False
    weapon = equipment.get("weapon")
    return bool(weapon and weapon.get("special") == LONG_DAY_SPECIAL)


# ── Phase ─────────────────────────────────────────────────────────────────

def actor_phase(actor):
    """'morning' | 'noon' | 'night' — projected arena clock first."""
    blocks = actor.get("_map_boss_clock_blocks")
    if blocks is None:
        return get_day_phase(actor)
    try:
        return get_day_phase(int(blocks) % 24)
    except (TypeError, ValueError):
        return get_day_phase(actor)


def sync_party_phase(player):
    """Mirror the arena clock onto allies and refresh the Echo Mantle.

    Called by the arena whenever its projected clock advances, so an ally
    wearing these uniques reads the same phase as the player.
    """
    clock = player.get("_map_boss_clock_blocks")
    day = player.get("day")
    for actor in [player] + list(player.get("allies", [])):
        if clock is not None:
            actor["_map_boss_clock_blocks"] = clock
        if day is not None:
            actor["day"] = day
        refresh_echo_mantle(actor)


def begin_map_boss_uniques(player):
    """Combat start: reset round stacks, mirror context, arm the Echo Mantle."""
    for actor in [player] + list(player.get("allies", [])):
        actor["long_day_stacks"] = 0
        actor.pop("long_day_phase", None)
        actor.setdefault("day", player.get("day", 1))
        refresh_echo_mantle(actor)


def clear_map_boss_unique_state(actor):
    """Battle-scoped cleanup (stack state + the mantle's ward).

    ``sundial_used_day`` deliberately survives: the crown recharges with the
    calendar, not with the encounter.
    """
    actor["long_day_stacks"] = 0
    actor.pop("long_day_phase", None)
    if actor.get("active_buffs"):
        actor["active_buffs"] = [
            b for b in actor["active_buffs"]
            if b.get("source") != ECHO_MANTLE_SOURCE
        ]


# ── Damage dealt: Signet + Long Day's Edge ────────────────────────────────

def signet_bonus(actor):
    """Phase damage bonus from the Warden's Signet (0.0 when not worn)."""
    if not actor_has_warden_signet(actor):
        return 0.0
    phase = actor_phase(actor)
    if phase == "noon":
        return SIGNET_NOON_BONUS
    if phase == "night":
        return SIGNET_NIGHT_BONUS
    return 0.0


def long_day_bonus(actor):
    """Round-stack damage bonus from Long Day's Edge (0.0 when not worn)."""
    if not actor_has_long_day_edge(actor):
        return 0.0
    stacks = int(actor.get("long_day_stacks", 0) or 0)
    return min(LONG_DAY_STACK_CAP, max(0, stacks)) * LONG_DAY_PER_ROUND


def apply_long_day_damage(actor, dmg):
    """Add the Signet phase bonus and the Edge round stacks to one hit.

    Called from all four damage paths (player/ally × basic/skill).
    """
    bonus = signet_bonus(actor) + long_day_bonus(actor)
    if bonus <= 0 or dmg <= 0:
        return dmg
    return max(0, int(dmg * (1.0 + bonus)))


def tick_long_day(actor):
    """End of round: +1 stack, and reset when the phase turns to Morning."""
    if not actor_has_long_day_edge(actor):
        return
    phase = actor_phase(actor)
    previous = actor.get("long_day_phase")
    if previous is not None and previous != "morning" and phase == "morning":
        if int(actor.get("long_day_stacks", 0) or 0) > 0:
            c_print("  \u23f3 Dawn empties Long Day's Edge \u2014 its stacks "
                    "reset.")
        actor["long_day_stacks"] = 0
    actor["long_day_phase"] = phase
    stacks = min(LONG_DAY_STACK_CAP,
                 int(actor.get("long_day_stacks", 0) or 0) + 1)
    actor["long_day_stacks"] = stacks
    if stacks == LONG_DAY_STACK_CAP:
        name = "Your" if not actor.get("is_ally") else f"{actor.get('name', 'Their')}'s"
        c_print(f"  \u23f3 {name} Long Day's Edge is fully charged "
                f"(+{int(LONG_DAY_PER_ROUND * LONG_DAY_STACK_CAP * 100)}% damage).")


# ── Damage taken: Echo Mantle ─────────────────────────────────────────────

def refresh_echo_mantle(actor):
    """(Re)apply the Echo Mantle's sourced percentage damage reduction."""
    if not actor.get("active_buffs") and not actor_has_echo_mantle(actor):
        return
    actor["active_buffs"] = [
        b for b in actor.get("active_buffs", [])
        if b.get("source") != ECHO_MANTLE_SOURCE
    ]
    if not actor_has_echo_mantle(actor):
        return
    value = (ECHO_MANTLE_NIGHT if actor_phase(actor) == "night"
             else ECHO_MANTLE_BASE)
    actor["active_buffs"].append({
        "type": "defense_pct",
        "value": value,
        "remaining": 999,
        "source": ECHO_MANTLE_SOURCE,
    })


# ── Fatal survival: Sundial Crown ─────────────────────────────────────────

def try_sundial_crown_save(actor):
    """Once per day: survive a lethal blow at 1 HP and clear every debuff."""
    if not actor_has_sundial_crown(actor):
        return False
    try:
        today = int(actor.get("day", 0) or 0)
        used = int(actor.get("sundial_used_day", -1) or -1)
    except (TypeError, ValueError):
        today, used = 0, -1
    if used == today:
        return False

    actor["sundial_used_day"] = today
    actor["current_hp"] = max(1, 1)

    cleared = []
    remaining = []
    for debuff in actor.get("active_debuffs", []):
        if debuff.get("permanent") or debuff.get("_uncleansable"):
            remaining.append(debuff)
        else:
            cleared.append(debuff.get("type", "?"))
    actor["active_debuffs"] = remaining
    for flag in SUNDIAL_DEBUFF_FLAGS:
        actor[flag] = False

    if actor.get("is_ally"):
        owner, pronoun = f"{actor.get('name', 'An ally')}'s", "they"
    else:
        owner, pronoun = "Your", "you"
    c_print("  \U0001F551 " + "~*~ " * 12)
    c_print(f"  {owner} Sundial Crown turns the hour back \u2014 "
            f"{pronoun} survive at 1 HP!")
    if cleared:
        c_print("  Every debuff falls away with the stolen hour.")
    c_print("  \U0001F551 " + "~*~ " * 12)
    return True
