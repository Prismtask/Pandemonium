"""Inject a temperate PDG-demo wild ruin into a save file.

Usage:
    python scripts/spawn_pdg_demo.py                 # save slot 1, 2 floors
    python scripts/spawn_pdg_demo.py 2               # save slot 2
    python scripts/spawn_pdg_demo.py --path savefile/savegame_3.json
    python scripts/spawn_pdg_demo.py 1 --floors 3
    python scripts/spawn_pdg_demo.py 1 --dry-run

The ruin is a normal wild dungeon record with ``pdg_demo`` set. Travel to it
from the world map: its DungeonScreen Map tab renders the 8x8 graph, and
movement uses the existing button panel. A timestamped backup is written
unless --no-backup is given.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pandemonium.core.save_load import get_filename  # noqa: E402
from pandemonium.resources.cities import CITIES  # noqa: E402
import pandemonium.world.wild_dungeons as wild_dungeons  # noqa: E402


def _load(path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("save file does not contain a player object")
    return data


def _write(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def _backup(path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(f"{path.stem}.backup_{stamp}{path.suffix}")
    shutil.copy2(path, target)
    return target


def _temperate_seed_city(player):
    available = wild_dungeons._available_seed_cities(player)
    for city_id in sorted(available):
        if CITIES.get(city_id, {}).get("biome") == "temperate":
            return city_id
    return None


def spawn_demo(player, floors=2, level=None):
    """Add one temperate PDG-demo ruin. Returns ``(dungeon, message)``."""
    state = wild_dungeons.ensure_wild_dungeon_state(player)
    wild_dungeons.expire_dungeons(player)
    for dungeon in state["active"]:
        if dungeon.get("pdg_demo"):
            return dungeon, "a PDG demo ruin is already active"

    seed_city = _temperate_seed_city(player)
    if seed_city is None:
        raise ValueError("no accessible temperate city can seed a ruin")

    taken = [tuple(dungeon.get("position", (0, 0)))
             for dungeon in state["active"]]
    dungeon = wild_dungeons._spawn_one(
        player,
        state,
        seed_city,
        taken,
        available_cities=wild_dungeons._available_seed_cities(player),
        reserved=wild_dungeons._reserved_sites(player),
    )
    dungeon["biome"] = "temperate"
    dungeon["pdg_demo"] = True
    if level is not None:
        dungeon["level"] = max(1, min(80, int(level)))
    if floors:
        dungeon["total_floors"] = max(1, int(floors))
    dungeon["reward_pool"] = wild_dungeons.generate_reward_pool(
        dungeon["level"], dungeon["total_floors"], "temperate")
    state["active"].append(dungeon)
    return dungeon, "added"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slot", nargs="?", type=int, default=1,
                        help="save slot number (default: 1)")
    parser.add_argument("--path", type=Path,
                        help="explicit save JSON path (overrides the slot)")
    parser.add_argument("--floors", type=int, default=2,
                        help="demo floors (default: 2)")
    parser.add_argument("--level", type=int, default=None,
                        help="override the ruin level (1-80)")
    parser.add_argument("--no-backup", action="store_true",
                        help="do not write a timestamped backup")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would change without writing the file")
    args = parser.parse_args(argv)

    path = args.path.expanduser().resolve() if args.path else Path(
        get_filename(args.slot))
    if not path.exists():
        parser.error(f"save file not found: {path}")

    try:
        player = _load(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(f"cannot read {path}: {exc}")

    try:
        dungeon, message = spawn_demo(
            player, floors=args.floors, level=args.level)
    except ValueError as exc:
        parser.error(str(exc))

    nearest = dungeon.get("nearest_city", "?")
    nearest_name = CITIES.get(nearest, {}).get("name", nearest)
    print(f"{path}: {message}")
    print(f"  {dungeon.get('name')} — Lv {dungeon.get('level')} · "
          f"{dungeon.get('total_floors')} floors · "
          f"{dungeon.get('biome')} PDG profile")
    print(f"  nearest city: {nearest_name}")
    print("  Open the world map and travel to the ruin; the current dungeon "
          "screen's Map tab shows the graph.")

    if message != "added":
        return 0
    if args.dry_run:
        print("dry run - file left unchanged")
        return 0
    if not args.no_backup:
        backup = _backup(path)
        print(f"backup: {backup}")
    _write(path, player)
    print("save written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
