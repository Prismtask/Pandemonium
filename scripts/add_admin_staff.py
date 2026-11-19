"""Inject the Admin Staff dev weapon into a save file.

Usage:
    python scripts/add_admin_staff.py                 # save slot 1, equipped
    python scripts/add_admin_staff.py 2               # save slot 2, equipped
    python scripts/add_admin_staff.py --path savefile/savegame_3.json
    python scripts/add_admin_staff.py 2 --inventory-only
    python scripts/add_admin_staff.py 2 --dry-run

The Admin Staff is a development-only weapon: every basic attack hits every
enemy for a flat 999999 damage, and damaging skills follow up with an AoE
burst. It never appears in shops or loot. This script only rewrites the JSON
save file; it never launches the game.

Safe to re-run: an existing Admin Staff is reused instead of duplicated. The
weapon previously in the equipped slot is moved into the inventory so it is
not lost. A timestamped backup is written unless --no-backup is given.
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
from pandemonium.resources.items import build_item  # noqa: E402

ADMIN_STAFF_ID = "admin_staff"


def _staff_instance():
    """Build a current Admin Staff instance from the item registry."""
    item = build_item(ADMIN_STAFF_ID, "unique")
    item.setdefault("count", 1)
    return item


def _find_staff(items):
    for item in items:
        if isinstance(item, dict) and item.get("id") == ADMIN_STAFF_ID:
            return item
    return None


def inject_admin_staff(player, equip=True):
    """Add (or equip) the Admin Staff in a loaded player dict.

    Returns ``(description, changed)`` where ``changed`` is False when the
    save already had the requested state.
    """
    equipped = player.setdefault("equipped", {})
    inventory = player.setdefault("inventory", [])
    weapon = equipped.get("weapon")

    if isinstance(weapon, dict) and weapon.get("id") == ADMIN_STAFF_ID:
        return "already equipped - nothing to do", False

    staff = _find_staff(inventory)

    if not equip:
        if staff:
            return "already in inventory - nothing to do", False
        inventory.append(_staff_instance())
        return "added to inventory", True

    if staff:
        inventory.remove(staff)
        suffix = " (reused inventory copy)"
    else:
        staff = _staff_instance()
        suffix = ""

    if isinstance(weapon, dict):
        inventory.append(weapon)

    equipped["weapon"] = staff
    return f"equipped{suffix}", True


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slot", nargs="?", type=int, default=1,
                        help="save slot number (default: 1)")
    parser.add_argument("--path", type=Path,
                        help="explicit save JSON path (overrides the slot)")
    parser.add_argument("--inventory-only", action="store_true",
                        help="put the staff in the inventory instead of equipping it")
    parser.add_argument("--no-backup", action="store_true",
                        help="do not write a timestamped backup before saving")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would change without writing the file")
    args = parser.parse_args(argv)

    path = args.path.expanduser().resolve() if args.path else Path(get_filename(args.slot))
    if not path.exists():
        parser.error(f"save file not found: {path}")

    try:
        player = _load(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(f"cannot read {path}: {exc}")

    action, changed = inject_admin_staff(player, equip=not args.inventory_only)
    print(f"{path}: {action}")

    if not changed:
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
