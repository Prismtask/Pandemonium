"""
gui/widgets/hp_bar.py — Visual HP/MP/XP bar widget using tkinter Canvas.

More flexible than ttk.Progressbar for custom colors and sizing.
"""

import tkinter as tk

from pandemonium.gui.theme import Theme


class HPBar(tk.Canvas):
    """
    A custom horizontal bar widget for displaying HP, MP, XP, etc.

    Usage:
        bar = HPBar(parent, current=50, maximum=100, width=200, height=20,
                    fill_color=Theme.HP_BAR_FILL, empty_color=Theme.HP_BAR_EMPTY)
        bar.set_value(75)
        bar.set_maximum(150)
    """

    def __init__(
        self,
        parent,
        current: int = 100,
        maximum: int = 100,
        width: int = 200,
        height: int = 20,
        fill_color: str = Theme.HP_BAR_FILL,
        empty_color: str = Theme.HP_BAR_EMPTY,
        text_color: str = Theme.TEXT,
        show_text: bool = True,
        **kwargs,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=empty_color,
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            **kwargs,
        )

        self._current = max(0, current)
        self._maximum = max(1, maximum)
        self._width = width
        self._height = height
        self._fill_color = fill_color
        self._empty_color = empty_color
        self._text_color = text_color
        self._show_text = show_text

        # Reused canvas items; rebuilding them every HUD tick made the
        # combat screen redraw 8-9 bar canvases 5x/s (2026-11-17 perf pass).
        self._items = {}
        self._render_key = None

        self._draw()

    # ── Core drawing ──────────────────────────────────────────────────────────

    def _ensure_items(self):
        """Create the fill/empty/text items once, in stacking order.

        The text overlay MUST be created after both rectangles. The empty
        rectangle is only needed once HP drops below max, and creating it
        lazily at that point would stack it above the already-created text
        and hide the numbers over the empty part of the bar
        (2026-11-17 playtest: "HP text got cut off when they got low").
        """
        if self._items.get("text") is not None:
            return True
        try:
            fill_id = self.create_rectangle(
                0, 0, 0, self._height, fill=self._fill_color,
                outline="", tags="fill", state="hidden",
            )
            empty_id = self.create_rectangle(
                0, 0, 0, self._height, fill=self._empty_color,
                outline="", tags="empty", state="hidden",
            )
            text_id = self.create_text(
                6, self._height // 2, text="", anchor=tk.W,
                fill=self._text_color, font=("Consolas", 9, "bold"),
                tags="text", state="hidden",
            )
        except tk.TclError:
            self._items = {}
            return False
        self._items.update(
            {"fill": fill_id, "empty": empty_id, "text": text_id}
        )
        return True

    def _draw(self):
        """Update the bar, reusing existing canvas items where possible."""
        key = (self._current, self._maximum, self._width, self._height,
               self._fill_color, self._empty_color, self._text_color,
               self._show_text)
        if key == self._render_key:
            return  # Nothing visible changed — skip all Tcl calls.

        if not self._ensure_items():
            return

        try:
            ratio = min(self._current / self._maximum, 1.0)
            fill_width = int(self._width * ratio)

            # Filled portion
            fill_id = self._items["fill"]
            if fill_width > 0:
                self.coords(fill_id, 0, 0, fill_width, self._height)
                self.itemconfigure(
                    fill_id, fill=self._fill_color, state="normal"
                )
            else:
                self.itemconfigure(fill_id, state="hidden")

            # Empty portion
            empty_id = self._items["empty"]
            if fill_width < self._width:
                self.coords(empty_id, fill_width, 0,
                            self._width, self._height)
                self.itemconfigure(
                    empty_id, fill=self._empty_color, state="normal"
                )
            else:
                self.itemconfigure(empty_id, state="hidden")

            # Text overlay — left-aligned inside the bar (always on top)
            text_id = self._items["text"]
            if self._show_text:
                self.coords(text_id, 6, self._height // 2)
                self.itemconfigure(
                    text_id,
                    text=f"{self._current}/{self._maximum}",
                    fill=self._text_color,
                    state="normal",
                )
            else:
                self.itemconfigure(text_id, state="hidden")

            self._render_key = key
        except tk.TclError:
            # Items deleted behind our back or widget being torn down.
            # Reset the cache so the next draw rebuilds from scratch.
            self._items = {}
            self._render_key = None

    def clear(self):
        """Delete all canvas items (used for reserved empty HUD slots)."""
        try:
            self.delete("all")
        except tk.TclError:
            pass
        self._items = {}
        self._render_key = None

    # ── Public API ────────────────────────────────────────────────────────────

    def set_value(self, value: int):
        """Update the current value and redraw."""
        self._current = max(0, value)
        self._draw()

    def set_maximum(self, maximum: int):
        """Update the maximum value and redraw."""
        self._maximum = max(1, maximum)
        self._draw()

    def set_both(self, current: int, maximum: int):
        """Update both values and redraw."""
        self._current = max(0, current)
        self._maximum = max(1, maximum)
        self._draw()

    def set_width(self, width: int):
        """Resize the bar (used when a party card shrinks to an equal slot)."""
        self._width = max(20, int(width))
        self.configure(width=self._width)
        self._draw()

    def get_percentage(self) -> float:
        """Return the fill percentage (0.0–100.0)."""
        return (self._current / self._maximum) * 100.0
