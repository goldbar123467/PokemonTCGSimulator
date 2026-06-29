from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.benchmark_comparison import compare_candidate_archives


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a candidate PTCG archive against a baseline benchmark gate.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/benchmark_league.json"))
    parser.add_argument("--gate-config", type=Path, default=Path("configs/benchmark_gate.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-results-dir", type=Path)
    parser.add_argument("--baseline-results-dir", type=Path)
    parser.add_argument("--index-path", type=Path, default=Path("artifacts/benchmark_lab/benchmark_index.json"))
    parser.add_argument("--champion-registry", type=Path, default=Path("configs/champion_registry.json"))
    args = parser.parse_args(argv)

    report = compare_candidate_archives(
        candidate_archive=args.candidate,
        baseline_archive=args.baseline,
        benchmark_config_path=args.config,
        gate_config_path=args.gate_config,
        output_dir=args.output_dir,
        candidate_results_dir=args.candidate_results_dir,
        baseline_results_dir=args.baseline_results_dir,
        index_path=args.index_path,
        champion_registry_path=args.champion_registry,
        command=_command_string(),
    )
    print(
        json.dumps(
            {
                "decision": report["decision"]["status"],
                "report_paths": report["report_paths"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _command_string() -> str:
    return " ".join(shlex.quote(part) for part in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
