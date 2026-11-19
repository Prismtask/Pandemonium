"""
gui/widgets/confirm_dialog.py — Yes/No, OK and option-list modal dialogs.

Since 2026-11-18 these render as in-app overlay panels (Option C design,
``gui/widgets/overlay_panel.py``): a dim backdrop plus a centered panel drawn
inside the game window — no Toplevel, no native title bar, no header row.
The public API (parent, title, message, callbacks) is unchanged.
"""

import tkinter as tk
from typing import Callable, Optional

from pandemonium.gui.widgets.overlay_panel import (
    choice_panel,
    confirm_panel,
    ok_panel,
    panel_host,
)


def _safe_toplevel(parent: tk.Widget) -> tk.Toplevel:
    """Return parent.winfo_toplevel(), falling back to the default root window."""
    try:
        return parent.winfo_toplevel()
    except tk.TclError:
        # Parent destroyed — fall back to the tkinter root
        return parent._root() if hasattr(parent, '_root') else parent.master.winfo_toplevel()
    except Exception:
        # Last resort
        import tkinter as _tk
        return _tk._default_root


# Rough metrics for the dialog font (Consolas ~7px per char at the sizes used).
_CHAR_PX = 7
_LINE_HEIGHT = 18


def _estimate_dialog_size(message, min_width, base_height, max_width):
    """Estimate a dialog's pixel size, accounting for text wrapping.

    The message label wraps at (width - 40) px, so one long source line can
    occupy several visual lines; the height estimate must count those or the
    button row ends up clipped (fixed 2026-09-28 — Glass Anchor examine).
    """
    lines = message.split("\n")
    max_line_len = max((len(line) for line in lines), default=30)
    dw = max(min_width, min(max_width, max_line_len * _CHAR_PX + 60))
    chars_per_line = max(20, (int(dw) - 40) // _CHAR_PX)
    visual_lines = sum(
        max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        for line in lines
    )
    dh = base_height + visual_lines * _LINE_HEIGHT + 24
    return int(dw), int(dh)


def confirm_dialog(
    parent: tk.Widget,
    title: str,
    message: str,
    on_yes: Optional[Callable] = None,
    on_no: Optional[Callable] = None,
    yes_text: str = "Yes",
    no_text: str = "No",
    focus_no: bool = False,
    on_close: Optional[Callable] = None,
):
    """
    Show a Yes/No confirmation dialog.

    Keyboard shortcuts: Enter = Yes, Escape = No (or close).

    Args:
        parent: Parent widget (usually self or self.winfo_toplevel()).
        title: Window title.
        message: Body text.
        on_yes: Callback if user clicks Yes / presses Enter.
        on_no: Callback if user clicks No / presses Escape / closes window.
        yes_text: Label for the affirmative button.
        no_text: Label for the negative button. If None, only the Yes button is shown.
        focus_no: Start the thin outline on the No button instead of Yes — for
                  dialogs that pop up while the player may be mid-Enter (e.g.
                  after "Press Enter" prompts), preventing an accidental
                  instant confirm.
        on_close: Optional callback for the legacy window X. The in-app panel
                  has no X; when provided, Escape behaves like a pure cancel
                  (closes without firing on_no).
    """
    width = _estimate_dialog_size(
        message, min_width=340, base_height=100, max_width=520,
    )[0]
    escape_cb = on_close if on_close is not None else on_no
    if no_text is None:
        # Legacy single-button variant: only the affirmative button shows.
        return ok_panel(
            panel_host(parent), title, message,
            on_ok=on_yes, ok_text=yes_text, width=width,
        )
    return confirm_panel(
        panel_host(parent), title, message,
        on_yes=on_yes, on_no=on_no,
        yes_text=yes_text, no_text=no_text,
        width=width, focus_no=focus_no, escape_cb=escape_cb,
    )


def ok_dialog(
    parent: tk.Widget,
    title: str,
    message: str,
    on_ok: Optional[Callable] = None,
):
    """Show a simple OK dialog.  Enter or Escape = dismiss."""
    width = _estimate_dialog_size(
        message, min_width=300, base_height=90, max_width=480,
    )[0]
    return ok_panel(panel_host(parent), title, message, on_ok=on_ok, width=width)


def choice_dialog(
    parent: tk.Widget,
    title: str,
    heading: str,
    subtitle: str = "",
    details: str = "",
    options=None,
    on_choice: Optional[Callable[[str], None]] = None,
    default_choice: Optional[str] = None,
    min_width: int = 380,
):
    """Show a modal list-of-buttons dialog (the floor-clear window style).

    Args:
        parent: Parent widget — must still be alive (the dialog is created
                as a child of its toplevel).
        title: Window title.
        heading: Large accent headline (e.g. "=== FLOOR 5/6 CLEARED ===").
        subtitle: Optional normal-weight line under the heading.
        details: Optional dim multi-line block (stats, loot, ...).
        options: list of (key, label) pairs rendered as stacked buttons.
        on_choice: Callback(key) fired when a button is clicked (or the
                   window is closed, using default_choice).
        default_choice: Key used for Escape (legacy: window X / Return).

    Returns the overlay panel.
    """
    return choice_panel(
        panel_host(parent), title, heading,
        subtitle=subtitle, details=details, options=options,
        on_choice=on_choice, default_choice=default_choice,
        min_width=min_width,
    )
    dialog.bind("<Return>", _close_default)
    dialog.bind("<KP_Enter>", _close_default)

    # Size to the built content, then center on the parent toplevel.
    dialog.update_idletasks()
    dw = max(min_width, dialog.winfo_reqwidth())
    dh = dialog.winfo_reqheight()
    try:
        px = root.winfo_x()
        py = root.winfo_y()
        pw = max(1, root.winfo_width())
        ph = max(1, root.winfo_height())
    except Exception:
        px = py = 100
        pw = ph = 600
    dialog.geometry(f"{int(dw)}x{int(dh)}+{px + (pw - int(dw)) // 2}+{py + (ph - int(dh)) // 2}")

    # Show only once the content is built (prevents a blank window flash)
    dialog.deiconify()
    dialog.lift()
    dialog.grab_set()
    dialog.focus_set()
    return dialog
