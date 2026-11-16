# -*- coding: utf-8 -*-
"""Diag — the GUI combat input bridge never sends a stale answer (2026-11-14).

Playtest report (Winter Warden): the log showed
``Internal error: override action '' is not available.`` and then the legacy
``[A]ttack  [D]efend  [F]lee  [U]se item`` line. Both came from the superboss
action loop:

  * a duplicate answer (double click / repeated Enter on Continue) was queued
    and consumed by the NEXT prompt, which then had no valid action;
  * the loop printed the legacy key list, which the GUI never needs (it draws
    its own action panel).

This diag drives a **real CombatScreen** through a Winter arena fight: every
engine prompt is handled by the screen's own ``_handle_input_needed`` and the
"click" is taken from the buttons that were actually rendered, so the engine
and the panel can never disagree unless the bridge is broken.

Run:
    c:/Code/Pandemonium/.venv/Scripts/python.exe tests/_diag_combat_input_path.py
"""
import os
import sys
import types
import tkinter as tk

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


from pandemonium.combat import map_boss as cmb  # noqa: E402
from pandemonium.combat.combat_io import reset_io, set_io  # noqa: E402
from pandemonium.gui.screens.combat_screen import (  # noqa: E402
    CombatScreen, GUICombatIO,
)
from pandemonium.world import map_boss as mb  # noqa: E402


class FakeSM:
    """Minimal screen-manager stand-in."""

    def __init__(self, player):
        self.player = player
        noop = types.SimpleNamespace(config=lambda *a, **k: None)
        self.top_name = noop
        self.top_info = noop

    def log(self, *a, **k):
        pass

    def clear_log(self, *a, **k):
        pass

    def update_top_bar(self, *a, **k):
        pass


class HeadlessCombatScreen(CombatScreen):
    """CombatScreen without starting its own thread or polls."""

    def _start_combat(self):
        pass

    def _schedule_poll(self):
        pass

    def _refresh_hud(self):
        pass


class NoopRenderer:
    def __getattr__(self, name):
        return lambda *a, **k: None


class ClickBridge(GUICombatIO):
    """The real input bridge, clicked by a robot.

    Every prompt is rendered by the screen's own ``_handle_input_needed`` and
    the "click" is taken from the buttons that were actually drawn, then fed
    through ``send_input`` exactly like a mouse click. ``double_click`` sends a
    second value for the same prompt, which the bridge must drop.
    """

    renders_menus = True

    def __init__(self, screen, double_click=False):
        super().__init__()
        self.screen = screen
        self.log = []
        self.clicks = 0
        self.double_click = double_click
        self.max_clicks = 400
        self._idx = 0

    def print(self, *args, **kwargs):
        text = " ".join(str(a) for a in args)
        self.log.append(text)
        self.screen._handle_output(text)

    def input(self, prompt=""):
        low = str(prompt).lower()
        # The engine opens the prompt first (exactly like GUICombatIO.input),
        # so the click below is a legitimate answer and not a stray.
        self.begin_prompt(prompt)
        self.screen._handle_input_needed(prompt)
        if "choose" in low:
            keys = [k for k, b in self.screen.action_panel._buttons.items()
                    if str(b.cget("state")) != "disabled"]
            key = keys[self._idx % len(keys)] if keys else "a"
            self._idx += 1
            self.clicks += 1
            if self.clicks > self.max_clicks:
                raise KeyboardInterrupt("click cap")
            self.send_input(key)
            if self.double_click:
                self.send_input(key)     # dropped: this prompt is answered
        elif any(w in low for w in ("target", "select", "which", "net choice",
                                    "choice:")):
            self.send_input("1")
        else:
            # Continue / "Press Enter" prompts: click Continue.
            self.send_input("")
        return self.wait_answer()

    def clear(self):
        pass

    def is_active(self):
        return True


def hero(day=302, blocks=10, strength=200, hp=6000, con=40):
    return {
        "name": "WinterTest", "class": "Warrior", "level": 60,
        "current_hp": hp, "passive_unlocked": True,
        "attributes": {"Strength": strength, "Constitution": con,
                       "Dexterity": 10, "Wisdom": 10, "Learning": 40,
                       "Charisma": 40},
        "level_hp_bonus": 0,
        "equipped": {"weapon": None, "armor": None,
                     "accessory1": None, "accessory2": None},
        "active_buffs": [], "active_debuffs": [], "elemental_dmg": {},
        "elemental_res": {}, "inventory": [], "allies": [], "skills": [],
        "skill_mastery": {}, "skill_cooldowns": {},
        "day_blocks": blocks, "day": day, "gold": 1000, "max_floor": 21,
        "location": "dungeon", "origin_city": "solmere",
        "dungeon_region": "tundra", "save_slot": 99,
        "journal": {"events": [], "main_quests": [], "side_quests": []},
    }


def run_fight(label, blocks, double_click=False):
    root = tk.Tk()
    root.geometry("1x1+0+0")
    container = tk.Frame(root)
    container.pack()

    player = hero(blocks=blocks)
    sm = FakeSM(player)
    site = mb.maybe_spawn(player)
    boss = cmb.build_boss(site)
    boss["hp"] = boss["max_hp"]
    enemies = [boss]

    screen = HeadlessCombatScreen(container, sm, enemies=enemies,
                                  floor=site["level"],
                                  combat_context="map_boss")
    screen.renderer = NoopRenderer()
    io = ClickBridge(screen, double_click=double_click)
    screen.io = io

    set_io(io)
    try:
        result = cmb.combat_map_boss(player, floor=site["level"],
                                     enemies=enemies)
    except KeyboardInterrupt:
        result = "CAP"
    finally:
        reset_io()
    # Snapshot BEFORE teardown: destroy() pushes the stop() sentinel.
    leftover = list(io.input_queue.queue)
    root.update()
    root.destroy()

    joined = "\n".join(io.log)
    internal = [l for l in io.log if "Internal error" in l]
    legacy = [l for l in io.log
              if "[A]ttack  [D]efend  [F]lee  [U]se item" in l]
    print(f"       {label}: result={result} "
          f"rounds={player.get('_map_boss_rounds')} clicks={io.clicks}")
    check(f"{label}: fight resolves", result in ("victory", "fled", "dead"),
          result)
    check(f"{label}: no internal-error lines", not internal, internal[:2])
    check(f"{label}: no legacy action list in the log", not legacy, legacy[:2])
    check(f"{label}: panel keys were used", io.clicks > 0, str(io.clicks))
    check(f"{label}: no stale answer queued", not leftover,
          f"leftover={leftover!r}")
    return result


def main():
    section("1. Winter arena — real CombatScreen input path")
    run_fight("Night start", 16)
    run_fight("Noon start", 10)

    section("2. Duplicate answers (double clicks) are dropped")
    run_fight("Night, double clicks", 16, double_click=True)

    section("3. GUICombatIO only answers an open prompt")
    io = GUICombatIO()
    io.send_input("a")                # no prompt open — dropped
    check("input without an open prompt is dropped", io.input_queue.empty(),
          f"{list(io.input_queue.queue)!r}")
    io.begin_prompt("Choose: ")
    io.send_input("a")
    io.send_input("a")                # duplicate click — dropped
    io.send_input("")                 # stray Enter — dropped
    check("duplicate answers dropped", io.input_queue.qsize() == 1,
          str(io.input_queue.qsize()))
    check("the first answer is the one kept", io.wait_answer() == "a")
    check("no stale answer queued", io.input_queue.empty(),
          f"{list(io.input_queue.queue)!r}")
    io.send_input("d")                # prompt already consumed — dropped
    check("answers after the prompt closed are dropped",
          io.input_queue.empty(), f"{list(io.input_queue.queue)!r}")
    io.begin_prompt("Choose: ")
    io.send_input("d")
    check("the next prompt accepts again", io.wait_answer() == "d")

    print()
    if FAILS:
        print(f"FAILED: {len(FAILS)} check(s): {FAILS}")
        sys.exit(1)
    print("All combat input-path checks passed.")


if __name__ == "__main__":
    main()
