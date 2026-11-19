"""
gui/screens/city_screen.py — City hub with service buttons and action bar.

Shows all city services as clickable buttons, plus Inventory, Travel,
Dungeon, and Save & Quit actions.
"""

import tkinter as tk
import tkinter.font as tkfont

import pandemonium.progression.karma as karma
from pandemonium.progression.karma_dialogue import service_line

from pandemonium.gui.screens.base_screen import BaseScreen
from pandemonium.gui.theme import Theme
from pandemonium.gui.widgets.confirm_dialog import choice_dialog, confirm_dialog, ok_dialog
from pandemonium.gui.widgets.keyboard_nav import NavGroup
from pandemonium.gui.widgets.overlay_panel import OverlayPanel
from pandemonium.gui.widgets.hp_bar import HPBar

from pandemonium.resources.cities import CITIES
from pandemonium.core.character import player_max_hp
from pandemonium.core.save_load import save_game
from pandemonium.core.utils import display_name
from pandemonium.core.events import format_date, get_event_queue_events
from pandemonium.combat.combat_ui import _get_entity_buff_tags
import random as _random
from pandemonium.resources.city_maps import CITY_SERVICE_POSITIONS
from pandemonium.gui.widgets.city_map import CityMapWidget
from pandemonium.core.time_blocks import is_service_open
from pandemonium.facilities.house import HOUSE_LEVELS, _pending_income
from pandemonium.core.events import format_event_alert
from pandemonium.gui.widgets.event_dialog import show_event_notice
import random
from pandemonium.combat import city_guards
from pandemonium.progression.titles import format_name as _format_title_name
from pandemonium.gui.screens.base_screen import city_header_parts
from pandemonium.progression.karma_dialogue import title_line
import pandemonium.core.time_blocks as time_blocks
from pandemonium.facilities.house import house_menu
from pandemonium.resources.house_stories import get_part
from pandemonium.world.curse_pandemonium import end_pandemonium_run
from pandemonium.core.time_blocks import format_block_track
from pandemonium.gui.screens.settings_screen import SettingsScreen


# The hero card is laid out for a full 8-actor party. Each member box uses
# this fixed slot size, so a 2-member party does not stretch into huge boxes
# and an 8-member party still fits without overflow.
HERO_CARD_MAX_SLOTS = 8          # == combat.ally.MAX_PARTY_SIZE (player + 7)
# Worst-case non-box width at 8 members: gaps + front/back dividers + margin.
HERO_ROW_EXTRAS_MAX = 8 * (HERO_CARD_MAX_SLOTS - 1) + 15 + 32 + 10


def _fit_text_to_width(text, font, max_width, ellipsis="\u2026"):
    """Truncate `text` with an ellipsis so its rendered width fits `max_width`.

    Used by the single-row party card: character names and titles are free
    text, and a long one used to push the card past the window edge.
    """
    if not text:
        return ""
    if max_width <= 0:
        return ""
    try:
        measure = tkfont.Font(font=font).measure
    except Exception:
        # No Tk root yet (e.g. headless call) — leave the text untouched.
        return text
    if measure(text) <= max_width:
        return text
    ell_width = measure(ellipsis)
    if ell_width > max_width:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid]) + ell_width <= max_width:
            lo = mid
        else:
            hi = mid - 1
    if lo <= 0:
        return ellipsis
    return text[:lo].rstrip() + ellipsis


class CityScreen(BaseScreen):
    """The city hub — main navigation screen between dungeon runs."""

    def build_ui(self):
        from pandemonium.world.city_dialogue import get_city_dialogues
        self._refresh_city_id()
        self.sm.clear_history()
        self._update_top_bar()
        self.sm.clear_log()

        # Arrival checks run in order: Karma gate first, then story beats /
        # Event Horizon. A low-Karma gate must never stack with a story overlay.

        # ── Main layout ────────────────────────────────────────────────────────
        self.content = self.styled_frame(self)
        self.content.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # City name header
        city_name = self.city.get("name", "Unknown City")
        tk.Label(
            self.content,
            text=city_name.upper(),
            bg=Theme.BG_DARK,
            fg=Theme.ACCENT,
            font=Theme.FONT_LARGE,
        ).pack(pady=(0, 4))

        # Description
        desc = self.city.get("description", "")
        if desc:
            tk.Label(
                self.content,
                text=desc,
                bg=Theme.BG_DARK,
                fg=Theme.TEXT_DIM,
                font=Theme.FONT_SMALL,
                wraplength=700,
                justify=tk.CENTER,
            ).pack(pady=(0, 6))

        # ── Receptionist dialogue ─────────────────────────────────────────
        receptionist_lines = get_city_dialogues(self.city_id, "receptionist").get("enter", [])
        if receptionist_lines:
            dialogue = service_line(self.player, "receptionist", self.city_id)
            if not dialogue:
                dialogue = _random.choice(receptionist_lines)
            tk.Label(
                self.content,
                text=f'"{dialogue}"',
                bg=Theme.BG_DARK,
                fg=Theme.TEXT_DIM,
                font=(Theme.FONT_FAMILY, Theme.FONT_SIZE - 2, "italic") if Theme.FONT_SIZE > 1 else Theme.FONT_SMALL,
                wraplength=700,
                justify=tk.CENTER,
            ).pack(pady=(0, 10))
            # Also log to the session log
            self.sm.log(dialogue, category="dialogue")

        # ── Hero Status Card ────────────────────────────────────────────────
        if self.player:
            self._build_hero_card()

        # ── City Map (clickable ASCII art) ─────────────────────────────────────

        positions = CITY_SERVICE_POSITIONS.get(self.city_id, {})
        closed_services = [
            svc for svc in positions
            if svc != "dungeon"
            and not is_service_open(self.player, svc, self.city_id)
        ]

        self._map_frame = tk.Frame(self.content, bg=Theme.BG_DARK,
                                   highlightthickness=1, highlightbackground=Theme.BORDER)
        self._map_frame.pack(fill=tk.BOTH, expand=True, pady=8)

        self.city_map = CityMapWidget(
            self._map_frame,
            city_id=self.city_id,
            city=self.city,
            positions=positions,
            closed_services=closed_services,
            on_service_click=self._open_service,
            on_dungeon_click=self._enter_dungeon,
        )
        self.city_map.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Keyboard nav targets: house button (if any) + bottom action bar.
        self._button_entries = []

        # House button (below the map, if player owns a house in this city)
        has_house = self.city_id in self.player.get("houses", {})
        if has_house:
            house_data = self.player["houses"][self.city_id]
            lvl_name = HOUSE_LEVELS[house_data["level"]]["name"]
            pending = _pending_income(self.player, self.city_id, house_data)
            house_text = f"🏠 Your House ({lvl_name})"
            if pending > 0:
                house_text += f" [{pending}g]"

            house_wrap = tk.Frame(
                self.content, bg=Theme.BG_DARK,
                highlightthickness=1, highlightbackground=Theme.BG_DARK,
            )
            house_wrap.pack(pady=(4, 0))
            self._house_wrap = house_wrap
            self._house_btn = self.styled_button(
                house_wrap,
                text=house_text,
                command=self._open_house,
                width=28,
                bg=Theme.BG_LIGHT,
            )
            self._house_btn.pack(padx=2, pady=2)
            self._button_entries.append((house_wrap, self._house_btn))

        # ── Bottom action bar ──────────────────────────────────────────────────
        self._action_frame = tk.Frame(self.content, bg=Theme.BG_DARK)
        self._action_frame.pack(fill=tk.X, pady=(12, 0))
        action_frame = self._action_frame  # alias for local use below

        actions = [
            ("[I] Inventory", self._open_inventory),
            ("[M] World Map", self._open_world_map),
            ("[W] Wait", self._do_wait),
            ("[S] Settings", self._open_settings),
            ("[Q] Save & Quit", self._save_and_quit),
            ("[?] Help", self._show_help),
        ]

        for text, cmd in actions:
            wrap = tk.Frame(
                action_frame, bg=Theme.BG_DARK,
                highlightthickness=1, highlightbackground=Theme.BG_DARK,
            )
            wrap.pack(side=tk.LEFT, padx=4, expand=True)
            btn = self.styled_button(wrap, text=text, command=cmd, width=16)
            btn.pack(padx=2, pady=2)
            self._button_entries.append((wrap, btn))

        # ── Keyboard navigation ────────────────────────────────────────────
        # Two focus zones: the city map (facilities) and the button bar.
        # Tab switches zones; arrows move within the active zone.  Facilities
        # are highlighted in the ASCII art itself (Text tag), buttons use the
        # thin white ring used by the main menu and save browser.
        self._nav_buttons = NavGroup(self, self._button_entries)
        self._nav_buttons.clear_outline()
        self._zone = "map"
        self._set_zone("map")

        # ── Keyboard shortcuts ─────────────────────────────────────────────
        self._setup_city_keys()

        # ── Arrival checks ─────────────────────────────────────────────────
        # Deferred so navigation callbacks stay clean. The gate is one-shot
        # per travel/menu arrival (flag set by the travel/load paths).
        self.after(50, self._begin_arrival)

    def _setup_city_keys(self):
        """Bind keyboard shortcuts and outline-navigation keys."""
        self.bind("<KeyPress>", self._on_city_key)
        # Specific bindings win over the generic <KeyPress> handler above.
        for sequence in (
            "<Up>", "<Down>", "<Left>", "<Right>",
            "<Tab>", "<Shift-Tab>", "<ISO_Left_Tab>",
            "<Home>", "<End>",
            "<Return>", "<KP_Enter>", "<space>",
        ):
            self.bind(sequence, self._on_city_nav)
        self.focus_set()

    def _set_zone(self, zone):
        """Switch keyboard focus between map/floors and the button bar."""
        self._zone = zone
        floor_nav = getattr(self, "_floor_nav", None)
        if zone == "map":
            self._nav_buttons.clear_outline()
            if floor_nav is not None:
                floor_nav.clear_outline()
            self.city_map.select_facility(self.city_map.facility_index)
            self._map_frame.configure(highlightbackground=Theme.TEXT_HEADER)
        elif zone == "floors":
            self._nav_buttons.clear_outline()
            if floor_nav is not None:
                floor_nav.select(floor_nav.index)
        else:  # "buttons"
            if floor_nav is not None:
                floor_nav.clear_outline()
            self.city_map.clear_facility_focus()
            self._map_frame.configure(highlightbackground=Theme.BORDER)
            self._nav_buttons.select(self._nav_buttons.index)

    def _on_city_nav(self, event):
        """Tab switches zones; arrows/Enter act inside the active zone."""
        key = event.keysym
        if key in ("Tab", "ISO_Left_Tab"):
            self._set_zone("buttons" if self._zone == "map" else "map")
            return "break"

        if self._zone == "map":
            if key in ("Up", "Left"):
                self.city_map.move_facility(-1)
            elif key in ("Down", "Right"):
                self.city_map.move_facility(1)
            elif key == "Home":
                self.city_map.select_facility(0)
            elif key == "End":
                self.city_map.select_facility(self.city_map.facility_count() - 1)
            elif key in ("Return", "KP_Enter", "space"):
                self._activate_facility()
            return "break"

        return self._nav_buttons.on_key(event)

    def _activate_facility(self):
        """Open the facility highlighted on the map."""
        service = self.city_map.current_facility()
        if not service:
            return
        if service == "dungeon":
            self._enter_dungeon()
        else:
            self._open_service(service)

    def _on_city_key(self, event):
        """Handle keyboard shortcuts in the city screen."""
        key = event.char
        if key == "?":
            self._show_help()
            return
        # Number keys 1-9 → services (cycle through position keys)
        if key and key in "123456789":
            positions = CITY_SERVICE_POSITIONS.get(self.city_id, {})
            svc_keys = [k for k in positions.keys() if k != "dungeon"]
            idx = int(key) - 1
            if idx < len(svc_keys):
                # Keep the map highlight in sync with the shortcut jump.
                self.city_map.select_facility_key(svc_keys[idx])
                self._open_service(svc_keys[idx])
            return
        # Letter keys → bottom actions
        key_map = {
            "i": self._open_inventory,
            "m": self._open_world_map,
            "w": self._do_wait,
            "d": self._enter_dungeon,
            "s": self._open_settings,
            "q": self._save_and_quit,
        }
        action = key_map.get(key.lower())
        if action:
            if key.lower() == "d":
                self.city_map.select_facility_key("dungeon")
            action()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_city_id(self):
        if self.player:
            loc = self.player.get("location", "solmere")
            if loc == "dungeon":
                loc = self.player.get("origin_city", "solmere")
            self.city_id = loc
        else:
            self.city_id = "solmere"
        self.city = CITIES.get(self.city_id, CITIES["solmere"])

        # Refresh the map widget if it exists
        if hasattr(self, 'city_map') and self.city_map.winfo_exists():
            positions = CITY_SERVICE_POSITIONS.get(self.city_id, {})
            self.city_map.refresh(self.city_id, self.city, positions)

    # ── Karma gate (Phase 2) ──────────────────────────────────────────────────

    def _begin_arrival(self):
        """Run the one-shot gate check, then resume normal city arrivals."""
        if not self.winfo_exists():
            return
        if self._start_karma_gate():
            return
        self._resume_arrival()

    def _resume_arrival(self):
        """Show queued world events, then schedule story beats / EH intro."""
        if not self.winfo_exists():
            return
        self._show_queued_events()
        self.after(200, self._check_story_beats)
        if self.player:
            self.after(700, self._maybe_event_horizon_intro)

    def _show_queued_events(self):
        """Display queued dungeon/world events once the gate is resolved."""
        if not self.player:
            return
        events = get_event_queue_events(self.player)
        if not events:
            return
        for evt in events:
            self.sm.log(format_event_alert(evt), category="event")
        show_event_notice(
            events,
            day_text=format_date(self.player),
            parent=self.sm.root,
        )

    def _start_karma_gate(self):
        p = self.player
        if not p:
            return False
        karma.ensure_state(p)
        gate = p["karma_gate"]
        if not gate.pop("check_pending", False):
            return False
        response = karma.get_gate_response(p, self.city_id)
        if not response:
            return False
        self._show_karma_gate(response)
        return True

    def _show_karma_gate(self, response):
        tier = response["tier"]
        fee = int(response["fee"])
        gold = max(0, int(self.player.get("gold", 0) or 0))
        karma_tier = karma.get_karma_tier(self.player)

        if tier == "warning":
            heading = "The Gate Captain Stops You"
            details = (
                f"Karma: {karma_tier['label']} ({karma.get_karma(self.player):+d})\n\n"
                "Your reputation has preceded you. This once, the captain offers "
                f"to overlook it for a {fee}-gold processing fee."
            )
        elif tier == "suspect":
            heading = "The Watch Is Waiting"
            details = (
                f"Karma: {karma_tier['label']} ({karma.get_karma(self.player):+d})\n\n"
                f"They name a fee of {fee} gold. Pay it, or turn away."
            )
        elif tier == "wanted":
            heading = "Wanted at the Gate"
            details = (
                f"Karma: {karma_tier['label']} ({karma.get_karma(self.player):+d})\n\n"
                f"Three guards block the gate. The fee is {fee} gold — or you "
                "can talk, submit, or fight."
            )
        else:
            heading = "The Gate Is Closed to You"
            details = (
                f"Karma: {karma_tier['label']} ({karma.get_karma(self.player):+d})\n\n"
                f"Two elite guards and two guards bar the way. The fee is {fee} gold "
                "— or you can talk, submit, or fight."
            )

        if gold < fee:
            details += f"\n\nYou only have {gold} gold."
        guard_line = service_line(self.player, "guard", self.city_id)
        if guard_line:
            details += f"\n\n\"{guard_line}\""

        options = []
        if gold >= fee:
            options.append(("pay", f"Pay {fee} gold and enter"))
        if tier in ("wanted", "outlaw"):
            options.append(("talk", "Talk them down (CHA check)"))
            options.append(("submit", "Submit to judgment"))
            options.append(("fight", "Fight the guards"))
        options.append(("leave", "Turn away (return to map)"))

        choice_dialog(
            parent=self,
            title="City Gate",
            heading=heading,
            subtitle=f"{self.city.get('name', self.city_id)} — Gate Check",
            details=details,
            options=options,
            on_choice=lambda key: self._on_gate_choice(key, response),
            default_choice="leave",
        )

    def _on_gate_choice(self, key, response):
        if key == "pay":
            self._gate_pay(response)
        elif key == "talk":
            self._gate_talk(response)
        elif key == "submit":
            self._gate_submit(response)
        elif key == "fight":
            self._gate_fight(response)
        else:
            self._gate_turn_away()

    def _refresh_after_gate(self):
        self._update_top_bar()
        if hasattr(self, "_hero_card") and self._hero_card.winfo_exists():
            self._refresh_hero_card()

    def _gate_pay(self, response):
        from pandemonium.combat.city_guards import resolve_gate
        fee = int(response["fee"])
        p = self.player
        if int(p.get("gold", 0) or 0) < fee:
            ok_dialog(self, "Not Enough Gold",
                      f"You need {fee} gold, but you only have {p.get('gold', 0)}.")
            return

        p["gold"] = int(p.get("gold", 0) or 0) - fee
        warning = response["tier"] == "warning"
        resolve_gate(p, self.city_id, days=1 if warning else 3, warning=warning)
        self.sm.log(
            f"Gate fee paid: {fee} gold. "
            + ("The captain waves you through — this once." if warning
               else "The guards step aside.")
        )
        self._refresh_after_gate()
        self._resume_arrival()

    def _gate_talk(self, response):

        from pandemonium.combat.stats import compute_player_stats
        from pandemonium.combat.city_guards import resolve_gate
        p = self.player
        cha = compute_player_stats(p)[5]
        dc = karma.get_gate_talkdown_dc(p)
        roll = random.randint(1, 20)
        total = roll + cha
        # Natural 20 always talks the guards down, no matter the DC.
        if roll == 20 or total >= dc:
            fee = max(1, int(response["fee"]) // 2)
            if int(p.get("gold", 0) or 0) < fee:
                ok_dialog(
                    self, "Talk-Down Succeeded",
                    f"You roll {roll} + {cha} = {total} vs DC {dc}.\n\n"
                    f"They halve the fee to {fee} gold, but you cannot pay it. "
                    "They offer you a cell instead.",
                    on_ok=lambda: self._gate_submit(response),
                )
                return
            p["gold"] = int(p.get("gold", 0) or 0) - fee
            resolve_gate(p, self.city_id, days=3)
            self.sm.log(
                f"Talk-down: {roll} + {cha} = {total} vs DC {dc} — success. "
                f"Half fee paid: {fee} gold."
            )
            self._refresh_after_gate()
            self._resume_arrival()
            return

        ok_dialog(
            self, "Talk-Down Failed",
            f"You roll {roll} + {cha} = {total} vs DC {dc}.\n\n"
            "The guards do not buy it. Steel rings as they close in.",
            on_ok=lambda: self._gate_fight(response),
        )

    def _gate_submit(self, response):
        from pandemonium.combat.city_guards import city_guard_jail
        from pandemonium.gui.screens.city_screen import CityScreen

        info = city_guard_jail(self.player, self.city_id)
        msg = f"You spend the night in a cell. Fine: {info['fine']} gold."
        if info.get("karma"):
            msg += f"  Karma {info['karma']:+d}."
        self.sm.switch_to(CityScreen, push_history=False)
        self.sm.log(msg)

    def _gate_fight(self, response):

        from pandemonium.combat.city_guards import spawn_city_guards
        from pandemonium.gui.screens.combat_screen import CombatScreen
        enemies = spawn_city_guards(self.player, response["tier"])
        self.sm.log("The guards draw steel.")
        self.sm.switch_to(
            CombatScreen,
            enemy_keys=[],
            enemies=enemies,
            combat_context="city_guard",
            on_result=self._after_city_guard_combat,
        )

    def _gate_turn_away(self):

        from pandemonium.gui.screens.world_map_screen import WorldMapScreen
        self.sm.switch_to(WorldMapScreen, travel_mode=True)
        self.sm.log("You turn away from the gate. The road is still open.")

    def _after_city_guard_combat(self, result):
        """Resolve a non-lethal gate fight without ever showing DeathScreen."""
        from pandemonium.gui.screens.world_map_screen import WorldMapScreen
        from pandemonium.gui.screens.city_screen import CityScreen

        if result == "victory":
            city_guards.city_guard_victory(self.player, self.city_id)
            self.sm.switch_to(CityScreen, push_history=False)
            self.sm.log("The guards lower their weapons. You enter under watch.")
            return
        if result in ("dead", "defeat"):
            info = city_guards.city_guard_jail(self.player, self.city_id)
            self.sm.switch_to(CityScreen, push_history=False)
            msg = f"You wake in a cell. Fine: {info['fine']} gold."
            if info.get("karma"):
                msg += f"  Karma {info['karma']:+d}."
            self.sm.log(msg)
            return
        if result == "fled":
            city_guards.city_guard_flee(self.player, self.city_id)
            self.sm.switch_to(WorldMapScreen, travel_mode=True)
            self.sm.log("You slip away from the gate. The watch will remember.")
            return

        # Error / aborted combat: return to the city without a death penalty.
        self.sm.switch_to(CityScreen, push_history=False)
        self.sm.log(f"Gate combat ended unexpectedly: {result}.")

    def _build_hero_card(self):
        """Show party status card — all members in one horizontal row: 
        player + front allies + back allies. Front/back separated by a subtle divider.

        Click-to-swap: clicking two ally cards swaps their positions in
        player['party_order'] (front row ↔ bench). The player card is fixed.
        """
        from pandemonium.combat.ally import (ensure_party_order, get_all_active_allies_including_defeated,
                                         get_all_reserve_allies_including_defeated)
        p = self.player
        ensure_party_order(p)
        front_allies = get_all_active_allies_including_defeated(p)
        back_allies = get_all_reserve_allies_including_defeated(p)

        # Click-to-swap state: absolute ally index awaiting a swap partner
        self._swap_selected = None
        self._member_blocks = {}  # absolute ally index -> card frame (highlight)
        # Name labels are ellipsized to fit the party row (see _fit_hero_names)
        self._hero_name_labels = []
        self._hero_blocks = []      # (block, hp_bar, tag_label, full_tags)
        self._hero_fit_state = None

        allies_list = p.get("allies", [])

        def _abs_index(ally):
            """Absolute index of an ally in player['allies'] (identity match)."""
            for i, a in enumerate(allies_list):
                if a is ally:
                    return i
            return None

        self._hero_card = tk.Frame(self.content, bg=Theme.BG_CARD, highlightthickness=1,
                                   highlightbackground=Theme.BORDER)
        # On refresh the map frame already exists, so keep the card above it.
        map_frame = getattr(self, "_map_frame", None)
        if map_frame is not None and map_frame.winfo_exists():
            self._hero_card.pack(fill=tk.X, pady=(0, 10), padx=20, before=map_frame)
        else:
            self._hero_card.pack(fill=tk.X, pady=(0, 10), padx=20)
        card = self._hero_card  # alias for local use below

        # ── Collect all party members in order ─────────────────────────────
        members = []
        # Player (always first, FRONT)
        members.append({
            "name": _format_title_name(
                p, "full",
                show_title=self.sm.settings.get("show_title_beside_name", True)),
            "level": p.get("level", 1),
            "hp": p.get("current_hp", 1),
            "max_hp": player_max_hp(p),
            "tags": _get_entity_buff_tags(p),
            "color": Theme.ACCENT,
            "section": "player",
            "defeated": False,
            "party_idx": None,  # player is fixed
        })

        # Front-row allies
        for ally in front_allies:
            defeated = ally.get("defeated") or ally.get("current_hp", 0) <= 0
            members.append({
                "name": display_name(ally),
                "level": ally.get("level", 1),
                "hp": 0 if defeated else ally.get("current_hp", 0),
                "max_hp": ally.get("max_hp", 1),
                "tags": _get_entity_buff_tags(ally),
                "color": Theme.TEXT_DIM if defeated else Theme.TEXT,
                "section": "front",
                "defeated": defeated,
                "party_idx": _abs_index(ally),
            })

        # Back-row allies (go beside front, after a divider)
        for ally in back_allies:
            defeated = ally.get("defeated") or ally.get("current_hp", 0) <= 0
            members.append({
                "name": display_name(ally),
                "level": ally.get("level", 1),
                "hp": 0 if defeated else ally.get("current_hp", 0),
                "max_hp": ally.get("max_hp", 1),
                "tags": _get_entity_buff_tags(ally),
                "color": "#8b7355" if not defeated else "#555555",
                "section": "back",
                "defeated": defeated,
                "party_idx": _abs_index(ally),
            })

        # ── Single horizontal party row ─────────────────────────────────────
        party_row = tk.Frame(card, bg=Theme.BG_CARD)
        party_row.pack(fill=tk.X, padx=10, pady=(8, 4))
        self._hero_party_row = party_row
        # Fixed layout budget for a full 8-actor party (gaps + dividers).
        self._hero_row_extras = HERO_ROW_EXTRAS_MAX
        party_row.bind("<Configure>", lambda e: self._fit_hero_names(e.width))

        last_section = None
        for i, m in enumerate(members):
            # Insert a subtle divider between front and back sections
            if m["section"] != last_section and i > 0:
                if m["section"] == "back":
                    # Divider between front and back
                    sep = tk.Frame(party_row, bg=Theme.BG_CARD, width=2)
                    sep.pack(side=tk.LEFT, padx=6)
                    tk.Label(sep, text="│", bg=Theme.BG_CARD,
                             fg="#8b7355", font=(Theme.FONT_FAMILY, 16, "bold")).pack()
                    sep_frame = tk.Frame(party_row, bg=Theme.BG_CARD, width=6)
                    sep_frame.pack(side=tk.LEFT)
                elif m["section"] == "front" and last_section == "player":
                    # Subtle space after player
                    sep = tk.Frame(party_row, bg=Theme.BG_CARD, width=1)
                    sep.pack(side=tk.LEFT, padx=2)
                    tk.Label(sep, text="│", bg=Theme.BG_CARD,
                             fg=Theme.BORDER, font=(Theme.FONT_FAMILY, 14)).pack()
                    sep_frame = tk.Frame(party_row, bg=Theme.BG_CARD, width=6)
                    sep_frame.pack(side=tk.LEFT)
            last_section = m["section"]

            # highlightthickness=2 reserved from the start so selecting a card
            # only recolors the border without shifting the layout
            block = tk.Frame(party_row, bg=Theme.BG_CARD,
                             highlightthickness=2, highlightbackground=Theme.BG_CARD)
            block.pack(side=tk.LEFT, padx=(0 if i == 0 else 8, 0))

            name_color = m["color"]
            if m.get("defeated"):
                name_color = "#555555"

            # Name + level on one row. The name gets ellipsized later to the
            # per-member slot width so long names/titles never overflow.
            name_row = tk.Frame(block, bg=Theme.BG_CARD)
            name_row.pack(anchor=tk.W)
            name_lbl = tk.Label(name_row, text=m["name"],
                                bg=Theme.BG_CARD, fg=name_color,
                                font=Theme.FONT_BOLD, anchor=tk.W)
            name_lbl.pack(side=tk.LEFT)
            level_lbl = tk.Label(name_row, text=f"Lv.{m['level']}",
                                 bg=Theme.BG_CARD, fg=name_color,
                                 font=Theme.FONT_BOLD)
            level_lbl.pack(side=tk.LEFT, padx=(5, 0))
            self._hero_name_labels.append((name_lbl, level_lbl, m["name"]))

            ratio = m["hp"] / max(1, m["max_hp"])
            if m["section"] == "back":
                if ratio > 0.5:
                    hp_fill = "#7a6a4a"
                elif ratio > 0.25:
                    hp_fill = "#8b6914"
                else:
                    hp_fill = "#aa4444"
            else:
                if ratio > 0.5:
                    hp_fill = Theme.HP_BAR_FILL
                elif ratio > 0.25:
                    hp_fill = "#f39c12"
                else:
                    hp_fill = Theme.ACCENT
            if m.get("defeated"):
                hp_fill = "#333333"

            hp_bar = HPBar(block, current=m["hp"], maximum=m["max_hp"],
                           width=90, height=14, show_text=True,
                           fill_color=hp_fill)
            hp_bar.pack(anchor=tk.W, pady=(2, 0))

            # Always show tag label to maintain vertical alignment;
            # use a non-breaking space when there are no tags.
            tag_text = m["tags"] if m["tags"] else " "
            tag_lbl = tk.Label(block, text=tag_text, bg=Theme.BG_CARD,
                               fg=Theme.BUFF_NEUTRAL,
                               font=(Theme.FONT_FAMILY, 7),
                               anchor=tk.W)
            tag_lbl.pack(anchor=tk.W)
            self._hero_blocks.append((block, hp_bar, tag_lbl, tag_text))

            # Click-to-swap registration (player card stays fixed)
            if m.get("party_idx") is not None:
                self._member_blocks[m["party_idx"]] = block
                self._bind_party_card_clicks(block, m)

        # Widths are only known after the first layout pass — fit then, and
        # refit whenever the window (and therefore the row) is resized.
        self.after_idle(self._fit_hero_names)

        # ── Gold row ──────────────────────────────────────────────────────
        gold = p.get("gold", 0)
        gold_frame = tk.Frame(card, bg=Theme.BG_CARD)
        gold_frame.pack(fill=tk.X, padx=10, pady=(4, 8))
        tk.Label(gold_frame, text=f"💰 {gold}g", bg=Theme.BG_CARD,
                 fg=Theme.TEXT, font=Theme.FONT_SMALL).pack(side=tk.LEFT)
        if len(members) > 2:
            tk.Label(gold_frame,
                     text="Click two allies to swap positions",
                     bg=Theme.BG_CARD, fg=Theme.TEXT_DIM,
                     font=Theme.FONT_SMALL).pack(side=tk.RIGHT)

    def _fit_hero_names(self, row_width=None):
        """Ellipsize party-card names so the single-row party bar fits.

        The player's name can include a title ("hundur the Hundred") and
        ally nicknames are free text, so a fixed label grew the row past the
        card/window edge. Each member gets the SAME fixed slot — sized for a
        full 8-actor card — so a 2-member party does not stretch into huge
        boxes. Only the name is shortened (the level suffix stays visible).
        """
        labels = getattr(self, "_hero_name_labels", None)
        if not labels or not self.winfo_exists():
            return
        if row_width is None:
            row = getattr(self, "_hero_party_row", None)
            try:
                row_width = row.winfo_width() if row is not None else 0
            except tk.TclError:
                return
        if row_width <= 60:          # not mapped yet
            return

        extras = getattr(self, "_hero_row_extras", HERO_ROW_EXTRAS_MAX)
        # Fixed slot sized for a full 8-actor card. Short parties keep the
        # same box size and simply leave empty space to the right.
        slot = max(56, (row_width - extras) // HERO_CARD_MAX_SLOTS)
        block_w = max(52, slot - 4)

        blocks = getattr(self, "_hero_blocks", [])
        max_h = 0
        for block, _hp, _tag, _tags in blocks:
            try:
                max_h = max(max_h, block.winfo_reqheight())
            except tk.TclError:
                pass
        freeze_ok = max_h >= 20       # requested height is laid out

        state = (row_width,
                 tuple((full, lvl.cget("text")) for _, lvl, full in labels),
                 freeze_ok)
        if state == getattr(self, "_hero_fit_state", None):
            return
        self._hero_fit_state = state

        for name_lbl, level_lbl, full_name in labels:
            try:
                level_w = level_lbl.winfo_reqwidth()
            except tk.TclError:
                level_w = 40
            # 14px = level spacing + Tk label padding/border margin.
            available = max(16, block_w - level_w - 14)
            text = _fit_text_to_width(full_name, Theme.FONT_BOLD, available)
            try:
                name_lbl.config(text=text)
            except tk.TclError:
                pass

        if freeze_ok:
            # Freeze every member box at the same width/height so short
            # names no longer produce visibly smaller cards.
            for block, hp_bar, tag_lbl, full_tags in blocks:
                try:
                    block.pack_propagate(False)
                    block.config(width=block_w, height=max_h)
                except tk.TclError:
                    pass
                # Default bar is 90px; shrink only when the fixed slot is
                # too narrow (e.g. 8 members at the minimum window width).
                try:
                    hp_bar.set_width(min(90, max(50, block_w - 10)))
                except tk.TclError:
                    pass
                if full_tags.strip():
                    tag_text = _fit_text_to_width(
                        full_tags, (Theme.FONT_FAMILY, 7), max(20, block_w - 8))
                    try:
                        tag_lbl.config(text=tag_text)
                    except tk.TclError:
                        pass

    # ── Party position swap (click-to-swap) ──────────────────────────────

    def _bind_party_card_clicks(self, widget, member):
        """Recursively bind click handlers on a party member card.

        Tk delivers mouse events to the deepest widget under the cursor, so
        every child (labels, HP bar canvas) needs its own binding.
        """
        try:
            widget.config(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind("<Button-1>", lambda e, m=member: self._on_party_member_click(m))
        for child in widget.winfo_children():
            self._bind_party_card_clicks(child, member)

    def _on_party_member_click(self, member):
        """Handle a click on a party member card.

        First click selects the member (highlighted border); clicking a
        second member swaps their positions in player['party_order'].
        Clicking the selected member again deselects. The player is fixed.
        """
        idx = member.get("party_idx")
        if idx is None:
            return

        if self._swap_selected is None:
            self._swap_selected = idx
            self._update_swap_highlights()
            self.sm.log(f"Selected {member['name']} — click another ally to swap positions.")
        elif self._swap_selected == idx:
            self._swap_selected = None
            self._update_swap_highlights()
        else:
            self._swap_party_positions(self._swap_selected, idx)

    def _swap_party_positions(self, idx_a, idx_b):
        """Swap two allies' slots in player['party_order'].

        A pure position swap never changes the front/bench head-counts, so
        no capacity validation is needed — the first get_active_limit()
        positions are the front row, the next bench entries are the reserve.
        """
        from pandemonium.combat.ally import ensure_party_order, get_active_limit

        p = self.player
        ensure_party_order(p)
        allies = p.get("allies", [])
        order = p.get("party_order", [])

        self._swap_selected = None

        valid = (idx_a != idx_b and idx_a in order and idx_b in order
                 and idx_a < len(allies) and idx_b < len(allies))
        if not valid:
            self._refresh_hero_card()
            return

        pos_a, pos_b = order.index(idx_a), order.index(idx_b)
        order[pos_a], order[pos_b] = order[pos_b], order[pos_a]

        name_a = display_name(allies[idx_a])
        name_b = display_name(allies[idx_b])
        limit = get_active_limit(p)
        a_was_front = pos_a < limit
        b_was_front = pos_b < limit

        if a_was_front == b_was_front:
            msg = f"{name_a} and {name_b} swap places."
        else:
            fwd, back = (name_a, name_b) if not a_was_front else (name_b, name_a)
            msg = f"{fwd} steps forward! {back} moves to the back row."

        self.sm.log(msg)
        self._refresh_hero_card()

    def _update_swap_highlights(self):
        """Apply or clear the selection highlight on member cards."""
        for idx, block in getattr(self, "_member_blocks", {}).items():
            try:
                if not block.winfo_exists():
                    continue
                color = Theme.ACCENT if idx == self._swap_selected else Theme.BG_CARD
                block.config(highlightbackground=color)
            except tk.TclError:
                pass

    def _refresh_hero_card(self):
        """Rebuild the hero card in place (used after a position swap)."""
        if hasattr(self, "_hero_card") and self._hero_card.winfo_exists():
            self._hero_card.destroy()
        self._build_hero_card()

    def _update_top_bar(self):
        # Priority-driven header (see base_screen.city_header_parts): the clock
        # stays bright; floor, karma and the watched marker sit in the dim tier.
        primary, secondary = city_header_parts(self.player, self.city_id)
        self.sm.update_top_bar_parts(primary, secondary)

    # ── Service handlers ──────────────────────────────────────────────────────

    def _open_service(self, service):
        """Open a facility in the GUI FacilityScreen wrapper."""
        from pandemonium.core.time_blocks import is_service_open, service_closed_message
        from pandemonium.world.city import SERVICE_HANDLERS
        from pandemonium.gui.screens.facility_screen import FacilityScreen
        if not is_service_open(self.player, service, self.city_id):
            msg = (service_closed_message(self.player, service, self.city_id)
                   or "Closed right now.")
            ok_dialog(self, service.replace("_", " ").title(), msg)
            return
        # Port opens the World Map instead of the old terminal UI
        if service == "port":
            self._open_world_map()
            return
        handler = SERVICE_HANDLERS.get(service)
        if handler:
            _title_greeting = title_line(self.player, service, self.city_id)
            if _title_greeting:
                self.sm.log(_title_greeting)
            self.sm.log(f"Entering {service.replace('_', ' ').title()}...")
            self.sm.switch_to(
                FacilityScreen,
                title=service.replace("_", " ").title(),
                func=handler,
                func_args=(self.player, self.city_id),
                on_close=lambda _: self._after_facility(),
            )

    def _do_wait(self):
        """Wait: a brief moment (1 block) or a while (until the next phase)."""
        confirm_dialog(
            parent=self, title="Wait",
            message=("How long would you like to wait?\n\n"
                     "· A brief moment — pass a little time.\n"
                     "· A while — pass until the next phase"
                     " (from Night you simply greet the morning, exhausted)."),
            on_yes=self._wait_brief,
            on_no=self._wait_a_while,
            yes_text="A Brief", no_text="A While",
            on_close=lambda: None,      # X = cancel, do nothing
        )

    def _wait_brief(self):
        """Pass one block; day rollover handles fatigue normally."""
        time_blocks.wait_blocks(self.player, 1)
        self.sm.log("You wait a brief moment.")
        self.sm.switch_to(CityScreen, push_history=False)

    def _wait_a_while(self):
        """Pass to the next phase (from Night: greet the morning, +1 fatigue)."""
        result = time_blocks.wait_to_next_phase(self.player)
        if result is None:
            # Wonderland time pocket — nothing passes here
            self.sm.log("Time politely declines to pass in Wonderland.")
        elif result == "morning":
            self.sm.log("A while passes — you greet the morning, exhausted.")
        else:
            self.sm.log(f"A while passes — it is now {result}.")
        self.sm.switch_to(CityScreen, push_history=False)

    def _maybe_event_horizon_intro(self):
        """Play Vesper's first-contact scene once the EH gate is met."""
        from pandemonium.world.event_horizon import site_unlocked
        from pandemonium.gui.screens.facility_screen import FacilityScreen
        from pandemonium.facilities.event_horizon_intro import event_horizon_intro_service
        if getattr(self, "_eh_intro_launched", False):
            return
        p = self.player
        if not p or p.get("eh_intro_seen"):
            return
        if not site_unlocked(p):
            return
        if p.get("location") == "dungeon":
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._eh_intro_launched = True
        self.sm.switch_to(
            FacilityScreen,
            title="A Tear in the Sky",
            func=event_horizon_intro_service,
            func_args=(p, self.city_id),
            on_close=lambda _: self.sm.switch_to(CityScreen, push_history=False),
        )

    def _open_house(self):
        """Open the player's house in this city."""
        from pandemonium.gui.screens.facility_screen import FacilityScreen
        self.sm.log("Entering Your House...")
        self.sm.switch_to(
            FacilityScreen,
            title="Your House",
            func=house_menu,
            func_args=(self.player, self.city_id),
            on_close=lambda _: self._after_facility(),
        )

    def _after_facility(self):
        """Called when any facility screen closes. Refresh state."""
        self._update_top_bar()
        if self.player and self.player.get("current_hp", 1) <= 0:
            self._handle_death()
        elif self.player and self.player.pop("_pending_dummy_combat", None):
            self._launch_dummy_combat()
        else:
            self.sm.switch_to(CityScreen, push_history=False)

    # ── Story beats ───────────────────────────────────────────────────────────

    def _check_story_beats(self):
        """Resolve quest state and deliver story beats on city entry.

        Runs on every CityScreen entry — which covers travel arrivals, dungeon
        exits, post-floor returns and menu loads, because every path funnels
        back through CityScreen. Story never interrupts combat or dungeons.
        """
        import pandemonium.progression.quests as quests
        from pandemonium.facilities.story_beats import ensure_city_story_triggers
        from pandemonium.facilities.house_stories import claim_city_trigger
        if not self.winfo_exists() or not self.player:
            return


        # Resolve any state-based objectives (own a house, capture a girl...).
        # Results are recorded in the session log + Journal — no popups.
        messages = quests.update_quests(self.player)
        for msg in messages:
            self.sm.log(msg)

        # Deliver the next story beat: the Archivist intro first, then queue.
        flags = quests.ensure_quest_state(self.player)["flags"]
        if not flags.get("intro_seen"):
            self._open_story_beat("archivist_intro")
            return
        ensure_city_story_triggers(self.player, self.city_id)
        if quests.has_pending_story(self.player):
            beat_id = quests.pop_pending_story(self.player)
            if beat_id:
                self._open_story_beat(beat_id)
                return

        # Fireside Tales can also find the player while travelling (city or
        # phase triggers), instead of waiting at home.
        part = claim_city_trigger(self.player, self.city_id)
        if part:
            self._open_house_story(part)

    def _open_house_story(self, part):
        """Open a city-triggered house story as an overlay."""
        from pandemonium.facilities.house_stories import play_part
        from pandemonium.gui.screens.story_screen import StoryScreen

        _, story, _, _ = get_part(part["id"])
        title = part.get("title", "Story")
        if story:
            title = f"{story.get('title', 'Story')} — {title}"

        self.sm.push_overlay(
            StoryScreen,
            title=title,
            func=play_part,
            func_args=(self.player, part["id"]),
            on_close=lambda _result: self.sm.dismiss_overlay(),
        )

    def _open_story_beat(self, beat_id):
        """Open a story conversation as an overlay over the city."""
        from pandemonium.facilities.story_beats import get_story_beat
        from pandemonium.gui.screens.story_screen import StoryScreen

        func = get_story_beat(beat_id)
        if func is None:
            return
        titles = {"archivist_intro": "A Message in Starlight",
                  "voss_epilogue": "The First Page"}
        self.sm.push_overlay(
            StoryScreen,
            title=titles.get(beat_id, "Story"),
            func=func,
            func_args=(self.player,),
            on_close=lambda _result: self.sm.dismiss_overlay(),
        )

    def _launch_dummy_combat(self):
        """Launch a sparring match against the training dummy in CombatScreen."""
        from pandemonium.gui.screens.combat_screen import CombatScreen
        config = self.player.pop("_pending_dummy_combat", None)
        if not config:
            self.sm.switch_to(CityScreen, push_history=False)
            return

        self.sm.log("Entering sparring arena...")
        self.sm.update_top_bar("⚔ Training Dummy")

        def dummy_combat_func(player, floor=None, enemies=None):
            """Custom combat function for the training dummy."""
            from pandemonium.combat.dummy import create_dummy_enemy, _run_dummy_combat

            # Inject the dummy into the shared enemies list so the HUD sees it
            dummy = create_dummy_enemy(config)
            if enemies is not None:
                enemies.clear()
                enemies.append(dummy)

            # Use the protected runner that disables Pandemonium flee blocking.
            # Pass enemies (shared list) so the HUD reflects live combat state.
            return _run_dummy_combat(player, config, enemies=enemies)

        self.sm.switch_to(
            CombatScreen,
            enemy_keys=[],
            combat_context="training",
            combat_func=dummy_combat_func,
            on_result=lambda result: self._after_dummy_combat(result),
        )

    def _after_dummy_combat(self, result):
        """Handle return from dummy sparring — always go back to city."""
        self.sm.log(f"Sparring ended: {result.upper()}")
        self._update_top_bar()
        if self.player and self.player.get("current_hp", 1) <= 0:
            self._handle_death()
        else:
            self.sm.switch_to(CityScreen, push_history=False)

    def _open_inventory(self):
        from pandemonium.gui.screens.inventory_screen import InventoryScreen
        self.sm.log("Opening Inventory...")
        self.sm.switch_to(InventoryScreen)

    def _open_world_map(self):
        """Open the unified world map — travel mode with pathfinding + Travel Here."""
        from pandemonium.gui.screens.world_map_screen import WorldMapScreen
        self.sm.log("Opening World Map...")
        self.sm.switch_to(WorldMapScreen, travel_mode=True)

    def _enter_dungeon(self):
        """Prompt for floor selection, then launch the dungeon."""
        # Guard against double-invocation (e.g., double-click on button)
        if getattr(self, '_entering_dungeon', False):
            return
        self._entering_dungeon = True
        try:
            self._do_enter_dungeon()
        finally:
            self._entering_dungeon = False

    def _do_enter_dungeon(self):
        # Ensure per-city progress exists
        from pandemonium.world.dungeon import _ensure_city_floors
        from pandemonium.progression.leveling import is_pandemonium_unlocked
        _ensure_city_floors(self.player, self.city_id)
        city_prog = self.player["city_floors"][self.city_id]
        max_unlocked = city_prog["max_floor"]
        current_floor = city_prog["floor"]

        # ── Pandemonium lock check ───────────────────────────────────────
        if self.city_id == "isle_of_glass":
            if not is_pandemonium_unlocked(self.player):
                ok_dialog(
                    parent=(self.sm.root if self.sm else self),
                    title="Pandemonium Sealed",
                    message=(
                        "The crystalline gates of Pandemonium stand sealed.\n\n"
                        "REQUIREMENT: Clear Floor 40 in at least 4 unique biomes.\n"
                        "(Visit any Guild Hall to check your biome progress.)"
                    ),
                )
                return
            else:
                self.sm.log("The crystalline gates of Pandemonium shimmer open...")

        # ── Floor selection dialog ────────────────────────────────────────
        self._show_floor_selection(current_floor, max_unlocked)

    def _launch_dungeon(self, floor):
        """Set the chosen floor and launch the DungeonScreen."""
        from pandemonium.world.city_dialogue import get_city_dialogues
        from pandemonium.gui.screens.dungeon_screen import DungeonScreen
        city_prog = self.player["city_floors"][self.city_id]
        city_prog["floor"] = floor
        self.player["dungeon_region"] = self.city.get("biome", "temperate")
        self.player["origin_city"] = self.city_id
        self.player["location"] = "dungeon"

        # Pandemonium mode is a per-run flag: only true inside the Isle of
        # Glass dungeon. Clear it for every other dungeon so a stale flag
        # (e.g. from a canceled floor selection or an old save) can't make
        # Elderfen or other dungeons display as PANDEMONIUM.
        if self.city_id == "isle_of_glass":
            self.player["pandemonium_mode"] = True
        else:
            self.player.pop("pandemonium_mode", None)

        # Clear any saved dungeon state and log for a fresh start
        for key in ("saved_dungeon_floor", "saved_dungeon_rooms", "saved_dungeon_room_index"):
            self.player.pop(key, None)
        self.player.pop("_dungeon_log", None)
        # A stale wild-dungeon id must never hijack a city-floor run
        self.player.pop("wild_dungeon_id", None)
        self.player.pop("_combat_floor_label", None)
        for key in ("saved_wild_floor", "saved_wild_rooms", "saved_wild_room_index"):
            self.player.pop(key, None)
        # A stale Event Horizon gate must never hijack a city-floor run
        # (the suspended run state itself is preserved).
        self.player.pop("_eh_in_run", None)
        # Same for the seasonal map boss's arena context (the Warden itself
        # lives in player["map_boss"] and is untouched).
        self.player.pop("_map_boss_site", None)
        self.player.pop("_map_boss_prev_floor", None)
        self.player.pop("_map_boss_victory", None)
        self.player.pop("_combat_time_label", None)

        # ── Receptionist "leave" dialogue ─────────────────────────────────
        leave_lines = get_city_dialogues(self.city_id, "receptionist").get("leave", [])
        if leave_lines:
            self.sm.log(_random.choice(leave_lines), category="dialogue")

        self.sm.log(f"Entering dungeon — Floor {floor}...")
        self.sm.switch_to(
            DungeonScreen,
            on_result=self._return_from_dungeon,
        )

    def _show_floor_selection(self, current_floor, max_unlocked):
        """Show floor selection as a scrollable grid of buttons.

        Hides the hero card and city map to claim maximum screen real
        estate, then displays every unlocked floor as a clickable button
        in a multi-column grid.  The current floor is highlighted.
        Pressing Escape or clicking Cancel restores the original layout.
        """

        # The picker takes over the map zone; Tab still reaches the action
        # bar (the generic options stay visible above the panel).
        self._floor_nav = None
        self.city_map.clear_facility_focus()
        self._set_zone("floors")

        # ── Hide city UI elements to free up space ────────────────────────
        self._map_frame.pack_forget()
        if hasattr(self, '_hero_card') and self._hero_card.winfo_exists():
            self._hero_card.pack_forget()
        # Hide the house row (the wrapper owns the pack geometry).
        if hasattr(self, '_house_wrap') and self._house_wrap.winfo_exists():
            self._house_wrap.pack_forget()

        # ── Floor-selection panel ─────────────────────────────────────────
        sel_frame = tk.Frame(
            self.content, bg=Theme.BG_DARK,
            highlightthickness=1, highlightbackground=Theme.BORDER,
        )
        sel_frame.pack(fill=tk.BOTH, expand=True, pady=8)

        min_floor = max(1, int(self.city.get("dungeon_start_floor", 1) or 1))

        # Header
        tk.Label(
            sel_frame, text="Select Floor",
            bg=Theme.BG_DARK, fg=Theme.ACCENT, font=Theme.FONT_LARGE,
        ).pack(pady=(12, 2))

        tk.Label(
            sel_frame,
            text=(f"Select a floor to descend  ({min_floor} – {max_unlocked})"
                  "  — arrows + Enter · Tab: buttons:"),
            bg=Theme.BG_DARK, fg=Theme.TEXT_DIM, font=Theme.FONT,
        ).pack(pady=(0, 6))

        # ── Scrollable grid of floor buttons ──────────────────────────────
        canvas = tk.Canvas(sel_frame, bg=Theme.BG_DARK, highlightthickness=0,
                           bd=0)
        scrollbar = tk.Scrollbar(sel_frame, orient=tk.VERTICAL,
                                 command=canvas.yview)
        grid_inner = tk.Frame(canvas, bg=Theme.BG_DARK)

        grid_inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=grid_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 20), pady=5)

        # Mouse-wheel scrolling
        def _on_mousewheel(event):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        COLS = 5
        BTN_W = 14

        # ── Shadow floor guard (Wonderland floors 41-50) ────────────────
        # When the player is on floors 41-50 in Wonderland, they carry
        # accumulated Shadows.  To prevent going back to earlier floors
        # to pick different Shadows, only the current floor is selectable.
        # The lock releases after Mary Sue is defeated (floor > 50).
        wonderland_biome = self.city.get("biome", "") == "wonderland"
        shadow_locked = wonderland_biome and 41 <= current_floor <= 50
        if shadow_locked:
            lock_warning = tk.Label(
                sel_frame,
                text="🌑 Shadows bind you — only your current floor is accessible.",
                bg=Theme.BG_DARK, fg="#d4a574", font=Theme.FONT_SMALL,
            )
            lock_warning.pack(pady=(0, 6))

        def _restore_and_go(floor):
            """Destroy the selection panel, restore hidden widgets, launch dungeon."""
            canvas.unbind_all("<MouseWheel>")
            sel_frame.destroy()
            self._floor_nav = None
            self._restore_city_widgets()
            self._set_zone("map")
            self._launch_dungeon(floor)

        def _restore_and_cancel():
            """Destroy the selection panel, restore hidden widgets, do nothing."""
            canvas.unbind_all("<MouseWheel>")
            sel_frame.destroy()
            self._floor_nav = None
            self._restore_city_widgets()
            self._set_zone("map")
            self.focus_set()

        floor_entries = []   # (floor, wrapper, button) for selectable floors
        for f in range(min_floor, max_unlocked + 1):
            row = (f - min_floor) // COLS
            col = (f - min_floor) % COLS
            is_current = f == current_floor
            is_locked = shadow_locked and not is_current

            if is_locked:
                bg = "#3a2a3a"        # dimmed, unclickable
                fg = "#6a5a6a"        # greyed-out text
                txt = f"🔒 Floor {f}"
                state = tk.DISABLED
            elif is_current:
                # Current floor: star + accent text only.  The red fill was
                # replaced by the white keyboard outline (NavGroup) so the
                # two indicators never fight over the same button.
                bg = Theme.BG_MID
                fg = Theme.ACCENT
                txt = f"★ Floor {f}"
                state = tk.NORMAL
            else:
                bg = Theme.BG_MID
                fg = Theme.TEXT
                txt = f"Floor {f}"
                state = tk.NORMAL

            # Wrapper frames carry the 1px keyboard outline (tk.Buttons ignore
            # highlight rings on Windows).
            wrap = tk.Frame(
                grid_inner, bg=Theme.BG_DARK,
                highlightthickness=1, highlightbackground=Theme.BG_DARK,
            )
            wrap.grid(row=row, column=col, padx=3, pady=3, sticky="ew")

            btn = tk.Button(
                wrap, text=txt,
                command=lambda floor=f: _restore_and_go(floor),
                bg=bg, fg=fg,
                font=Theme.FONT_BOLD,
                width=BTN_W,
                relief=tk.FLAT,
                bd=1,
                state=state,
                disabledforeground="#6a5a6a",
                activebackground=Theme.ACCENT,
                activeforeground=Theme.BG_DARK,
            )
            btn.pack(fill=tk.X, padx=1, pady=1)
            if not is_locked:
                floor_entries.append((f, wrap, btn))

        # Make columns equally wide
        for c in range(COLS):
            grid_inner.grid_columnconfigure(c, weight=1, uniform="floor_col")

        # ── Keyboard navigation over the floor grid ───────────────────────
        def _ensure_floor_visible(wrap):
            """Scroll the canvas so the outlined floor stays visible."""
            try:
                grid_inner.update_idletasks()
                total = grid_inner.winfo_height()
                view_h = canvas.winfo_height()
                if total <= 0 or view_h <= 0:
                    return
                top = canvas.canvasy(0)
                y = wrap.winfo_y()
                h = wrap.winfo_height()
                if y < top:
                    canvas.yview_moveto(max(0.0, y / total))
                elif y + h > top + view_h:
                    canvas.yview_moveto((y + h - view_h) / total)
            except tk.TclError:
                pass

        start_index = 0
        for i, (floor, _wrap, _btn) in enumerate(floor_entries):
            if floor == current_floor:
                start_index = i
                break

        floor_nav = NavGroup(
            sel_frame,
            [(wrap, btn) for _f, wrap, btn in floor_entries],
            start=start_index,
            on_change=lambda i: (
                _ensure_floor_visible(floor_entries[i][1])
                if 0 <= i < len(floor_entries) else None
            ),
        )
        self._floor_nav = floor_nav

        def _on_floor_key(event):
            """Floors zone: grid movement; Tab switches to the button bar."""
            key = event.keysym
            if key in ("Tab", "ISO_Left_Tab"):
                self._set_zone("buttons" if self._zone == "floors" else "floors")
                return "break"
            if self._zone == "buttons":
                return self._nav_buttons.on_key(event)

            if key == "Left":
                floor_nav.move(-1)
            elif key == "Right":
                floor_nav.move(1)
            elif key == "Up":
                floor_nav.move(-COLS)
            elif key == "Down":
                floor_nav.move(COLS)
            elif key == "Home":
                floor_nav.select(0)
            elif key == "End":
                floor_nav.select(len(floor_nav.widgets) - 1)
            elif key in ("Return", "KP_Enter", "space"):
                floor_nav.activate()
            else:
                return None
            return "break"

        for sequence in (
            "<Left>", "<Right>", "<Up>", "<Down>",
            "<Tab>", "<Shift-Tab>", "<ISO_Left_Tab>",
            "<Home>", "<End>",
            "<Return>", "<KP_Enter>", "<space>",
        ):
            canvas.bind(sequence, _on_floor_key)

        # ── Cancel button at the bottom of the grid ───────────────────────
        cancel_btn = tk.Button(
            sel_frame, text="Cancel", command=_restore_and_cancel,
            bg="#5a3a5a", fg=Theme.BUTTON_FG,
            font=Theme.FONT_BOLD, width=12,
        )
        cancel_btn.pack(pady=(4, 12))

        # ── Keyboard shortcuts ────────────────────────────────────────────
        sel_frame.bind("<Escape>", lambda e: _restore_and_cancel())
        canvas.bind("<Escape>", lambda e: _restore_and_cancel())
        # Focus the canvas so scroll wheel works immediately
        canvas.focus_set()

    def _restore_city_widgets(self):
        """Re-pack city widgets that were hidden during floor selection.

        All restored widgets are inserted *before* the action bar so the
        bottom buttons stay pinned at the bottom of the content area.
        """
        # Pack map_frame first so 'before' references can resolve.
        self._map_frame.pack(
            fill=tk.BOTH, expand=True, pady=8,
            before=self._action_frame,
        )
        if hasattr(self, '_hero_card') and self._hero_card.winfo_exists():
            self._hero_card.pack(
                fill=tk.X, pady=(0, 10), padx=20,
                before=self._map_frame,
            )
        if hasattr(self, '_house_wrap') and self._house_wrap.winfo_exists():
            self._house_wrap.pack(pady=(4, 0), before=self._action_frame)

    def _cleanup_dungeon_exit(self):
        """Clear all dungeon-specific state when leaving a dungeon.
        Mirrors the cleanup done in dungeon.py's synchronous loop.
        
        NOTE: Wonderland Shadows are intentionally NOT cleared here.
        Shadows persist across floor clears and city returns so the
        player's accumulated shadow choices are preserved when they
        re-enter the dungeon.  Shadows are only cleared on death/flee
        (handled in dungeon.py) or on floors 46/50 (by design).
        """
        from pandemonium.world.wonderland_curses import clear_wonderland_quirk
        p = self.player
        end_pandemonium_run(p)
        # Reset High Tide stacks
        p["cutlass_high_tide_stacks"] = 0
        p.pop("cutlass_high_tide_floor", None)
        # Clear Wonderland floor quirk (but NOT persistent Shadows)
        clear_wonderland_quirk(p)
        # Reset location to origin city
        p["location"] = p.get("origin_city", "solmere")

    def _return_from_dungeon(self, result):
        """Called when dungeon run ends."""
        from pandemonium.gui.screens.main_menu_screen import MainMenuScreen
        if result == "dead":
            self._handle_death()
        elif result == "fled":
            self._cleanup_dungeon_exit()
            self.sm.log("You fled the dungeon.")
            self.sm.switch_to(CityScreen, push_history=False)
        elif result == "save_exit":
            self.sm.log("Game saved. Exiting to menu.")
            self.sm.player = None
            self.sm.switch_to(MainMenuScreen)
        elif result is True:
            # explore_dungeon() returns True when a floor was actually cleared.
            self._show_post_floor_menu()
        else:
            # "timeout" / "error" / None — the run was interrupted (e.g. a
            # combat overlay crashed). Do NOT treat this as a floor clear:
            # that used to pop the "Floor Cleared!" dialog on a failed fight.
            self._cleanup_dungeon_exit()
            self.sm.log(f"Dungeon run interrupted ({result}). Returning to city.",
                        category="warning")
            self.sm.switch_to(CityScreen, push_history=False)

    def _show_post_floor_menu(self):
        """Show the 3-option menu after clearing a floor."""
        from pandemonium.gui.screens.dungeon_screen import DungeonScreen
        from pandemonium.gui.screens.main_menu_screen import MainMenuScreen

        p = self.player
        city_prog = p["city_floors"].get(self.city_id, {"floor": 1})
        cleared_floor = city_prog["floor"] - 1

        panel = OverlayPanel(
            self, f"=== FLOOR {cleared_floor} CLEARED ===", width=400,
        )

        tk.Label(
            panel.body,
            text=f"Now entering Floor {city_prog['floor']}",
            bg=Theme.BG_DARK, fg=Theme.TEXT,
            font=Theme.FONT,
        ).pack(pady=(0, 8))

        # Stats
        stats_text = (
            f"HP: {p.get('current_hp', 0)}/{player_max_hp(p)}\n"
            f"Gold: {p.get('gold', 0)}"
        )
        _track = format_block_track(p)
        if _track:
            stats_text += f"\nTime: {_track}"
        tk.Label(
            panel.body,
            text=stats_text,
            bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
            font=Theme.FONT_SMALL,
            justify=tk.CENTER,
        ).pack(pady=(0, 10))

        choice = [None]  # Mutable container
        done = tk.IntVar(self, 0)

        def _choose(opt):
            choice[0] = opt
            panel.close()
            done.set(1)

        btn_frame = tk.Frame(panel.body, bg=Theme.BG_DARK)
        btn_frame.pack(pady=(0, 12))

        tk.Button(
            btn_frame, text="1. Continue to next floor",
            command=lambda: _choose("continue"),
            bg=Theme.BUTTON_BG, fg=Theme.BUTTON_FG,
            font=Theme.FONT_BOLD, width=26, anchor=tk.W,
        ).pack(pady=3)

        tk.Button(
            btn_frame, text="2. Return to city",
            command=lambda: _choose("city"),
            bg=Theme.BUTTON_BG, fg=Theme.BUTTON_FG,
            font=Theme.FONT_BOLD, width=26, anchor=tk.W,
        ).pack(pady=3)

        tk.Button(
            btn_frame, text="3. Save and return to main menu",
            command=lambda: _choose("save_exit"),
            bg=Theme.BUTTON_BG, fg=Theme.BUTTON_FG,
            font=Theme.FONT_BOLD, width=26, anchor=tk.W,
        ).pack(pady=3)

        panel.finalize(on_escape=lambda _e: _choose("city"))
        # Blocks like the old wait_window(), but inside the game window.
        self.wait_variable(done)

        opt = choice[0]
        if opt == "continue":
            self.player["location"] = "dungeon"
            self.sm.switch_to(
                DungeonScreen,
                on_result=self._return_from_dungeon,
            )
        elif opt == "save_exit":
            self._cleanup_dungeon_exit()
            self.player["location"] = self.city_id
            save_game(self.player)
            self.sm.log("Game saved. Returning to main menu.")
            self.sm.player = None
            self.sm.switch_to(MainMenuScreen)
        else:
            # Default: return to city
            self._cleanup_dungeon_exit()
            self.sm.switch_to(CityScreen, push_history=False)

    def _save_and_quit(self):
        def _do_save():
            from pandemonium.gui.screens.main_menu_screen import MainMenuScreen
            self.player["location"] = self.city_id
            save_game(self.player)
            self.sm.log("Game saved. Returning to main menu.")
            self.sm.player = None
            self.sm.switch_to(MainMenuScreen)

        confirm_dialog(
            parent=self,
            title="Save & Quit",
            message="Save your progress and return to the main menu?",
            on_yes=_do_save,
        )

    def _handle_death(self):

        # Safety net: death always ends the run — scrub Pandemonium run state
        # so no stale curse can survive into other dungeons or the next save.
        from pandemonium.gui.screens.death_screen import DeathScreen
        end_pandemonium_run(self.player)

        def _continue_game():
            from pandemonium.core.utils import apply_death_penalty
            apply_death_penalty(self.player)
            self.sm.switch_to(CityScreen, push_history=False)

        def _quit_to_menu():
            from pandemonium.gui.screens.main_menu_screen import MainMenuScreen
            self.sm.player = None
            self.sm.switch_to(MainMenuScreen)

        self.sm.switch_to(
            DeathScreen,
            floor=self.player.get("city_floors", {}).get(self.city_id, {}).get("floor", "?"),
            city_id=self.city_id,
            on_continue=_continue_game,
            on_quit=_quit_to_menu,
        )

    def _show_help(self):
        """Show a keyboard shortcut reference dialog."""
        help_text = (
            "Keyboard Shortcuts:\n\n"
            "City Screen:\n"
            "  ↑/↓      — Previous / next facility\n"
            "  Tab      — Switch map/floors ↔ button bar\n"
            "  ←/→      — Move in the button bar\n"
            "  Enter    — Open facility / press button\n"
            "  1–9      — Open city service\n"
            "  I        — Inventory\n"
            "  M        — World Map / Travel\n"
            "  D        — Enter Dungeon\n"
            "  S        — Settings\n"
            "  Q        — Save & Quit\n"
            "  ?        — This help\n\n"
            "Combat:\n"
            "  A    — Attack\n"
            "  D    — Defend\n"
            "  F    — Flee (confirm)\n"
            "  C    — Capture\n"
            "  U    — Use Item\n"
            "  1–9  — Skills / Select target\n"
            "  Esc  — Cancel target selection\n\n"
            "Global:\n"
            "  Esc      — Go back\n"
            "  Ctrl+Q   — Quit"
        )
        from pandemonium.gui.widgets.confirm_dialog import ok_dialog
        ok_dialog(self, "Help — Keyboard Shortcuts", help_text)

    def _open_settings(self):
        self.sm.switch_to(SettingsScreen, push_history=True)

    # ── Keyboard shortcut support ────────────────────────────────────────────

    def handle_escape(self):
        """Override: Esc does nothing in city (no modal to cancel)."""
        pass  # City has no modal state to cancel; player uses buttons
