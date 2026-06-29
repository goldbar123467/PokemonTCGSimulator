from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.loss_trend_ml import write_loss_trend_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a lightweight ML trend model over Kaggle loss labels.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/ptcg_research/current/kaggle_loss_mining/dataset/decision_labels.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ptcg_research/current/kaggle_loss_mining/dataset/ml_trends"),
    )
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    report = write_loss_trend_report(input_path=args.input, output_dir=args.output_dir, seed=args.seed)
    print(
        json.dumps(
            {
                "rows": report["rows"],
                "loss_rows": report["loss_rows"],
                "balanced_accuracy": report.get("balanced_accuracy"),
                "json_report": report["paths"]["json_report"],
                "markdown_report": report["paths"]["markdown_report"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
