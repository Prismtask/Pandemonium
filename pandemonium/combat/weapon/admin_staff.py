# combat/weapon/admin_staff.py
"""Admin Staff — development-only cheat weapon.

Every basic attack and damaging skill made while this staff is equipped deals
a flat 999999 damage, applied after all other modifiers so the result is exact
and effectively unresistable. The item is flagged unique so it is excluded
from shops, dungeon drops and random equipment rolls; it is meant to be
injected straight into a save file for fast playtesting.

Actor-based like every other weapon effect, so it also works if an ally is
handed a copy for testing.
"""

from pandemonium.combat.helpers import format_damage_msg

ADMIN_STAFF_ID = "admin_staff"
ADMIN_STAFF_DAMAGE = 999999


def actor_has_admin_staff(actor):
    """Return True when *actor* has the Admin Staff equipped as a weapon."""
    if not isinstance(actor, dict):
        return False
    equipped = actor.get("equipped")
    if not isinstance(equipped, dict):
        return False
    weapon = equipped.get("weapon")
    return bool(isinstance(weapon, dict) and weapon.get("id") == ADMIN_STAFF_ID)


def apply_admin_staff_damage(actor, dmg):
    """Force the final damage to ADMIN_STAFF_DAMAGE when the staff is wielded."""
    if not actor_has_admin_staff(actor):
        return dmg
    return ADMIN_STAFF_DAMAGE


def admin_staff_damage_all(actor, enemies, on_hit=None, on_kill=None):
    """Hit every living enemy for ADMIN_STAFF_DAMAGE.

    Returns the combat-log lines produced. ``on_kill`` is only supplied by
    callers that do not post-process kills themselves (basic attacks); the
    skill wrapper lets its caller fire ``on_kill`` for every newly dead enemy.
    """
    source = actor.get("name") or "You"
    targets = [e for e in enemies
               if isinstance(e, dict) and e.get("hp", 0) > 0]
    lines = []
    for target in targets:
        target["hp"] -= ADMIN_STAFF_DAMAGE
        if on_hit:
            on_hit(target, enemies)
        lines.append(format_damage_msg(source, target.get("name", "enemy"),
                                       ADMIN_STAFF_DAMAGE))
    if on_kill:
        for target in targets:
            if target.get("hp", 0) <= 0:
                lines.append(f"{source} defeated {target.get('name', 'enemy')}!")
                on_kill(target, enemies)
    return lines


def admin_staff_skill_aoe(actor, enemies, hp_before):
    """Follow a damaging skill with an AoE burst for the Admin Staff.

    No-op for support skills (no enemy HP changed) and for non-staff actors.
    Returns the extra log lines; the skill caller fires ``on_kill`` itself.
    """
    if not actor_has_admin_staff(actor):
        return []
    dealt_damage = any(
        id(e) in hp_before and e.get("hp", 0) < hp_before[id(e)]
        for e in enemies
    )
    if not dealt_damage:
        return []
    return admin_staff_damage_all(actor, enemies)
