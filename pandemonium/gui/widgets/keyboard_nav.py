"""
gui/widgets/keyboard_nav.py — thin-outline keyboard focus navigation.

Tk's classic buttons draw a dotted focus rectangle *inside* the widget when
they hold keyboard focus (seen as a white dotted box inside the Quit dialog's
Yes button).  Instead of focusing the buttons, a NavGroup keeps keyboard focus
on the owning container (a screen frame or dialog Toplevel) and marks the
selected entry with a thin 1px outline via the highlight ring.

Why wrapper widgets: on Windows, classic ``tk.Button`` ignores the highlight
ring (all -highlightbackground / -highlightcolor values render identically —
verified by pixel capture), so call sites wrap each Button in a ``tk.Frame``
and pass ``(wrapper, button)`` to NavGroup.  Frames do render the ring, and
the same style is already used by the save browser's selected-card outline.

Usage:
    nav = NavGroup(self, [(wrap_a, btn_a), (wrap_b, btn_b)])
    nav.bind_keys(self)   # Up/Down/Left/Right/Tab/Home/End/Enter/Space

The owner must have keyboard focus; ScreenManager already focuses each new
screen, and modal dialogs focus themselves.
"""

import tkinter as tk
from typing import Callable, List, Optional, Sequence, Tuple, Union

from pandemonium.gui.theme import Theme

# A nav entry is either a single widget (ring + action) or a
# (ring_widget, action) pair.  The action is normally a Button (invoke is
# called); a plain callable is also accepted for dynamic lists (save cards).
NavEntry = Union[
    tk.Widget,
    Tuple[tk.Widget, Union[tk.Widget, Callable[[], None]]],
]


class NavGroup:
    """Arrow-key selection over entries, drawn as a thin outline ring.

    Selected entries are never keyboard-focused, so Tk never draws its dotted
    in-button focus rectangle.  Enter/Space invoke the action widget instead
    (``Button.invoke`` runs its command).
    """

    def __init__(
        self,
        owner: tk.Misc,
        entries: Sequence[NavEntry],
        *,
        start: int = 0,
        idle_color: str = Theme.BG_DARK,
        focus_color: str = Theme.TEXT_HEADER,
        on_change: Optional[Callable[[int], None]] = None,
    ):
        self.owner = owner
        self.idle_color = idle_color
        self.focus_color = focus_color
        self.on_change = on_change
        self.widgets: List[tk.Widget] = []   # outline holders
        self._actions: List[tk.Widget] = []  # invoke targets
        self.index = 0

        for entry in entries:
            if isinstance(entry, tuple):
                ring_widget, action = entry
            else:
                ring_widget = action = entry
            self.widgets.append(ring_widget)
            self._actions.append(action)
            if isinstance(action, tk.Misc):
                action.configure(takefocus=0)
            if ring_widget is not action:
                ring_widget.configure(takefocus=0)
            ring_widget.configure(
                highlightthickness=1,
                highlightbackground=idle_color,
                # If something focuses the widget programmatically, keep the
                # outline colour instead of the OS default ring.
                highlightcolor=focus_color,
            )
        if self.widgets:
            self.select(start)

    # ── Selection ─────────────────────────────────────────────────────────

    def select(self, index: int) -> None:
        """Select ``index`` (wrapping) and repaint the outline."""
        if not self.widgets:
            return
        self.index = index % len(self.widgets)
        for i, ring_widget in enumerate(self.widgets):
            try:
                ring_widget.configure(
                    highlightbackground=(
                        self.focus_color if i == self.index else self.idle_color
                    )
                )
            except tk.TclError:
                pass  # widget destroyed mid-navigation
        if self.on_change is not None:
            self.on_change(self.index)

    def move(self, delta: int) -> None:
        self.select(self.index + delta)

    def clear_outline(self) -> None:
        """Remove the outline without changing the remembered index."""
        for ring_widget in self.widgets:
            try:
                ring_widget.configure(highlightbackground=self.idle_color)
            except tk.TclError:
                pass

    def activate(self) -> None:
        """Run the selected action (Button.invoke or a plain callable)."""
        if not self._actions:
            return
        action = self._actions[self.index]
        try:
            invoke = getattr(action, "invoke", None)
            if callable(invoke):
                invoke()
            elif callable(action):
                action()
        except tk.TclError:
            pass

    # ── Key handling ─────────────────────────────────────────────────────

    def on_key(self, event: tk.Event):
        """Handle one key press; returns ``"break"`` when it was consumed."""
        key = event.keysym
        if key in ("Up", "Left", "ISO_Left_Tab"):
            self.move(-1)
            return "break"
        if key in ("Down", "Right", "Tab"):
            # Shift+Tab arrives as keysym "Tab" with the shift bit set on
            # Windows, and as "ISO_Left_Tab" elsewhere (handled above).
            if key == "Tab" and (event.state & 0x1):
                self.move(-1)
            else:
                self.move(1)
            return "break"
        if key == "Home":
            self.select(0)
            return "break"
        if key == "End":
            self.select(len(self.widgets) - 1)
            return "break"
        if key in ("Return", "KP_Enter", "space"):
            self.activate()
            return "break"
        return None

    def bind_keys(self, owner: Optional[tk.Misc] = None) -> None:
        """Bind navigation keys on ``owner`` (defaults to the group's owner)."""
        target = owner or self.owner
        for sequence in (
            "<Up>", "<Down>", "<Left>", "<Right>",
            "<Tab>", "<Shift-Tab>", "<ISO_Left_Tab>",
            "<Home>", "<End>",
            "<Return>", "<KP_Enter>", "<space>",
        ):
            target.bind(sequence, self.on_key)
