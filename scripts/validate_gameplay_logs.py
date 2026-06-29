from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.gameplay_log_hygiene import DEFAULT_CURRENT_MIN_DATE, build_manifest, validate_manifest, write_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate the gameplay log manifest.")
    parser.add_argument("--root", action="append", type=Path, default=[Path("data/kaggle_public_leaderboard")])
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--current-min-date", default=DEFAULT_CURRENT_MIN_DATE)
    parser.add_argument("--output", type=Path, default=Path("data_manifest/gameplay_logs.json"))
    args = parser.parse_args(argv)

    manifest = build_manifest(
        roots=args.root,
        project_root=args.project_root,
        current_min_date=args.current_min_date,
    )
    validation = validate_manifest(manifest)
    manifest["validation"] = validation
    write_manifest(args.output, manifest)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": manifest["summary"],
                "validation": validation,
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )
    return 0 if validation["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
