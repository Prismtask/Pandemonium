"""Phase 2 diagnostic — arena GUI branding (docs/map_boss_design.md §10.3–10.5).

Manual diagnostic (run directly, not under pytest):
    c:/Code/Pandemonium/.venv/Scripts/python.exe tests/_diag_map_boss_gui.py

Tk is required (skipped cleanly when unavailable). Covers:
  1. DungeonScreen arena branding — title, subtitle, top bar, Arena panel,
     "Leave Arena" button, no craft hint
  2. Leave-Arena confirm — wording, `focus_no`, expire day
  3. DeathScreen — "You were slain by the … — Spring Echo I."
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FAILS = []


def check(label, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(label)


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def make_player(day=20):
    return {
        "name": "Diag",
        "day": 20 if day is None else day,
        "max_floor": 21,
        "gold": 5000,
        "location": "dungeon",
        "floor": 3,
        "level": 20,
        "exp": 0,
        "current_hp": 50,
        "inventory": [],
        "allies": [],
        "daily_effects": {},
        "active_buffs": [],
        "attributes": {"Strength": 10, "Dexterity": 10, "Constitution": 10,
                       "Intelligence": 10, "Wisdom": 10, "Charisma": 10},
        "city_floors": {"solmere": {"floor": 1, "max_floor": 21}},
        "journal": {"events": [], "main_quests": [], "side_quests": []},
        "origin_city": "solmere",
        "dungeon_region": "temperate",
    }


def main():
    try:
        from _tk_test_utils import shared_tk_root
        root = shared_tk_root()
    except Exception as exc:  # pragma: no cover - environment guard
        print(f"SKIP: Tk unavailable ({exc})")
        return

    from pandemonium.gui.screen_manager import ScreenManager
    from pandemonium.gui.screens.dungeon_screen import DungeonScreen
    from pandemonium.gui.screens.death_screen import DeathScreen
    from pandemonium.world import map_boss as mb
    from pandemonium.combat import map_boss as cmb

    # ── 1. Arena branding ───────────────────────────────────────────────
    section("1. DungeonScreen arena branding")
    player = make_player()
    site = mb.maybe_spawn(player)
    player["map_boss"]["active"]["hp"] = 630
    player["_map_boss_site"] = site["id"]
    player["_map_boss_prev_floor"] = 3

    sm = ScreenManager(root, player=player, settings={})
    results = []
    sm.switch_to(DungeonScreen, on_result=results.append, push_history=False)
    root.update()
    screen = sm.current_screen

    check("screen built", isinstance(screen, DungeonScreen))
    check("title is the Warden",
          screen._dungeon_name == "Warden of the First Bloom",
          screen._dungeon_name)
    subtitle = screen._subtitle_label.cget("text")
    check("subtitle = season · echo · level · mechanic",
          subtitle == "Spring \u00b7 Echo 0 \u00b7 Lv 20 \u00b7 Bloom", subtitle)
    check("leave button says Leave Arena",
          "\u2190 Leave Arena" == screen.back_btn.cget("text"),
          screen.back_btn.cget("text"))
    map_text = str(screen.map_text.get("1.0", "end"))
    check("arena panel shows the arena", "ARENA" in map_text, map_text)
    check("no floor wording on the map", "Floor" not in map_text, map_text)
    top_text = sm.top_name.cget("text")
    check("top bar shows the season + Echo",
          "Spring Echo 0" in top_text, top_text)
    check("top bar shows Echo HP",
          "HP 63%" in top_text, top_text)
    check("static top-line helper",
          screen._map_boss_top_line(site) == "\U0001F331 Spring Echo 0 \u00b7 HP 63%",
          screen._map_boss_top_line(site))

    # ── 2. Leave confirm ────────────────────────────────────────────────
    section("2. Leave-Arena confirm")
    import pandemonium.gui.screens.dungeon_screen as ds_mod
    captured = {}
    original = ds_mod.confirm_dialog

    def _fake_confirm(parent=None, title=None, message="", on_yes=None,
                      on_no=None, **kwargs):
        captured.update({"title": title, "message": message,
                         "focus_no": kwargs.get("focus_no"),
                         "yes": kwargs.get("yes_text"),
                         "no": kwargs.get("no_text"),
                         "on_yes": on_yes, "on_no": on_no})

    ds_mod.confirm_dialog = _fake_confirm
    try:
        screen._confirm_dialog_open = False
        screen._on_flee()
        check("confirm title", captured.get("title") == "Leave the Arena?",
              str(captured.get("title")))
        check("confirm mentions HP is kept",
              "HP is kept" in captured.get("message", ""),
              captured.get("message", ""))
        check("confirm names the season end day",
              "Day 91" in captured.get("message", ""),
              captured.get("message", ""))
        check("confirm defaults to staying",
              captured.get("focus_no") is True
              and captured.get("no") == "Keep Fighting",
              f"{captured.get('no')!r} focus_no={captured.get('focus_no')}")
        check("confirm yes leaves the arena",
              captured.get("yes") == "Leave Arena")
        captured["on_no"]()
        check("staying re-arms the confirm", screen._confirm_dialog_open is False)
    finally:
        ds_mod.confirm_dialog = original

    # ── 3. Death screen ─────────────────────────────────────────────────
    section("3. DeathScreen")
    sm.switch_to(
        DeathScreen, floor=1, city_id="solmere", death_type="map_boss",
        boss_name="Warden of the First Bloom", boss_season="Spring",
        boss_echo=1, on_continue=lambda: None, on_quit=lambda: None,
        push_history=False,
    )
    root.update()
    death = sm.current_screen
    labels = []

    def _collect(widget):
        for child in widget.winfo_children():
            try:
                text = child.cget("text")
                if text:
                    labels.append(str(text))
            except Exception:
                pass
            _collect(child)

    _collect(death)
    joined = " | ".join(labels)
    check("death screen names the Warden",
          "You were slain by the Warden of the First Bloom \u2014 Spring Echo I."
          in joined, joined[:400])

    # ── 4. CombatScreen arena wiring (Phase 3) ──────────────────────────
    section("4. CombatScreen arena wiring")
    import types

    from pandemonium.gui.screens.combat_screen import CombatScreen
    from pandemonium.gui.screens.dungeon_screen import DungeonScreen

    player = make_player()
    site = mb.maybe_spawn(player)
    player["map_boss"]["active"]["hp"] = 630
    sm.player = player

    class FakeRoot:
        def after(self, _delay, fn=None, *a):
            if fn:
                fn()

    class FakeOverlaySM:
        def __init__(self):
            self.calls = []
            self.root = FakeRoot()

        def push_overlay(self, screen_class, **kwargs):
            self.calls.append((screen_class, kwargs))

    fake_sm = FakeOverlaySM()
    fake = types.SimpleNamespace(
        sm=fake_sm,
        _await_combat_result=lambda queue, label="Combat": "fled",
    )
    enemies = [cmb.build_encounter(site)[0]]
    result = DungeonScreen._gui_map_boss(fake, player, site, enemies)
    check("arena fight returns its result", result == "fled", str(result))
    check("one overlay pushed", len(fake_sm.calls) == 1, str(fake_sm.calls))
    screen_class, kwargs = fake_sm.calls[0]
    check("overlay is CombatScreen", screen_class is CombatScreen)
    check("shared enemy list passed", kwargs.get("enemies") is enemies)
    check("arena context",
          kwargs.get("combat_context") == "map_boss", str(kwargs.get("combat_context")))
    check("combat_func is the arena",
          getattr(kwargs.get("combat_func"), "__name__", "") == "combat_map_boss",
          str(kwargs.get("combat_func")))
    check("overlay mode", kwargs.get("is_overlay") is True)

    # Top bar + gimmick pinning.
    top = CombatScreen._map_boss_top_bar(
        types.SimpleNamespace(player=player))
    check("combat top bar names the Warden",
          "Warden of the First Bloom" in top, top)
    check("combat top bar shows season/Echo",
          "Spring Echo 0" in top, top)
    check("combat top bar shows Echo HP", "HP 63%" in top, top)
    check("[PHASE] banners are pinned",
          "[phase]" in CombatScreen._GIMMICK_TAGS,
          str(CombatScreen._GIMMICK_TAGS))

    # Projected clock label reaches the combat header.
    from pandemonium.combat.combat_ui import current_time_label
    player["_combat_time_label"] = "\u2600 Morning \u25ae\u25ae\u25ae"
    check("header reads the projected clock",
          current_time_label(player) == "\u2600 Morning \u25ae\u25ae\u25ae",
          current_time_label(player))
    player.pop("_combat_time_label", None)

    # ── 5. Reform window loot lines (Phase 4) ───────────────────────────
    section("5. Reform window loot lines")
    from pandemonium.gui.screens.world_map_screen import WorldMapScreen

    summary = {
        "warden_name": "Warden of the First Bloom",
        "season": "spring", "season_name": "Spring",
        "echo": 0, "level": 20, "night": True,
        "gold": 550, "exp": 600,
        "cache": {"name": "Rare Verdant Blade", "rarity": "rare"},
        "consumables": [{"name": "Elixir of Bloom", "rarity": "common"},
                        {"name": "Salve", "rarity": "common"}],
        "flowers": [{"name": "Emberbloom", "rarity": "common"},
                    {"name": "Emberbloom", "rarity": "common"}],
        "uniques": [{"name": "Warden's Signet", "rarity": "unique",
                     "id": "warden_signet"}],
        "extra_caches": 0,
    }
    lines = WorldMapScreen._map_boss_loot_lines(summary)
    joined_loot = " | ".join(lines)
    check("loot lines show gold and XP", "550 gold" in joined_loot
          and "600 XP" in joined_loot, joined_loot)
    check("loot lines flag the Night kill", "(Night kill)" in joined_loot,
          joined_loot)
    check("loot lines list the cache",
          "Warden's Cache: Rare Verdant Blade" in joined_loot, joined_loot)
    check("loot lines name the trophy",
          "\u2605 Trophy: Warden's Signet" in joined_loot, joined_loot)
    check("duplicate flowers collapse to a count",
          "Emberbloom \u00d72" in joined_loot, joined_loot)
    check("no summary means no loot lines",
          WorldMapScreen._map_boss_loot_lines(None) == [])

    # The reform window must consume the stash so it never shows twice.
    player["_map_boss_victory"] = dict(summary)
    captured = {}

    from pandemonium.gui.widgets import confirm_dialog as _cd

    def _fake_choice(**kwargs):
        captured.update(kwargs)

    _orig_choice = _cd.choice_dialog
    _cd.choice_dialog = _fake_choice
    try:
        wm = types.SimpleNamespace(
            player=player,
            sm=types.SimpleNamespace(root=root,
                                     get_top_screen=lambda: sm.current_screen),
            _map_boss_reenter=lambda: None,
            _map_boss_leave_to_city=lambda: None,
            _map_boss_loot_lines=WorldMapScreen._map_boss_loot_lines,
        )
        WorldMapScreen._show_map_boss_victory(wm)
    finally:
        _cd.choice_dialog = _orig_choice
    details = captured.get("details", "")
    check("reform window shows the spoils",
          "550 gold" in details and "Warden's Cache" in details,
          details[-300:])
    check("reform window consumes the stash",
          "_map_boss_victory" not in player)
    check("reform window keeps both choices",
          [opt[0] for opt in captured.get("options", [])] == ["fight", "leave"],
          str(captured.get("options")))

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)} check(s): {FAILS}")
        sys.exit(1)
    print("All map boss GUI checks passed (Phases 2-4).")


if __name__ == "__main__":
    main()
