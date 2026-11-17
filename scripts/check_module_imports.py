"""Import every module in a fresh interpreter and report failures.

Circular imports only fail when a module is imported *first*, so a normal test
run can miss them. This checker spawns one subprocess per module, making the
module the entry point of its own import graph.

Usage:
    python scripts/check_module_imports.py [--include-tests]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 8


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-tests", action="store_true",
                        help="also check tests/ modules")
    args = parser.parse_args()

    paths = sorted((ROOT / "pandemonium").rglob("*.py")) + sorted(ROOT.glob("*.py"))
    if args.include_tests:
        paths += sorted((ROOT / "tests").rglob("*.py"))

    names = []
    for path in paths:
        if path.name in {"launcher.py", "make_exe.py"} and path.parent == ROOT:
            continue  # covered indirectly via pandemonium imports
        name = module_name(path)
        if name == "pandemonium.__main__":
            continue  # convenience alias, same graph as gui.app
        if name and name not in names:
            names.append(name)

    def check(name: str) -> tuple[str, str | None]:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", f"import {name}"],
                cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return name, f"TIMEOUT after {TIMEOUT}s"
        if proc.returncode != 0:
            tail = (proc.stderr.strip().splitlines() or [""])[-1]
            return name, tail
        return name, None

    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, error in pool.map(check, names):
            if error:
                failures[name] = error
                print(f"FAIL {name}: {error}")

    print(f"\n{len(names) - len(failures)}/{len(names)} modules import cleanly")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
