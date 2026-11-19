"""gui/widgets/overlay_panel.py — In-app modal panels ("Option C" design).

In-game windows are drawn INSIDE the game window and stack on top of the
CURRENT SCREEN, exactly like the old Toplevel dialogs behaved: the screen
stays fully visible behind the panel.  No Toplevel is created, so there is
no native (white) title bar to remove in the first place, and the panel can
never float outside the game window.

Finalized conventions (2026-11-18):

* No header row and no ✕ button — the title is drawn inside the panel.
* The only exits are the footer buttons (Cancel / No) and Escape.
* No full-screen dim: Tk frames have no alpha, so any opaque backdrop
  replaces the whole screen and reads as a brand-new screen.  The panel
  instead floats over the live screen with a thin dark rim standing in
  for a shadow.

Usage:
    panel = OverlayPanel(self, "Save Files", width=520, height=480)
    ... build content into panel.body ...
    panel.finalize(on_escape=custom_handler)   # binds Esc, focuses, grabs
    panel.close()                              # teardown + focus restore
"""

import tkinter as tk
from typing import Callable, Optional

from pandemonium.gui.theme import Theme
from pandemonium.gui.widgets.keyboard_nav import NavGroup

# Soft dark rim behind the panel — the depth cue that replaces the old dim.
_SHADOW_BG = "#0d0d19"
_SHADOW_PAD = 3


def panel_host(parent: tk.Widget) -> tk.Widget:
    """Return the current-screen widget the panel should stack on.

    Panels float on top of the CURRENT SCREEN — the direct child of the
    ScreenManager content frame — so the screen's own widgets stay visible
    behind them and the panel is destroyed together with that screen (the
    same lifecycle the old per-screen dialogs had).  If ``parent`` is the
    window or the content frame itself, that container is used as-is.
    """
    widget = parent
    try:
        while True:
            master = widget.master
            if master is None or isinstance(master, (tk.Tk, tk.Toplevel)):
                break  # parent is the window itself
            grand = master.master
            if grand is None or isinstance(grand, (tk.Tk, tk.Toplevel)):
                break  # widget is a direct child of the content area
            widget = master
    except (AttributeError, tk.TclError):
        pass
    return widget if isinstance(widget, tk.Widget) else parent


def _bind_escape_recursive(widget: tk.Widget, handler: Callable) -> None:
    """Bind Escape on ``widget`` and every current descendant.

    The panel lives *inside* the main toplevel, so binding only the panel is
    bypassed once focus moves to a child button (bindtags walk up to the
    toplevel, not intermediate frames).  Call after the content is built.
    """
    widget.bind("<Escape>", handler)
    for child in widget.winfo_children():
        _bind_escape_recursive(child, handler)


class OverlayPanel:
    """Modal panel stacked on top of the current screen.

    Args:
        parent:   Widget owned by the calling screen (the panel resolves the
                  screen it should float over via ``panel_host``).
        title:    Title text drawn inside the panel — no header bar.
        width:    Panel width in pixels (clamped to the screen).
        height:   Fixed height; None sizes the panel to its content.
        on_close: Optional callback() run after teardown (any exit path).
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        *,
        width: int = 520,
        height: Optional[int] = None,
        on_close: Optional[Callable] = None,
    ):
        self.parent = parent
        self.on_close = on_close
        self._closed = False

        try:
            self._prev_focus = parent.focus_get()
        except Exception:
            self._prev_focus = None

        host = panel_host(parent)
        width = max(280, min(width, host.winfo_width() - 40))

        # Floating panel: centered over the current screen, which stays fully
        # visible around it.  The dark frame is the pseudo-shadow rim.
        self.shadow = tk.Frame(host, bg=_SHADOW_BG)
        self.shadow.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.shadow.lift()
        # Marker used by diagnostics to find open panels on a screen.
        self.shadow._pandemonium_panel = True

        outer = tk.Frame(self.shadow, bg=Theme.BORDER)  # 1px panel border
        outer.pack(padx=_SHADOW_PAD, pady=_SHADOW_PAD)

        if height is not None:
            height = max(160, min(height, host.winfo_height() - 60))
            holder = tk.Frame(
                outer, bg=Theme.BG_DARK, width=width - 2, height=height - 2,
            )
            holder.pack(padx=1, pady=1)
            holder.pack_propagate(False)  # fixed panel size
        else:
            holder = tk.Frame(outer, bg=Theme.BG_DARK)
            holder.pack(padx=1, pady=1)
            # Zero-height spacer pins the minimum width so wrapped labels
            # size against a stable panel width (auto height from content).
            tk.Frame(holder, bg=Theme.BG_DARK, width=width - 2, height=0).pack()
        self.holder = holder

        # Title inside the panel — deliberately no header bar / ✕ button.
        tk.Label(
            holder,
            text=title,
            bg=Theme.BG_DARK,
            fg=Theme.ACCENT,
            font=Theme.FONT_LARGE,
        ).pack(pady=(16, 10))

        self.body = tk.Frame(holder, bg=Theme.BG_DARK)
        self.body.pack(fill=tk.BOTH, expand=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def finalize(self, on_escape: Optional[Callable] = None) -> None:
        """Wire Escape, focus and modality — call once after building content."""
        _bind_escape_recursive(
            self.holder, on_escape if on_escape is not None else self.close,
        )
        self.holder.focus_set()
        self.grab()

    def grab(self) -> None:
        """(Re)assert modality — e.g. after a nested confirm panel closes."""
        try:
            self.holder.grab_set()
        except tk.TclError:
            pass

    def close(self, _event=None) -> None:
        """Tear the panel down and hand keyboard focus back to the opener."""
        if self._closed:
            return
        self._closed = True
        try:
            self.holder.grab_release()
        except tk.TclError:
            pass
        try:
            self.shadow.destroy()
        except tk.TclError:
            pass
        try:
            if self._prev_focus is not None and self._prev_focus.winfo_exists():
                self._prev_focus.focus_set()
        except tk.TclError:
            pass
        if self.on_close is not None:
            self.on_close()


def confirm_panel(
    parent: tk.Widget,
    title: str,
    message: str,
    on_yes: Optional[Callable] = None,
    on_no: Optional[Callable] = None,
    yes_text: str = "Yes",
    no_text: str = "No",
    *,
    width: int = 380,
    focus_no: bool = False,
    escape_cb: Optional[Callable] = None,
) -> OverlayPanel:
    """In-app Yes/No confirmation panel (Option C style).

    Escape behaves like No unless ``escape_cb`` overrides it.  Buttons never
    take keyboard focus; Left/Right/Tab move a thin outline and Enter/Space
    activate the outlined button.  ``focus_no=True`` starts on No (for
    dialogs that pop up while the player may still be mid-Enter).
    """
    panel = OverlayPanel(parent, title, width=width)

    tk.Label(
        panel.body,
        text=message,
        bg=Theme.BG_DARK,
        fg=Theme.TEXT,
        font=Theme.FONT,
        wraplength=width - 60,
        justify=tk.CENTER,
    ).pack(padx=20, pady=(0, 16), fill=tk.BOTH, expand=True)

    def _yes(_event=None):
        panel.close()
        if on_yes is not None:
            on_yes()

    def _cancel(_event=None):
        panel.close()
        if escape_cb is not None:
            escape_cb()
        elif on_no is not None:
            on_no()

    btn_row = tk.Frame(panel.body, bg=Theme.BG_DARK)
    btn_row.pack(pady=(0, 16))

    # Wrapper frames carry the 1px outline (tk.Buttons ignore it on Windows).
    yes_wrap = tk.Frame(
        btn_row, bg=Theme.BG_DARK,
        highlightthickness=1, highlightbackground=Theme.BG_DARK,
    )
    yes_wrap.pack(side=tk.LEFT, padx=8)
    yes_btn = tk.Button(
        yes_wrap, text=yes_text, command=_yes, width=12,
        bg=Theme.ACCENT, fg=Theme.TEXT_HEADER,
        activebackground=Theme.ACCENT_HOVER,
        font=Theme.FONT_BOLD, cursor="hand2",
    )
    yes_btn.pack(padx=2, pady=2)

    no_wrap = tk.Frame(
        btn_row, bg=Theme.BG_DARK,
        highlightthickness=1, highlightbackground=Theme.BG_DARK,
    )
    no_wrap.pack(side=tk.LEFT, padx=8)
    no_btn = tk.Button(
        no_wrap, text=no_text, command=_cancel, width=12,
        bg=Theme.BUTTON_BG, fg=Theme.TEXT,
        activebackground=Theme.BUTTON_ACTIVE_BG,
        font=Theme.FONT_BOLD, cursor="hand2",
    )
    no_btn.pack(padx=2, pady=2)

    nav = NavGroup(
        panel.holder, [(yes_wrap, yes_btn), (no_wrap, no_btn)],
        start=1 if focus_no else 0,
    )
    nav.bind_keys(panel.holder)

    panel.finalize(on_escape=_cancel)
    return panel


def ok_panel(
    parent: tk.Widget,
    title: str,
    message: str,
    on_ok: Optional[Callable] = None,
    ok_text: str = "OK",
    *,
    width: int = 380,
) -> OverlayPanel:
    """In-app single-button notice panel (Option C style)."""
    panel = OverlayPanel(parent, title, width=width)

    tk.Label(
        panel.body,
        text=message,
        bg=Theme.BG_DARK,
        fg=Theme.TEXT,
        font=Theme.FONT,
        wraplength=width - 60,
        justify=tk.CENTER,
    ).pack(padx=20, pady=(0, 16), fill=tk.BOTH, expand=True)

    def _ok(_event=None):
        panel.close()
        if on_ok is not None:
            on_ok()

    btn_row = tk.Frame(panel.body, bg=Theme.BG_DARK)
    btn_row.pack(pady=(0, 16))

    ok_wrap = tk.Frame(
        btn_row, bg=Theme.BG_DARK,
        highlightthickness=1, highlightbackground=Theme.BG_DARK,
    )
    ok_wrap.pack(padx=8)
    ok_btn = tk.Button(
        ok_wrap, text=ok_text, command=_ok, width=12,
        bg=Theme.ACCENT, fg=Theme.TEXT_HEADER,
        activebackground=Theme.ACCENT_HOVER,
        font=Theme.FONT_BOLD, cursor="hand2",
    )
    ok_btn.pack(padx=2, pady=2)

    nav = NavGroup(panel.holder, [(ok_wrap, ok_btn)])
    nav.bind_keys(panel.holder)

    panel.finalize(on_escape=_ok)
    return panel


def choice_panel(
    parent: tk.Widget,
    title: str,
    heading: str,
    subtitle: str = "",
    details: str = "",
    options=None,
    on_choice: Optional[Callable[[str], None]] = None,
    default_choice: Optional[str] = None,
    min_width: int = 380,
) -> OverlayPanel:
    """In-app stacked-options panel (replaces the floor-clear Toplevel).

    Escape resolves to ``default_choice``.  Arrow keys / Tab move a thin
    outline; Enter/Space activate the outlined option.
    """
    panel = OverlayPanel(parent, heading or title, width=min_width)
    closed = [False]

    if subtitle:
        tk.Label(
            panel.body,
            text=subtitle,
            bg=Theme.BG_DARK,
            fg=Theme.TEXT,
            font=Theme.FONT,
            wraplength=min_width - 60,
            justify=tk.CENTER,
        ).pack(padx=16, pady=(0, 6))

    if details:
        tk.Label(
            panel.body,
            text=details,
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_DIM,
            font=Theme.FONT_SMALL,
            justify=tk.CENTER,
            wraplength=min_width - 60,
        ).pack(padx=16, pady=(0, 10))

    def _choose(key):
        if closed[0]:
            return
        closed[0] = True
        panel.close()
        if on_choice is not None and key is not None:
            on_choice(key)

    btn_frame = tk.Frame(panel.body, bg=Theme.BG_DARK)
    btn_frame.pack(pady=(0, 14))

    entries = []
    start = 0
    for i, (key, label) in enumerate(options or []):
        wrapper = tk.Frame(
            btn_frame, bg=Theme.BG_DARK,
            highlightthickness=1, highlightbackground=Theme.BG_DARK,
        )
        wrapper.pack(pady=2)
        btn = tk.Button(
            wrapper, text=label,
            command=lambda k=key: _choose(k),
            width=26, anchor=tk.W,
            bg=Theme.BUTTON_BG, fg=Theme.BUTTON_FG,
            activebackground=Theme.BUTTON_ACTIVE_BG,
            activeforeground=Theme.BUTTON_ACTIVE_FG,
            font=Theme.FONT_BOLD, cursor="hand2",
        )
        btn.pack(padx=2, pady=2)
        entries.append((wrapper, btn))
        if default_choice is not None and key == default_choice:
            start = i

    if entries:
        nav = NavGroup(panel.holder, entries, start=start)
        nav.bind_keys(panel.holder)

    panel.finalize(on_escape=lambda _e=None: _choose(default_choice))
    return panel
