from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.historical_calibration import run_historical_calibration


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run historical benchmark calibration for known PTCG archives.")
    parser.add_argument("--registry", type=Path, default=Path("configs/archive_registry.json"))
    parser.add_argument("--config", type=Path, default=Path("configs/benchmark_league.json"))
    parser.add_argument("--gate", type=Path, default=Path("configs/benchmark_gate.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--load-only", action="store_true", help="Resolve and report pairs without launching new games.")
    parser.add_argument("--max-pairs", type=int, default=None)
    args = parser.parse_args(argv)

    report = run_historical_calibration(
        registry_path=args.registry,
        config_path=args.config,
        gate_path=args.gate,
        output_dir=args.output_dir,
        load_only=args.load_only,
        max_pairs=args.max_pairs,
        command=_command_string(),
    )
    print(
        json.dumps(
            {
                "status": report["summary"]["status"],
                "pair_status_counts": report["summary"]["pair_status_counts"],
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
