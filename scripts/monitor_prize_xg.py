from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.prize_mapping import iter_prize_map_decisions, rank_openings, write_rankings


def run_once(args: argparse.Namespace) -> tuple[int, int]:
    decisions = list(
        iter_prize_map_decisions(
            args.replay_dir,
            max_replays=args.max_replays,
            opening_steps=args.opening_steps,
        )
    )
    rankings = rank_openings(decisions)
    write_rankings(args.output_csv, rankings[: args.top_n])
    return len(decisions), len(rankings)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor replay-derived prize maps and xG-style opening rankings."
    )
    parser.add_argument("--replay-dir", type=Path, default=Path("data/Pokemon-Replays-Public"))
    parser.add_argument("--output-csv", type=Path, default=Path("artifacts/prize_xg/opening_rankings.csv"))
    parser.add_argument("--max-replays", type=int, default=None)
    parser.add_argument("--opening-steps", type=int, default=24)
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    args = parser.parse_args()

    while True:
        started = datetime.now(timezone.utc).isoformat()
        decisions, rankings = run_once(args)
        print(
            "heartbeat "
            f"utc={started} decisions={decisions} ranked_openings={rankings} "
            f"output={args.output_csv}",
            flush=True,
        )
        if args.interval_seconds <= 0:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
