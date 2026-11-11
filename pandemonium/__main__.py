"""Run Pandemonium with ``python -m pandemonium``.

``launcher.py`` stays the PyInstaller entry point (it also installs the
background-thread exception hook). This module is the convenience alias so the
game can be started without referring to a top-level script.
"""

from pandemonium.gui.app import run_gui


def main():
    run_gui()


if __name__ == "__main__":
    main()
