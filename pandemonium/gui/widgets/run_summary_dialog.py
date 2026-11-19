"""
gui/widgets/run_summary_dialog.py — scrollable modal run-summary dialog.

Long-form aftermath text (e.g. an Event Horizon run end: depth, payout,
cards, flask effects) in a monospace scrollable body with a single dismiss
button. Enter / Escape / window close all dismiss.

Mirrors confirm_dialog's center-over-parent + grab_set pattern; the button
row is packed FIRST (bottom) so it can never be clipped on small screens.
"""

import tkinter as tk
from typing import Callable, Optional

from pandemonium.gui.theme import Theme
from pandemonium.gui.widgets.overlay_panel import OverlayPanel


def run_summary_dialog(
    parent: tk.Widget,
    title: str = "Run Summary",
    heading: str = "RUN SUMMARY",
    body: str = "",
    subtitle: str = "",
    on_close: Optional[Callable] = None,
    close_text: str = "Continue",
):
    """Show a scrollable read-only summary panel. `on_close` runs after dismiss."""
    panel = OverlayPanel(parent, heading or title, width=680, height=560)

    if subtitle:
        tk.Label(
            panel.body, text=subtitle, bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
            font=Theme.FONT_SMALL, wraplength=640, justify=tk.CENTER,
        ).pack(padx=20, pady=(0, 8))

    def _close(_event=None):
        panel.close()
        if on_close:
            on_close()

    # Button row FIRST (bottom) — it gets first claim on vertical space.
    btn_frame = tk.Frame(panel.body, bg=Theme.BG_DARK)
    btn_frame.pack(side=tk.BOTTOM, pady=(6, 14))

    close_btn = tk.Button(
        btn_frame, text=close_text, command=_close, width=14,
        bg=Theme.ACCENT, fg=Theme.TEXT_HEADER,
        activebackground=Theme.ACCENT_HOVER,
        font=Theme.FONT_BOLD, cursor="hand2",
    )
    close_btn.pack()

    # Scrollable monospace body
    body_frame = tk.Frame(panel.body, bg=Theme.BG_DARK)
    body_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(4, 2))
    scrollbar = tk.Scrollbar(body_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text = tk.Text(
        body_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set,
        bg=Theme.BG_CARD, fg=Theme.TEXT,
        font=(Theme.FONT_FAMILY, 10),
        relief=tk.FLAT, padx=12, pady=10,
        cursor="arrow",
    )
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=text.yview)
    text.insert("1.0", body)
    text.config(state=tk.DISABLED)

    panel.finalize(on_escape=_close)
    # Enter dismisses even when the focus moved into the read-only body.
    for widget in (panel.holder, text):
        widget.bind("<Return>", _close)
        widget.bind("<KP_Enter>", _close)

    return panel
