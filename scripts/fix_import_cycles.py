"""Restore cycle-breaking imports as function-local imports.

Uses the SCC analysis from ``find_import_cycles``: any module-level import that
(a) closes a cycle and (b) was function-local in HEAD is moved back into the
top of the same function(s) that imported it originally.

Rationale: this codebase deliberately keeps some imports lazy to avoid circular
imports (see docs/conventions). Everything else stays hoisted at module level.

Usage:
    python scripts/fix_import_cycles.py            # dry run
    python scripts/fix_import_cycles.py --apply    # rewrite files
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from find_import_cycles import (  # noqa: E402
    ROOT,
    imports_from_source,
    module_name,
    parents_of,
    read_head,
)


def sig_of(node: ast.Import | ast.ImportFrom) -> tuple:
    names = tuple(sorted((a.name, a.asname) for a in node.names))
    if isinstance(node, ast.ImportFrom):
        return ("from", node.level or 0, node.module or "", names)
    return ("import", 0, "", names)


def target_of(node: ast.Import | ast.ImportFrom, alias: ast.alias | None = None) -> str:
    if isinstance(node, ast.Import):
        return alias.name if alias else node.names[0].name
    return node.module or ""


def function_map(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{prefix}.{child.name}" if prefix else child.name
                out.setdefault(qname, child)
                walk(child, qname)
            elif not isinstance(child, (ast.Import, ast.ImportFrom)):
                walk(child, prefix)

    walk(tree, "")
    return out


def local_imports_by_function(tree: ast.Module) -> list[tuple[str, ast.Import | ast.ImportFrom]]:
    """(function qualname, import node) for every import inside a function."""
    out: list[tuple[str, ast.Import | ast.ImportFrom]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{prefix}.{child.name}" if prefix else child.name
                collect(child, qname)
                walk(child, qname)
            else:
                walk(child, prefix)

    def collect(func: ast.AST, qname: str) -> None:
        def inner(node: ast.AST) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue  # handled by outer walk
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    out.append((qname, child))
                inner(child)

        inner(func)

    walk(tree, "")
    return out


def top_level_imports(tree: ast.Module) -> dict[tuple, tuple[int, int]]:
    out: dict[tuple, tuple[int, int]] = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            out.setdefault(sig_of(stmt), (stmt.lineno, stmt.end_lineno))
    return out


def compute_cycle_edges(current_eager: dict[str, set[str]],
                        head_lazy: dict[str, set[str]]) -> set[tuple[str, str]]:
    index_counter = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index_counter
        indices[v] = low[v] = index_counter
        index_counter += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(current_eager.get(v, ())):
            if w not in indices:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(comp)

    sys.setrecursionlimit(10000)
    for m in sorted(current_eager):
        if m not in indices:
            strongconnect(m)

    revertable: set[tuple[str, str]] = set()
    for comp in sccs:
        members = set(comp)
        for m in comp:
            for target in current_eager[m]:
                if target in members and target in head_lazy.get(m, set()):
                    revertable.add((m, target))
    return revertable


def process(path: Path, revert_targets: set[str], apply: bool) -> list[str]:
    notes: list[str] = []
    cur_src = path.read_text(encoding="utf-8-sig")
    head_src = read_head(path)
    if head_src is None:
        return notes
    cur_tree = ast.parse(cur_src)
    head_tree = ast.parse(head_src)

    head_top_sigs = set(top_level_imports(head_tree))
    cur_top = top_level_imports(cur_tree)
    head_locals = local_imports_by_function(head_tree)
    cur_funcs = function_map(cur_tree)
    cur_lines = cur_src.splitlines()

    removals: list[tuple[int, int]] = []
    insertions: list[tuple[int, int, str]] = []  # (anchor_line, seq, text)
    seen: set[tuple[str, tuple]] = set()

    for qname, node in head_locals:
        target = target_of(node)
        if target not in revert_targets:
            continue
        sig = sig_of(node)
        if sig in head_top_sigs:
            continue  # was also eager in HEAD — keep it at module level
        if sig not in cur_top:
            continue  # hoister already left it local (clash/try/etc.)
        func = cur_funcs.get(qname)
        if func is None:
            notes.append(f"{path}: function {qname} not found; skipped {sig}")
            continue
        key = (qname, sig)
        if key in seen:
            continue
        seen.add(key)

        start, end = cur_top[sig]
        if (start, end) not in removals:
            removals.append((start, end))

        body = func.body
        anchor = body[0].lineno
        text = ast.get_source_segment(head_src, node) or ""
        # Dedent the original statement to 4-space body indent.
        raw_lines = text.splitlines()
        first_indent = len(raw_lines[0]) - len(raw_lines[0].lstrip())
        dedented = [ln[first_indent:] if ln[:first_indent].strip() == "" else ln.lstrip()
                    for ln in raw_lines]
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            anchor = body[0].end_lineno + 1  # after docstring
        # Use the function's body indentation.
        indent = " " * (func.col_offset + 4)
        stmt_text = "\n".join(indent + ln for ln in dedented)
        insertions.append((anchor, node.lineno, stmt_text))

    if not removals and not insertions:
        return notes

    notes.append(f"{path}: restoring {len(seen)} local import(s)")
    if not apply:
        return notes

    drop = set()
    for start, end in removals:
        drop.update(range(start, end + 1))
    lines = [ln for i, ln in enumerate(cur_lines, start=1) if i not in drop]

    # Adjust insertion anchors for removed lines above them.
    adjusted = []
    for anchor, seq, text in insertions:
        shift = sum(1 for i in drop if i < anchor)
        adjusted.append((anchor - shift, seq, text))
    for anchor, _seq, text in sorted(adjusted, key=lambda t: (t[0], t[1]), reverse=True):
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
    modules = {module_name(p): p for p in paths}

    current_eager: dict[str, set[str]] = {m: set() for m in modules}
    head_lazy: dict[str, set[str]] = {m: set() for m in modules}
    for name, path in modules.items():
        cur = path.read_text(encoding="utf-8-sig")
        for _, target, _names in imports_from_source(cur, top_level=True):
            for t in {target} | set(parents_of(target)):
                if t in modules:
                    current_eager[name].add(t)
        head = read_head(path)
        if head:
            for _, target, _names in imports_from_source(head, top_level=False):
                for t in {target} | set(parents_of(target)):
                    if t in modules:
                        head_lazy[name].add(t)

    revertable = compute_cycle_edges(current_eager, head_lazy)
    by_module: dict[str, set[str]] = {}
    for src, target in revertable:
        by_module.setdefault(src, set()).add(target)

    print(f"{len(by_module)} module(s) need local imports restored:")
    for m, targets in sorted(by_module.items()):
        print(f"  {m}: {', '.join(sorted(targets))}")

    total = 0
    for m, targets in sorted(by_module.items()):
        for note in process(modules[m], targets, args.apply):
            print(note)
            total += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
