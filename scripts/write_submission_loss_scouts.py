from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.submission_loss_scouts import write_submission_loss_scouts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write per-game scout reports for a pulled Kaggle submission dataset.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--submission-id", type=int, required=True)
    parser.add_argument("--scope", default="all losses in selected submission pull")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = write_submission_loss_scouts(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        submission_id=args.submission_id,
        scope=args.scope,
        command=" ".join(sys.argv),
    )
    print(
        json.dumps(
            {
                "summary_json": str(args.output_dir / "loss_scout_summary.json"),
                "summary_md": str(args.output_dir / "loss_scout_summary.md"),
                "loss_game_count": summary["loss_game_count"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

