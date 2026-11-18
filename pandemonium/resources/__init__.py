"""resources — lazy package facade (PEP 562).

This package used to import every data module eagerly. Because a package's
``__init__`` runs before any submodule, even ``from pandemonium.resources.cities
import CITIES`` on the main menu paid for the full enemy book (629 entries),
the item table and the city maps — about 1.6 s of startup.

``__getattr__`` keeps the historical ``from pandemonium.resources import X``
API while loading each data module only when a name from it is first used.
"""
import importlib

_EXPORTS = {
    "EXP_COEFF_A": ".constants",
    "EXP_COEFF_B": ".constants",
    "EXP_POWER": ".constants",
    "RACES": ".races_classes",
    "CLASSES": ".races_classes",
    "ATTRIBUTES": ".races_classes",
    "TOTAL_POINTS": ".races_classes",
    "ENEMY_RACES": ".enemies",
    "ENEMIES": ".enemies",
    "BIOME_RACES": ".enemies",
    "ITEM_RARITY": ".items",
    "ITEMS": ".items",
    "build_item": ".items",
    "upgrade_rarity": ".items",
    "CITIES": ".cities",
    "CITY_MAPS": ".city_maps",
    "get_city_map": ".city_maps",
    "list_city_maps": ".city_maps",
    "get_city_map_by_name": ".city_maps",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value  # cache so later lookups skip __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
