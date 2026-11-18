"""
gui/app.py — Main tkinter application class and entry point for GUI mode.

Creates the root window, sets up the ScreenManager, and launches the
first screen (main menu or splash). Manages global keyboard shortcuts
and settings persistence.
"""

import tkinter as tk
import threading
from tkinter import font as tkfont

from pandemonium.gui.theme import (
    Theme,
    WINDOW_DEFAULT_SIZE,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_TITLE,
    set_font_size,
)
from pandemonium.gui.screen_manager import ScreenManager
from pandemonium.gui.settings import load_settings, save_settings
import traceback
from pandemonium.gui.screens.splash_screen import SplashScreen
from pandemonium.gui.screens.main_menu_screen import MainMenuScreen
from pandemonium.gui import perf


class PandemoniumApp:
    """
    Main application wrapper for the GUI version of Pandemonium.

    Responsibilities:
    - Create and configure the root tk.Tk window
    - Load and apply GUI settings
    - Set up the ScreenManager
    - Register global keyboard shortcuts
    - Show splash screen (optional), then main menu
    - Handle clean shutdown with settings persistence
    """

    def __init__(self, player: dict = None):
        # ── Load settings before window creation ──────────────────────────
        self.settings = load_settings()

        # Apply font size before any widgets are created
        set_font_size(self.settings.get("font_size", 11))

        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(self.settings.get("window_size", WINDOW_DEFAULT_SIZE))
        self.root.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.root.configure(bg=Theme.BG_DARK)

        # Suppress known Tkinter internal race-condition errors that occur
        # when after() callbacks fire after a widget's Tcl context is torn down.
        # These are harmless and unrecoverable at the application level.
        def _tk_error_handler(exc_type, exc_val, exc_tb):
            msg = str(exc_val)
            # Known Tcl-level race conditions during widget destruction
            if ("can't delete Tcl command" in msg or
                    "'NoneType' object has no attribute 'remove'" in msg):
                return  # Silently suppress — harmless race condition
            # For everything else, print the full traceback
            traceback.print_exception(exc_type, exc_val, exc_tb)

        self.root.report_callback_exception = _tk_error_handler

        # Restore window position if saved
        pos = self.settings.get("window_position")
        if pos:
            try:
                self.root.geometry(pos)
            except tk.TclError:
                pass

        # Ensure monospace font is available
        self._ensure_monospace_font()

        # Shared game state (None until a save is loaded or character is created)
        self.player = player

        # Screen manager handles all screen transitions
        self.screen_manager = ScreenManager(self.root, player=self.player, settings=self.settings)

        # Register global keyboard shortcuts
        self._setup_global_bindings()

        # Save settings on window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _ensure_monospace_font(self):
        """Pre-load the monospace font family so widgets can reference it."""
        families = tkfont.families(self.root)
        # The Theme module already defines FONT_FAMILY based on platform.

    def _setup_global_bindings(self):
        """Bind global keyboard shortcuts on the root window."""
        if not self.settings.get("keyboard_mode", True):
            return

        self.root.bind("<Escape>", self._on_global_escape)
        self.root.bind("<KeyPress-i>", self._on_inventory_key)
        self.root.bind("<KeyPress-I>", self._on_inventory_key)
        self.root.bind("<Control-q>", lambda e: self._on_close())
        self.root.bind("<Control-Q>", lambda e: self._on_close())

    def _on_global_escape(self, event):
        """Global Escape key handler — delegates to the topmost screen.

        Must prefer an active overlay: dispatching to current_screen sent
        Escape to the hidden screen underneath (e.g. the world map), whose
        default handle_escape called sm.go_back() and rebuilt CityScreen
        below the still-running combat overlay (2026-10-08 — its VEILHOLT
        banner peeked out at the bottom of the combat screen).
        """
        screen = self.screen_manager.get_top_screen()
        if screen and hasattr(screen, "handle_escape"):
            screen.handle_escape()

    def _on_inventory_key(self, event):
        """Global 'I' key — opens inventory. Uses overlay for DungeonScreen
        to avoid destroying the dungeon thread mid-run.

        Dispatches to the topmost screen: while an overlay (combat, story,
        ...) is up the key is ignored, because pushing the inventory overlay
        would first dismiss the live overlay — pressing 'I' mid-fight used
        to kill the combat screen (2026-10-08).

        NOTE: CityScreen has its own local 'I' handler in _on_city_key,
        so we skip CityScreen here to avoid double-dispatch.
        """

        # Local import: heavy screens load on demand (and are pre-warmed on a
        # worker thread) so the main menu does not pay their import cost.
        from pandemonium.gui.screens.dungeon_screen import DungeonScreen
        from pandemonium.gui.screens.inventory_screen import InventoryScreen

        screen = self.screen_manager.get_top_screen()
        if isinstance(screen, DungeonScreen):
            self.screen_manager.push_overlay(
                InventoryScreen,
                is_overlay=True,
            )

    def _on_close(self):
        """Save settings and clean up before closing."""
        try:
            # Capture current window size and position
            geo = self.root.geometry()
            self.settings["window_size"] = geo.split("+")[0] if "+" in geo else geo
            # Save position offset
            parts = geo.split("+")
            if len(parts) >= 3:
                self.settings["window_position"] = f"+{parts[1]}+{parts[2]}"
            save_settings(self.settings)
        except Exception:
            pass
        perf.restore()
        self.root.destroy()

    def run(self):
        """Start the tkinter main loop. Optionally shows splash screen first."""
        if self.settings.get("show_splash", True):

            def _after_splash():
                self.screen_manager.switch_to(MainMenuScreen, push_history=False)

            self.screen_manager.switch_to(
                SplashScreen,
                push_history=False,
                on_complete=_after_splash,
            )
        else:
            self.screen_manager.switch_to(MainMenuScreen, push_history=False)

        # Import the game screens in the background while the player reads the
        # splash/menu. Without this, the first Load/New Game click pays the
        # multi-second import chain (city + dungeon + combat + facility data).
        self.root.after(300, self._start_screen_warmup)
        self.root.mainloop()

    def _start_screen_warmup(self):
        """Kick the screen import warm-up off the UI thread."""
        threading.Thread(
            target=self._warm_up_screen_imports,
            name="screen-warmup",
            daemon=True,
        ).start()

    @staticmethod
    def _warm_up_screen_imports():
        """Import the heavy GUI screens ahead of first use.

        Runs on a daemon thread and never creates widgets. Python's import
        lock makes the later on-demand import a cheap no-op; a failure here is
        harmless because the real import retries on demand.
        """
        try:
            import pandemonium.gui.screens.city_screen  # noqa: F401
            import pandemonium.gui.screens.dungeon_screen  # noqa: F401
            import pandemonium.gui.screens.inventory_screen  # noqa: F401
            import pandemonium.gui.screens.world_map_screen  # noqa: F401
            import pandemonium.gui.screens.combat_screen  # noqa: F401
        except Exception:
            pass


def run_gui(player: dict = None):
    """Convenience entry point: create app and run it."""
    # Windows: opt out of EcoQoS throttling, raise priority slightly and use
    # 1 ms timers (keeps combat pacing stable on battery).
    perf.apply()
    app = PandemoniumApp(player=player)
    try:
        app.run()
    except KeyboardInterrupt:
        # Ctrl+C in the terminal running the GUI: save settings, close the
        # window, and let launcher.py print a clean exit message.
        try:
            app._on_close()
        except Exception:
            pass
        raise
