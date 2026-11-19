"""
version.py — Single source of truth for the game's version.

Scheme: custom 4-part MAJOR.DEVELOPMENT.FEATURE.PATCH (NOT strict SemVer):
  - The 3rd digit opens a named feature chapter and resets the 4th to 0
    (0.1.7.0 "The Chromatic Artisan" → 0.1.8.0 "The Distant Journey").
  - The 4th digit counts quick fixes / small updates within a chapter
    (0.1.8.0 → 0.1.8.1).
The game is pre-1.0: RELEASE_STAGE stays "alpha" or "beta" until the first
stable release (1.0.0).

Bump procedure:
  1. Update GAME_VERSION / VERSION_NAME here (RELEASE_STAGE only at 1.0.0).
  2. Prepend the new version block (header + sections) at the TOP of
     gui/screens/changelog_screen.py — never edit older headers.
  3. Run tests/_diag_version_consistency.py — expect "version consistency OK".
"""

GAME_VERSION = "0.1.9.1"
VERSION_NAME = "The Family We Choose"

# Release stage: "alpha" → "beta" → "stable".
#   alpha  — features still landing, placeholders may ship, save formats
#            change freely between builds.
#   beta   — feature-frozen; polish and bug fixes only, saves preserved.
#   stable — the first non-pre-release build. Not allowed before 1.0.0.
RELEASE_STAGE = "alpha"

# Pre-1.0 clarifier (shown in-game and in the window title).
IS_PRERELEASE = RELEASE_STAGE in ("alpha", "beta")

# Pure version header — matches the changelog's newest (current) header.
VERSION_DISPLAY = f"v{GAME_VERSION} — {VERSION_NAME}"

# Player-facing label (adds the stage clarifier while pre-1.0).
VERSION_LABEL = VERSION_DISPLAY + (f" ({RELEASE_STAGE})" if IS_PRERELEASE else "")
