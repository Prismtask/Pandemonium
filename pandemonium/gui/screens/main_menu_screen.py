"""
gui/screens/main_menu_screen.py — Main menu: New Game, Load Game, Settings, Changelog, Quit.
"""

import tkinter as tk

from pandemonium.gui.screens.base_screen import BaseScreen
from pandemonium.gui.theme import Theme
from pandemonium.gui.widgets.confirm_dialog import ok_dialog
from pandemonium.gui.widgets.keyboard_nav import NavGroup
from pandemonium.gui.widgets.overlay_panel import OverlayPanel, confirm_panel

from pandemonium.core.version import VERSION_LABEL
from pandemonium.gui.screens.settings_screen import SettingsScreen
from pandemonium.gui.screens.changelog_screen import ChangelogScreen
from pandemonium.core.save_load import list_save_details, load_game, delete_save
from pandemonium.core.character import ensure_player_fields


# Last keyboard selection, kept across MainMenuScreen rebuilds so returning
# from Settings / Changelog lands on the same button (Quit / Load dialogs
# already keep the live screen instance, so they preserved the selection).
_last_nav_index = 0


def _remember_nav_index(index: int) -> None:
    global _last_nav_index
    _last_nav_index = index


class MainMenuScreen(BaseScreen):
    """The game's main menu — first screen shown on launch."""

    def build_ui(self):
        self.sm.clear_history()
        self.sm.player = None
        self.sm.update_top_bar("Pandemonium — Main Menu")
        self.sm.clear_log()

        # ── Center container ───────────────────────────────────────────────────
        container = self.styled_frame(self)
        container.place(relx=0.5, rely=0.45, anchor=tk.CENTER)

        # Title
        tk.Label(
            container,
            text="PANDEMONIUM",
            bg=Theme.BG_DARK,
            fg=Theme.ACCENT,
            font=Theme.FONT_LARGE,
        ).pack(pady=(0, 8))

        tk.Label(
            container,
            text="Mystery of the Accord",
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_DIM,
            font=Theme.FONT_SMALL,
        ).pack(pady=(0, 30))

        # Buttons — each Button sits in a wrapper Frame because Tk buttons on
        # Windows ignore the highlight ring; the wrapper carries the 1px
        # keyboard-focus outline.  The 2px inner gap keeps the outline from
        # touching the button's own 3D border.
        btn_width = 20
        btn_pady = 6
        menu_buttons = []
        menu_entries = []

        for text, command in (
            ("New Game", self._on_new_game),
            ("Load Game", self._on_load_game),
            ("Settings", self._on_settings),
            ("Changelog", self._on_changelog),
            ("Quit", self._on_quit),
        ):
            wrapper = tk.Frame(
                container,
                bg=Theme.BG_DARK,
                highlightthickness=1,
                highlightbackground=Theme.BG_DARK,
            )
            wrapper.pack(pady=btn_pady - 2)
            btn = self.styled_button(
                wrapper,
                text=text,
                command=command,
                width=btn_width,
            )
            btn.pack(padx=2, pady=2)
            menu_buttons.append(btn)
            menu_entries.append((wrapper, btn))

        # Version label + beta clarifier (single source of truth: version.py)
        tk.Label(
            container,
            text=VERSION_LABEL,
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_DIM,
            font=Theme.FONT_SMALL,
        ).pack(pady=(20, 0))

        # ── Keyboard navigation ───────────────────────────────────────────
        # Keyboard focus stays on this screen frame, so Tk's dotted in-button
        # focus rectangle never appears.  Arrow keys / Tab move a thin 1px
        # outline between the menu buttons; Enter or Space activates the
        # outlined one.  The selection is remembered across screen rebuilds.
        self._nav = NavGroup(
            self,
            menu_entries,
            start=_last_nav_index,
            on_change=_remember_nav_index,
        )
        self._nav.bind_keys()
        # Mouse clicks move the outline too, so the next Enter/Space press
        # lands on the button the player last interacted with.
        for i, btn in enumerate(menu_buttons):
            btn.bind("<Button-1>", lambda _e, i=i: self._nav.select(i), add="+")

    # ── Button handlers ───────────────────────────────────────────────────────

    def _on_new_game(self):
        from pandemonium.gui.screens.char_create_screen import CharCreateScreen
        self.sm.switch_to(CharCreateScreen)

    def _on_load_game(self):
        self._show_save_browser()

    def _on_quit(self):
        confirm_panel(
            parent=self,
            title="Quit Game",
            message="Are you sure you want to quit?",
            on_yes=lambda: self.sm.root.destroy(),
        )

    def _on_settings(self):
        self.sm.switch_to(SettingsScreen, push_history=True)

    def _on_changelog(self):
        self.sm.switch_to(ChangelogScreen, push_history=True)

    # ── Save browser (combined Load / Delete) ─────────────────────────────────

    def _show_save_browser(self):
        """Unified, scrollable save browser — click a card, then Load or Delete.

        Replaces the old fixed-height Load/Delete dialogs, whose action buttons
        got squeezed once more than ~4 saves existed.  Every action asks for
        confirmation, and cancelling backs out of the pending action.
        """
        from pandemonium.gui.screens.city_screen import CityScreen

        if not list_save_details():
            ok_dialog(self, "Save Files", "No save files found.")
            return

        # Option C window design: the browser is a panel drawn inside the
        # main menu (no Toplevel), so there is no native title bar at all.
        # The panel restores keyboard focus to the menu when it closes.
        def _cleanup():
            try:
                self.unbind_all("<MouseWheel>")
            except tk.TclError:
                pass

        panel = OverlayPanel(
            self, "Save Files", width=520, height=480, on_close=_cleanup,
        )
        body = panel.body

        tk.Label(
            body,
            text="Select a save file:",
            bg=Theme.BG_DARK,
            fg=Theme.TEXT,
            font=Theme.FONT_BOLD,
        ).pack(padx=20, pady=(0, 8))

        # ── Scrollable card list ─────────────────────────────────────────
        list_outer = tk.Frame(body, bg=Theme.BG_DARK)
        list_outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 8))

        canvas = tk.Canvas(list_outer, bg=Theme.BG_DARK, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(list_outer, orient=tk.VERTICAL, command=canvas.yview)
        cards = tk.Frame(canvas, bg=Theme.BG_DARK)

        window_id = canvas.create_window((0, 0), window=cards, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # The scroll region is anchored at (0, 0) and never shorter than the
        # canvas itself — otherwise a viewport taller than the cards lets the
        # view drift above the first card into empty space (fixed 2026-10-06).
        def _sync_scrollregion(_event=None):
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(
                    scrollregion=(0, 0, bbox[2], max(bbox[3], canvas.winfo_height()))
                )

        # Keep cards stretched to the canvas width + refresh the region
        def _on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)
            _sync_scrollregion()

        cards.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mouse-wheel scrolling — bound app-wide while the modal browser is
        # open so it also works over the cards, then unbound on close.
        def _on_mousewheel(event):
            try:
                step = int(-1 * (event.delta / 120))
                first, last = canvas.yview()
                if (step < 0 and first <= 0.0) or (step > 0 and last >= 1.0):
                    return  # already at the top / bottom
                canvas.yview_scroll(step, "units")
            except tk.TclError:
                pass

        body.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Action bar (fixed — buttons never shrink with the save count) ─
        action_bar = tk.Frame(body, bg=Theme.BG_DARK)
        action_bar.pack(fill=tk.X, padx=20, pady=(0, 14))

        hint = tk.Label(
            action_bar,
            text="Click a save file to load or delete it.",
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_DIM,
            font=Theme.FONT_SMALL,
        )
        hint.pack(side=tk.LEFT)

        state = {
            "slot": None,
            "info": {},
            "cards": {},
            "order": [],
            "list_index": 0,
            "list_nav": None,
            "action_nav": None,
            "nav": None,
        }

        def _regrab():
            panel.grab()

        def _close():
            panel.close()   # unbinds MouseWheel via on_close, restores focus

        # ── Actions (each one asks for confirmation / cancel) ────────────
        def _do_load(slot):
            name = state["info"].get(slot, {}).get("name", "Unknown")

            def _confirmed():
                # Local import: keeps the karma/title data chain off the main
                # menu's startup path (only needed once a save is loaded).
                import pandemonium.progression.karma as karma

                player = load_game(slot)
                if player is None:
                    ok_dialog(self, "Error", f"Failed to load Savefile {slot}.",
                              on_ok=_regrab)
                    return
                _close()
                ensure_player_fields(player)
                karma.mark_city_arrival(player)
                self.sm.player = player
                self.sm.log(f"Loaded {player['name']} — {player['race']} {player['class']}")
                self.sm.switch_to(CityScreen)

            confirm_panel(
                parent=self,
                title="Confirm Load",
                message=f"Load '{name}' (Savefile {slot})?",
                on_yes=_confirmed,
                on_no=_regrab,
                yes_text="Load",
                no_text="Cancel",
            )

        def _do_delete(slot):
            name = state["info"].get(slot, {}).get("name", "Unknown")

            def _confirmed():
                if delete_save(slot):
                    _rebuild()
                    _regrab()
                else:
                    ok_dialog(self, "Error", f"Could not delete Savefile {slot}.",
                              on_ok=_regrab)

            confirm_panel(
                parent=self,
                title="Confirm Deletion",
                message=f"Permanently delete '{name}' (Savefile {slot})?\nThis cannot be undone.",
                on_yes=_confirmed,
                on_no=_regrab,
                yes_text="Delete",
                no_text="Cancel",
            )

        # One bottom button: "Close" normally, flips to "Cancel" while a save
        # is selected — cancel backs out of the selection, close shuts the
        # window.  (Escape follows the same rule.)
        def _on_bottom_action():
            if state["slot"] is not None:
                _select(None)
            else:
                _close()

        bottom_wrap = tk.Frame(
            action_bar, bg=Theme.BG_DARK,
            highlightthickness=1, highlightbackground=Theme.BG_DARK,
        )
        bottom_wrap.pack(side=tk.RIGHT)
        bottom_btn = tk.Button(
            bottom_wrap, text="Close", command=_on_bottom_action, width=10,
            bg=Theme.BUTTON_BG, fg=Theme.TEXT,
            activebackground=Theme.BUTTON_ACTIVE_BG,
            font=Theme.FONT_BOLD, cursor="hand2",
        )
        bottom_btn.pack(padx=2, pady=2)

        # ── Keyboard navigation helpers ──────────────────────────────────
        def _remember_slot_index(slot):
            try:
                state["list_index"] = state["order"].index(slot)
            except ValueError:
                pass

        def _scroll_into_view(widget):
            """Keep the outlined entry visible inside the scroll canvas."""
            try:
                cards.update_idletasks()
                total = cards.winfo_height()
                view_h = canvas.winfo_height()
                if total <= 0 or view_h <= 0:
                    return
                top = canvas.canvasy(0)
                y = widget.winfo_y()
                h = widget.winfo_height()
                if y < top:
                    canvas.yview_moveto(max(0.0, y / total))
                elif y + h > top + view_h:
                    canvas.yview_moveto((y + h - view_h) / total)
            except tk.TclError:
                pass

        def _on_list_change(index):
            state["list_index"] = index
            if 0 <= index < len(state["order"]):
                _scroll_into_view(
                    state["cards"][state["order"][index]]["wrapper"]
                )

        def _activate_card(slot):
            _remember_slot_index(slot)
            _select(slot)

        def _on_browser_key(event):
            """Forward keys to the active nav group (card list or actions)."""
            nav = state["nav"]
            if nav is not None:
                return nav.on_key(event)
            return None

        # ── Selection state ──────────────────────────────────────────────
        def _select(slot):
            state["slot"] = slot
            for s, entry in state["cards"].items():
                if s == slot:
                    entry["card"].configure(highlightbackground=Theme.ACCENT,
                                            highlightthickness=2)
                    entry["slot_lbl"].pack_forget()
                    entry["btn_frame"].pack(anchor=tk.E)
                else:
                    entry["card"].configure(highlightbackground=Theme.BORDER,
                                            highlightthickness=1)
                    entry["btn_frame"].pack_forget()
                    entry["slot_lbl"].pack(anchor=tk.E)

            if slot is None:
                state["nav"] = state["list_nav"]
                if state["list_nav"] is not None:
                    # Return the outline to the card list.
                    state["list_nav"].select(state["list_index"])
                bottom_btn.configure(text="Close")
                hint.configure(text="Click a save file to load or delete it.",
                               fg=Theme.TEXT_DIM)
                return

            # Card selected: fade the list outline and outline the inline
            # Load / Delete buttons (Load first — Enter then activates it).
            if state["list_nav"] is not None:
                state["list_nav"].clear_outline()
            entry = state["cards"].get(slot)
            if entry is not None:
                state["action_nav"] = NavGroup(
                    panel.holder,
                    [
                        (entry["load_wrap"], entry["load_btn"]),
                        (entry["delete_wrap"], entry["delete_btn"]),
                    ],
                    idle_color=Theme.BG_CARD,
                )
                state["nav"] = state["action_nav"]
            bottom_btn.configure(text="Cancel")
            name = state["info"].get(slot, {}).get("name", "Unknown")
            hint.configure(text=f"Selected: Savefile {slot} — {name}",
                           fg=Theme.TEXT)

        # ── Card rendering ───────────────────────────────────────────────
        def _make_card(slot, info):
            # Wrapper frame carries the white keyboard outline (Tk buttons
            # ignore highlight rings on Windows); the card's own accent ring
            # means "selected for action".
            wrapper = tk.Frame(
                cards, bg=Theme.BG_DARK,
                highlightthickness=1, highlightbackground=Theme.BG_DARK,
            )
            wrapper.pack(fill=tk.X, pady=2)

            card = tk.Frame(
                wrapper, bg=Theme.BG_CARD,
                highlightthickness=1, highlightbackground=Theme.BORDER,
                cursor="hand2",
            )
            card.pack(fill=tk.X, padx=2, pady=2)

            # Right side: "Savefile N" normally, replaced by Load / Delete
            # when this card is selected.  Packed first so the buttons always
            # get their space and can never be squeezed out.
            right = tk.Frame(card, bg=Theme.BG_CARD)
            right.pack(side=tk.RIGHT, anchor=tk.E, padx=(8, 12), pady=6)

            slot_lbl = tk.Label(
                right, text=f"Savefile {slot}",
                bg=Theme.BG_CARD, fg=Theme.TEXT_HEADER, font=Theme.FONT_BOLD,
            )
            slot_lbl.pack(anchor=tk.E)

            btn_frame = tk.Frame(right, bg=Theme.BG_CARD)

            load_wrap = tk.Frame(
                btn_frame, bg=Theme.BG_CARD,
                highlightthickness=1, highlightbackground=Theme.BG_CARD,
            )
            load_wrap.pack(side=tk.LEFT)
            card_load_btn = tk.Button(
                load_wrap, text="Load", command=lambda s=slot: _do_load(s),
                width=6, bg=Theme.ACCENT, fg=Theme.TEXT_HEADER,
                activebackground=Theme.ACCENT_HOVER,
                font=Theme.FONT_BOLD, cursor="hand2",
            )
            card_load_btn.pack(padx=2, pady=2)

            delete_wrap = tk.Frame(
                btn_frame, bg=Theme.BG_CARD,
                highlightthickness=1, highlightbackground=Theme.BG_CARD,
            )
            delete_wrap.pack(side=tk.LEFT, padx=(6, 0))
            card_delete_btn = tk.Button(
                delete_wrap, text="Delete", command=lambda s=slot: _do_delete(s),
                width=7, bg=Theme.BUTTON_BG, fg=Theme.ACCENT,
                activebackground=Theme.BUTTON_ACTIVE_BG,
                activeforeground=Theme.ACCENT_HOVER,
                font=Theme.FONT_BOLD, cursor="hand2",
            )
            card_delete_btn.pack(padx=2, pady=2)

            # Left side: character info (always visible)
            info_frame = tk.Frame(card, bg=Theme.BG_CARD)
            info_frame.pack(side=tk.LEFT, anchor=tk.W, padx=(12, 8), pady=8)
            name_lbl = tk.Label(
                info_frame, text=info["name"],
                bg=Theme.BG_CARD, fg=Theme.TEXT_HEADER, font=Theme.FONT_BOLD,
            )
            name_lbl.pack(anchor=tk.W)
            detail_lbl = tk.Label(
                info_frame,
                text=f"Lv {info['level']}  •  {info['race']}  •  {info['class']}",
                bg=Theme.BG_CARD, fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL,
            )
            detail_lbl.pack(anchor=tk.W)

            # Clicking anywhere on the card toggles selection; clicking the
            # selected card again backs out of the pending action.
            def _click(_event=None, s=slot):
                if state["slot"] == s:
                    _select(None)
                else:
                    _remember_slot_index(s)
                    _select(s)

            for widget in (wrapper, card, info_frame, name_lbl, detail_lbl,
                           slot_lbl):
                widget.bind("<Button-1>", _click)
            state["cards"][slot] = {
                "card": card,
                "wrapper": wrapper,
                "slot_lbl": slot_lbl,
                "btn_frame": btn_frame,
                "load_wrap": load_wrap,
                "load_btn": card_load_btn,
                "delete_wrap": delete_wrap,
                "delete_btn": card_delete_btn,
            }

        def _build_list_nav():
            """Outline targets for the list: cards in order, then Close."""
            entries = [
                (state["cards"][s]["wrapper"], lambda s=s: _activate_card(s))
                for s in state["order"]
            ]
            entries.append((bottom_wrap, _on_bottom_action))
            return NavGroup(
                panel.holder,
                entries,
                start=state["list_index"],
                on_change=_on_list_change,
            )

        def _rebuild():
            state["slot"] = None
            state["action_nav"] = None
            for child in cards.winfo_children():
                child.destroy()
            state["cards"].clear()
            state["info"] = list_save_details()
            state["order"] = sorted(state["info"])
            for slot in state["order"]:
                _make_card(slot, state["info"][slot])
            if not state["info"]:
                tk.Label(
                    cards, text="No save files found.",
                    bg=Theme.BG_DARK, fg=Theme.TEXT_DIM, font=Theme.FONT,
                ).pack(pady=24)
            state["list_nav"] = _build_list_nav()
            _select(None)

        def _on_escape(_event=None):
            _on_bottom_action()   # Escape = Cancel while selected, else Close

        # ── Keyboard bindings ────────────────────────────────────────────
        # The panel holder owns keyboard focus; one dispatcher forwards keys
        # to the active NavGroup (card list, or inline Load/Delete actions).
        for sequence in (
            "<Up>", "<Down>", "<Left>", "<Right>",
            "<Tab>", "<Shift-Tab>", "<ISO_Left_Tab>",
            "<Home>", "<End>",
            "<Return>", "<KP_Enter>", "<space>",
        ):
            panel.holder.bind(sequence, _on_browser_key)

        _rebuild()
        # Escape = Cancel while a card is selected, else Close.
        panel.finalize(on_escape=_on_escape)

