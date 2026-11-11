"""Shared formatting helpers for facilities intro sequences."""
from pandemonium.gui.terminal import term


def print_header(text):
    """Print a boxed section header through the GUI-aware terminal."""
    rule = "═" * min(len(text) + 4, 70)
    term.print(rule)
    term.print(f"  {text}")
    term.print(rule)
