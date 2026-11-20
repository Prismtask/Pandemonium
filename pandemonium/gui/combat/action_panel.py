"""
gui/combat/action_panel.py — Dynamic action buttons for combat.

Builds Attack, Defend, Skills, Items, Flee, Capture buttons from
combat/action_menu.py. Handles cooldown grey-out and target-selection mode.
"""

import re
import tkinter as tk

import pandemonium.progression.karma as karma
from pandemonium.gui.theme import Theme
from pandemonium.gui.widgets.keyboard_nav import NavGroup
from pandemonium.combat.action_menu import get_action_menu
from pandemonium.combat.ally import _ally_action_menu
from pandemonium.combat.weapon.black_silence_gloves import _actor_has_black_silence_gloves
from pandemonium.core.utils import display_name


class ActionPanel(tk.Frame):
    """
    Bottom action bar for the combat screen.
    Dynamically generates buttons based on the current combatant's available actions.
    """

    # Button rows the panel ALWAYS reserves (see _reserve_rows) so 1-row and
    # multi-row menus render at identical height — spare room from the HUD rework.
    # Wave 2 (2026-10-15): 9 skills + utility buttons (and the gloves' 9
    # workshops + Furioso) wrap to 3 rows, so the reservation is now 3.
    MIN_ROWS = 3
    # Fixed buttons per row. Every button is the same size everywhere, so the
    # count no longer varies with the content (2026-11-19).
    MAX_PER_ROW = 7
    # THE standard action-button width, in characters. The theme font is
    # monospace, so this is an exact pixel width on every menu — actions,
    # ally turns and the capture prompt all share it. Anything longer is cut
    # with an ellipsis. 24 chars ≈ 202px: seven buttons fit a 1536px window.
    BTN_WIDTH = 24
    # Trailing value tags — workshop attributes and karma/cost values — that
    # _fit_label keeps visible when it shortens an overlong label.
    _TRAILING_TAG = re.compile(r"(\s+\[[^\[\]()]*\]|\s+\([^\[\]()]*\))\s*$")

    # ── Two-tier menu (2026-11-19) ─────────────────────────────────────────
    # The top level shows Attack / Skill / Defend / Use item / Flee (plus
    # Capture, Switch and free actions when they apply). Skill opens the
    # class + equipment actives; with the Black Silence Gloves equipped,
    # Attack opens the nine workshops + Furioso instead (the gloves replace
    # the basic attack AND all class skills). These wrapper keys are GUI-only
    # — they are NEVER passed to on_action/engine; the engine only ever
    # receives real menu keys.
    KEY_ATTACK_MENU = "__attack__"
    KEY_SKILL_MENU = "__skill__"
    KEY_BACK = "__back__"

    # Top-level order. Slots missing from the menu are skipped; unknown
    # top-level keys keep their engine order at the end (never dropped).
    ROOT_ORDER = ("c", "a", KEY_ATTACK_MENU, KEY_SKILL_MENU,
                  "d", "u", "b", "t", "f", "s")
    # Keys that stay on the top-level bar (the rest live in a submenu).
    TOP_KEYS = frozenset({"c", "a", "d", "f", "u", "b", "t", "s"})

    def __init__(self, parent, on_action=None, **kwargs):
        """
        Args:
            on_action: callback(action_key: str) called when a button is clicked.
        """
        super().__init__(parent, bg=Theme.BG_DARK, **kwargs)
        self.on_action = on_action
        self._buttons = {}
        self._button_wraps = {}  # action key -> outline wrapper frame
        self._entries = []    # [(key, text, category, enabled)] in engine order
        self._submenu = None  # None | "attack" | "skill"
        # Thin-outline keyboard navigation (same NavGroup style as the
        # other screens). Rebuilt whenever the menu changes.
        self._nav = None
        self._nav_keys = []       # action key per nav entry, menu order
        self._nav_positions = []  # (row, col) per nav entry, for Up/Down
        self._build_layout()

    def _build_layout(self):
        # Section label
        self.section_label = tk.Label(
            self,
            text="ACTIONS",
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_DIM,
            font=Theme.FONT_BOLD,
        )
        self.section_label.pack(anchor=tk.W, pady=(0, 4))

        # Button container (flows left-to-right, wrapping)
        self.btn_container = tk.Frame(self, bg=Theme.BG_DARK)
        self.btn_container.pack(fill=tk.X)

        # Target-mode instruction label — PACKED ALWAYS (its one-line slot is
        # reserved even when idle) so entering/leaving target selection never
        # changes the panel height. Its text is cleared when not targeting.
        self.target_instruction = tk.Label(
            self,
            text="",
            bg=Theme.BG_DARK,
            fg=Theme.ACCENT,
            font=Theme.FONT_BOLD,
            anchor=tk.W,
            height=1,
        )
        self.target_instruction.pack(fill=tk.X, pady=(4, 4), before=self.btn_container)

        # Cooldown messages — ALWAYS two lines tall, even when empty, so the
        # panel height never jumps between 1-line and 2-line cooldown lists
        # (mirrors the reserved second button row below).
        self.cooldown_label = tk.Label(
            self,
            text="",
            bg=Theme.BG_DARK,
            fg=Theme.TEXT_DIM,
            font=(Theme.FONT_FAMILY, 9),
            anchor=tk.W,
            justify=tk.LEFT,
            height=2,
            wraplength=700,
        )
        self.cooldown_label.pack(fill=tk.X, pady=(4, 0))

        # Wrap cooldown text at the panel's real width instead of a fixed
        # 700px cap — uses the space freed by the HUD rework.
        self._cooldown_wrap = 700
        self.bind("<Configure>", self._on_panel_configure)

        # ── Reserve the panel's final height from the very first frame ────
        # The combat screen sizes the Continue/Leave Battle slot from
        # `reserved_height`, and the first prompt of a fight ('Press Enter to
        # begin...') arrives before set_actions() ever runs — so the two
        # button rows must be reserved here too, using a probe button to
        # measure the real row height.
        probe = tk.Button(
            self.btn_container, text="X",
            font=Theme.FONT_BOLD, relief=tk.RAISED, borderwidth=2,
        )
        self.update_idletasks()
        row_h = probe.winfo_reqheight() + 4  # + button pady (2 top/bottom)
        probe.destroy()
        for _ in range(self.MIN_ROWS):
            spacer = tk.Frame(self.btn_container, bg=self.btn_container["bg"], height=row_h)
            spacer.pack(fill=tk.X, pady=1)

        # Canonical height — constant for the panel's whole lifetime;
        # set_actions() rebuilds its rows at exactly this size.
        self.update_idletasks()
        self.reserved_height = self.winfo_reqheight()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_actions(self, player, enemies, active_ally=None, cooldowns=None):
        """Rebuild the action bar from the current two-tier menu."""
        # Fetch menu
        ally_name = None
        if active_ally is not None:
            menu_str, valid_actions, _disabled = _ally_action_menu(active_ally, player, enemies)
            ally_name = display_name(active_ally) or "Ally"
            actor = active_ally
        else:
            menu_str, valid_actions, _disabled = get_action_menu(player, enemies)
            actor = player

        # Header is always "ACTIONS" — player and ally turns must match.
        # The lighter panel tint is the only remaining ally-turn cue.
        self.section_label.config(text="ACTIONS", fg=Theme.TEXT_DIM)
        if ally_name:
            self.config(bg="#16213e")
            self.btn_container.config(bg="#16213e")
        else:
            self.config(bg=Theme.BG_DARK)
            self.btn_container.config(bg=Theme.BG_DARK)

        # Parse the engine menu once, in its own order, and tag every entry
        # with the tier it belongs to. Used workshops stay greyed in place
        # instead of jumping to the end of the menu.
        has_gloves = _actor_has_black_silence_gloves(actor)
        valid_set = set(valid_actions)
        self._entries = []
        for part in menu_str.split("  "):
            match = re.match(r"^\[([^\]]+)\](.*)$", part.strip())
            if not match:
                continue
            key = match.group(1).lower()
            label = match.group(2).strip()
            self._entries.append((
                key,
                f"[{key.upper()}] {label}",
                self._category_for(key, has_gloves),
                key in valid_set,
            ))
        self._submenu = None
        self._render()

        # Cooldown messages
        if cooldowns:
            self.cooldown_label.config(text="  |  ".join(cooldowns))
        else:
            self.cooldown_label.config(text="")

    def set_capture_choice_actions(self, on_action, player=None, house_full=False):
        """Show the capture disposition buttons (Karma-aware)."""
        # Clear existing
        for widget in self.btn_container.winfo_children():
            widget.destroy()
        self._buttons.clear()
        self._entries = []
        self._submenu = None

        karma_on = karma.is_enabled(player)
        if house_full:
            title = "⌖ House Full — Choose What Happens to Her"
            if karma_on:
                choices = [
                    ("1", "Sell to a Broker"),
                    ("2", "Sell to a Slaver (−5 Karma)"),
                    ("3", "Release (+1 Karma)"),
                ]
            else:
                choices = [
                    ("1", "Sell to a Broker"),
                    ("2", "Release to Wild"),
                ]
        else:
            title = "⌖ Duplicate Monster Girl Captured — Choose Action"
            if karma_on:
                choices = [
                    ("1", "Sell to a Broker"),
                    ("2", "Sell to a Slaver (−5 Karma)"),
                    ("3", "Release (+1 Karma)"),
                    ("4", "Bond (+20 Affection)"),
                ]
            else:
                choices = [
                    ("1", "Sell to a Broker"),
                    ("2", "Release to Wild"),
                    ("3", "Bond (+20 Affection)"),
                ]

        self.section_label.config(text=title, fg="#e67e22")
        self.config(bg=Theme.BG_DARK)
        self.btn_container.config(bg=Theme.BG_DARK)
        self.target_instruction.config(text="")
        self.cooldown_label.config(text="")
        # Same uniform sizing + row reservation as the regular panel so this
        # prompt keeps the exact panel height (see _build_buttons).
        self._build_buttons([(key, f"[{key}] {label}", True) for key, label in choices])

    def set_target_mode(self, enabled: bool, prompt: str = "Select a target", is_ally_target: bool = False):
        """Enable/disable target selection mode."""
        if enabled:
            self.section_label.config(text=prompt, fg=Theme.ACCENT)
            # Instruction label is always packed (slot reserved) — set text only
            target_type = "ally" if is_ally_target else "enemy"
            self.target_instruction.config(
                text=(f"▶ Press 1–9 or ←/→ to pick a {target_type}"
                      "  (Enter confirm · Esc cancel)"),
            )
            # Disable non-target actions, keep Cancel implicit
            for key, btn in self._buttons.items():
                if key not in ("0", "cancel"):
                    btn.config(state=tk.DISABLED)
            self._clear_nav()
        else:
            self.section_label.config(text="ACTIONS", fg=Theme.TEXT_DIM)
            self.target_instruction.config(text="")
            self.config(bg=Theme.BG_DARK)
            self.btn_container.config(bg=Theme.BG_DARK)
            for btn in self._buttons.values():
                btn.config(state=tk.NORMAL)
            self._refresh_nav()

    def enable_all(self):
        """Enable all buttons."""
        for btn in self._buttons.values():
            btn.config(state=tk.NORMAL)
        self._refresh_nav()

    # ── Outline keyboard navigation (arrows + Enter) ─────────────────────────

    def on_nav_key(self, event):
        """Handle a navigation key press; returns 'break' when consumed.

        The combat screen owns keyboard focus, so it forwards key events
        here instead of relying on widget focus (which would draw Tk's own
        dotted focus rectangle inside a button).
        """
        if self._nav is None or not self._nav.widgets:
            return None
        key = event.keysym
        if key == "Left":
            self._nav.move(-1)
            return "break"
        if key == "Right":
            self._nav.move(1)
            return "break"
        if key in ("Up", "Down"):
            self._move_nav_vertical(-1 if key == "Up" else 1)
            return "break"
        if key == "ISO_Left_Tab":
            self._nav.move(-1)
            return "break"
        if key == "Tab":
            self._nav.move(-1 if event.state & 0x1 else 1)
            return "break"
        if key == "Home":
            self._nav.select(0)
            return "break"
        if key == "End":
            self._nav.select(len(self._nav.widgets) - 1)
            return "break"
        if key in ("Return", "KP_Enter", "space"):
            self._nav.activate()
            return "break"
        return None

    def select_action(self, key):
        """Sync the outline to `key` (used when a hotkey is pressed)."""
        if self._nav is None:
            return
        try:
            index = self._nav_keys.index(key)
        except ValueError:
            return
        self._nav.select(index)

    def _refresh_nav(self):
        """Rebuild the outline entries over the enabled buttons."""
        self._clear_nav()
        entries = []
        keys = []
        positions = []
        for i, (key, btn) in enumerate(self._buttons.items()):
            wrap = self._button_wraps.get(key)
            if wrap is None or str(btn.cget("state")) == "disabled":
                continue
            entries.append((wrap, btn))
            keys.append(key)
            positions.append((i // self.MAX_PER_ROW, i % self.MAX_PER_ROW))
        if not entries:
            return
        self._nav = NavGroup(
            self, entries,
            idle_color=self.btn_container["bg"],
            focus_color=Theme.TEXT_HEADER,
        )
        self._nav_keys = keys
        self._nav_positions = positions

    def _clear_nav(self):
        """Remove the outline and forget the entries."""
        if self._nav is not None:
            self._nav.clear_outline()
        self._nav = None
        self._nav_keys = []
        self._nav_positions = []

    def _move_nav_vertical(self, delta):
        """Move to the nearest button on the row above/below."""
        if self._nav is None or not self._nav_positions:
            return
        rows = {}
        for i, (row, col) in enumerate(self._nav_positions):
            rows.setdefault(row, []).append((i, col))
        row, col = self._nav_positions[self._nav.index]
        candidates = rows.get(row + delta)
        if not candidates:
            return
        best = min(candidates, key=lambda pair: abs(pair[1] - col))
        self._nav.select(best[0])

    def disable_all(self):
        """Disable all buttons (e.g. during enemy turns)."""
        for btn in self._buttons.values():
            btn.config(state=tk.DISABLED)
        self._clear_nav()

    # ── Two-tier navigation (GUI-only — never sends a key) ───────────────────

    def in_submenu(self):
        """True while a Skill/Attack submenu is open."""
        return self._submenu is not None

    def go_back(self):
        """Return to the top-level bar. Returns True when it did."""
        if self._submenu is None:
            return False
        self._open_submenu(None)
        return True

    def open_attack_submenu(self):
        """Open the gloves' workshop list (the 'A' shortcut on gloved turns)."""
        if self._submenu is None and self._has_category("attack"):
            self._open_submenu("attack")
            return True
        return False

    def open_skill_submenu(self):
        """Open the skill list (the 'K' shortcut)."""
        if self._submenu is None and self._has_category("skill"):
            self._open_submenu("skill")
            return True
        return False

    # ── Internals ─────────────────────────────────────────────────────────────

    def _category_for(self, key, has_gloves):
        """Tier for an engine menu key.

        Black Silence Gloves replace the basic attack AND all class skills:
        every numbered entry (1-9, 0 = Furioso) is a workshop attack, so the
        whole kit lives under Attack. Everything else that is not a top-level
        utility is skill-class (class skills, weapon actives, brush exhibits).
        """
        if key in self.TOP_KEYS:
            return "top"
        if has_gloves:
            return "attack"
        return "skill"

    def _has_category(self, category):
        return any(entry[2] == category for entry in self._entries)

    def _open_submenu(self, submenu):
        self._submenu = submenu
        self._render()

    def _render(self):
        """Draw the top-level bar or the open submenu."""
        for widget in self.btn_container.winfo_children():
            widget.destroy()
        self._buttons.clear()
        if self._submenu is None:
            self._build_buttons(self._root_specs())
        else:
            self._build_buttons(self._submenu_specs())

    def _root_specs(self):
        """Top-level buttons in ROOT_ORDER, with the two submenu wrappers."""
        by_key = {key: (key, text, enabled) for key, text, _cat, enabled in self._entries}
        specs = []
        used = set()
        for slot in self.ROOT_ORDER:
            if slot == self.KEY_ATTACK_MENU:
                if self._has_category("attack"):
                    specs.append((slot, "[A] Attack", True))
                continue
            if slot == self.KEY_SKILL_MENU:
                if self._has_category("skill"):
                    specs.append((slot, "[K] Skill", True))
                continue
            entry = by_key.get(slot)
            if entry:
                specs.append(entry)
                used.add(slot)
        # Unknown top-level keys keep engine order (never silently dropped).
        for key, text, category, enabled in self._entries:
            if category == "top" and key not in used:
                specs.append((key, text, enabled))
        return specs

    def _submenu_specs(self):
        """Entries of the open submenu, plus a Back button."""
        specs = [(key, text, enabled)
                 for key, text, category, enabled in self._entries
                 if category == self._submenu]
        specs.append((self.KEY_BACK, "[Esc] Back", True))
        return specs

    def _build_buttons(self, specs):
        """Create the panel's buttons at the one standard size.

        `specs` is a list of `(action_key, text, enabled)` tuples in menu
        order. Every button — player, ally, capture prompt — is exactly
        `BTN_WIDTH` characters wide; a longer label is shortened with an
        ellipsis, keeping any trailing value tag (`[STR]`, `(−5 Karma)`)
        visible so the grid never goes ragged or hides the numbers.
        """
        self._button_wraps = {}
        self._clear_nav()
        if not specs:
            self._reserve_rows([])
            return

        rows = []
        panel_bg = self.btn_container["bg"]
        for i, (key, text, enabled) in enumerate(specs):
            if i % self.MAX_PER_ROW == 0:
                row_frame = tk.Frame(self.btn_container, bg=panel_bg)
                row_frame.pack(fill=tk.X, pady=1)
                rows.append(row_frame)
            row_frame = rows[-1]

            # Keep the key prefix intact; shorten only the label's middle.
            text = self._fit_label(text)

            # The keyboard-focus outline lives on a wrapper frame — Windows
            # Tk buttons ignore the highlight ring entirely (same wrapper
            # pattern as the other screens). Inner pad 1 + ring 1 + outer
            # pad 2 keeps the exact former footprint of padx=4/pady=2.
            wrap = tk.Frame(
                row_frame,
                bg=panel_bg,
                highlightthickness=1,
                highlightbackground=panel_bg,
                highlightcolor=Theme.TEXT_HEADER,
                takefocus=0,
            )
            wrap.pack(side=tk.LEFT, padx=2)

            if enabled:
                btn = tk.Button(
                    wrap,
                    text=text,
                    width=self.BTN_WIDTH,
                    bg=Theme.BUTTON_BG,
                    fg=Theme.BUTTON_FG,
                    activebackground=Theme.BUTTON_ACTIVE_BG,
                    activeforeground=Theme.BUTTON_ACTIVE_FG,
                    font=Theme.FONT_BOLD,
                    relief=tk.RAISED,
                    borderwidth=2,
                    cursor="hand2",
                    command=lambda k=key, e=None: self._click(k),
                )
                btn.bind("<Enter>", lambda e=None, b=btn: b.config(bg=Theme.BUTTON_ACTIVE_BG))
                btn.bind("<Leave>", lambda e=None, b=btn: b.config(bg=Theme.BUTTON_BG))
            else:
                btn = tk.Button(
                    wrap,
                    text=text,
                    width=self.BTN_WIDTH,
                    bg=Theme.BG_MID,
                    fg=Theme.TEXT_DIM,
                    font=Theme.FONT_BOLD,
                    relief=tk.SUNKEN,
                    borderwidth=2,
                    state=tk.DISABLED,
                )
            btn.pack(padx=1, pady=1)
            self._buttons[key] = btn
            self._button_wraps[key] = wrap

        # Pad a short menu with invisible spacer rows so every menu keeps the
        # same panel height (constant panel size).
        self._reserve_rows(rows)
        self._refresh_nav()

    def _fit_label(self, text):
        """Fit `text` into BTN_WIDTH, keeping a trailing value tag.

        Workshop attributes and karma/cost values are gameplay information,
        so they survive truncation:
            '[4] Old Boys Workshop [STR]'      -> '[4] Old Boys Wo... [STR]'
            '[2] Sell to a Slaver (−5 Karma)'  -> '[2] Sell t... (−5 Karma)'
        Labels without a trailing tag fall back to a plain tail ellipsis.
        """
        if len(text) <= self.BTN_WIDTH:
            return text
        match = self._TRAILING_TAG.search(text)
        if match:
            tag = match.group(1)  # includes the space before the tag
            head_budget = self.BTN_WIDTH - len(tag) - 3
            if head_budget >= 6:  # keep the key prefix + some of the name
                return text[:head_budget].rstrip() + "..." + tag
        return text[: self.BTN_WIDTH - 3].rstrip() + "..."

    def _reserve_rows(self, rows):
        """Pad `rows` with invisible spacer frames up to MIN_ROWS so short
        menus keep the same panel height as a full menu."""
        self.update_idletasks()
        row_h = rows[0].winfo_reqheight() if rows else 0
        while len(rows) < self.MIN_ROWS:
            spacer = tk.Frame(self.btn_container, bg=self.btn_container["bg"], height=row_h)
            spacer.pack(fill=tk.X, pady=1)
            rows.append(spacer)

    def _on_panel_configure(self, event):
        """Re-wrap cooldown text at the panel's actual (spare) width."""
        wrap = max(300, event.width - 4)
        if wrap != self._cooldown_wrap:
            self._cooldown_wrap = wrap
            self.cooldown_label.config(wraplength=wrap)

    def _click(self, key):
        """Handle button click with brief visual flash (or submenu navigation)."""
        # Keep the keyboard outline in sync with mouse clicks.
        self.select_action(key)
        # Two-tier navigation is GUI-only — these keys never reach the engine.
        if key == self.KEY_ATTACK_MENU:
            self._open_submenu("attack")
            return
        if key == self.KEY_SKILL_MENU:
            self._open_submenu("skill")
            return
        if key == self.KEY_BACK:
            self._open_submenu(None)
            return
        btn = self._buttons.get(key)
        if btn:
            btn.config(bg=Theme.ACCENT)
            btn.after(100, lambda b=btn: b.config(bg=Theme.BUTTON_ACTIVE_BG if b.cget("state") != "disabled" else Theme.BUTTON_BG))
        if self.on_action:
            self.on_action(key)
