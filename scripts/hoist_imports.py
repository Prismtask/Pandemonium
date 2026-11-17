"""Hoist function-local imports to the top of each module.

Pandemonium convention: every import lives at module level. This tool rewrites
files to follow that convention and reports imports it deliberately leaves in
place (defensive try/except imports, TYPE_CHECKING guards, name conflicts).

Usage:
    python scripts/hoist_imports.py            # dry run: report only
    python scripts/hoist_imports.py --apply    # rewrite files in place

Safety rules (imports are NOT hoisted when):
- inside a try/except block (optional dependency / fallback pattern)
- inside an ``if TYPE_CHECKING`` block
- the import is the only statement in its block (removal would empty it)
- hoisting would shadow or clash with an existing module-level binding
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    [ROOT / "launcher.py", ROOT / "make_exe.py"]
    + sorted((ROOT / "pandemonium").rglob("*.py"))
    + sorted((ROOT / "tests").rglob("*.py"))
    + sorted((ROOT / "scripts").rglob("*.py"))
)


def build_parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def is_type_checking_test(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def import_signature(node: ast.Import | ast.ImportFrom) -> tuple:
    names = tuple(sorted((a.name, a.asname) for a in node.names))
    if isinstance(node, ast.ImportFrom):
        return ("from", node.level or 0, node.module or "", names)
    return ("import", 0, "", names)


def bound_names(node: ast.Import | ast.ImportFrom) -> set[str]:
    out = set()
    for alias in node.names:
        if alias.asname:
            out.add(alias.asname)
        else:
            out.add(alias.name.split(".")[0])
    return out


def module_level_bindings(tree: ast.Module) -> dict[str, str]:
    """Map name -> signature-description for every module-level binding."""
    bindings: dict[str, str] = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            sig = import_signature(stmt)
            for alias in stmt.names:
                name = alias.asname or alias.name.split(".")[0]
                bindings[name] = repr(sig)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings[stmt.name] = "definition"
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = "assignment"
    return bindings


def chain_to_root(node: ast.AST, parents: dict[ast.AST, ast.AST], stop: ast.AST):
    """Yield ancestor nodes from `node` (exclusive) up to `stop` (exclusive)."""
    cur = node
    while True:
        parent = parents.get(cur)
        if parent is None or parent is stop:
            return
        yield parent
        cur = parent


def sole_statement_in_block(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """True if removing `node` would leave its containing block empty."""
    cur = node
    while True:
        parent = parents.get(cur)
        if parent is None:
            return False
        container = None
        for field in ("body", "orelse", "finalbody"):
            seq = getattr(parent, field, None)
            if isinstance(seq, list) and cur in seq:
                container = seq
                break
        if container is not None:
            if len(container) == 1 and not isinstance(parent, ast.Module):
                return True
            # Reached the statement list holding this chain link; only the
            # innermost list matters for emptiness.
            return False
        cur = parent


def collect_module_imports(tree: ast.Module) -> list[ast.stmt]:
    out = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            out.append(stmt)
    return out


def insertion_anchor(tree: ast.Module) -> int:
    """1-based line number after which new imports are inserted."""
    anchor = 0
    body = list(tree.body)
    idx = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        anchor = body[0].end_lineno
        idx = 1
    for stmt in body[idx:]:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            anchor = max(anchor, stmt.end_lineno)
            continue
        # Allow a single blank/comment gap in source, but stop at first real code.
        break
    return anchor


def dedent_import_text(lines: list[str]) -> str:
    first_indent = len(lines[0]) - len(lines[0].lstrip())
    out = []
    for line in lines:
        if line[:first_indent].strip() == "":
            out.append(line[first_indent:])
        else:
            out.append(line.lstrip())
    # Trailing blank lines inside the captured range are not expected.
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out)


def process_file(path: Path, apply: bool) -> tuple[int, int, list[str]]:
    """Return (hoisted_count, skipped_count, notes)."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError) as exc:
        return 0, 0, [f"{path}: parse failed ({exc})"]

    parents = build_parents(tree)
    lines = source.splitlines()

    module_sigs: dict[tuple, str] = {}
    for imp in collect_module_imports(tree):
        module_sigs[import_signature(imp)] = ast.get_source_segment(source, imp) or ""
    bindings = module_level_bindings(tree)

    removals: list[tuple[int, int]] = []          # (start_line, end_line) 1-based
    hoisted: list[tuple[int, str, set[str]]] = []  # (line, text, names)
    hoisted_names: dict[str, tuple] = {}            # name -> signature
    notes: list[str] = []
    skipped = 0

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            ancestors = list(chain_to_root(node, parents, func))
            if any(isinstance(a, (ast.Try, getattr(ast, "TryStar", ast.Try))) for a in ancestors):
                skipped += 1
                notes.append(f"{path}:{node.lineno}: kept (try/except import)")
                continue
            if any(isinstance(a, ast.If) and is_type_checking_test(a.test) for a in ancestors):
                skipped += 1
                notes.append(f"{path}:{node.lineno}: kept (TYPE_CHECKING guard)")
                continue
            if sole_statement_in_block(node, parents):
                skipped += 1
                notes.append(f"{path}:{node.lineno}: kept (sole statement in block)")
                continue
            sig = import_signature(node)
            names = bound_names(node)
            clash = [
                n for n in names
                if n in bindings and bindings[n] != repr(sig) and bindings[n] != "imported"
            ]
            # Same-signature module import: name is identical, safe to drop.
            if clash:
                skipped += 1
                notes.append(
                    f"{path}:{node.lineno}: kept (name clash: {', '.join(sorted(clash))})"
                )
                continue
            text = dedent_import_text(lines[node.lineno - 1:node.end_lineno])
            if sig in module_sigs:
                removals.append((node.lineno, node.end_lineno))
                continue  # already imported at module level: drop local copy
            pending_clash = [
                n for n in names
                if n in hoisted_names and hoisted_names[n] != sig
            ]
            if pending_clash:
                skipped += 1
                notes.append(
                    f"{path}:{node.lineno}: kept (conflicts with another hoisted "
                    f"import: {', '.join(sorted(pending_clash))})"
                )
                continue
            removals.append((node.lineno, node.end_lineno))
            module_sigs[sig] = text
            for n in names:
                hoisted_names.setdefault(n, sig)
            hoisted.append((node.lineno, text, names))

    if not removals and not hoisted:
        return 0, skipped, notes

    if not apply:
        return len(hoisted), skipped, notes

    # Remove local import lines (from bottom up to keep line numbers valid).
    drop = set()
    for start, end in removals:
        drop.update(range(start, end + 1))
    kept_lines = [ln for i, ln in enumerate(lines, start=1) if i not in drop]

    # Recompute anchor on the reduced text (module-level imports unchanged).
    anchor = insertion_anchor(tree)
    inserted = sum(1 for i in drop if i <= anchor)
    insert_at = anchor - inserted
    block: list[str] = []
    for _, text, _ in sorted(hoisted):
        for i, part in enumerate(text.splitlines()):
            block.append(part)
    kept_lines[insert_at:insert_at] = block

    new_source = "\n".join(kept_lines)
    if source.endswith("\n"):
        new_source += "\n"
    # Verify the result still parses before writing.
    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        raise RuntimeError(f"{path}: generated invalid syntax ({exc}); aborting") from exc
    path.write_text(new_source, encoding="utf-8")
    return len(hoisted), skipped, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="rewrite files in place")
    parser.add_argument("--quiet", action="store_true", help="only print totals")
    args = parser.parse_args()

    total_hoisted = total_skipped = changed_files = 0
    all_notes: list[str] = []
    for path in TARGETS:
        if not path.exists():
            continue
        hoisted, skipped, notes = process_file(path, args.apply)
        total_hoisted += hoisted
        total_skipped += skipped
        if hoisted:
            changed_files += 1
        all_notes.extend(notes)

    if not args.quiet:
        for note in all_notes:
            print(note)
        print()
    mode = "hoisted" if args.apply else "would hoist"
    print(f"{total_hoisted} imports {mode} across {changed_files} files; "
          f"{total_skipped} kept in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
