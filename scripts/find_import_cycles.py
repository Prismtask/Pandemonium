"""Find circular imports introduced by hoisting local imports.

Compares the eager (module-level) import graph of the working tree with the
HEAD graph, computes strongly connected components, and lists the edges that
were function-local in HEAD (i.e. the existing cycle breakers). Reverting
those specific edges restores acyclic imports while keeping everything else
at module level.

Usage:
    python scripts/find_import_cycles.py
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_head(path: Path) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    try:
        return subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imports_from_source(source: str, top_level: bool) -> set[tuple[str, str, str]]:
    """Return {(kind, module, names)} for imports at top level or in functions."""
    tree = ast.parse(source.lstrip("\ufeff"))
    edges: set[tuple[str, str, str]] = set()

    def walk(node: ast.AST, depth_in_func: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, True)
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                if top_level == depth_in_func:
                    continue  # function imports in top-level pass, or vice versa
                names = ",".join(sorted(a.name for a in child.names))
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        module = alias.name
                        if module.startswith("pandemonium"):
                            edges.add(("import", module, alias.asname or "*"))
                elif isinstance(child, ast.ImportFrom):
                    if child.level:
                        continue
                    if child.module and child.module.startswith("pandemonium"):
                        edges.add(("from", child.module, names))
            walk(child, depth_in_func)

    walk(tree, False)
    return edges


def parents_of(module: str) -> list[str]:
    parts = module.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def main() -> int:
    paths = sorted((ROOT / "pandemonium").rglob("*.py"))
    modules = {module_name(p): p for p in paths}

    current_eager: dict[str, set[str]] = {m: set() for m in modules}
    head_eager: dict[str, set[str]] = {m: set() for m in modules}
    head_lazy: dict[str, set[str]] = {m: set() for m in modules}

    for name, path in modules.items():
        cur_src = path.read_text(encoding="utf-8-sig")
        for _, target, _names in imports_from_source(cur_src, top_level=True):
            targets = {target}
            if target.endswith(".*"):
                targets = {target[:-2]}
            for t in targets | set(parents_of(target)):
                if t in modules:
                    current_eager[name].add(t)
        head_src = read_head(path)
        if head_src:
            for _, target, _names in imports_from_source(head_src, top_level=True):
                for t in {target} | set(parents_of(target)):
                    if t in modules:
                        head_eager[name].add(t)
            for _, target, _names in imports_from_source(head_src, top_level=False):
                for t in {target} | set(parents_of(target)):
                    if t in modules:
                        head_lazy[name].add(t)

    # Tarjan SCC over eager graph.
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
        for w in sorted(current_eager[v]):
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
                sccs.append(sorted(comp))

    sys.setrecursionlimit(10000)
    for m in sorted(modules):
        if m not in indices:
            strongconnect(m)

    print(f"{len(sccs)} circular import group(s):\n")
    revertable = set()
    for comp in sccs:
        print("  group:", ", ".join(comp))
        for m in comp:
            for target in sorted(current_eager[m]):
                if target in comp and target in head_lazy[m]:
                    revertable.add((m, target))
        print()
    if revertable:
        print("Edges that were function-local in HEAD (restore as local imports):")
        for m, t in sorted(revertable):
            print(f"  {m} -> {t}")
    else:
        print("No previously-lazy edges inside cycles were found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
