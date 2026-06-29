from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.top_ranked_gameplay_report import write_report_bundle


DEFAULT_LABEL_ROOT = (
    Path("artifacts")
    / "_old"
    / "2026-06-25-scratch-and-superseded"
    / "kaggle_episode_labels"
    / "2026-06-24"
)
DEFAULT_INDEX_MANIFEST = (
    Path.home()
    / ".cache"
    / "kagglehub"
    / "datasets"
    / "kaggle"
    / "pokemon-tcg-ai-battle-episodes-index"
    / "versions"
    / "9"
    / "manifest.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an agent-facing report from top-ranked June 24 PTCG gameplay.")
    parser.add_argument("--date", default="2026-06-24")
    parser.add_argument("--full-dataset-dir", type=Path, default=DEFAULT_LABEL_ROOT / "full_dataset")
    parser.add_argument("--episode-manifest", type=Path, default=DEFAULT_INDEX_MANIFEST)
    parser.add_argument("--rankings", type=Path, default=DEFAULT_LABEL_ROOT / "full_scan" / "episode_rankings_top50.json")
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABEL_ROOT / "full_scan" / "consolidated_teacher_label_batch.json",
    )
    parser.add_argument(
        "--meta-snapshot",
        type=Path,
        default=Path("artifacts") / "reports" / "top_ranked_gameplay_2026-06-24" / "meta_api_snapshot.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "reports" / "top_ranked_gameplay_2026-06-24",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = write_report_bundle(
        date=args.date,
        full_dataset_dir=args.full_dataset_dir,
        episode_manifest_path=args.episode_manifest,
        rankings_path=args.rankings,
        labels_path=args.labels,
        meta_snapshot_path=args.meta_snapshot,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
