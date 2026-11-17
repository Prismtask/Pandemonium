"""Remove function-local imports that duplicate a module-level import.

A function-local import binds its name for the *whole* function, shadowing the
module-level import. If the same import exists at module level, the local copy
is redundant and can make earlier uses raise UnboundLocalError.

Usage:
    python scripts/remove_redundant_local_imports.py            # dry run
    python scripts/remove_redundant_local_imports.py --apply    # rewrite
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def import_key(node: ast.Import | ast.ImportFrom) -> tuple:
    if isinstance(node, ast.ImportFrom):
        return ("from", node.level or 0, node.module or "",
                tuple(sorted((a.name, a.asname) for a in node.names)))
    return ("import", 0, "", tuple(sorted((a.name, a.asname) for a in node.names)))


def names_of(node: ast.Import | ast.ImportFrom) -> set[str]:
    return {a.asname or a.name.split(".")[0] for a in node.names}


def sole_statement_parent(tree: ast.Module) -> set[ast.AST]:
    """Import nodes that are the only statement in their block."""
    sole: set[ast.AST] = set()
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            seq = getattr(node, field, None)
            if isinstance(seq, list) and len(seq) == 1 \
                    and isinstance(seq[0], (ast.Import, ast.ImportFrom)):
                sole.add(seq[0])
        handlers = getattr(node, "handlers", None)
        if handlers:
            for handler in handlers:
                if len(handler.body) == 1 and isinstance(
                        handler.body[0], (ast.Import, ast.ImportFrom)):
                    sole.add(handler.body[0])
    return sole


def process(path: Path, apply: bool) -> list[str]:
    src = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(src)

    module_keys: dict[str, tuple] = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            key = import_key(stmt)
            for name in names_of(stmt):
                module_keys.setdefault(name, key)

    sole = sole_statement_parent(tree)
    removals: list[tuple[int, int]] = []

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node in sole:
                continue
            key = import_key(node)
            names = names_of(node)
            if names and all(module_keys.get(n) == key for n in names):
                removals.append((node.lineno, node.end_lineno))

    if not removals:
        return []
    notes = [f"{path}: remove {len(removals)} redundant local import(s)"]
    if not apply:
        return notes

    drop = set()
    for start, end in removals:
        drop.update(range(start, end + 1))
    lines = [ln for i, ln in enumerate(src.splitlines(), start=1) if i not in drop]
    new_src = "\n".join(lines)
    if src.endswith("\n"):
        new_src += "\n"
    ast.parse(new_src)
    path.write_text(new_src, encoding="utf-8")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    paths = sorted((ROOT / "pandemonium").rglob("*.py"))
    paths += sorted((ROOT / "tests").rglob("*.py"))
    total = 0
    for path in paths:
        for note in process(path, args.apply):
            print(note)
            total += 1
    print(f"\n{total} file(s) affected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
