from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.benchmark_league import run_benchmark_league
from ptcg.seed_schedule import parse_seed_list


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a fixed-opponent, seed-scheduled PTCG benchmark league.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", default=None, help="Optional comma-separated seed list overriding config seed_list.")
    parser.add_argument("--target-games-per-matchup", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    report = run_benchmark_league(
        archive=args.archive,
        config_path=args.config,
        output_dir=args.output_dir,
        explicit_seeds=parse_seed_list(args.seeds) if args.seeds is not None else None,
        target_games_per_matchup=args.target_games_per_matchup,
        resume=args.resume,
        command=_command_string(),
    )
    print(
        json.dumps(
            {
                "status": report["summary"]["status"],
                "scheduled_games": report["summary"]["scheduled_games"],
                "available_opponent_count": report["summary"]["available_opponent_count"],
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
