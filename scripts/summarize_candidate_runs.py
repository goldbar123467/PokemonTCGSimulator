from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_summary(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        row["source"] = str(path)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize best PTCG candidate gauntlet runs.")
    parser.add_argument("--summary", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows: list[dict] = []
    for path in args.summary:
        rows.extend(_load_summary(path))
    rows.sort(key=lambda row: (-float(row.get("win_rate", 0.0)), -int(row.get("finished", 0)), row.get("candidate", "")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    for row in rows[:10]:
        print(json.dumps({key: row.get(key) for key in ("candidate", "family", "wins", "finished", "win_rate", "source")}))


if __name__ == "__main__":
    main()
