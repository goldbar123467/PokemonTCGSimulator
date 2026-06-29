from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_eval import smoke_native_agent_vs_random


def main() -> None:
    parser = argparse.ArgumentParser(description="Run native cg simulator smoke games for public agents.")
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/public_code/opponents_manifest.json"))
    parser.add_argument("--sdk-path", type=Path, default=Path("data/official"))
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("artifacts/public_code/native_smoke_results.json"))
    args = parser.parse_args()

    entries = [
        entry
        for entry in json.loads(args.manifest.read_text(encoding="utf-8"))
        if entry.get("ok")
    ]
    results = []
    for entry in entries:
        result = smoke_native_agent_vs_random(
            main_path=Path(entry["main_path"]),
            deck_path=Path(entry["deck_path"]),
            sdk_path=args.sdk_path,
            games=args.games,
        )
        row = {
            "ref": entry["ref"],
            "games": result.games,
            "finished": result.finished,
            "wins_vs_random": result.wins,
            "losses_vs_random": result.losses,
            "draws_vs_random": result.draws,
            "errors": list(result.errors),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote={args.output}")


if __name__ == "__main__":
    main()
