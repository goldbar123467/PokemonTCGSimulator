from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_eval import trace_native_agent_vs_agent


def _load_opponent(manifest_path: Path, ref: str) -> dict:
    rows = [row for row in json.loads(manifest_path.read_text(encoding="utf-8")) if row.get("ok")]
    for row in rows:
        if row["ref"] == ref:
            return row
    raise ValueError(f"opponent not found or not ok: {ref}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace candidate turns against one public PTCG opponent.")
    parser.add_argument("--candidate-main", type=Path, required=True)
    parser.add_argument("--candidate-deck", type=Path, required=True)
    parser.add_argument("--opponents-manifest", type=Path, default=Path("artifacts/public_code/opponents_manifest.json"))
    parser.add_argument("--opponent-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-trace-steps", type=int, default=80)
    args = parser.parse_args()

    opponent = _load_opponent(args.opponents_manifest, args.opponent_ref)
    result = trace_native_agent_vs_agent(
        candidate_main_path=args.candidate_main,
        candidate_deck_path=args.candidate_deck,
        opponent_main_path=Path(opponent["main_path"]),
        opponent_deck_path=Path(opponent["deck_path"]),
        games=args.games,
        seed=args.seed,
        max_trace_steps_per_game=args.max_trace_steps,
    )
    row = {
        "opponent": opponent["ref"],
        "candidate_main": str(args.candidate_main),
        "candidate_deck": str(args.candidate_deck),
        "games": result.games,
        "finished": result.finished,
        "wins": result.wins,
        "losses": result.losses,
        "draws": result.draws,
        "errors": list(result.errors),
        "traces": list(result.traces),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: row[key] for key in ("opponent", "games", "finished", "wins", "losses", "draws", "errors")}))


if __name__ == "__main__":
    main()
