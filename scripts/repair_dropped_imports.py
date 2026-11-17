"""Repair function-local imports that were dropped during hoisting.

An early version of ``hoist_imports.py`` recorded a local import for deletion
before checking for signature conflicts, so conflicting imports were removed
without being re-added at module level. This script walks each file's HEAD
version, finds function-local imports whose bound names are no longer bound in
the current file, and restores them at the top of the same function.

Usage:
    python scripts/repair_dropped_imports.py            # dry run
    python scripts/repair_dropped_imports.py --apply    # rewrite files
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fix_import_cycles import (  # noqa: E402
    function_map,
    local_imports_by_function,
)
from find_import_cycles import ROOT, read_head  # noqa: E402


def bound_names(node: ast.Import | ast.ImportFrom) -> set[str]:
    out = set()
    for alias in node.names:
        out.add(alias.asname or alias.name.split(".")[0])
    return out


def module_bindings(tree: ast.Module) -> set[str]:
    """Names bound by module-level imports."""
    out: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            out |= bound_names(stmt)
    return out


def function_bindings(tree: ast.Module) -> dict[str, set[str]]:
    """qname -> names bound by imports inside that function (any depth)."""
    out: dict[str, set[str]] = {}
    for qname, node in local_imports_by_function(tree):
        out.setdefault(qname, set()).update(bound_names(node))
    return out


def other_uses_at_module_level(tree: ast.Module, names: set[str]) -> set[str]:
    """Names also used outside functions at module level (constants etc.)."""
    used: set[str] = set()

    def visit(node: ast.AST, in_func: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, True)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) \
                    and not in_func and child.id in names:
                used.add(child.id)
                visit(child, in_func)
            else:
                visit(child, in_func)

    visit(tree, False)
    return used


def process(path: Path, apply: bool) -> list[str]:
    cur_src = path.read_text(encoding="utf-8-sig")
    head_src = read_head(path)
    if head_src is None:
        return []
    cur_tree = ast.parse(cur_src)
    head_tree = ast.parse(head_src.lstrip("\ufeff"))

    top_names = module_bindings(cur_tree)
    func_names = function_bindings(cur_tree)
    cur_funcs = function_map(cur_tree)
    head_locals = local_imports_by_function(head_tree)

    insertions: list[tuple[str, int, int, str]] = []  # (qname, anchor, seq, text)
    seen: set[tuple[str, tuple]] = set()

    for qname, node in head_locals:
        names = bound_names(node)
        if names <= top_names:
            continue  # still available at module level
        if names <= func_names.get(qname, set()):
            continue  # still available in the same function
        func = cur_funcs.get(qname)
        if func is None:
            continue
        sig = tuple(sorted((a.name, a.asname) for a in node.names))
        key = (qname, (isinstance(node, ast.ImportFrom), node.module if isinstance(
            node, ast.ImportFrom) else "", sig))
        if key in seen:
            continue
        seen.add(key)

        text = ast.get_source_segment(head_src, node) or ""
        body = func.body
        anchor = body[0].lineno
        if body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            anchor = body[0].end_lineno + 1
        raw_lines = text.splitlines()
        first_indent = len(raw_lines[0]) - len(raw_lines[0].lstrip())
        indent = " " * (func.col_offset + 4)
        stmt_text = "\n".join(
            indent + (ln[first_indent:] if ln[:first_indent].strip() == "" else ln.lstrip())
            for ln in raw_lines
        )
        insertions.append((qname, anchor, node.lineno, stmt_text))

    if not insertions:
        return []
    notes = [f"{path}: restoring {len(insertions)} dropped import(s)"]
    for qname, *_ in insertions:
        notes.append(f"    {qname}")
    if not apply:
        return notes

    lines = cur_src.splitlines()
    for _qname, anchor, _seq, text in sorted(insertions, key=lambda t: (t[1], t[2]),
                                             reverse=True):
        idx = max(0, anchor - 1)
        lines[idx:idx] = text.splitlines()
    new_src = "\n".join(lines)
    if cur_src.endswith("\n"):
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
    paths += sorted(ROOT.glob("*.py"))
    total = 0
    for path in paths:
        if path.name == "__init__.py" and path.parent == ROOT / "pandemonium":
            continue
        if path.name in {"launcher.py", "make_exe.py"}:
            continue  # never contained function-local imports
        for note in process(path, args.apply):
            print(note)
            total += 1
    print(f"\n{total} note(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
