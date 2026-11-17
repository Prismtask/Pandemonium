"""
gui/screens/inventory_screen.py — Tabbed inventory: characters (stats, gear, skills), bag, journal.

Replaces the terminal-based inventory_ui.py with a full GUI using tkinter's Notebook.
"""

import tkinter as tk
from tkinter import ttk

from pandemonium.gui.screens.base_screen import BaseScreen
from pandemonium.gui.theme import Theme
from pandemonium.inventory.core import format_scaling_stat
from pandemonium.core.utils import display_name
from pandemonium.core.character import _reconcile_heroine_vorpal_skills
from pandemonium.core.character import player_max_hp
from pandemonium.resources.races_classes import ATTRIBUTES
from pandemonium.combat.stat_milestones import format_milestone_label
from pandemonium.progression.titles import combat_stat_bonus as title_bonus
from pandemonium.combat.stat_milestones import format_milestone_bonuses
from pandemonium.resources.skill_loader import PROFESSIONS
from pandemonium.resources.enemies import ENEMIES
from pandemonium.resources.item_generation import is_flower_item
import pandemonium.progression.titles as _titles
import pandemonium.progression.karma as karma
import pandemonium.progression.titles as title_mod
from pandemonium.core.events import format_day_delta
from pandemonium.core.events import format_short_date
from pandemonium.core.events import format_date
from pandemonium.combat.form_perks import describe_item_perk
from pandemonium.resources.items import ITEMS
from pandemonium.resources.unique_effects import unique_effect_text
from pandemonium.gui.widgets.confirm_dialog import ok_dialog
from pandemonium.gui.widgets.confirm_dialog import confirm_dialog


class InventoryScreen(BaseScreen):
    """
    Tabbed inventory interface.

    Tabs:
        1. Characters (sub-tab per character — You, then each ally — each
           with an Overview view and a Skills view)
        2. Bag
        3. Journal
        4. Event Horizon (only while a run is active/suspended)

    Constructor kwargs:
        is_overlay  — if True, this screen is shown via push_overlay (e.g. from
                      dungeon); the Back button dismisses the overlay instead of
                      using the history stack.
    """

    def __init__(self, parent, screen_manager, is_overlay=False, **kwargs):
        self.is_overlay = is_overlay
        self._equip_target_ally = None   # If set, bag "Equip" goes to this ally dict
        self._equip_target_slot = None   # Desired slot hint (weapon/armor/accessory1/accessory2)
        self._char_tab_index = 0         # Selected Characters sub-tab: 0 = you, 1.. = allies
        self._char_view = "overview"     # "overview" | "skills" — shared by every character page
        self._char_pages = []            # One dict per character sub-tab (see _refresh_characters_tab)
        self._char_scroll = {}           # (id(character), view) -> last scroll fraction
        self.char_notebook = None
        super().__init__(parent, screen_manager, **kwargs)

    def build_ui(self):
        self.sm.clear_log()
        self.sm.update_top_bar("Inventory")

        # ── Main container ───────────────────────────────────────────────────
        container = self.styled_frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Inv.TNotebook",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT,
            tabmargins=[2, 5, 2, 0],
        )
        style.configure(
            "Inv.TNotebook.Tab",
            background=Theme.BG_MID,
            foreground=Theme.TEXT,
            font=Theme.FONT_BOLD,
            padding=[10, 4],
        )
        style.map(
            "Inv.TNotebook.Tab",
            background=[("selected", Theme.BG_LIGHT)],
            foreground=[("selected", Theme.TEXT_HEADER)],
        )

        # Sub-notebook style for ally tabs (slightly smaller)
        style.configure(
            "Ally.TNotebook",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT,
            tabmargins=[2, 5, 2, 0],
        )
        style.configure(
            "Ally.TNotebook.Tab",
            background=Theme.BG_MID,
            foreground=Theme.TEXT,
            font=Theme.FONT,
            padding=[8, 3],
        )
        style.map(
            "Ally.TNotebook.Tab",
            background=[("selected", Theme.BG_LIGHT)],
            foreground=[("selected", Theme.TEXT_HEADER)],
        )

        self.notebook = ttk.Notebook(container, style="Inv.TNotebook")
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Create tabs
        self._build_characters_tab()
        self._build_bag_tab()
        self._build_journal_tab()
        # Event Horizon tab: live/suspended run or a quiet history stub
        if self._eh_tab_visible():
            self._build_eh_tab()

        # Loot lands in the bag while this screen is hidden — rebuild the Bag
        # whenever the player switches to it (flowers were the visible miss).
        self.notebook.bind("<<NotebookTabChanged>>", self._on_main_tab_changed)

        # ── Bottom action bar ────────────────────────────────────────────────
        action_frame = tk.Frame(container, bg=Theme.BG_DARK)
        action_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

        back_label = "← Close" if self.is_overlay else "← Back"
        self.styled_button(
            action_frame,
            text=back_label,
            command=self._on_back,
            width=16,
        ).pack(side=tk.LEFT)

        refresh_btn = self.styled_button(
            action_frame,
            text="Refresh",
            command=self._refresh_all,
            width=12,
        )
        refresh_btn.pack(side=tk.RIGHT)

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 1 — Characters  (one sub-tab per character: You, then each ally)
    #
    #  Every character page has the same two views, picked with the
    #  Overview | Skills buttons at the top of the page:
    #      Overview — identity (you), vitals, attributes, equipment, milestones
    #      Skills   — passive + skills (battle loadout for you, the kit for allies)
    #  The chosen view is shared by all pages, so switching character keeps you
    #  on the same view — handy for comparing skills across the party.
    #  Pages are drawn lazily: only the visible one is built.
    # ═══════════════════════════════════════════════════════════════════════

    def _build_characters_tab(self):
        self.characters_frame = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(self.characters_frame, text=" Characters ")
        self.characters_frame.grid_rowconfigure(0, weight=1)
        self.characters_frame.grid_columnconfigure(0, weight=1)
        self._refresh_characters_tab()

    def _characters(self):
        """Player first, then allies — the order of the Characters sub-tabs."""
        if not self.player:
            return []
        return [self.player] + list(self.player.get("allies", []))

    def _current_char_index(self):
        """Index of the visible character sub-tab (falls back to the last known)."""
        nb = self.char_notebook
        if nb is not None:
            try:
                selected = nb.select()
                if selected:
                    return nb.index(selected)
            except (tk.TclError, ValueError):
                pass
        return self._char_tab_index

    def _refresh_characters_tab(self):
        # Remember where the player was: which character, and scroll positions.
        self._save_char_scroll()
        self._char_tab_index = max(0, self._current_char_index())

        for w in self.characters_frame.winfo_children():
            w.destroy()
        self.char_notebook = None
        self._char_pages = []

        if not self.player:
            self.styled_label(self.characters_frame, text="No player data.").pack(pady=20)
            return

        chars = self._characters()
        nb = ttk.Notebook(self.characters_frame, style="Ally.TNotebook")
        nb.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.char_notebook = nb

        for idx, char in enumerate(chars):
            is_player = idx == 0
            frame = tk.Frame(nb, bg=Theme.BG_DARK)
            frame.grid_rowconfigure(1, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            bar = tk.Frame(frame, bg=Theme.BG_DARK)          # Overview | Skills
            bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
            body = tk.Frame(frame, bg=Theme.BG_DARK)         # scrollable content
            body.grid(row=1, column=0, sticky="nsew")
            label = " You " if is_player else f" {display_name(char) or 'Ally'} "
            nb.add(frame, text=label)
            self._char_pages.append({
                "char": char, "is_player": is_player,
                "bar": bar, "body": body,
                "canvas": None,   # scroll canvas of the drawn view
                "view": None,     # view currently drawn (None = not drawn yet)
            })

        # Restore the previously selected character (clamped if the party shrank).
        index = min(self._char_tab_index, len(chars) - 1)
        self._char_tab_index = index
        nb.select(index)
        nb.bind("<<NotebookTabChanged>>", self._on_char_tab_changed)
        self._ensure_char_page(index)

    # ── Lazy page drawing ────────────────────────────────────────────────────

    def _on_char_tab_changed(self, _event=None):
        """Draw a character's page the first time (or in a new view) it is shown."""
        try:
            index = self._current_char_index()
            self._char_tab_index = index
            self._ensure_char_page(index)
        except tk.TclError:
            pass

    def _ensure_char_page(self, index):
        """Draw the page at *index* unless it is already drawn in the current view."""
        if not (0 <= index < len(self._char_pages)):
            return
        page = self._char_pages[index]
        if page["view"] != self._char_view:
            self._render_char_page(page)

    def _rerender_current_char_page(self):
        """Redraw just the visible page (scroll position is kept)."""
        index = self._current_char_index()
        if 0 <= index < len(self._char_pages):
            self._render_char_page(self._char_pages[index])

    def _set_char_view(self, view):
        """Switch every character page between 'overview' and 'skills'."""
        if view == self._char_view:
            return
        self._char_view = view
        self._ensure_char_page(self._current_char_index())

    def _render_char_page(self, page):
        char, is_player = page["char"], page["is_player"]
        self._save_page_scroll(page)          # keyed by the view being replaced

        for w in page["bar"].winfo_children():
            w.destroy()
        for w in page["body"].winfo_children():
            w.destroy()
        page["canvas"] = None
        page["view"] = self._char_view

        if not is_player:
            # Safety net: ensures innate/learned skills match the vorpal flags
            # even if the load-time reconciliation in ensure_player_fields was
            # missed.
            _reconcile_heroine_vorpal_skills(char, self.player)

        self._render_view_toggle(page["bar"])

        canvas, inner = self._make_scroll_area(page["body"])
        page["canvas"] = canvas

        if self._char_view == "skills":
            self._render_character_skills(inner, char, is_player)
        else:
            self._render_character_overview(inner, char, is_player)

        self._restore_page_scroll(page)

    def _render_view_toggle(self, bar):
        for key, label in (("overview", "Overview"), ("skills", "Skills")):
            active = self._char_view == key
            self.styled_button(
                bar, text=label, width=12,
                command=lambda k=key: self._set_char_view(k),
                bg=Theme.BG_LIGHT if active else Theme.BG_MID,
                fg=Theme.TEXT_HEADER if active else Theme.TEXT_DIM,
            ).pack(side=tk.LEFT, padx=(0, 2))

    def _make_scroll_area(self, parent):
        """Vertical scroll container. Returns (canvas, inner_frame)."""
        scroll = tk.Scrollbar(parent)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(parent, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        # Stretch the content to the canvas width so boxes fill the page.
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        return canvas, inner

    # ── Scroll memory (per character + view, survives refreshes) ─────────────

    @staticmethod
    def _page_scroll_key(page):
        return (id(page["char"]), page["view"])

    def _save_page_scroll(self, page):
        canvas = page.get("canvas")
        if canvas is None or page.get("view") is None:
            return
        try:
            if canvas.winfo_exists():
                self._char_scroll[self._page_scroll_key(page)] = canvas.yview()[0]
        except tk.TclError:
            pass

    def _save_char_scroll(self):
        for page in self._char_pages:
            self._save_page_scroll(page)

    def _restore_page_scroll(self, page):
        fraction = self._char_scroll.get(self._page_scroll_key(page), 0.0)
        canvas = page["canvas"]
        if fraction > 0 and canvas is not None:
            self.after_idle(lambda c=canvas, y=fraction: self._scroll_canvas_to(c, y))

    @staticmethod
    def _scroll_canvas_to(canvas, fraction):
        try:
            # A freshly built canvas has no scroll region until geometry has
            # settled; moving before that is a silent no-op (jumps to top).
            canvas.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
            canvas.yview_moveto(fraction)
        except tk.TclError:
            pass

    # ── Overview view ────────────────────────────────────────────────────────

    def _render_character_overview(self, inner, char, is_player):
        """Identity/vitals, attributes + equipment side by side, milestones."""
        if is_player:
            self._render_personal_box(inner)
            hp = f"{char.get('current_hp', 0)}/{player_max_hp(char)}"
            info = f"HP: {hp}  |  Gold: {char.get('gold', 0)}"
            self.styled_label(inner, text=info).pack(anchor=tk.W, padx=4, pady=(0, 8))
        else:
            self._render_ally_header(inner, char)

        # Side by side so gear and the stat totals it feeds are visible
        # together without scrolling. Milestones (below) stay full width.
        columns = tk.Frame(inner, bg=Theme.BG_DARK)
        columns.pack(fill=tk.X, pady=4, padx=4)
        # 2 : 3 split — equipment rows carry more text than attribute rows.
        columns.grid_columnconfigure(0, weight=2, uniform="char_cols")
        columns.grid_columnconfigure(1, weight=3, uniform="char_cols")
        columns.grid_rowconfigure(0, weight=1)

        self._render_attributes_box(columns, char, is_player)
        self._render_equipment_box(columns, char, is_player)
        self._render_milestones_box(inner, char)

    def _render_ally_header(self, inner, ally):
        from pandemonium.combat.ally import get_growth_label
        defeated = ally.get("defeated") or ally.get("current_hp", 0) <= 0
        status_str = "  [INCAPACITATED]" if defeated else ""

        # ── Personal Information — ally mirror of the player's box ──────────
        # The player box lists Name / Race / Class. Allies have no class, so
        # that slot becomes a second Name line: the given name (nickname or
        # awakened name) first, then the species name, then the race.
        personal = tk.LabelFrame(
            inner, text=" Personal Information ", bg=Theme.BG_DARK,
            fg=Theme.TEXT, font=Theme.FONT_BOLD, highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        personal.pack(fill=tk.X, pady=4, padx=4)

        self.styled_label(
            personal,
            text=f"Name: {display_name(ally) or 'Ally'}   "
                 f"Level: {ally.get('level', 1)}{status_str}",
            fg=Theme.BUFF_NEGATIVE if defeated else Theme.ACCENT,
            font=Theme.FONT_BOLD,
        ).pack(anchor=tk.W, padx=6, pady=(4, 1))

        species = ally.get("name") or "Unknown"
        race = ally.get("race") or "Unknown"
        self.styled_label(
            personal, text=f"Name: {species}   Race: {race}",
        ).pack(anchor=tk.W, padx=6, pady=(1, 3))

        tk.Frame(personal, height=4, bg=Theme.BG_DARK).pack()

        # ── Vitals ──────────────────────────────────────────────────────────
        hp = ally.get("current_hp", 0)
        max_hp = ally.get("max_hp", 1)
        pct = max(0, min(100, int(100 * hp / max_hp))) if max_hp > 0 else 0
        hp_color = Theme.HP_BAR_FILL if pct > 50 else (Theme.BUFF_NEUTRAL if pct > 25 else Theme.BUFF_NEGATIVE)
        tk.Label(
            inner, text=f"HP: {hp}/{max_hp}", bg=Theme.BG_DARK, fg=hp_color,
            font=Theme.FONT_BOLD,
        ).pack(anchor=tk.W, padx=4, pady=(0, 4))

        # Late-bloomer growth band (previously shown in the Skill Book).
        growth_label = get_growth_label(ally)
        if growth_label and growth_label != "—":
            tk.Label(
                inner, text=f"Growth: {growth_label} (late bloomer)",
                bg=Theme.BG_DARK, fg=Theme.BUFF_NEUTRAL,
                font=Theme.FONT_SMALL,
            ).pack(anchor=tk.W, padx=4, pady=(0, 8))
        else:
            tk.Frame(inner, bg=Theme.BG_DARK, height=4).pack()

    def _render_attributes_box(self, parent, char, is_player):

        from pandemonium.inventory.core import get_total_equipment_mods
        from pandemonium.combat.stats import format_crit_summary
        from pandemonium.combat.ally import compute_ally_stats
        equip_mods = get_total_equipment_mods(char)
        buff_mods = self._compute_buff_mods(char)
        if is_player:
            legend = "base + equipment (+ buff / title) = total"
            title_bonus_fn = title_bonus
        else:
            legend = "base + equipment (+ buff) = total"
            title_bonus_fn = None     # allies carry no deed title

        attr_frame = tk.LabelFrame(
            parent, text=" Attributes ", bg=Theme.BG_DARK, fg=Theme.TEXT,
            font=Theme.FONT_BOLD, highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        attr_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.styled_label(
            attr_frame, text=legend, fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL,
        ).pack(anchor=tk.W, padx=6, pady=(2, 3))

        rows = []
        for attr in ATTRIBUTES:
            base = char["attributes"][attr]
            eq = equip_mods.get(attr, 0)
            bf = buff_mods.get(attr, 0)
            tb = title_bonus_fn(char, attr) if title_bonus_fn else 0
            total = base + eq + bf + tb
            short = attr[:3].upper()
            rows.append((short, attr, base, eq, bf, tb, total))

        # Column widths so the numbers line up like a table:
        #   STR: 22 + 16            = 38  [+4 dmg]
        #   CON:  6 +  5            = 11
        base_w  = max(len(str(r[2])) for r in rows)
        eq_w    = max(len(str(r[3])) for r in rows)
        buff_w  = max(len(str(r[4])) for r in rows)
        title_w = max(len(str(r[5])) for r in rows)
        total_w = max(len(str(r[6])) for r in rows)
        any_buff  = any(r[4] for r in rows)
        any_title = any(r[5] for r in rows)
        blank_buff  = " " * len(f" + {0:>{buff_w}}(buff)")
        blank_title = " " * len(f" + {0:>{title_w}}(title)")

        lines = []
        for short, attr, base, eq, bf, tb, total in rows:
            line = f"{short}: {base:>{base_w}} + {eq:>{eq_w}}"
            if any_buff:
                line += f" + {bf:>{buff_w}}(buff)" if bf else blank_buff
            if any_title:
                line += f" + {tb:>{title_w}}(title)" if tb else blank_title
            line += f" = {total:>{total_w}}"
            lines.append((line, format_milestone_label(char, attr)))

        line_w = max(len(line) for line, _m in lines)
        for line, milestone in lines:
            if milestone:
                line = f"{line:<{line_w}}  [{milestone}]"
            self.styled_label(attr_frame, text=line).pack(anchor=tk.W, padx=6, pady=1)

        # ── Crit summary — chance + damage (includes overflow conversion) ──
        if is_player:
            crit_text = format_crit_summary(char, "player")
        else:
            _str, _con, dex, lrn, _wis, _cha = compute_ally_stats(char)
            crit_text = format_crit_summary(char, "ally", dex=dex, lrn=lrn)
        tk.Frame(attr_frame, height=1, bg=Theme.BORDER).pack(
            fill=tk.X, padx=6, pady=(4, 3)
        )
        self.styled_label(attr_frame, text=crit_text).pack(
            anchor=tk.W, padx=6, pady=(1, 4)
        )

    def _render_equipment_box(self, parent, char, is_player):
        eq_frame = tk.LabelFrame(
            parent, text=" Equipment ", bg=Theme.BG_DARK, fg=Theme.TEXT,
            font=Theme.FONT_BOLD, highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        eq_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        def unequip_cmd(slot):
            if is_player:
                return lambda: self._unequip_slot(slot)
            return lambda: self._unequip_ally_slot(char, slot)

        def equip_cmd(slot):
            if is_player:
                return lambda: self._jump_to_bag_and_hint(slot)
            return lambda: self._jump_to_bag_and_hint(slot, ally=char)

        eq_slots = ["weapon", "armor", "accessory1", "accessory2"]
        if char.get("acc3_unlocked"):
            eq_slots.append("accessory3")

        # Column widths: slot prefixes are padded so every item name starts
        # in the same column, and the mods cell is padded so the gold
        # ▸ Scales tag lands in one column too.
        slot_w = max(len(f"{_slot_display_name(s)}:") for s in eq_slots)
        mods_w = 0
        for s in eq_slots:
            worn = char.get("equipped", {}).get(s)
            if worn:
                mods_w = max(mods_w, len(", ".join(
                    f"{k[:3]} {'+' if v >= 0 else ''}{v}"
                    for k, v in worn.get("mods", {}).items()
                )))

        for slot_idx, slot in enumerate(eq_slots):
            item = char.get("equipped", {}).get(slot)
            slot_name = _slot_display_name(slot)

            if slot_idx:
                tk.Frame(eq_frame, height=1, bg=Theme.BORDER).pack(
                    fill=tk.X, padx=6, pady=0
                )

            # Left: item text (name line + detail line). Right: buttons.
            row = tk.Frame(eq_frame, bg=Theme.BG_DARK)
            row.pack(fill=tk.X, padx=(6, 10), pady=3)
            row.grid_columnconfigure(0, weight=1)

            text_col = tk.Frame(row, bg=Theme.BG_DARK)
            text_col.grid(row=0, column=0, sticky="w")
            btn_col = tk.Frame(row, bg=Theme.BG_DARK)
            btn_col.grid(row=0, column=1, sticky="e", padx=(8, 0))

            prefix = f"{slot_name + ':':<{slot_w}}"
            if item:
                rarity = item.get("rarity", "common")
                color = Theme.RARITY_COLORS.get(rarity, Theme.TEXT)
                mods = item.get("mods", {})
                mod_txt = ", ".join(
                    f"{k[:3]} {'+' if v >= 0 else ''}{v}" for k, v in mods.items()
                )
                tk.Label(
                    text_col, text=f"{prefix} {item['name']}",
                    bg=Theme.BG_DARK, fg=color, font=Theme.FONT, anchor=tk.W,
                ).pack(anchor=tk.W)

                detail = tk.Frame(text_col, bg=Theme.BG_DARK)
                detail.pack(anchor=tk.W)
                # Spacer aligns the detail line under the item-name column.
                tk.Label(
                    detail, text="", width=slot_w + 1, bg=Theme.BG_DARK,
                    font=Theme.FONT,
                ).pack(side=tk.LEFT)
                tk.Label(
                    detail, text=mod_txt, width=mods_w, bg=Theme.BG_DARK,
                    fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL, anchor=tk.W,
                ).pack(side=tk.LEFT)
                scale_txt = format_scaling_stat(item)
                if scale_txt:
                    tk.Label(
                        detail, text=f"  {scale_txt}",
                        bg=Theme.BG_DARK, fg=Theme.RARITY_LEGENDARY,
                        font=Theme.FONT_SMALL,
                    ).pack(side=tk.LEFT)

                # Every worn piece is examinable — affinity and effect without
                # a trip to the blacksmith.
                self.styled_button(
                    btn_col, text="Examine", width=9,
                    command=lambda it=item: self._examine_item(it),
                ).pack(side=tk.LEFT, padx=(0, 2))
                self.styled_button(
                    btn_col, text="Unequip", width=8,
                    command=unequip_cmd(slot),
                ).pack(side=tk.LEFT)
            else:
                self.styled_label(
                    text_col, text=f"{prefix} (empty)", fg=Theme.TEXT_DIM,
                ).pack(anchor=tk.W)
                # Quick jump to the Bag to equip an item into this empty slot
                self.styled_button(
                    btn_col, text="Equip", width=6,
                    command=equip_cmd(slot),
                ).pack(side=tk.LEFT)

    def _render_milestones_box(self, parent, char):
        mb = format_milestone_bonuses(char)
        if not mb:
            return
        mb_frame = self._section_box(parent, "Milestones")
        tk.Label(
            mb_frame, text=mb,
            bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT,
            wraplength=600, justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=6, pady=4)

    # ── Skills view ──────────────────────────────────────────────────────────
    #
    #  The two sides have different mechanics (you curate a loadout and unlock
    #  by level; allies have a fixed kit and learn with EXP), so each keeps its
    #  own sections — but they share the section frames, the passive box and
    #  the skill card below, so a skill looks the same whoever owns it.

    def _section_box(self, parent, title, fg=None):
        """A titled box, packed into *parent*."""
        frame = tk.LabelFrame(
            parent, text=f" {title} ", bg=Theme.BG_DARK, fg=fg or Theme.TEXT,
            font=Theme.FONT_BOLD, highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        frame.pack(fill=tk.X, pady=4, padx=4)
        return frame

    def _render_passive_box(self, parent, passive):
        if not passive:
            return
        frame = self._section_box(parent, "Passive")
        tk.Label(
            frame, text=f"{passive['name']}: {passive['description']}",
            bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT,
            wraplength=600, justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=6, pady=4)

    def _render_skill_card(self, parent, title, *, title_fg, marker=None,
                           on_toggle=None, description="", meta=(),
                           extra="", extra_fg=None):
        """One skill block, shared by the player and ally pages.

        marker: "on" / "off" → clickable ✓/– loadout box (calls *on_toggle*),
                "locked"     → 🔒,
                None         → no gutter (skills with nothing to toggle).
        meta:   pieces joined with " · " on the small line under the description.
        extra:  optional highlighted line (e.g. mastery bonuses).
        """
        indent = 32 if marker else 16
        entry = tk.Frame(parent, bg=Theme.BG_DARK)
        entry.pack(fill=tk.X, padx=6, pady=(3, 2))

        top = tk.Frame(entry, bg=Theme.BG_DARK)
        top.pack(fill=tk.X)

        if marker in ("on", "off"):
            on = marker == "on"
            self.styled_button(
                top, text="✓" if on else "–", width=2, command=on_toggle,
                bg=Theme.BG_LIGHT if on else Theme.BG_MID,
                fg=Theme.BUFF_POSITIVE if on else Theme.TEXT_DIM,
            ).pack(side=tk.LEFT, anchor=tk.N)
        elif marker == "locked":
            tk.Label(
                top, text="🔒", width=2, bg=Theme.BG_DARK,
                fg=Theme.TEXT_DIM, font=Theme.FONT,
            ).pack(side=tk.LEFT, anchor=tk.N)

        self.styled_label(
            top, text=title, fg=title_fg, font=Theme.FONT_BOLD,
        ).pack(side=tk.LEFT, padx=(4, 0) if marker else 0, anchor=tk.N)

        if description:
            tk.Label(
                entry, text=description, bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
                font=Theme.FONT_SMALL, wraplength=620, justify=tk.LEFT,
            ).pack(anchor=tk.W, padx=(indent, 4), pady=(1, 0))

        if meta:
            self.styled_label(
                entry, text="  ·  ".join(meta),
                fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL,
            ).pack(anchor=tk.W, padx=(indent, 4))

        if extra:
            self.styled_label(
                entry, text=extra, fg=extra_fg or Theme.BUFF_NEUTRAL,
                font=Theme.FONT_SMALL,
            ).pack(anchor=tk.W, padx=(indent, 4))

    def _render_character_skills(self, inner, char, is_player):
        if is_player:
            self._render_player_skills(inner)
        else:
            self._render_ally_skills(inner, char)

    def _render_player_skills(self, inner):
        """Battle loadout, class passive, unlocked/locked skills, profession."""
        from pandemonium.combat.skills import (
                    get_class_skill_map, format_mastery_label, get_equipped_skill_ids,
                    MAX_SKILL_LOADOUT, get_skill_mastery_level, get_mastery_bonuses,
                    get_passive_skill,
                )
        p = self.player

        skill_map = get_class_skill_map(p)
        if not skill_map:
            self.styled_label(inner, text="No skills available.").pack(pady=20)
            return

        unlocked = set(p.get("skills", []))
        equipped = set(get_equipped_skill_ids(p))
        level = p.get("level", 1)
        cooldowns = p.get("skill_cooldowns", {})
        mastery_uses = p.get("skill_mastery", {})

        self.styled_label(
            inner,
            text=f"Battle Loadout: {len(equipped)}/{MAX_SKILL_LOADOUT} equipped — "
                 "click a skill's ✓/– box to choose what you bring into combat.",
            fg=Theme.ACCENT,
        ).pack(anchor=tk.W, padx=6, pady=(6, 0))

        profs = PROFESSIONS.get(p.get("class"), {})
        if profs:
            prof = p.get("profession")
            prof_text = (f"Profession: {profs[prof]['name']}" if prof in profs
                         else "Profession: none — choose at the Guild after the Lv-40 capstone")
            self.styled_label(inner, text=prof_text, fg=Theme.TEXT_DIM).pack(
                anchor=tk.W, padx=6, pady=(2, 0)
            )

        # ── Passive skill (class passive, upgraded by the chosen profession) ─
        self._render_passive_box(inner, get_passive_skill(p))

        def mastery_text(sid, mastery_lvl):
            bonuses = get_mastery_bonuses(sid, mastery_lvl)
            bits = []
            if bonuses["power_mult"] > 1.0:
                bits.append(f"+{int(round((bonuses['power_mult'] - 1) * 100))}% power")
            if bonuses["cooldown_reduction"]:
                bits.append(f"−{bonuses['cooldown_reduction']} turn cooldown")
            if bonuses["status_mult"] > 1.0:
                bits.append(f"effect potency ×{bonuses['status_mult']:g}")
            if bonuses["duration_bonus"]:
                bits.append(f"+{bonuses['duration_bonus']} turn duration")
            if bonuses["extra_effect"]:
                bits.append("bonus effect at ★★★")
            if not bits:
                return ""
            uses = mastery_uses.get(sid, 0)
            return f"Mastery Lv.{mastery_lvl} ({uses} uses): " + ", ".join(bits)

        def add_card(parent, sid, sdef, is_unlocked_entry):
            ul = sdef.get("unlock_level", 1)
            cd = cooldowns.get(sid, 0)
            mastery_lvl = get_skill_mastery_level(p, sid)
            mastery_label = format_mastery_label(sid, p)
            is_equipped = sid in equipped

            title = sdef["name"]
            if cd > 0:
                title += f"  [CD: {cd}]"
            if mastery_label:
                title += f"  {mastery_label}"
            if is_unlocked_entry and not is_equipped:
                title += "  [not equipped]"
            if not is_unlocked_entry:
                title += "  [LOCKED]"
            title_fg = (Theme.BUFF_POSITIVE if is_equipped
                        else (Theme.TEXT if is_unlocked_entry else Theme.TEXT_DIM))

            meta = [f"Unlock: Level {ul}", f"Cooldown: {sdef.get('cooldown', 0)} turns"]
            if sdef.get("target"):
                meta.append(f"Target: {sdef['target']}")
            if sdef.get("elemental"):
                meta.append(f"Element: {sdef['elemental']}")

            if is_unlocked_entry:
                marker = "on" if is_equipped else "off"
            else:
                marker = "locked"

            self._render_skill_card(
                parent, title, title_fg=title_fg, marker=marker,
                on_toggle=lambda s=sid: self._toggle_skill_loadout(s),
                description=sdef.get("description", ""), meta=meta,
                extra=mastery_text(sid, mastery_lvl) if mastery_lvl > 0 else "",
            )

        by_unlock = lambda kv: (kv[1].get("unlock_level", 1), kv[1].get("name", ""))
        unlocked_entries, locked_entries = [], []
        for sid, sdef in sorted(skill_map.items(), key=by_unlock):
            ul = sdef.get("unlock_level", 1)
            if sid in unlocked and level >= ul:
                unlocked_entries.append((sid, sdef))
            else:
                locked_entries.append((sid, sdef))

        unlocked_frame = self._section_box(inner, "Unlocked", Theme.BUFF_POSITIVE)
        for sid, sdef in unlocked_entries:
            add_card(unlocked_frame, sid, sdef, True)
        if not unlocked_entries:
            self.styled_label(
                unlocked_frame,
                text="No skills unlocked yet — level up to learn your first skill.",
                fg=Theme.TEXT_DIM,
            ).pack(anchor=tk.W, padx=6, pady=2)

        if locked_entries:
            locked_frame = self._section_box(inner, "Locked", Theme.TEXT_DIM)
            for sid, sdef in locked_entries:
                add_card(locked_frame, sid, sdef, False)

        # ── The profession branch you gave up (Skill Book parity) ─────────
        chosen = p.get("profession")
        if chosen in profs:
            for pid, pdata in profs.items():
                if pid == chosen:
                    continue
                branch = self._section_box(
                    inner,
                    f"{pdata['name']} — locked (you chose {profs[chosen]['name']})",
                    Theme.TEXT_DIM,
                )
                for sid, sdef in sorted(pdata.get("skills", {}).items(), key=by_unlock):
                    self._render_skill_card(
                        branch,
                        f"{sdef['name']}  — Lv.{sdef.get('unlock_level', '?')}",
                        title_fg=Theme.TEXT_DIM, marker="locked",
                        description=sdef.get("description", ""),
                    )

    @staticmethod
    def _ally_passive(ally):
        """Race passive, falling back to the stored id, then the enemy template."""
        from pandemonium.combat.ally_skills import get_race_passive, get_passive_by_id
        race = ally.get("race")
        passive = get_race_passive(race) if race else None
        if not passive and ally.get("passive_skill"):
            passive = get_passive_by_id(ally["passive_skill"])
        if not passive and ally.get("key"):
            template = ENEMIES.get(ally["key"], {})
            template_race = template.get("race")
            if template_race:
                passive = get_race_passive(template_race)
        return passive

    def _render_ally_skills(self, inner, ally):
        """Passive, then Innate / Upgrades / Learned, then learning progress."""
        from pandemonium.combat.ally_skills import (
                    get_innate_skill_def, get_learnable_skill_def,
                    get_ally_skill_mastery_level, format_skill_learning_progress,
                    format_ally_mastery_label,
                )

        self._render_passive_box(inner, self._ally_passive(ally))

        tier_labels = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
        groups = (
            ("Innate", "innate_skills", get_innate_skill_def),
            ("Upgrades", "upgrade_skills", get_innate_skill_def),
            ("Learned", "learned_skills", get_learnable_skill_def),
        )
        shown_any = False
        for section_title, key, lookup in groups:
            entries = []
            for sid in ally.get(key, []):
                sdef = lookup(sid)
                if sdef:
                    entries.append((sid, sdef))
            if not entries:
                continue
            shown_any = True
            frame = self._section_box(inner, section_title)
            for sid, sdef in entries:
                stars = format_ally_mastery_label(sid, ally)
                cd = ally.get("skill_cooldowns", {}).get(sid, 0)
                cd_str = f"  [CD: {cd}]" if cd > 0 else ""
                mastery_lvl = get_ally_skill_mastery_level(ally, sid)

                meta = [f"Cooldown: {sdef.get('cooldown', 0)} turns"]
                if sdef.get("target"):
                    meta.append(f"Target: {sdef['target']}")
                if key == "learned_skills":
                    meta.append(f"Tier {tier_labels.get(sdef.get('tier', 1), '?')}")
                    meta.append(f"Cost: {sdef.get('exp_cost', 300)} EXP")
                    if sdef.get("required_cap"):
                        meta.append(f"Cap: {sdef['required_cap']}")
                if mastery_lvl > 0:
                    meta.append(f"Mastery Lv.{mastery_lvl}")

                self._render_skill_card(
                    frame, f"{sdef['name']}{cd_str}  {stars}".rstrip(),
                    title_fg=Theme.TEXT,
                    description=sdef.get("description", ""), meta=meta,
                )

        progress = format_skill_learning_progress(ally)
        if progress and "Not learning" not in progress:
            shown_any = True
            frame = self._section_box(inner, "Learning")
            self.styled_label(
                frame, text=progress, fg=Theme.BUFF_NEUTRAL,
            ).pack(anchor=tk.W, padx=6, pady=(2, 4))

        if not shown_any:
            self.styled_label(
                inner, text="No skills yet.", fg=Theme.TEXT_DIM,
            ).pack(anchor=tk.W, padx=6, pady=6)

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 2 — Bag
    # ═══════════════════════════════════════════════════════════════════════

    def _build_bag_tab(self):
        self.bag_frame = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(self.bag_frame, text=" Bag ")
        self.bag_frame.grid_columnconfigure(0, weight=1)
        self._refresh_bag_tab()

    def _jump_to_bag_and_hint(self, slot_name: str, ally=None):
        """Switch to the Bag tab and hint the user to choose an item to equip.

        If *ally* is provided, subsequent Equip clicks in the bag will target
        that ally instead of the player.  *slot_name* is the desired slot.
        """
        try:
            self.notebook.select(self.bag_frame)
            if ally:
                self._equip_target_ally = ally
                self._equip_target_slot = slot_name
                self.log(f"Select an item in Bag to equip to {display_name(ally)}'s {_slot_display_name(slot_name)}.")
            else:
                self._equip_target_ally = None
                self._equip_target_slot = slot_name
                self.log(f"Select an item in Bag to equip to {slot_name}.")
        except Exception:
            pass

    def _refresh_bag_tab(self):
        from pandemonium.inventory.core import (
                    get_inventory_caps, count_inventory,
                    get_sorted_equipment, get_sorted_items, get_key_items, get_cargo_items,
                    get_flower_items,
                )
        from pandemonium.resources.trade_goods import cargo_total_weight, cargo_capacity
        for w in self.bag_frame.winfo_children():
            w.destroy()

        if not self.player:
            self.styled_label(self.bag_frame, text="No player data.").pack(pady=20)
            return

        eq_cap, other_cap = get_inventory_caps(self.player)
        eq_count, other_count = count_inventory(self.player)

        cap_text = f"Equipment: {eq_count}/{eq_cap}  |  Items: {other_count}/{other_cap}"
        load = cargo_total_weight(self.player)
        if load > 0:
            cap = cargo_capacity(self.player)
            cap_text += f"  |  Cargo: {load} wt"
            cap_text += f"/{cap} wt" if cap > 0 else " (no mount)"
        self.styled_label(self.bag_frame, text=cap_text).pack(anchor=tk.W, pady=(4, 8))

        # ── Flowers: their own tab with live counts ──────────────────────
        # They used to be buried among Key Items, which made it impossible to
        # tell how many of each element you actually had.
        flowers = get_flower_items(self.player)
        flower_total = sum(int(i.get("count", 1) or 1) for i in flowers)
        key_items = [i for i in get_key_items(self.player)
                     if not is_flower_item(i)]

        # ── Sub-tabs dividing the bag by item type ──────────────────────────
        self.bag_sub = ttk.Notebook(self.bag_frame, style="Ally.TNotebook")
        self.bag_sub.pack(fill=tk.BOTH, expand=True)

        sections = [
            (" Equipment ", get_sorted_equipment(self.player), True, False),
            (" Items ", get_sorted_items(self.player), False, False),
            (" Cargo ", get_cargo_items(self.player), False, False),
            (f" Flowers ({flower_total}) ", flowers, False, True),
            (" Key Items ", key_items, False, True),
        ]
        for label, items, is_equip, is_key in sections:
            self._build_bag_subtab(label, items, is_equip, is_key)

    def _build_bag_subtab(self, label, items, is_equip, is_key):
        """One scrollable sub-tab in the bag notebook."""
        tab = tk.Frame(self.bag_sub, bg=Theme.BG_DARK)
        self.bag_sub.add(tab, text=label)

        scroll = tk.Scrollbar(tab)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        canvas = tk.Canvas(tab, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))

        if not items:
            self.styled_label(inner, text="Nothing here.").pack(pady=20)
            return

        # Column widths: short names are padded so [slot]/(type), the stat
        # list and the scale tag all start in the same column on every row.
        parts = [self._bag_item_parts(i, is_equip, is_key) for i in items]
        widths = (
            max(len(p[0]) for p in parts),
            max(len(p[1]) for p in parts),
            max(len(p[2]) for p in parts),
        )
        for item in items:
            self._render_bag_item(inner, item, is_equip=is_equip, is_key=is_key,
                                  widths=widths)

    def _is_unique_item(self, item):
        """True if the item is unique (template fallback covers old saves)."""
        if item.get("unique"):
            return True
        try:
            return bool(ITEMS.get(item.get("id"), {}).get("unique"))
        except Exception:
            return False

    def _bag_item_parts(self, item, is_equip, is_key=False):
        """Display columns for one bag row: (name + count, [slot]/(type), mods)."""
        count = item.get("count", 1)
        count_str = f" (x{count})" if count > 1 else ""
        name_part = f"{item['name']}{count_str}"

        if is_equip:
            mods = item.get("mods", {})
            mod_txt = ", ".join(
                f"{k[:3]} {'+' if v >= 0 else ''}{v}" for k, v in mods.items()
            )
            return (name_part, f"[{item.get('slot', '?')}]",
                    f"({mod_txt})" if mod_txt else "")

        item_type = item.get("type", "?")
        if is_flower_item(item):
            type_label = "Flower"
        elif item_type == "crafting_material":
            type_label = "Material"
        elif item_type == "key_item":
            type_label = "Key Item"
        elif item_type == "cargo":
            type_label = "Cargo"
        else:
            type_label = item_type
        return name_part, f"({type_label})", ""

    def _render_bag_item(self, parent, item, is_equip, is_key=False, widths=None):
        rarity = item.get("rarity", "common")
        color = Theme.RARITY_COLORS.get(rarity, Theme.TEXT)
        name_part, tag_part, mods_part = self._bag_item_parts(item, is_equip, is_key)

        # Column-aligned text: short names gain padding so [slot]/(type),
        # stats and the ▸ Scales tag line up across the whole tab.
        if widths:
            name_w, tag_w, mods_w = widths
            text = f"{name_part:<{name_w}}  {tag_part}"
            if is_equip and mods_w:
                text += f"  {mods_part:<{mods_w}}"
        else:
            text = f"{name_part}  {tag_part}"
            if is_equip and mods_part:
                text += f"  {mods_part}"

        # Living key items (the resonance blank) carry a fill-meter.
        meter = item.get("resonance_meter")
        if meter:
            text += f"  {meter}"

        row = tk.Frame(parent, bg=Theme.BG_DARK)
        row.pack(fill=tk.X, padx=6, pady=(2, 0))

        name_lbl = tk.Label(
            row, text=text, bg=Theme.BG_DARK, fg=color,
            font=Theme.FONT, anchor=tk.W,
        )
        if widths and is_equip:
            # Fixed-width cell so the smaller gold ▸ Scales label lands in
            # the same column even when this row's name is short.
            name_lbl.configure(width=len(text))
        name_lbl.pack(side=tk.LEFT)

        if is_equip:
            scale_txt = format_scaling_stat(item)
            if scale_txt:
                tk.Label(
                    row, text=f"  {scale_txt}", bg=Theme.BG_DARK,
                    fg=Theme.RARITY_LEGENDARY, font=Theme.FONT_SMALL,
                ).pack(side=tk.LEFT)

        # Key items and crafting materials cannot be dropped, sold, or used,
        # but they can be examined for their name and lore. (The Beating Root
        # is the exception — it opens a third accessory slot for one actor.)
        if is_key:
            if item.get("special") == "beating_root":
                self.styled_button(
                    row, text="Use", width=5,
                    command=lambda it=item: self._use_beating_root(it),
                ).pack(side=tk.RIGHT, padx=2)
            self.styled_button(
                row, text="Examine", width=9,
                command=lambda it=item: self._examine_item(it),
            ).pack(side=tk.RIGHT, padx=2)
            sep = tk.Frame(parent, height=1, bg=Theme.BORDER)
            sep.pack(fill=tk.X, padx=10, pady=0)
            return

        if is_equip:
            self.styled_button(
                row, text="Equip", width=6,
                command=lambda it=item: self._equip_item(it),
            ).pack(side=tk.RIGHT, padx=2)
            # Every piece of equipment explains its affinity and effect —
            # uniques additionally carry lore in the same popup.
            self.styled_button(
                row, text="Examine", width=9,
                command=lambda it=item: self._examine_item(it),
            ).pack(side=tk.RIGHT, padx=2)

        if item.get("type") in ("consumable", "utility"):
            self.styled_button(
                row, text="Use", width=5,
                command=lambda it=item: self._use_item(it),
            ).pack(side=tk.RIGHT, padx=2)

        self.styled_button(
            row, text="Drop", width=6,
            command=lambda it=item: self._drop_item(it),
        ).pack(side=tk.RIGHT, padx=2)

        # Thin separator line between items
        sep = tk.Frame(parent, height=1, bg=Theme.BORDER)
        sep.pack(fill=tk.X, padx=10, pady=0)

    # ═══════════════════════════════════════════════════════════════════════
    #  Skill loadout  (the ✓/– boxes on your character page → Skills view)
    # ═══════════════════════════════════════════════════════════════════════

    def _toggle_skill_loadout(self, skill_id):
        """Equip/unequip a class skill for combat from your Skills view."""
        from pandemonium.combat.skills import (
                    get_class_skill_map, get_equipped_skill_ids, MAX_SKILL_LOADOUT,
                )
        p = self.player
        if not p or skill_id not in p.get("skills", []):
            return


        skill_map = get_class_skill_map(p)
        name = skill_map.get(skill_id, {}).get("name", skill_id)

        # Materialise the implicit "everything unlocked" loadout before edits.
        if p.get("skill_loadout") is None:
            p["skill_loadout"] = list(get_equipped_skill_ids(p))
        loadout = p["skill_loadout"]
        equipped_now = [sid for sid in loadout if sid in p.get("skills", [])]

        if skill_id in equipped_now:
            loadout.remove(skill_id)
            self.sm.log(f"{name} unequipped — it will not appear in combat.")
        elif len(equipped_now) >= MAX_SKILL_LOADOUT:
            self.sm.log(
                f"Battle Loadout full ({MAX_SKILL_LOADOUT}/{MAX_SKILL_LOADOUT}) "
                "— unequip a skill first."
            )
            return
        else:
            loadout.append(skill_id)
            self.sm.log(f"{name} equipped — it will appear in combat.")

        self._rerender_current_char_page()

    # ═══════════════════════════════════════════════════════════════════════
    #  Personal Information box (top of the player's Overview view)
    # ═══════════════════════════════════════════════════════════════════════

    def _render_personal_box(self, parent):
        """Draw the non-stat personal block into `parent`.

        Holds name/level, race/class/profession, the active deed title and
        the Karma summary. Stats, equipment and milestones keep their own
        boxes below it.
        """
        if not self.player:
            return
        p = self.player

        personal = tk.LabelFrame(
            parent, text=" Personal Information ", bg=Theme.BG_DARK, fg=Theme.TEXT,
            font=Theme.FONT_BOLD, highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        personal.pack(fill=tk.X, pady=4, padx=4)

        # ── Identity ─────────────────────────────────────────────────────────
        self.styled_label(
            personal,
            text=f"Name: {p.get('name', 'Adventurer')}   "
                 f"Level: {p.get('level', 1)}",
            fg=Theme.ACCENT, font=Theme.FONT_BOLD,
        ).pack(anchor=tk.W, padx=6, pady=(4, 1))

        race = p.get("race") or "Unknown"
        klass = p.get("class") or "Unknown"
        self.styled_label(
            personal, text=f"Race: {race}   Class: {klass}",
        ).pack(anchor=tk.W, padx=6, pady=1)

        profs = PROFESSIONS.get(klass, {})
        prof = p.get("profession")
        if prof in profs:
            prof_text = profs[prof]["name"]
        elif profs:
            prof_text = "none — choose at the Guild after the Lv-40 capstone"
        else:
            prof_text = "none"
        self.styled_label(
            personal, text=f"Profession: {prof_text}",
        ).pack(anchor=tk.W, padx=6, pady=(1, 3))

        # ── Deed title (docs/titles_design.md) ──────────────────────────────
        active_title = _titles.get_active(p)
        if active_title:
            title_line = (f"Title: {active_title['name']} — "
                          f"{_titles.format_effect_line(active_title)}")
            title_fg = Theme.ACCENT
        else:
            title_line = "Title: none — choose one in Journal → Titles."
            title_fg = Theme.TEXT_DIM
        self.styled_label(
            personal, text=title_line, fg=title_fg,
            wraplength=620, justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=6, pady=1)

        # ── Karma summary (hidden when the save has the rule off) ───────────
        if karma.is_enabled(p):
            karma_value = karma.get_karma(p)
            tier = karma.get_karma_tier(p)
            color = (Theme.BUFF_POSITIVE if karma_value > 0
                     else Theme.BUFF_NEGATIVE if karma_value < 0
                     else Theme.TEXT)
            self.styled_label(
                personal, text=f"Karma: {tier['label']} ({karma_value:+d})",
                fg=color, font=Theme.FONT_BOLD,
            ).pack(anchor=tk.W, padx=6, pady=(3, 1))

            shop_pct = int(tier["buy_pct"])
            if shop_pct > 0:
                shop_text = f"+{shop_pct}% shop/forge discount"
            elif shop_pct < 0:
                shop_text = f"{abs(shop_pct)}% shop/forge surcharge"
            else:
                shop_text = "no price shift"
            bills_mult = karma.get_bills_mult(p)
            self.styled_label(
                personal,
                text=f"   {shop_text}  |  Bills ×{bills_mult:.2f}",
                fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL,
            ).pack(anchor=tk.W, padx=6, pady=(0, 2))
        else:
            self.styled_label(
                personal, text="Karma rules are off for this save.",
                fg=Theme.TEXT_DIM,
            ).pack(anchor=tk.W, padx=6, pady=(1, 4))

        tk.Frame(personal, height=4, bg=Theme.BG_DARK).pack()

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 5 — Journal  (sub-notebook: Bounty, Main Quest, Side Quest, Event)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_journal_tab(self):
        self.journal_frame = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(self.journal_frame, text=" Journal ")
        self.journal_frame.grid_rowconfigure(0, weight=1)
        self.journal_frame.grid_columnconfigure(0, weight=1)
        self._refresh_journal_tab()

    def _refresh_journal_tab(self):
        for w in self.journal_frame.winfo_children():
            w.destroy()

        if not self.player:
            self.styled_label(self.journal_frame, text="No player data.").pack(pady=20)
            return

        # ── Sub-notebook for journal categories ──────────────────────────────
        self.journal_notebook = ttk.Notebook(self.journal_frame, style="Ally.TNotebook")
        self.journal_notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Bounty sub-tab
        bounty_tab = tk.Frame(self.journal_notebook, bg=Theme.BG_DARK)
        self.journal_notebook.add(bounty_tab, text=" Bounty ")
        self._render_bounty_subtab(bounty_tab)

        # Main Quest sub-tab
        main_quest_tab = tk.Frame(self.journal_notebook, bg=Theme.BG_DARK)
        self.journal_notebook.add(main_quest_tab, text=" Main Quest ")
        self._render_quest_subtab(main_quest_tab, "main_quests", "No main quests yet.")

        # Side Quest sub-tab
        side_quest_tab = tk.Frame(self.journal_notebook, bg=Theme.BG_DARK)
        self.journal_notebook.add(side_quest_tab, text=" Side Quest ")
        self._render_quest_subtab(side_quest_tab, "side_quests", "No side quests yet.")

        # Event sub-tab
        event_tab = tk.Frame(self.journal_notebook, bg=Theme.BG_DARK)
        self.journal_notebook.add(event_tab, text=" Event ")
        self._render_event_subtab(event_tab)

        # Dreams sub-tab (Dream Journal — docs/dream_events_design.md §5.3)
        dream_tab = tk.Frame(self.journal_notebook, bg=Theme.BG_DARK)
        self.journal_notebook.add(dream_tab, text=" Dreams ")
        self._render_dream_subtab(dream_tab)

        # Titles sub-tab (docs/titles_design.md)
        titles_tab = tk.Frame(self.journal_notebook, bg=Theme.BG_DARK)
        self.journal_notebook.add(titles_tab, text=" Titles ")
        self._render_titles_subtab(titles_tab)

    def _render_dream_subtab(self, parent):
        """Render the Dream Journal — every dream seen so far, re-readable."""
        import pandemonium.progression.dreams as dream_mod

        entries = dream_mod.journal_entries(self.player)
        if not entries:
            self.styled_label(
                parent, text="No dreams yet — sleep at home, at an inn, or at camp.",
                fg=Theme.TEXT_DIM,
            ).pack(anchor=tk.CENTER, expand=True)
            return

        scroll = tk.Scrollbar(parent)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(parent, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        total = sum(e["count"] for e in entries)
        self.styled_label(
            inner,
            text=f"Dream Journal — {len(entries)} of {len(dream_mod.DREAMS)} dreams "
                 f"seen ({total} night{'s' if total != 1 else ''} of dreams).",
            fg=Theme.TEXT_DIM,
        ).pack(anchor=tk.W, padx=6, pady=(4, 6))

        category_color = {
            "boon": Theme.BUFF_POSITIVE,
            "burden": Theme.BUFF_NEGATIVE,
            "choice": Theme.ACCENT,
            "story": Theme.TEXT,
        }

        for entry in entries:
            title = f" {entry['name']} "
            if entry["count"] > 1:
                title = f" {entry['name']} (seen ×{entry['count']}) "
            frame = tk.LabelFrame(
                inner, text=title, bg=Theme.BG_DARK,
                fg=category_color.get(entry["category"], Theme.TEXT),
                font=Theme.FONT_BOLD, highlightthickness=1,
                highlightbackground=Theme.BORDER,
            )
            frame.pack(fill=tk.X, pady=4, padx=4)
            self.styled_label(
                frame, text=entry["category"].title(), fg=Theme.TEXT_DIM,
            ).pack(anchor=tk.W, padx=6, pady=(2, 0))
            if entry["lines"]:
                tk.Label(
                    frame, text=entry["lines"], bg=Theme.BG_DARK,
                    fg=Theme.TEXT, font=Theme.FONT, wraplength=620,
                    justify=tk.LEFT,
                ).pack(anchor=tk.W, padx=6, pady=2)
            if entry["journal"]:
                self.styled_label(
                    frame, text=entry["journal"], fg=Theme.TEXT_DIM,
                ).pack(anchor=tk.W, padx=6, pady=(0, 4))

    def _render_titles_subtab(self, parent):
        """Render the deed-title collection (docs/titles_design.md)."""

        rows = title_mod.list_titles(self.player)
        unlocked = sum(1 for r in rows if r["unlocked"])

        scroll = tk.Scrollbar(parent)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(parent, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        self.styled_label(
            inner,
            text=f"Titles — {unlocked} of {len(rows)} earned. One may be equipped.",
            fg=Theme.TEXT_DIM,
        ).pack(anchor=tk.W, padx=6, pady=(4, 2))
        self.styled_label(
            inner,
            text=title_mod.collection_summary(self.player),
            fg=Theme.TEXT_DIM,
        ).pack(anchor=tk.W, padx=6, pady=(0, 6))

        rows.sort(key=lambda r: (not r["active"], not r["unlocked"],
                                 r["tier"], r["name"]))

        for row in rows:
            if row["unlocked"]:
                frame_title = f" {row['name']} "
                if row["active"]:
                    frame_title = f" {row['name']} — EQUIPPED "
                color = Theme.ACCENT if row["active"] else Theme.TEXT
            else:
                frame_title = " ??? "
                color = Theme.TEXT_DIM

            frame = tk.LabelFrame(
                inner, text=frame_title, bg=Theme.BG_DARK, fg=color,
                font=Theme.FONT_BOLD, highlightthickness=1,
                highlightbackground=Theme.ACCENT if row["active"] else Theme.BORDER,
            )
            frame.pack(fill=tk.X, pady=4, padx=4)

            meta = f"Tier {row['tier']} · {str(row['category']).title()}"
            self.styled_label(frame, text=meta, fg=Theme.TEXT_DIM).pack(
                anchor=tk.W, padx=6, pady=(2, 0)
            )

            if row["unlocked"]:
                self.styled_label(
                    frame, text=row["effect_line"], fg=Theme.BUFF_POSITIVE,
                ).pack(anchor=tk.W, padx=6, pady=1)
                if row["description"]:
                    self.styled_label(
                        frame, text=row["description"], fg=Theme.TEXT_DIM,
                    ).pack(anchor=tk.W, padx=6, pady=(0, 2))
            else:
                self.styled_label(
                    frame, text=f"Hint: {row['hint']}", fg=Theme.TEXT,
                ).pack(anchor=tk.W, padx=6, pady=1)
                if not row["available"]:
                    self.styled_label(
                        frame,
                        text="Unavailable — this save's game rule is disabled.",
                        fg=Theme.BUFF_NEGATIVE,
                    ).pack(anchor=tk.W, padx=6, pady=1)
                progress = row.get("progress")
                if progress:
                    label, current, target = progress
                    self.styled_label(
                        frame, text=f"{str(label).title()}: {current} / {target}",
                        fg=Theme.TEXT_DIM,
                    ).pack(anchor=tk.W, padx=6, pady=(0, 2))

            # Gambling titles share the same lifetime casino record line,
            # shown whether the title is locked or unlocked.
            if row.get("record_line"):
                self.styled_label(
                    frame, text=row["record_line"], fg=Theme.TEXT_DIM,
                    wraplength=620, justify=tk.LEFT,
                ).pack(anchor=tk.W, padx=6, pady=(0, 2))

            btn_row = tk.Frame(frame, bg=Theme.BG_DARK)
            btn_row.pack(anchor=tk.W, padx=6, pady=(2, 4))
            if row["active"]:
                self.styled_button(
                    btn_row, text="Unequip", width=12,
                    command=lambda: self._title_action(None),
                ).pack(side=tk.LEFT)
            elif row["unlocked"] and row["available"]:
                self.styled_button(
                    btn_row, text="Equip", width=12,
                    command=lambda tid=row["id"]: self._title_action(tid),
                ).pack(side=tk.LEFT)

    def _title_action(self, title_id):
        """Equip (title_id) or unequip (None) from the Journal UI."""
        if title_id:
            ok, msg = title_mod.equip_title(self.player, title_id)
        else:
            ok, msg = title_mod.unequip_title(self.player)
        self.sm.log(msg)
        if ok:
            self._refresh_journal_tab()
            # Keep the player on the Titles sub-tab after a swap.
            try:
                self.journal_notebook.select(
                    len(self.journal_notebook.tabs()) - 1
                )
            except Exception:
                pass
            # Title bonuses feed the attribute lines and the personal box.
            self._refresh_characters_tab()

    def _render_bounty_subtab(self, parent):
        """Render the Bounty sub-tab showing active bounties."""
        bounties = self.player.get("active_bounties", [])
        if not bounties:
            self.styled_label(parent, text="No active bounties.", fg=Theme.TEXT_DIM).pack(
                anchor=tk.CENTER, expand=True
            )
            return

        # Scrollable container
        scroll = tk.Scrollbar(parent)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(parent, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        current_day = self.player.get("day", 1)

        for b in bounties:
            current = b.get("current", 0)
            required = b["required"]
            days_left = b.get("deadline", current_day) - current_day
            ready = current >= required
            # Matches guild.check_bounty_expiry: the deadline day is still valid.
            expired = days_left < 0

            frame_color = Theme.BORDER
            if expired:
                title_color = status_color = Theme.BUFF_NEGATIVE
                status_text = "✗ EXPIRED"
            elif ready:
                title_color = status_color = Theme.BUFF_POSITIVE
                status_text = "✓ READY TO CLAIM"
            else:
                title_color = status_color = Theme.TEXT
                status_text = f"{current}/{required}"

            frame = tk.LabelFrame(
                inner,
                text=f" {b['target_name']} ",
                bg=Theme.BG_DARK,
                fg=title_color,
                font=Theme.FONT_BOLD,
                highlightthickness=1,
                highlightbackground=frame_color,
            )
            frame.pack(fill=tk.X, pady=4, padx=4)

            self.styled_label(
                frame, text=f"Progress: {status_text}",
                fg=status_color,
            ).pack(anchor=tk.W, padx=6, pady=2)
            self.styled_label(
                frame, text=f"Difficulty: {b.get('difficulty', '?')}",
            ).pack(anchor=tk.W, padx=6, pady=1)
            self.styled_label(
                frame, text=f"Reward: {b.get('reward_gold', 0)} gold",
            ).pack(anchor=tk.W, padx=6, pady=1)
            days_text = f"Expires {format_day_delta(b.get('deadline', current_day), current_day)}"
            self.styled_label(
                frame, text=days_text,
                fg=Theme.BUFF_NEGATIVE if days_left <= 1 else Theme.TEXT_DIM,
            ).pack(anchor=tk.W, padx=6, pady=2)

    def _render_quest_subtab(self, parent, quest_key, empty_text):
        """Render a quest sub-tab (main or side).

        Entries come from the quest runtime's Journal mirror (quests.sync_journal).
        Active quests are listed first; completed quests trail at the bottom,
        dimmed, as a paper trail.
        """
        quests = self.player.get("journal", {}).get(quest_key, [])
        if not quests:
            self.styled_label(parent, text=empty_text, fg=Theme.TEXT_DIM).pack(
                anchor=tk.CENTER, expand=True
            )
            return

        scroll = tk.Scrollbar(parent)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(parent, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        ordered = sorted(
            quests,
            key=lambda q: (q.get("status") == "complete", q.get("day", 0)),
        )

        for q in ordered:
            status = q.get("status", "active")
            completed = status == "complete"
            ready = status == "ready"

            frame = tk.LabelFrame(
                inner,
                text=f" {q.get('name', 'Quest')} ",
                bg=Theme.BG_DARK,
                fg=Theme.TEXT_DIM if completed else Theme.TEXT,
                font=Theme.FONT_BOLD,
                highlightthickness=1,
                highlightbackground=Theme.BORDER,
            )
            frame.pack(fill=tk.X, pady=4, padx=4)

            # Status chip
            if completed:
                chip_text, chip_color = "✓ COMPLETE", Theme.TEXT_DIM
            elif ready:
                chip_text, chip_color = "★ READY TO TURN IN", Theme.BUFF_POSITIVE
            else:
                chip_text, chip_color = "ACTIVE", Theme.ACCENT
            self.styled_label(
                frame, text=chip_text, fg=chip_color, font=Theme.FONT_SMALL
            ).pack(anchor=tk.W, padx=6, pady=(2, 0))

            self.styled_label(
                frame,
                text=q.get("desc", ""),
                fg=Theme.TEXT_DIM if completed else Theme.TEXT,
            ).pack(anchor=tk.W, padx=6, pady=2)

            for obj in q.get("objectives", []):
                done = bool(obj.get("done"))
                mark = "✓" if done else "☐"
                color = Theme.BUFF_POSITIVE if done else Theme.TEXT_DIM
                self.styled_label(
                    frame, text=f"   {mark} {obj.get('label', '')}", fg=color
                ).pack(anchor=tk.W, padx=6, pady=0)

            if q.get("day"):
                self.styled_label(
                    frame, text=format_short_date(q["day"]), fg=Theme.TEXT_DIM,
                ).pack(anchor=tk.W, padx=6, pady=(2, 2))

    def _render_event_subtab(self, parent):
        """Render the Event sub-tab showing all recorded events."""
        events = self.player.get("journal", {}).get("events", [])
        if not events:
            self.styled_label(parent, text="No events recorded yet.", fg=Theme.TEXT_DIM).pack(
                anchor=tk.CENTER, expand=True
            )
            return

        # Scrollable container
        scroll = tk.Scrollbar(parent)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(parent, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        # Show most recent events first
        for evt in reversed(events):
            tag = evt.get("tag", "")
            if "[FIXED]" in tag:
                tag_color = Theme.ACCENT
            elif "[MAP BOSS]" in tag:
                # Seasonal Warden beats wear the world-map marker's gold.
                tag_color = "#d4a017"
            else:
                tag_color = Theme.BUFF_NEUTRAL

            frame = tk.LabelFrame(
                inner,
                text=f" {tag}  {evt.get('name', 'Event')} ",
                bg=Theme.BG_DARK,
                fg=tag_color,
                font=Theme.FONT_BOLD,
                highlightthickness=1,
                highlightbackground=Theme.BORDER,
            )
            frame.pack(fill=tk.X, pady=4, padx=4)

            self.styled_label(frame, text=evt.get("desc", "")).pack(
                anchor=tk.W, padx=6, pady=2
            )
            if evt.get("day"):
                # Create a temp dict with the day for format_date
                day_info = {"day": evt["day"]}
                self.styled_label(
                    frame, text=format_date(day_info),
                    fg=Theme.TEXT_DIM,
                ).pack(anchor=tk.W, padx=6, pady=1)

    # ═══════════════════════════════════════════════════════════════════════
    #  Actions
    # ═══════════════════════════════════════════════════════════════════════

    def _compute_buff_mods(self, entity):
        """Compute attribute buffs from active_buffs for any entity."""
        buff_mods = {}
        for buff in entity.get("active_buffs", []):
            if buff.get("stat") == "all" or buff.get("type") == "blessing":
                for attr in ATTRIBUTES:
                    buff_mods[attr] = buff_mods.get(attr, 0) + buff["value"]
            elif buff.get("stat") in ATTRIBUTES:
                attr = buff["stat"]
                buff_mods[attr] = buff_mods.get(attr, 0) + buff["value"]
        return buff_mods

    def _equip_item(self, item):
        """Equip an item on the player, or on the targeted ally if set."""
        from pandemonium.combat.ally import equip_ally_item
        from pandemonium.inventory.core import equip_item
        # ── Ally target path ─────────────────────────────────────────────
        if self._equip_target_ally is not None:
            ally = self._equip_target_ally
            slot_hint = self._equip_target_slot
            # Clear target immediately to avoid stale references
            self._equip_target_ally = None
            self._equip_target_slot = None

            # Handle accessory slot selection
            if item.get("slot") == "accessory" and slot_hint not in (
                    "accessory1", "accessory2", "accessory3"):
                eq = ally.get("equipped", {})
                if _acc_slots_full(eq, ally.get("acc3_unlocked")):
                    self._prompt_accessory_choice(item, target="ally", ally=ally)
                    return

            result = equip_ally_item(ally, item, self.player, target_slot=slot_hint)
            self.sm.log(result if isinstance(result, str) else f"Equipped {item['name']} on {display_name(ally)}.")
            self._show_character_page(ally)
            return

        # ── Player path (original) ───────────────────────────────────────

        # Handle accessory slot selection
        if item.get("slot") == "accessory":
            eq = self.player.get("equipped", {})
            if _acc_slots_full(eq, self.player.get("acc3_unlocked")):
                self._prompt_accessory_choice(item, target="player")
                return

        # Remove from inventory first
        try:
            idx = next(i for i, itm in enumerate(self.player.get("inventory", [])) if itm is item)
            self.player["inventory"].pop(idx)
        except (StopIteration, IndexError):
            pass

        result = equip_item(self.player, item)
        if result is False:
            # Equip failed (inventory full) — restore item
            self.player.setdefault("inventory", []).append(item)
            self.sm.log(f"Cannot equip {item['name']} — inventory full.")
        else:
            self.sm.log(f"Equipped {item['name']}.")
        self._refresh_all()

    def _unequip_slot(self, slot):
        """Unequip a slot on the player."""
        from pandemonium.inventory.core import unequip_slot
        result = unequip_slot(self.player, slot)
        self._handle_unequip_result(result)
        self._refresh_all()

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 6 — Event Horizon (visible only while a run is active/suspended)
    # ═══════════════════════════════════════════════════════════════════════

    def _eh_meta(self):
        """The persistent Event Horizon state dict (never None)."""
        return (self.player or {}).get("event_horizon") or {}

    def _eh_run_state(self):
        """The active/suspended Event Horizon run dict, or None."""
        state = self._eh_meta()
        return state if state.get("run_active") else None

    def _eh_tab_visible(self):
        """Tab shows while a run is live/suspended — or as a quiet history stub."""
        state = self._eh_meta()
        return (bool(state.get("run_active"))
                or int(state.get("best_room", 0) or 0) > 0)

    def _build_eh_tab(self):
        self.eh_frame = tk.Frame(self.notebook, bg=Theme.BG_DARK)
        self.notebook.add(self.eh_frame, text=" Event Horizon ")
        self._refresh_eh_tab()

    def _refresh_eh_tab(self):
        import pandemonium.world.event_horizon as eh
        for w in self.eh_frame.winfo_children():
            w.destroy()


        state = self._eh_meta()
        running = bool(state.get("run_active"))
        inside = bool((self.player or {}).get("_eh_in_run"))
        best = max(int(state.get("best_room", 0) or 0),
                   int(state.get("room", 0) or 0))

        if not running:
            # History stub — no live run to manage right now.
            self.styled_label(
                self.eh_frame,
                text=(f"No active Event Horizon run.\n\n"
                      f"Best room ever: {best}\n\n"
                      "Step into the rift again at the Event Horizon site "
                      "(world map, east of Veilholt)."),
                fg=Theme.TEXT_DIM, justify=tk.CENTER,
            ).pack(anchor=tk.CENTER, expand=True, padx=18, pady=18)
            return

        scroll = tk.Scrollbar(self.eh_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas = tk.Canvas(self.eh_frame, bg=Theme.BG_DARK, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=canvas.yview)
        canvas.config(yscrollcommand=scroll.set)
        inner = tk.Frame(canvas, bg=Theme.BG_DARK)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.config(scrollregion=canvas.bbox("all")))

        room = int(state.get("room", 0))
        motes = int(state.get("motes", 0))
        entropy = eh.get_entropy_total(self.player)
        pct = int(round(eh.entropy_stat_penalty(entropy) * 100))

        # ── Run status ──────────────────────────────────────────────────
        status = tk.LabelFrame(
            inner, text=" The Run ", bg=Theme.BG_DARK, fg=Theme.ACCENT,
            font=Theme.FONT_BOLD, highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        status.pack(fill=tk.X, pady=4, padx=4)
        if inside:
            banner, banner_fg = ("▶ IN RUN — deep in the distortion. "
                                 "Everything below is live.", Theme.ACCENT)
        else:
            banner, banner_fg = ("⏸ SUSPENDED — resume at the Event Horizon "
                                 "site. Flasks, cards and Entropy wait there.",
                                 Theme.TEXT_DIM)
        tk.Label(status, text=banner, bg=Theme.BG_DARK, fg=banner_fg,
                 font=Theme.FONT_SMALL, anchor=tk.W, wraplength=620,
                 justify=tk.LEFT).pack(fill=tk.X, padx=8, pady=(4, 2))
        rows = [
            ("Next room", f"{room + 1}"),
            ("Deepest room (this run)", f"{room}"),
            ("Best room ever", f"{best}"),
            ("Horizon Motes", f"\u25ce {motes}"),
            ("Entropy", f"{entropy} stacks  (attributes \u2212{pct}%)"),
        ]
        for label, value in rows:
            row = tk.Frame(status, bg=Theme.BG_DARK)
            row.pack(fill=tk.X, padx=8, pady=1)
            tk.Label(row, text=label, bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
                     font=Theme.FONT_SMALL, anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=Theme.BG_DARK, fg=Theme.TEXT,
                     font=Theme.FONT_SMALL, anchor=tk.E).pack(side=tk.RIGHT)
        tk.Frame(status, bg=Theme.BG_DARK, height=3).pack()

        # ── Entropy afflictions ─────────────────────────────────────────
        aff_frame = tk.LabelFrame(
            inner, text=" Entropy Afflictions (battle-start debuffs) ",
            bg=Theme.BG_DARK, fg=Theme.BUFF_NEGATIVE, font=Theme.FONT_BOLD,
            highlightthickness=1, highlightbackground=Theme.BORDER,
        )
        aff_frame.pack(fill=tk.X, pady=4, padx=4)
        aff = list(state.get("entropy_afflictions") or [])
        if aff:
            for i, key in enumerate(aff, 1):
                name, desc = eh.ENTROPY_AFFLICTION_INFO.get(
                    key, (str(key).title(), ""))
                tk.Label(
                    aff_frame, text=f"{i}. {name} — {desc}",
                    bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_SMALL,
                    anchor=tk.W, wraplength=620, justify=tk.LEFT,
                ).pack(fill=tk.X, padx=8, pady=1)
        else:
            self.styled_label(aff_frame, text="None yet.",
                              fg=Theme.TEXT_DIM).pack(anchor=tk.W, padx=8,
                                                      pady=2)
        if len(aff) < len(eh.ENTROPY_DEBUFF_POOL):
            next_at = (len(aff) + 1) * eh.EH_ENTROPY_AFFLICTION_EVERY
            self.styled_label(
                aff_frame,
                text=(f"Entropy gains a random affliction every "
                      f"{eh.EH_ENTROPY_AFFLICTION_EVERY} stacks "
                      f"(next at {next_at}). Battles only use the afflictions "
                      f"listed above."),
                fg=Theme.TEXT_DIM,
            ).pack(anchor=tk.W, padx=8, pady=(2, 4))

        # ── Flask effects per actor ─────────────────────────────────────
        flask_frame = tk.LabelFrame(
            inner, text=" Flask Effects (permanent for the run) ",
            bg=Theme.BG_DARK, fg=Theme.BUFF_POSITIVE, font=Theme.FONT_BOLD,
            highlightthickness=1, highlightbackground=Theme.BORDER,
        )
        flask_frame.pack(fill=tk.X, pady=4, padx=4)
        flasks = state.get("actor_flasks") or {}
        if flasks:
            for key in sorted(flasks):
                who = "You" if key == "player" else str(key).split(":", 1)[-1]
                # Running total of the actor's flasks rides on the name row
                # (2026-10-08 request: "+n% dmg, so on" beside the actor name).
                total = eh.format_flask_summary(flasks[key])
                head = tk.Frame(flask_frame, bg=Theme.BG_DARK)
                head.pack(fill=tk.X, padx=8, pady=(4, 0))
                tk.Label(head, text=who, bg=Theme.BG_DARK,
                         fg=Theme.TEXT_HEADER, font=Theme.FONT_BOLD,
                         anchor=tk.W).pack(side=tk.LEFT)
                if total:
                    tk.Label(head, text=total, bg=Theme.BG_DARK,
                             fg=Theme.BUFF_POSITIVE, font=Theme.FONT_SMALL,
                             anchor=tk.E).pack(side=tk.RIGHT)
                for rec in flasks[key]:
                    tk.Label(
                        flask_frame,
                        text=f"    \u2022 {rec.get('label') or rec.get('name', '?')}",
                        bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_SMALL,
                        anchor=tk.W, wraplength=620, justify=tk.LEFT,
                    ).pack(fill=tk.X, padx=8)
        else:
            self.styled_label(flask_frame, text="No flasks consumed yet.",
                              fg=Theme.TEXT_DIM).pack(anchor=tk.W, padx=8, pady=4)

        # ── Tarot hand (the Joker's arcana, docs/joker_cards_proposal.md) ──
        tarot_frame = tk.LabelFrame(
            inner, text=" Tarot Hand (the Joker's arcana) ", bg=Theme.BG_DARK,
            fg=Theme.TEXT_HEADER, font=Theme.FONT_BOLD,
            highlightthickness=1, highlightbackground=Theme.BORDER,
        )
        tarot_frame.pack(fill=tk.X, pady=4, padx=4)
        jokers = state.get("joker_cards") or []
        head = tk.Frame(tarot_frame, bg=Theme.BG_DARK)
        head.pack(fill=tk.X, padx=8, pady=(4, 0))
        tk.Label(head, text=f"Hand: {len(jokers)} / {eh.EH_JOKER_HAND_CAP}",
                 bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_SMALL,
                 anchor=tk.W).pack(side=tk.LEFT)
        if any(r.get("id") == "joker_world" for r in jokers):
            tk.Label(head, text="The deal is closed.", bg=Theme.BG_DARK,
                     fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL,
                     anchor=tk.E).pack(side=tk.RIGHT)
        else:
            tk.Label(head, text="the Joker deals 2 at every 25th room",
                     bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
                     font=Theme.FONT_SMALL,
                     anchor=tk.E).pack(side=tk.RIGHT)
        if jokers:
            for r in jokers:
                tk.Label(
                    tarot_frame,
                    text=f"  \u2022 {r.get('name', '?')} — {r.get('desc', '')}",
                    bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_SMALL,
                    anchor=tk.W, wraplength=620, justify=tk.LEFT,
                ).pack(fill=tk.X, padx=8, pady=1)
        else:
            self.styled_label(tarot_frame, text="No arcana taken yet.",
                              fg=Theme.TEXT_DIM).pack(anchor=tk.W, padx=8, pady=4)

        # ── Positive cards ──────────────────────────────────────────────
        pos_frame = tk.LabelFrame(
            inner, text=" Deep Boons (team cards) ", bg=Theme.BG_DARK,
            fg=Theme.BUFF_POSITIVE, font=Theme.FONT_BOLD,
            highlightthickness=1, highlightbackground=Theme.BORDER,
        )
        pos_frame.pack(fill=tk.X, pady=4, padx=4)
        pos = state.get("positive_cards") or []
        if pos:
            for c in pos:
                tk.Label(
                    pos_frame,
                    text=(f"\u2022 {c.get('name', '?')} (T{c.get('tier', '?')}) "
                          f"— {c.get('desc', '')}"),
                    bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_SMALL,
                    anchor=tk.W, wraplength=620, justify=tk.LEFT,
                ).pack(fill=tk.X, padx=8, pady=1)
        else:
            self.styled_label(pos_frame, text="None taken.",
                              fg=Theme.TEXT_DIM).pack(anchor=tk.W, padx=8, pady=4)

        # ── Negative cards ──────────────────────────────────────────────
        neg_frame = tk.LabelFrame(
            inner, text=" Trial Burdens (enemy cards) ", bg=Theme.BG_DARK,
            fg=Theme.BUFF_NEGATIVE, font=Theme.FONT_BOLD,
            highlightthickness=1, highlightbackground=Theme.BORDER,
        )
        neg_frame.pack(fill=tk.X, pady=4, padx=4)
        neg = state.get("negative_cards") or []
        if neg:
            for c in neg:
                cost = c.get("entropy_cost", 0)
                tk.Label(
                    neg_frame,
                    text=(f"\u2022 {c.get('name', '?')} (T{c.get('tier', '?')}) "
                          f"— {c.get('desc', '')}  [Entropy +{cost}]"),
                    bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_SMALL,
                    anchor=tk.W, wraplength=620, justify=tk.LEFT,
                ).pack(fill=tk.X, padx=8, pady=1)
        else:
            self.styled_label(neg_frame, text="None taken.",
                              fg=Theme.TEXT_DIM).pack(anchor=tk.W, padx=8, pady=4)

        # ── Footer ───────────────────────────────────────────────────────
        self.styled_label(
            inner,
            text=("Everything here is lost on death or abandon — only your "
                  "best room is kept. Save & quit suspends the run."),
            fg=Theme.TEXT_DIM,
        ).pack(anchor=tk.W, padx=6, pady=(6, 10))

    @staticmethod
    def _weapon_element_line(item):
        """Examine line naming the element a weapon actually strikes with.

        Unique weapons keep their hand-authored names (no flower-tier word) —
        the element and its trait tier live here instead, so a player can see
        that, say, Abyss Fang causes Dark damage with Leech II.
        """
        if item.get("type") != "equipment" or item.get("slot") != "weapon":
            return ""
        dmg = item.get("elemental_dmg") or {}
        if not dmg:
            return ""
        primary = item.get("primary_element")
        if not primary or dmg.get(primary, 0.0) <= 1.0:
            primary = max(dmg, key=lambda el: dmg.get(el, 1.0))
        value = dmg.get(primary, 1.0)
        if value <= 1.0:
            return ""
        detail = f"\u00d7{value:.2f}"
        trait_name = ""
        try:
            from pandemonium.combat.elemental_traits import get_trait_for_weapon
            trait_name = (get_trait_for_weapon(item, item.get("rarity", "unique")) or {}).get("name", "")
        except Exception:
            trait_name = ""
        if trait_name:
            roman = {1: "I", 2: "II", 3: "III"}.get(item.get("trait_tier"))
            detail += f" | {trait_name}" + (f" {roman}" if roman else "")
        return (f"This weapon causes {primary.title()} damage ({detail}) "
                f"and powers {primary.title()} skills.")

    @staticmethod
    def _equipment_resistance_text(item):
        """'Resists Fire ×1.15 … · weak to Water ×0.85' ('' when neutral)."""
        res = item.get("elemental_res") or {}
        strong, weak = [], []
        for element, value in res.items():
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value > 1.0:
                strong.append(f"{element.title()} ×{value:.2f}")
            elif value < 1.0:
                weak.append(f"{element.title()} ×{value:.2f}")
        parts = []
        if strong:
            parts.append("Resists " + ", ".join(strong))
        if weak:
            parts.append("weak to " + ", ".join(weak))
        return " · ".join(parts)

    @staticmethod
    def _weapon_skill_boost_line(item):
        """Line for secondary/tertiary weapon elements (skills only).

        Weapon slots after the primary never proc traits or basic attacks —
        they only strengthen off-element skills. The Examine popup names them
        so a multi-element weapon's skill profile is visible.
        """
        if item.get("type") != "equipment" or item.get("slot") != "weapon":
            return ""
        dmg = item.get("elemental_dmg") or {}
        infusions = item.get("infusions") or []
        entries = []
        if item.get("unique"):
            # A unique's primary is locked; every infusion is an extra slot.
            extras = infusions
        elif len(infusions) > 1:
            extras = infusions[1:]
        else:
            extras = None
        if extras is not None:
            for inf in extras:
                element = inf.get("element")
                value = float(dmg.get(element, inf.get("value", 1.0)) or 1.0)
                if element and value > 1.0:
                    entries.append((element, value))
        else:
            # Legacy multi-element profiles without infusion slots.
            primary = item.get("primary_element")
            for element, value in dmg.items():
                if element != primary and float(value) > 1.0:
                    entries.append((element, float(value)))
        if not entries:
            return ""
        parts = [f"{element.title()} (\u00d7{value:.2f})" for element, value in entries]
        if len(parts) == 1:
            joined = parts[0]
        else:
            joined = ", ".join(parts[:-1]) + " and " + parts[-1]
        return f"This weapon boosts skills with {joined}."

    def _equipment_examine_body(self, item):
        """Affinity + Effect summary for a non-unique equipment piece.

        No lore: just the stats the piece grants (its affinity) and what it
        actually does, so players can compare gear without the blacksmith.
        """

        template = ITEMS.get(item.get("id"), {}) or {}
        mods = item.get("mods") or {}
        stat_txt = ", ".join(
            f"{stat} {'+' if value >= 0 else ''}{value}"
            for stat, value in mods.items()
        ) or "None"

        effects = []
        scale_txt = format_scaling_stat(item)
        if scale_txt:
            effects.append(scale_txt.lstrip("▸ ").strip())
        if item.get("slot") == "weapon":
            element_line = self._weapon_element_line(item)
            if element_line:
                effects.append(element_line)
            skill_line = self._weapon_skill_boost_line(item)
            if skill_line:
                effects.append(skill_line)
        else:
            effects.append(
                self._equipment_resistance_text(item)
                or "No elemental resistance — infuse a flower"
            )
        perk_line = describe_item_perk(item) or describe_item_perk(template)
        if perk_line:
            effects.append(f"Tradition — {perk_line}")
        special = item.get("special") or template.get("special")
        if special:
            effect_txt = unique_effect_text(special)
            if effect_txt:
                effects.append(effect_txt)

        body = f"Affinity: {stat_txt}"
        if effects:
            body += "\n\nEffect: " + " · ".join(effects)
        else:
            body += "\n\nEffect: None."
        return body

    def _examine_item(self, item):
        """Popup showing an item's name, rarity, lore, and equip effect.

        Covers key items and every unique (in the bag or equipped). Uniques
        state their equip effect: boss drops / guild legacies / Event Horizon
        trophies via `resources.unique_effects.py`, wedding accessories via
        their combat blurbs (base + bonded variant), and flavour-only uniques
        say so instead of staying silent.

        Ordinary equipment gets the compact form: its display name (rarity +
        element + form + enhancement) with Affinity and Effect lines, no lore.
        """

        name = item.get("name", "Key Item")
        if item.get("type") == "equipment" and not self._is_unique_item(item):
            ok_dialog(self, name,
                      f"{name}\n\n{self._equipment_examine_body(item)}")
            return

        template = ITEMS.get(item.get("id"), {}) or {}
        desc = item.get("description")
        if not desc:
            # Instances built before descriptions were carried through (old saves)
            desc = template.get("description")
        special = item.get("special") or template.get("special")

        effect = unique_effect_text(special)
        bonded_note = ""
        if not effect and special:
            # Wedding accessories keep their blurbs next to their implementation.
            try:
                from pandemonium.combat.weapon.wedding_specials import wedding_special_blurb
                effect = wedding_special_blurb(special, bonded=False)
                bonded = wedding_special_blurb(special, bonded=True)
                if bonded and bonded != effect:
                    bonded_note = f"Bonded (girl in active party): {bonded}"
            except Exception:
                effect = ""

        rarity = (item.get("rarity")
                  or template.get("drop_rarity")
                  or template.get("rarity") or "")
        rarity = rarity.capitalize()
        body = f"{name}  ({rarity})" if rarity else name
        element_line = self._weapon_element_line(item)
        if element_line:
            body += f"\n\n{element_line}"
        skill_line = self._weapon_skill_boost_line(item)
        if skill_line:
            body += f"\n{skill_line}"
        if item.get("slot") != "weapon":
            res_line = self._equipment_resistance_text(item)
            if res_line:
                body += f"\n\n{res_line}"
        if desc:
            body += f"\n\n{desc}"
        if effect:
            body += f"\n\nEquip Effect: {effect}"
        perk_line = describe_item_perk(item) or describe_item_perk(template)
        if perk_line:
            body += f"\n\nForm tradition — {perk_line}"
        if bonded_note:
            body += f"\n\n{bonded_note}"
        elif not desc and not effect and not perk_line:
            body += "\n\nNo description recorded for this keepsake."
        ok_dialog(self, name, body)

    def _use_beating_root(self, item):
        """Pick one actor to consume a Beating Root (opens their 3rd slot)."""
        import pandemonium.world.event_horizon as eh

        actors = [self.player] + list(self.player.get("allies", []))
        locked = [a for a in actors if not a.get("acc3_unlocked")]

        dlg = tk.Toplevel(self)
        dlg.title("Beating Root")
        dlg.configure(bg=Theme.BG_DARK)
        dlg.geometry(f"420x{150 + 38 * max(1, len(locked))}")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg, text="Whose third accessory slot should open?",
            bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_BOLD,
            wraplength=380, justify=tk.CENTER,
        ).pack(pady=(10, 4))
        tk.Label(
            dlg, text=("The root is consumed — the chosen actor keeps the "
                       "unlock forever, even at home in the house."),
            bg=Theme.BG_DARK, fg=Theme.TEXT_DIM, font=Theme.FONT_SMALL,
            wraplength=380, justify=tk.CENTER,
        ).pack(pady=(0, 6))

        def choose(actor):
            self.sm.log(eh.consume_beating_root(self.player, actor))
            dlg.destroy()
            self._refresh_all()

        if locked:
            for actor in locked:
                name = "You" if actor is self.player else display_name(actor)
                self.styled_button(
                    dlg, text=name, width=30,
                    command=lambda a=actor: choose(a),
                ).pack(pady=2)
        else:
            tk.Label(dlg, text="Every actor already carries the root.",
                     bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
                     font=Theme.FONT_SMALL).pack(pady=8)
        self.styled_button(dlg, text="Cancel", command=dlg.destroy).pack(pady=(8, 6))

    def _use_item(self, item):
        """Use a consumable/utility item."""
        from pandemonium.inventory.core import use_consumable, remove_item_by_reference, is_combat_only_item
        if is_combat_only_item(item):
            self.sm.log(f"{item['name']} can only be used in combat.")
            return
        msg = use_consumable(self.player, item, combat_state=None)
        self.sm.log(msg)
        remove_item_by_reference(self.player, item)
        self._refresh_all()

    def _drop_item(self, item):
        """Drop an item from inventory. Confirms for rare+ items. Key/unique items cannot be dropped."""
        if item.get("type") in ("key_item", "crafting_material"):
            self.sm.log("Key items cannot be dropped.")
            return
        if self._is_unique_item(item):
            self.sm.log("Unique items cannot be dropped.")
            return
        rarity = item.get("rarity", "common")
        if rarity in ("rare", "epic", "legendary", "mythic"):
            confirm_dialog(
                parent=self,
                title="Drop Rare Item?",
                message=f"Are you sure you want to drop {item['name']} ({rarity})?\nThis cannot be undone.",
                on_yes=lambda: self._do_drop(item),
            )
        else:
            self._do_drop(item)

    def _do_drop(self, item):
        """Actually perform the drop."""
        from pandemonium.inventory.core import remove_item_by_reference
        remove_item_by_reference(self.player, item, item.get("count", 1))
        self.sm.log(f"Dropped {item['name']}.")
        self._refresh_all()

    def _unequip_ally_slot(self, ally, slot):
        """Unequip a slot on an ally, staying on that ally's page."""
        from pandemonium.combat.ally import unequip_ally_slot
        result = unequip_ally_slot(ally, slot, self.player)
        self._remember_character(ally)
        self._handle_unequip_result(result)
        self._refresh_all()

    def _handle_unequip_result(self, result):
        """Log an unequip result; pop up a warning window if inventory is full."""
        if result and "inventory is full" in result.lower():
            self.sm.log(result)
            ok_dialog(
                parent=self,
                title="Inventory Full",
                message=(
                    f"{result}\n\n"
                    "Unequip failed. Drop or sell an item from your Bag "
                    "to make room, then try again."
                ),
            )
            return
        self.sm.log(result if isinstance(result, str) else "Done.")

    def _prompt_accessory_choice(self, item, target="player", ally=None):
        """Prompt user to choose which accessory slot to replace."""
        if target == "player":
            eq = self.player.get("equipped", {})
            unlocked3 = bool(self.player.get("acc3_unlocked"))
        else:
            eq = ally.get("equipped", {})
            unlocked3 = bool(ally.get("acc3_unlocked"))
        acc1 = eq.get("accessory1")
        acc2 = eq.get("accessory2")
        acc3 = eq.get("accessory3") if unlocked3 else None

        dlg = tk.Toplevel(self)
        dlg.title("Choose Accessory Slot")
        dlg.configure(bg=Theme.BG_DARK)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg, text=f"All accessory slots occupied. Replace which?",
            bg=Theme.BG_DARK, fg=Theme.TEXT, font=Theme.FONT_BOLD,
        ).pack(pady=8)

        def choose(slot):
            from pandemonium.inventory.core import equip_item
            from pandemonium.combat.ally import equip_ally_item
            if target == "player":
                # Remove from inventory first
                try:
                    idx = next(i for i, itm in enumerate(self.player.get("inventory", [])) if itm is item)
                    self.player["inventory"].pop(idx)
                except (StopIteration, IndexError):
                    pass

                result = equip_item(self.player, item, target_slot=slot)
                if result is False:
                    self.player.setdefault("inventory", []).append(item)
                    self.sm.log(f"Cannot equip {item['name']} — inventory full.")
                else:
                    self.sm.log(f"Equipped {item['name']} in {slot}.")
            else:
                # equip_ally_item handles inventory removal internally
                result = equip_ally_item(ally, item, self.player, target_slot=slot)
                self.sm.log(result if isinstance(result, str) else f"Equipped {item['name']} on {display_name(ally)}.")

            dlg.destroy()
            if target == "player":
                self._refresh_all()
            else:
                self._show_character_page(ally)

        btn1_text = f"Replace {acc1['name']}" if acc1 else "Accessory 1"
        btn2_text = f"Replace {acc2['name']}" if acc2 else "Accessory 2"

        self.styled_button(dlg, text=btn1_text, command=lambda: choose("accessory1")).pack(pady=4)
        self.styled_button(dlg, text=btn2_text, command=lambda: choose("accessory2")).pack(pady=4)
        if unlocked3:
            btn3_text = f"Replace {acc3['name']}" if acc3 else "Accessory 3"
            self.styled_button(dlg, text=btn3_text, command=lambda: choose("accessory3")).pack(pady=4)
        self.styled_button(dlg, text="Cancel", command=dlg.destroy).pack(pady=4)

        # Center over the app window — without explicit coordinates the window
        # manager drops this dialog in the top-left corner.
        dlg.update_idletasks()
        width, height = 400, 240 if unlocked3 else 200
        try:
            parent = self.winfo_toplevel()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except tk.TclError:
            px, py, pw, ph = 100, 100, 800, 600
        dlg.geometry(
            f"{width}x{height}"
            f"+{px + (pw - width) // 2}+{py + (ph - height) // 2}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    #  Navigation / Refresh
    # ═══════════════════════════════════════════════════════════════════════

    def _on_main_tab_changed(self, _event=None):
        """Rebuild the Bag whenever it becomes the visible tab.

        Dungeon loot (flowers especially) is added while this screen sits
        hidden, so a bag built once at login went stale and looked empty.
        """
        try:
            if self.notebook.select() == str(self.bag_frame):
                self._refresh_bag_tab()
        except tk.TclError:
            pass

    def _remember_character(self, char):
        """Keep *char*'s Characters sub-tab selected (you, or an ally in the party)."""
        chars = self._characters()
        index = None
        for idx, candidate in enumerate(chars):
            if candidate is char:
                index = idx
                break
        if index is None:
            try:
                index = chars.index(char)
            except ValueError:
                return
        self._char_tab_index = index
        # Mirror the choice onto the live notebook so a concurrent refresh
        # cannot fall back to the previously displayed character.
        try:
            if self.char_notebook is not None:
                self.char_notebook.select(index)
        except (tk.TclError, ValueError):
            pass

    def _show_character_page(self, char, view="overview"):
        """Refresh the screen, then return to *char*'s page.

        Opens the Overview by default — that's where gear lives, and where the
        Bag's "equip to ally" flow should land.
        """
        self._char_view = view
        self._remember_character(char)
        self._refresh_all()
        try:
            self.notebook.select(self.characters_frame)
            if self.char_notebook is not None and self._char_pages:
                self.char_notebook.select(min(self._char_tab_index, len(self._char_pages) - 1))
        except (tk.TclError, ValueError):
            pass

    def _refresh_all(self):
        self._refresh_characters_tab()
        self._refresh_bag_tab()
        self._refresh_journal_tab()
        if hasattr(self, "eh_frame"):
            self._refresh_eh_tab()

    def _on_back(self):
        """Return to the previous screen — dismiss overlay or go back in history."""
        if self.is_overlay:
            self.sm.dismiss_overlay()
        else:
            self.sm.go_back()

    def handle_escape(self):
        """Override: Esc dismisses overlay or returns to previous screen."""
        self._on_back()


def _acc_slots_full(eq, acc3_unlocked):
    """True when every accessory slot this actor owns is occupied."""
    if not (eq.get("accessory1") and eq.get("accessory2")):
        return False
    if acc3_unlocked and not eq.get("accessory3"):
        return False
    return True


def _slot_display_name(slot):
    if slot == "accessory1":
        return "Accessory 1"
    if slot == "accessory2":
        return "Accessory 2"
    if slot == "accessory3":
        return "Accessory 3"
    return slot.title()