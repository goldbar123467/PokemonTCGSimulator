from __future__ import annotations

import argparse
import json
from pathlib import Path


def _score_opponents(gauntlet_rows: list[dict]) -> list[dict]:
    scored: dict[str, dict] = {}
    for candidate in gauntlet_rows:
        for opponent in candidate.get("opponents", []):
            ref = opponent["opponent"]
            row = scored.setdefault(
                ref,
                {
                    "opponent": ref,
                    "wins": 0,
                    "finished": 0,
                    "losses": 0,
                    "draws": 0,
                    "candidate_results": [],
                },
            )
            row["wins"] += int(opponent.get("wins", 0))
            row["finished"] += int(opponent.get("finished", 0))
            row["losses"] += int(opponent.get("losses", 0))
            row["draws"] += int(opponent.get("draws", 0))
            row["candidate_results"].append(
                {
                    "candidate": candidate.get("candidate"),
                    "wins": opponent.get("wins", 0),
                    "finished": opponent.get("finished", 0),
                    "win_rate": opponent.get("win_rate", 0.0),
                }
            )
    rows = list(scored.values())
    for row in rows:
        row["win_rate"] = row["wins"] / row["finished"] if row["finished"] else 0.0
    rows.sort(key=lambda row: (row["win_rate"], -row["finished"], row["opponent"]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Select worst public opponents from a promotion gauntlet.")
    parser.add_argument("--gauntlet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    rows = _score_opponents(json.loads(args.gauntlet.read_text(encoding="utf-8")))
    focused = rows[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(focused, indent=2) + "\n", encoding="utf-8")
    for row in focused:
        print(json.dumps({k: row[k] for k in ("opponent", "wins", "finished", "win_rate")}))


if __name__ == "__main__":
    main()
