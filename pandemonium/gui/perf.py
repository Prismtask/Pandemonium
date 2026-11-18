"""gui/perf.py — Windows runtime tweaks for consistent performance.

Laptops on battery run with lower CPU clocks, coalesced OS timers and
EcoQoS power throttling. That stretches tkinter's 40 ms combat poll out to
~47 ms, makes the 25 ms pacing sleeps really sleep ~31 ms, and lets the OS
deprioritise the game against background work — the "plugged vs. unplugged"
performance gap (2026-11-17 report).

While the game is open this module asks Windows to:

* opt the process out of power throttling (EcoQoS),
* give it a slightly-above-normal scheduling priority,
* run with 1 ms timer resolution (accurate ``after()`` / ``sleep()``).

Every call is best-effort and Windows-only; elsewhere the functions are
no-ops. ``restore()`` releases the timer resolution on shutdown.
"""

import ctypes
import sys

# Kept as module globals so ctypes does not unload the timer DLL while the
# raised timer resolution is still active.
_winmm = None
_timer_resolution_set = False


def apply():
    """Apply Windows performance hints (call once at app startup)."""
    global _winmm, _timer_resolution_set
    if sys.platform != "win32":
        return

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return

    # ── 1) Opt out of EcoQoS / power throttling (Windows 8+) ─────────────
    try:
        class _PowerThrottlingState(ctypes.Structure):
            _fields_ = [
                ("Version", ctypes.c_ulong),
                ("ControlMask", ctypes.c_ulong),
                ("StateMask", ctypes.c_ulong),
            ]

        PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        ProcessPowerThrottling = 4  # PROCESS_INFORMATION_CLASS

        # ExecutionSpeed mask set, StateMask 0 = throttle disabled.
        state = _PowerThrottlingState(
            PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            0,
        )
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessInformation.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong,
        ]
        kernel32.SetProcessInformation(
            kernel32.GetCurrentProcess(),
            ProcessPowerThrottling,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
    except Exception:
        pass  # Older Windows / blocked by policy — not fatal.

    # ── 2) Slightly above normal priority ────────────────────────────────
    # Keeps the UI and combat threads scheduled ahead of background chores
    # while the CPU is down-clocked on battery.
    try:
        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel32.SetPriorityClass(
            kernel32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS
        )
    except Exception:
        pass

    # ── 3) 1 ms timer resolution ─────────────────────────────────────────
    # Default Windows resolution is 15.6 ms: after(40) fires at ~47 ms and
    # a 25 ms sleep really sleeps ~31 ms, so combat pacing drags on battery.
    try:
        _winmm = ctypes.WinDLL("winmm")
        _winmm.timeBeginPeriod.argtypes = [ctypes.c_uint]
        _winmm.timeBeginPeriod.restype = ctypes.c_uint
        if _winmm.timeBeginPeriod(1) == 0:  # TIMERR_NOERROR
            _timer_resolution_set = True
    except Exception:
        _winmm = None


def restore():
    """Release the raised timer resolution (call on shutdown)."""
    global _timer_resolution_set
    if sys.platform != "win32" or not _timer_resolution_set:
        return
    try:
        if _winmm is not None:
            _winmm.timeEndPeriod.argtypes = [ctypes.c_uint]
            _winmm.timeEndPeriod.restype = ctypes.c_uint
            _winmm.timeEndPeriod(1)
    except Exception:
        pass
    _timer_resolution_set = False
