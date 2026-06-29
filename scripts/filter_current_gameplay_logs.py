from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.gameplay_log_hygiene import write_current_log_allowlist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the current valid gameplay replay list from a manifest.")
    parser.add_argument("--manifest", type=Path, default=Path("data_manifest/gameplay_logs.json"))
    parser.add_argument("--output", type=Path, default=Path("data_manifest/current_gameplay_logs.txt"))
    args = parser.parse_args(argv)

    current_logs = write_current_log_allowlist(manifest_path=args.manifest, allowlist_path=args.output)
    print(
        json.dumps(
            {
                "manifest": str(args.manifest),
                "output": str(args.output),
                "current_log_count": len(current_logs),
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )
    return 0 if current_logs else 1


if __name__ == "__main__":
    raise SystemExit(main())
