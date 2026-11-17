"""Combat package — lazy public exports.

``pandemonium.combat`` used to import the whole engine (every superboss, the
status system, the HUD) as soon as *any* combat submodule was imported. That
made the package a hub in the import graph and forced dozens of function-local
imports elsewhere to break cycles.

Exports are resolved on first access instead (PEP 562), so
``from pandemonium.combat import status_effects`` or
``from pandemonium.combat import combat`` still work, but importing e.g.
``pandemonium.combat.stats`` no longer drags in the superbosses.
"""
from importlib import import_module

# public name -> submodule it lives in
_EXPORTS = {
    "combat": ".combat_engine",
    "enemy_stats": ".stats",
    "compute_player_stats": ".stats",
    "combat_broodmother": ".superboss.broodmother",
    "combat_slitcurrent": ".superboss.slitcurrent",
    "combat_ignis": ".superboss.ignis",
    "combat_sylvana": ".superboss.sylvana",
    "combat_rientrante": ".superboss.rientrante",
    "apply_poison": ".status_effects",
    "apply_curse": ".status_effects",
    "cure_curse": ".status_effects",
    "superboss_triple_action_loop": ".superboss.superboss_common",
    "superboss_combat_loop": ".superboss.superboss_common",
    "combat_io": ".combat_io",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    target = _EXPORTS.get(name)
    if target is not None:
        return getattr(import_module(target, __name__), name)
    # Allow `from pandemonium.combat import <submodule>` for any submodule.
    try:
        return import_module(f".{name}", __name__)
    except ModuleNotFoundError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
