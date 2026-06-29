from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.chain_library import write_chain_library


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build turn-chain strategy labels from Kaggle decision labels.")
    parser.add_argument("--decision-labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-run-report", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = write_chain_library(
        decision_labels_path=args.decision_labels,
        output_dir=args.output_dir,
        source_run_report_path=args.source_run_report,
        command=" ".join(sys.argv),
    )
    print(
        json.dumps(
            {
                "chain_library_jsonl": report["paths"]["chain_library_jsonl"],
                "chain_library_report_json": report["paths"]["chain_library_report_json"],
                "total_chains": report["total_chains"],
                "total_decisions": report["total_decisions"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
