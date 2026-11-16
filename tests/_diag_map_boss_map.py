"""Phase 2 diagnostic — Seasonal Map Boss world-map + arena entry.

Manual diagnostic (run directly, not under pytest):
    c:/Code/Pandemonium/.venv/Scripts/python.exe tests/_diag_map_boss_map.py

Covers (docs/map_boss_design.md §10.1–§10.3):
  1. Marker drawing: seasonal glyph, `E{n}`, HP %, gold outline, hitbox
  2. Hit-testing (inside/outside; city click still wins ties)
  3. Selection highlight + info panel (HP bar, mechanic, resists, next Echo,
     recalled depth, spoils preview, travel estimate)
  4. Travel route ends at the synthetic ``map_boss`` node
  5. Start-at-proven-depth dialog: recall / decline paths
  6. Expiry grace: a season turn mid-journey drops the party at the city
  7. Result routing / GUI wiring smoke strings
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import tkinter as tk

from pandemonium.world import map_boss as mb
from pandemonium.gui.screens.world_map_screen import (
    WorldMapScreen,
    _MAP_BOSS_MARKER_H,
    _MAP_BOSS_MARKER_W,
)

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


def make_player(day=20, max_floor=21):
    return {
        "name": "Diag",
        "day": day,
        "max_floor": max_floor,
        "gold": 5000,
        "location": "solmere",
        "floor": 3,
        "inventory": [],
        "allies": [],
        "daily_effects": {},
        "active_buffs": [],
        "journal": {"events": [], "main_quests": [], "side_quests": []},
        "wild_dungeons": {"active": [], "completed": [], "next_id": 1,
                          "last_spawn_day": 0},
    }


def _all_texts(widget):
    out = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
            if text:
                out.append(str(text))
        except tk.TclError:
            pass
        out.extend(_all_texts(child))
    return out


class FakeScreenManager:
    def __init__(self):
        self.calls = []
        self.logs = []

    def switch_to(self, screen_class, **kwargs):
        self.calls.append((screen_class, kwargs))

    def log(self, message, **kwargs):
        self.logs.append(message)

    def get_top_screen(self):
        return None

    @property
    def root(self):
        return None


class ScreenHarness(WorldMapScreen):
    """WorldMapScreen with BaseScreen bypassed — only map-boss state filled."""

    def __init__(self, canvas, info_frame, player):
        self._canvas = canvas
        self._info_frame = info_frame
        self.player = player
        self._selected_wild = None
        self._selected_city = None
        self._selected_horizon = False
        self._selected_map_boss = False
        self._map_boss_rect_id = None
        self._map_boss_hitbox = None
        self._wild_rect_ids = {}
        self._wild_hitboxes = {}
        self._horizon_rect_id = None
        self._horizon_hitbox = None
        self._node_rects = {}
        self._path_result = None
        self._mode = self.MODE_BROWSE
        self._travel_wild = None
        self._travel_horizon = None
        self._travel_map_boss = None
        self._travel_anim_job = None
        self._travel_check_job = None
        self._travel_dot = None
        self._travel_segments = []
        self._travel_paused = False
        self._log_lines = []
        self._finish_calls = []
        self.sm = FakeScreenManager()

    # Stub I/O that needs real travel widgets / navigation
    def _log(self, text, tag="text"):
        self._log_lines.append(str(text))

    def _finish_travel(self, dead=False, wild_arrival=False,
                       map_boss_arrival=False):
        self._finish_calls.append({"dead": dead, "wild": wild_arrival,
                                   "map_boss": map_boss_arrival})


def main():
    root = tk.Tk()
    root.withdraw()

    section("1. Marker drawing")
    player = make_player(day=20)
    site = mb.maybe_spawn(player)
    player["map_boss"]["active"]["hp"] = int(site["max_hp"] * 0.63)

    canvas = tk.Canvas(root)
    info = tk.Frame(root)
    screen = ScreenHarness(canvas, info, player)
    screen._draw_map_boss()

    x, y = site["position"]
    check("hitbox recorded", screen._map_boss_hitbox is not None)
    x1, y1, x2, y2 = screen._map_boss_hitbox
    check("marker centered on the site",
          (x1, y1) == (x - _MAP_BOSS_MARKER_W // 2, y - _MAP_BOSS_MARKER_H // 2),
          f"{(x1, y1)} vs {(x, y)}")
    check("marker size", (x2 - x1, y2 - y1) == (_MAP_BOSS_MARKER_W,
                                                _MAP_BOSS_MARKER_H))
    texts = [canvas.itemcget(i, "text") for i in canvas.find_withtag("map_boss_node")
             if canvas.type(i) == "text"]
    check("glyph + echo on the marker",
          any(site["glyph"] in t and "E0" in t for t in texts), str(texts))
    check("HP % shown while damaged",
          any("63%" in t for t in texts), str(texts))
    rect = canvas.find_withtag("map_boss_node")[0]
    check("gold outline",
          canvas.itemcget(rect, "outline") == "#d4a017",
          canvas.itemcget(rect, "outline"))

    section("2. Hit-testing")
    check("click centre hits", screen._find_map_boss_at(x, y))
    check("click corner inside", screen._find_map_boss_at(x1 + 1, y1 + 1))
    check("click outside misses", not screen._find_map_boss_at(x2 + 10, y2 + 10))
    check("no marker → no hit",
          not ScreenHarness(canvas, info, make_player(max_floor=5))
          ._find_map_boss_at(x, y))

    section("3. Info panel")
    screen._select_map_boss()
    check("selection flagged", screen._selected_map_boss)
    cfg = canvas.itemconfig(screen._map_boss_rect_id)
    check("selected outline gold",
          "#f1c40f" in cfg.get("outline", ()), str(cfg))
    joined = " ".join(_all_texts(info))
    for expected in ("WARDEN OF THE FIRST BLOOM", "Echo 0", "SPOILS",
                     "Travel to the Warden", "Bloom (Poison)",
                     "Nearest city", "Est. travel", "Recommended"):
        check(f"panel shows {expected!r}", expected in joined, joined[:400])
    check("mechanic section is gone",
          "MECHANIC" not in joined and "Resists:" not in joined,
          joined[:400])
    check("HP bar row", any(t.startswith("HP ") and "(" in t
                            for t in _all_texts(info)), joined[:400])
    check("no recalled-depth line yet",
          "Recalled depth" not in joined, joined[:400])

    screen._deselect_map_boss()
    # itemconfig returns a 5-tuple per option on some Tk builds — use membership.
    check("deselect restores outline",
          "#d4a017" in canvas.itemconfig(screen._map_boss_rect_id).get("outline", ()))
    check("placeholder back",
          any("Click a city" in t for t in _all_texts(info)))

    section("4. Travel route")
    journey = mb.build_journey_to_warden(player)
    check("journey built", journey is not None)
    check("route ends at map_boss", journey["path"][-1] == "map_boss",
          str(journey["path"]))
    check("off-road leg targets map_boss",
          journey["segments"][-1]["to"] == "map_boss")
    check("journey blocks estimate", screen._journey_blocks(journey) > 0)

    section("5. Start-at-proven-depth dialog")
    import pandemonium.gui.screens.world_map_screen as wm

    captured = {}

    def _fake_confirm(parent=None, title=None, message="", on_yes=None,
                      on_no=None, **kwargs):
        captured.update({"title": title, "message": message,
                         "on_yes": on_yes, "on_no": on_no,
                         "focus_no": kwargs.get("focus_no"),
                         "yes": kwargs.get("yes_text"),
                         "no": kwargs.get("no_text")})

    original_confirm = wm.confirm_dialog
    wm.confirm_dialog = _fake_confirm
    try:
        player = make_player(day=20)
        mb.maybe_spawn(player)
        player["map_boss"]["best_echo"] = 4
        screen = ScreenHarness(canvas, info, player)
        site = mb.get_active_boss(player)
        offer = mb.start_depth_offer(player)
        check("offer is Echo 4", offer == 4, str(offer))

        screen._travel_map_boss = site
        screen._ask_start_depth(site, offer)
        check("dialog titled", captured.get("title") == "Something Remembers You",
              str(captured.get("title")))
        check("dialog names element/weakness",
              "Earth" in captured["message"] and "Fire" in captured["message"],
              captured["message"])
        check("dialog defaults to Echo 0",
              captured.get("focus_no") is True
              and captured.get("no") == "Begin at Echo 0")
        check("no fight opened before choosing", not screen._finish_calls)

        captured["on_yes"]()
        check("recall sets Echo 4", player["map_boss"]["echo"] == 4)
        check("recall builds that Echo's stats",
              mb.get_active_boss(player)["max_hp"] == mb.echo_stats(4)["max_hp"])
        check("arena opened after recall",
              screen._finish_calls and screen._finish_calls[-1]["map_boss"])

        # Decline path on a fresh season
        player = make_player(day=20)
        mb.maybe_spawn(player)
        player["map_boss"]["best_echo"] = 4
        screen = ScreenHarness(canvas, info, player)
        site = mb.get_active_boss(player)
        screen._travel_map_boss = site
        screen._ask_start_depth(site, mb.start_depth_offer(player))
        captured["on_no"]()
        check("decline keeps Echo 0", player["map_boss"]["echo"] == 0)
        check("decline remembered",
              player["map_boss"]["depth_declined_season"] == "spring")
        check("arena opened after decline",
              screen._finish_calls and screen._finish_calls[-1]["map_boss"])
    finally:
        wm.confirm_dialog = original_confirm

    section("6. Arrival + expiry grace")
    player = make_player(day=20)
    mb.maybe_spawn(player)
    screen = ScreenHarness(canvas, info, player)
    screen._travel_map_boss = mb.get_active_boss(player)
    screen._arrive_at_map_boss()
    p = player
    check("floor cursor snapshotted", p.get("_map_boss_prev_floor") == 3, str(p.get("_map_boss_prev_floor")))
    check("arena site flag set", p.get("_map_boss_site") == "warden_spring_0")
    check("origin city is nearest", p.get("origin_city") == screen._travel_map_boss["nearest_city"])
    check("location = dungeon", p.get("location") == "dungeon")
    check("combat floor label = Arena", p.get("_combat_floor_label") == "Arena")
    check("stale log/flag scrub",
          "_dungeon_log" not in p and "pandemonium_mode" not in p
          and "_eh_in_run" not in p)
    check("arena opened", screen._finish_calls[-1]["map_boss"] is True)

    # Season turns mid-journey → grace exit to the nearest city
    player = make_player(day=90)
    mb.maybe_spawn(player)
    stale = mb.get_active_boss(player)
    screen = ScreenHarness(canvas, info, player)
    screen._travel_map_boss = stale
    player["day"] = 91
    screen._arrive_at_map_boss()
    check("grace exit does not open the arena",
          screen._finish_calls[-1]["map_boss"] is False)
    check("grace exit sends you to a city",
          player["location"] in mb.CITIES, player["location"])
    check("grace exit logs the turn",
          any("season has turned" in line for line in screen._log_lines),
          str(screen._log_lines))
    check("new season Warden spawned",
          mb.get_active_boss(player)["season"] == "summer")

    section("7. Result routing + GUI wiring")
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _read(rel):
        with open(os.path.join(root_dir, rel), encoding="utf-8") as f:
            return f.read()

    wm_src = _read("pandemonium/gui/screens/world_map_screen.py")
    ds_src = _read("pandemonium/gui/screens/dungeon_screen.py")
    dth_src = _read("pandemonium/gui/screens/death_screen.py")
    dun_src = _read("pandemonium/world/dungeon.py")

    check("map draws the Warden", "self._draw_map_boss()" in wm_src)
    check("map spawns on open", "maybe_spawn_map_boss(self.player)" in wm_src)
    check("travel handler", "_on_travel_to_map_boss" in wm_src)
    check("arrival handler", "_arrive_at_map_boss" in wm_src)
    check("result router", "_on_map_boss_result" in wm_src)
    check("depth dialog", "_ask_start_depth" in wm_src)
    check("defensive scrub", "_scrub_map_boss_run" in wm_src)
    check("legend mentions the Warden", "Seasonal Warden" in wm_src)
    check("arena branding branch", '_map_boss_site' in ds_src and
          "Leave Arena" in ds_src)
    check("arena static map", "ARENA" in ds_src)
    check("leave confirm defaults to staying",
          "Keep Fighting" in ds_src)
    check("death screen names the Warden", '"map_boss"' in dth_src
          and "death_boss_echo" in dth_src)
    check("dungeon dispatch", "_explore_map_boss_arena" in dun_src)
    check("interim guard result", "MAP_BOSS_ARENA_SEALED" in dun_src)

    # Death screen detail line, built without a real screen manager.
    from pandemonium.gui.screens.death_screen import DeathScreen
    detail = None
    site = {"warden_name": "Warden of the First Bloom", "season_name": "Spring"}
    echo_lbl = mb.echo_label(0)
    detail = (f"You were slain by the {site['warden_name']} — "
              f"{site['season_name']} Echo {echo_lbl}.")
    check("death line reads correctly",
          detail == "You were slain by the Warden of the First Bloom — "
                    "Spring Echo 0.", detail)
    check("DeathScreen accepts boss kwargs",
          "boss_name=None" in dth_src)
    check("DeathScreen imported", DeathScreen is not None)

    section("8. Arena result routing")
    from pandemonium.gui.screens.city_screen import CityScreen
    from pandemonium.gui.screens.death_screen import DeathScreen
    from pandemonium.gui.screens.main_menu_screen import MainMenuScreen

    ok_calls = {}
    wm_ok = None
    import pandemonium.gui.widgets.confirm_dialog as cd
    original_ok = cd.ok_dialog

    def _fake_ok(parent=None, title=None, message="", on_ok=None):
        ok_calls.update({"title": title, "message": message, "on_ok": on_ok})

    cd.ok_dialog = _fake_ok
    try:
        # ── death ───────────────────────────────────────────────────────
        player = make_player(day=20)
        mb.maybe_spawn(player)
        screen = ScreenHarness(canvas, info, player)
        player["_map_boss_site"] = "warden_spring_0"
        player["_map_boss_prev_floor"] = 3
        screen._on_map_boss_result("dead")
        screen_class, kwargs = screen.sm.calls[-1]
        check("death → DeathScreen", screen_class is DeathScreen)
        check("death carries the Warden",
              kwargs.get("death_type") == "map_boss"
              and kwargs.get("boss_name") == "Warden of the First Bloom"
              and kwargs.get("boss_season") == "Spring"
              and kwargs.get("boss_echo") == 0, str(kwargs))

        # ── interim sealed arena ────────────────────────────────────────
        player = make_player(day=20)
        mb.maybe_spawn(player)
        screen = ScreenHarness(canvas, info, player)
        player["_map_boss_site"] = "warden_spring_0"
        player["_map_boss_prev_floor"] = 3
        screen._on_map_boss_result("map_boss_locked")
        check("sealed arena dialog", ok_calls.get("title") == "The Arena Is Sealed",
              str(ok_calls.get("title")))
        check("sealed arena scrubs the run",
              "_map_boss_site" not in player and player.get("floor") == 3)
        ok_calls["on_ok"]()
        check("sealed arena returns to city",
              screen.sm.calls[-1][0] is CityScreen)

        # ── flee / timeout ─────────────────────────────────────────────
        player = make_player(day=20)
        mb.maybe_spawn(player)
        screen = ScreenHarness(canvas, info, player)
        player["_map_boss_site"] = "warden_spring_0"
        player["_map_boss_prev_floor"] = 3
        player["location"] = "dungeon"
        screen._on_map_boss_result("fled")
        check("flee → CityScreen", screen.sm.calls[-1][0] is CityScreen)
        check("flee restores floor/location",
              player.get("floor") == 3 and player.get("location") == "solmere")
        check("flee keeps the Warden alive",
              mb.get_active_boss(player) is not None)

        # ── save & exit ────────────────────────────────────────────────
        player = make_player(day=20)
        mb.maybe_spawn(player)
        screen = ScreenHarness(canvas, info, player)
        screen._on_map_boss_result("save_exit")
        check("save_exit → main menu", screen.sm.calls[-1][0] is MainMenuScreen)
    finally:
        cd.ok_dialog = original_ok

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)} check(s): {FAILS}")
        sys.exit(1)
    print("All Phase 2 map boss checks passed.")


if __name__ == "__main__":
    main()
