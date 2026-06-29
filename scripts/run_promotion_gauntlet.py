from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_eval import smoke_native_agent_vs_agent
from ptcg.internal_leaderboard import HARD_GATE_ARCHETYPES, normalize_archetype, rank_candidates


def _load_top_candidates(tuning_results: Path, limit: int) -> list[dict]:
    rows = json.loads(tuning_results.read_text(encoding="utf-8"))
    rows.sort(key=lambda row: (-float(row.get("win_rate", 0.0)), int(row.get("finished", 0)), row.get("candidate", "")))
    return rows[:limit]


def _load_public_opponents(manifest: Path) -> list[dict]:
    return [row for row in json.loads(manifest.read_text(encoding="utf-8")) if row.get("ok")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a larger gauntlet for tuned PTCG candidate promotion.")
    parser.add_argument("--tuning-results", type=Path, default=Path("artifacts/candidates/tuned_wide/tuning_results.json"))
    parser.add_argument("--opponents-manifest", type=Path, default=Path("artifacts/public_meta/opponents_manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/candidates/tuned_wide/promotion_gauntlet.json"))
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--seed", type=int, default=4001)
    args = parser.parse_args()

    candidates = _load_top_candidates(args.tuning_results, args.top)
    opponents = _load_public_opponents(args.opponents_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for candidate_index, candidate in enumerate(candidates):
        candidate_row = {
            "candidate": candidate["candidate"],
            "family": candidate.get("family"),
            "main_path": candidate["main_path"],
            "deck_path": candidate["deck_path"],
            "wins": 0,
            "finished": 0,
            "losses": 0,
            "draws": 0,
            "errors": [],
            "opponents": [],
        }
        print(f"candidate={candidate['candidate']}")
        for opponent_index, opponent in enumerate(opponents):
            result = smoke_native_agent_vs_agent(
                candidate_main_path=Path(candidate["main_path"]),
                candidate_deck_path=Path(candidate["deck_path"]),
                opponent_main_path=Path(opponent["main_path"]),
                opponent_deck_path=Path(opponent["deck_path"]),
                games=args.games,
                seed=args.seed + candidate_index * 1000 + opponent_index,
            )
            opponent_row = {
                "opponent": opponent["ref"],
                "archetype": normalize_archetype(opponent.get("archetype")),
                "gate_weight": float(opponent.get("raw_weight") or 1.0),
                "hard_gate": normalize_archetype(opponent.get("archetype")) in HARD_GATE_ARCHETYPES,
                "wins": result.wins,
                "finished": result.finished,
                "losses": result.losses,
                "draws": result.draws,
                "errors": list(result.errors),
                "win_rate": result.wins / result.finished if result.finished else 0.0,
            }
            candidate_row["wins"] += result.wins
            candidate_row["finished"] += result.finished
            candidate_row["losses"] += result.losses
            candidate_row["draws"] += result.draws
            candidate_row["errors"].extend(result.errors)
            candidate_row["opponents"].append(opponent_row)
            print(json.dumps({"candidate": candidate["candidate"], **opponent_row}))
        candidate_row["win_rate"] = candidate_row["wins"] / candidate_row["finished"] if candidate_row["finished"] else 0.0
        rows.append(candidate_row)

    matchup_rows = [
        {
            "candidate": row["candidate"],
            "gate_ref": opponent["opponent"],
            "archetype": opponent["archetype"],
            "wins": opponent["wins"],
            "finished": opponent["finished"],
            "losses": opponent["losses"],
            "draws": opponent["draws"],
            "errors": opponent["errors"],
            "gate_weight": opponent["gate_weight"],
            "hard_gate": opponent["hard_gate"],
        }
        for row in rows
        for opponent in row["opponents"]
    ]
    ranked = rank_candidates(
        [{"name": row["candidate"], "eligible_for_benchmark": True} for row in rows],
        matchup_rows,
    )
    score_by_candidate = {row["candidate"]: row for row in ranked}
    for row in rows:
        score = score_by_candidate.get(row["candidate"], {})
        row["leaderboard_score"] = score.get("leaderboard_score", row["win_rate"])
        row["weighted_win_rate"] = score.get("weighted_win_rate", row["win_rate"])
        row["hard_gate_collapses"] = score.get("hard_gate_collapses", [])
        row["promotable"] = score.get("promotable", False)

    rows.sort(key=lambda row: (-row["leaderboard_score"], len(row["hard_gate_collapses"]), len(row["errors"]), row["candidate"]))
    args.output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    summary_path = args.output.with_name(args.output.stem + "_summary.json")
    summary = [
        {
            "candidate": row["candidate"],
            "family": row["family"],
            "wins": row["wins"],
            "finished": row["finished"],
            "win_rate": row["win_rate"],
            "weighted_win_rate": row["weighted_win_rate"],
            "leaderboard_score": row["leaderboard_score"],
            "hard_gate_collapses": row["hard_gate_collapses"],
            "promotable": row["promotable"],
            "errors": len(row["errors"]),
            "main_path": row["main_path"],
            "deck_path": row["deck_path"],
        }
        for row in rows
    ]
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("SUMMARY")
    for row in summary:
        print(json.dumps(row))


if __name__ == "__main__":
    main()
