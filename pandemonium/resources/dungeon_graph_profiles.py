"""Data-driven dungeon graph profiles (docs/dungeon_graph_design.md §5).

Only the temperate profile is wired up for the PDG demo. The ``wild`` block
is merged over the base profile when a wild ruin runs a graph floor, matching
the locked smaller wild scale (N_cap = 14, spine 5-7).

Keep this module data-only: no combat, world, or GUI imports.
"""

TEMPERATE_PROFILE = {
    "id": "temperate",
    "name": "Open Roads",
    "traversal": "undirected",
    "entry_side": "left",
    # Base (city-floor) budget — docs §5.1.
    "spine_min": 8,
    "spine_max": 10,
    "branch_factor": 0.7,
    "node_min": 12,
    "node_cap": 20,
    # Local tuning.
    "loop_chance": 0.16,
    "toward_boss": 0.72,
    "connector_ratio": 0.30,
    "edge_cost": 0.5,
    "node_cost": 0.5,
    "fountain_min": 1,
    "merchant_min": 1,
    # Wild ruins adopt PDG at a smaller scale (docs §14.1 decision 9).
    "wild": {
        "spine_min": 5,
        "spine_max": 7,
        "branch_factor": 0.6,
        "node_min": 10,
        "node_cap": 14,
        "connector_ratio": 0.35,
    },
}

PROFILES = {
    TEMPERATE_PROFILE["id"]: TEMPERATE_PROFILE,
}

DEFAULT_PROFILE_ID = TEMPERATE_PROFILE["id"]


def get_profile(profile_id=None, wild=False):
    """Return a profile dict, optionally merged with its wild overrides.

    Unknown ids fall back to the temperate profile so a corrupt save can
    never block a run.
    """
    base = PROFILES.get(profile_id or DEFAULT_PROFILE_ID, TEMPERATE_PROFILE)
    profile = dict(base)
    if wild:
        profile.update(base.get("wild") or {})
        profile["wild"] = True
    else:
        profile["wild"] = False
    return profile
