"""
resources/world_layout.py — Shared world-map layout data.

Owns the city canvas positions, region groupings, and node metrics used by
the GUI world map (gui/screens/world_map_screen.py) AND by runtime systems
that need to place things on the map (wild_dungeons.py).

Design: docs/wild_dungeon_design.md §3 — moving layout out of the GUI module
lets runtime code place wild dungeon markers without importing tkinter.

This module is pure data + tiny helpers — no game-system imports.
"""

CITY_POSITIONS = {
    "stormhold": (80, 60),
    "thornwall": (230, 80),
    "celestia":  (250, 30),
    "solmere":    (200, 160),
    "greyharbor": (120, 220),
    "elderfen":   (310, 230),
    "irondeep":   (450, 140),
    "skylume":    (580, 80),
    "cinderpeak": (570, 190),
    "veilholt":   (680, 140),
    "sunreach":   (170, 330),
    "brinewatch": (60, 410),
    "mirefall":   (250, 380),
    "ashkara":    (100, 480),
    "dunemar":    (200, 510),
    "saltmarsh":  (310, 430),
    "tidebreak":    (450, 400),
    "coralhaven":   (600, 380),
    "blackwake":    (520, 500),
    "isle_of_glass": (650, 500),
}

REGIONS = {
    "North":       ("stormhold", "thornwall", "celestia"),
    "Central":     ("solmere", "greyharbor", "elderfen"),
    "East":        ("irondeep", "skylume", "cinderpeak", "veilholt"),
    "South":       ("sunreach", "brinewatch", "mirefall", "ashkara",
                    "dunemar", "saltmarsh"),
    "Far Reaches": ("tidebreak", "coralhaven", "blackwake", "isle_of_glass"),
}

# City node dimensions (px) — shared so runtime code can compute node centers
# and keep wild dungeon markers clear of them.
NODE_W = 120
NODE_H = 38

# Map-marker rectangles (px). Runtime placement (wild_dungeons.py, map_boss.py)
# draws these markers centred on their site, so spawn checks reason in real
# marker rectangles — a centre-distance rule alone lets 96px-wide ruins
# overlap at 70px apart. The GUI aliases these numbers so drawn and reserved
# areas can never drift apart.
WILD_MARKER_W = 96
WILD_MARKER_H = 30
MAP_BOSS_MARKER_W = 116
MAP_BOSS_MARKER_H = 30
EVENT_HORIZON_MARKER_W = 150
EVENT_HORIZON_MARKER_H = 30

MARKER_GAP = 6   # minimum px between the edges of two markers


def city_node_centers():
    """Return {city_id: (center_x, center_y)} for every mapped city."""
    return {
        cid: (x + NODE_W // 2, y + NODE_H // 2)
        for cid, (x, y) in CITY_POSITIONS.items()
    }


def markers_clear(ax, ay, a_w, a_h, bx, by, b_w, b_h, gap=MARKER_GAP):
    """True when two centred marker rectangles share no pixel.

    Rectangles are disjoint once their centres are a full half-width (x) or
    a full half-height (y) apart, plus *gap* between the edges.
    """
    return (abs(ax - bx) >= (a_w + b_w) // 2 + gap
            or abs(ay - by) >= (a_h + b_h) // 2 + gap)


def map_bounds(padding=30):
    """Return (x_min, y_min, x_max, y_max) of the world-map canvas content.

    Matches the GUI's region-background padding (30 px around the outermost
    city node rectangles).
    """
    xs = [x for x, _ in CITY_POSITIONS.values()]
    ys = [y for _, y in CITY_POSITIONS.values()]
    x_min = min(xs) - padding
    y_min = min(ys) - padding
    x_max = max(x + NODE_W for x, _ in CITY_POSITIONS.values()) + padding
    y_max = max(y + NODE_H for _, y in CITY_POSITIONS.values()) + padding
    return x_min, y_min, x_max, y_max
