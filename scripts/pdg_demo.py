"""Generate and print one PDG floor — the offline demo map.

Usage:
    python scripts/pdg_demo.py
    python scripts/pdg_demo.py --seed 1234 --floor 5
    python scripts/pdg_demo.py --wild 0        # city-sized budget instead

The in-game demo is a temperate wild ruin (see scripts/spawn_pdg_demo.py).
This script is for looking at the generator and invariants without launching
the GUI.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pandemonium.world.dungeon_graph import (  # noqa: E402
    generate_graph,
    render_map,
    summarize_graph,
    validate_graph,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed (default: random)")
    parser.add_argument("--floor", type=int, default=1,
                        help="content/scaling floor for enemy rooms")
    parser.add_argument("--index", type=int, default=None,
                        help="display floor index used for the spine budget")
    parser.add_argument("--wild", type=int, choices=(0, 1), default=1,
                        help="1 = wild scale (10-14 nodes), 0 = city scale")
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else random.randint(1, 999999)
    floor_index = args.index if args.index is not None else args.floor

    try:
        graph = generate_graph(
            args.floor,
            profile_id="temperate",
            region="temperate",
            wild=bool(args.wild),
            seed=seed,
            floor_index=floor_index,
        )
    except Exception as exc:
        print(f"generation failed (seed {seed}): {exc}")
        return 1

    summary = summarize_graph(graph)
    print(f"seed={seed} floor={args.floor} index={floor_index} "
          f"wild={bool(args.wild)}")
    print(f"profile={graph.get('profile')} nodes={summary['nodes']} "
          f"edges={summary['edges']} spine={summary['spine']} "
          f"shortest={summary['shortest_edges']} edges "
          f"(~{summary['route_blocks']} blocks)")
    print(f"node mix: {summary['types']}")
    print(f"invariants: {'OK' if validate_graph(graph) else 'FAILED'}")
    print()
    print(render_map(graph, force_reveal=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
