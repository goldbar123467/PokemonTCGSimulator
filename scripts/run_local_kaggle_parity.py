from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.local_kaggle_parity import LocalKaggleParityError, run_local_kaggle_parity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a strict local Kaggle parity check for one PTCG archive.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--smoke-games", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--sdk-path", type=Path, default=Path("data/official"))
    parser.add_argument("--max-steps", type=int, default=1000)
    args = parser.parse_args(argv)
    try:
        report = run_local_kaggle_parity(
            archive=args.archive,
            output_dir=args.output_dir,
            smoke_games=args.smoke_games,
            seed=args.seed,
            sdk_path=args.sdk_path,
            max_steps=args.max_steps,
            command=_command_string(),
        )
        print(json.dumps({"status": report["summary"]["status"], "report_paths": report["report_paths"]}, sort_keys=True))
        return 0
    except LocalKaggleParityError as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "output_dir": str(args.output_dir)}, sort_keys=True), file=sys.stderr)
        return 1


def _command_string() -> str:
    return " ".join(shlex.quote(part) for part in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
