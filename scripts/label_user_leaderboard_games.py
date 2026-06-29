from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.leaderboard_breakdown import build_label_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Hard-label user-supplied leaderboard PTCG games.")
    parser.add_argument("--replays", nargs="+", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--focus-team", default=None)
    parser.add_argument("--meta-json", type=Path, default=None)
    args = parser.parse_args()

    meta_snapshot = {}
    if args.meta_json is not None and args.meta_json.exists():
        meta_snapshot = json.loads(args.meta_json.read_text(encoding="utf-8-sig"))

    result = build_label_dataset(
        args.replays,
        output_dir=args.output_dir,
        focus_team=args.focus_team,
        meta_snapshot=meta_snapshot,
        command=" ".join(sys.argv),
    )
    print(
        json.dumps(
            {
                "focus_team": result["focus_team"],
                "summary": result["summary"],
                "paths": result["paths"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
