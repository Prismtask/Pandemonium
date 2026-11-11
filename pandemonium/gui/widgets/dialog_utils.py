"""Shared helpers for modal tkinter dialogs."""
from __future__ import annotations

import threading
import tkinter as tk


def safe_toplevel(parent=None):
    """Return a usable tkinter toplevel/root, or None if unavailable.

    Never creates a fresh Tk root — that flashes a blank window with the
    default Tk icon and creates a second Tcl interpreter.
    """
    try:
        if parent is not None:
            return parent.winfo_toplevel()
    except (tk.TclError, AttributeError):
        pass
    try:
        return tk._default_root
    except Exception:
        return None


def has_gui():
    """Return True if tkinter has a root window (GUI is available)."""
    try:
        return tk._default_root is not None
    except Exception:
        return False


def is_main_thread():
    """Return True if the calling thread is the main thread."""
    return threading.current_thread() is threading.main_thread()
