from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    candidate: str
    family: str | None
    source: str
    main_path: str
    deck_path: str
    wins: int
    finished: int
    losses: int
    draws: int
    errors: int
    leaderboard_score: float | None
    weighted_win_rate: float | None
    hard_gate_collapses: int
    promotable: bool
    opponents: tuple[dict, ...]

    @property
    def win_rate(self) -> float:
        return self.wins / self.finished if self.finished else 0.0


def _candidate_id(source: Path, row: dict) -> str:
    main_path = str(row.get("main_path", "")).replace("\\", "/")
    deck_path = str(row.get("deck_path", "")).replace("\\", "/")
    return f"{source.parent.name}:{row.get('candidate', '')}:{main_path}:{deck_path}"


def load_gauntlets(paths: list[Path]) -> list[CandidateScore]:
    candidates: list[CandidateScore] = []
    seen: set[str] = set()
    for path in paths:
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            candidate_id = _candidate_id(path, row)
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            candidates.append(
                CandidateScore(
                    candidate_id=candidate_id,
                    candidate=str(row.get("candidate", "")),
                    family=row.get("family"),
                    source=str(path),
                    main_path=str(row.get("main_path", "")),
                    deck_path=str(row.get("deck_path", "")),
                    wins=int(row.get("wins", 0)),
                    finished=int(row.get("finished", 0)),
                    losses=int(row.get("losses", 0)),
                    draws=int(row.get("draws", 0)),
                    errors=len(row.get("errors", [])),
                    leaderboard_score=(
                        float(row["leaderboard_score"]) if row.get("leaderboard_score") is not None else None
                    ),
                    weighted_win_rate=(
                        float(row["weighted_win_rate"]) if row.get("weighted_win_rate") is not None else None
                    ),
                    hard_gate_collapses=len(row.get("hard_gate_collapses") or []),
                    promotable=bool(row.get("promotable", False)),
                    opponents=tuple(row.get("opponents", [])),
                )
            )
    return candidates


def _score_tuple(opponent_row: dict) -> tuple[float, int, int]:
    finished = int(opponent_row.get("finished", 0))
    wins = int(opponent_row.get("wins", 0))
    win_rate = wins / finished if finished else 0.0
    return (win_rate, wins, finished)


def summarize(candidates: list[CandidateScore], top_k: int) -> dict:
    by_opponent: dict[str, list[dict]] = {}
    for candidate in candidates:
        for opponent in candidate.opponents:
            ref = str(opponent.get("opponent", ""))
            by_opponent.setdefault(ref, []).append(
                {
                    "candidate_id": candidate.candidate_id,
                    "candidate": candidate.candidate,
                    "family": candidate.family,
                    "source": candidate.source,
                    "main_path": candidate.main_path,
                    "deck_path": candidate.deck_path,
                    "wins": int(opponent.get("wins", 0)),
                    "finished": int(opponent.get("finished", 0)),
                    "losses": int(opponent.get("losses", 0)),
                    "draws": int(opponent.get("draws", 0)),
                    "errors": len(opponent.get("errors", [])),
                    "win_rate": _score_tuple(opponent)[0],
                }
            )

    best_by_opponent = []
    for opponent, rows in sorted(by_opponent.items()):
        rows.sort(key=lambda row: (-row["win_rate"], -row["wins"], row["errors"], row["source"], row["candidate"]))
        best = rows[0]
        best_by_opponent.append({"opponent": opponent, **best})

    candidate_rows = [
        {
            "candidate_id": candidate.candidate_id,
            "candidate": candidate.candidate,
            "family": candidate.family,
            "source": candidate.source,
            "main_path": candidate.main_path,
            "deck_path": candidate.deck_path,
            "wins": candidate.wins,
            "finished": candidate.finished,
            "losses": candidate.losses,
            "draws": candidate.draws,
            "errors": candidate.errors,
            "win_rate": candidate.win_rate,
            "weighted_win_rate": candidate.weighted_win_rate,
            "leaderboard_score": candidate.leaderboard_score,
            "hard_gate_collapses": candidate.hard_gate_collapses,
            "promotable": candidate.promotable,
        }
        for candidate in candidates
    ]
    candidate_rows.sort(
        key=lambda row: (
            -(row["leaderboard_score"] if row["leaderboard_score"] is not None else row["win_rate"]),
            row["hard_gate_collapses"],
            row["errors"],
            row["source"],
            row["candidate"],
        )
    )

    selected: list[CandidateScore] = []
    remaining = list(candidates)
    for _ in range(top_k):
        best_candidate: CandidateScore | None = None
        best_value: tuple[float, int, float, str] | None = None
        for candidate in remaining:
            value = _portfolio_value([*selected, candidate], by_opponent)
            tie = (value[0], value[1], candidate.win_rate, candidate.candidate_id)
            if best_value is None or tie > best_value:
                best_value = tie
                best_candidate = candidate
        if best_candidate is None:
            break
        selected.append(best_candidate)
        remaining = [candidate for candidate in remaining if candidate.candidate_id != best_candidate.candidate_id]

    portfolio = _portfolio_rows(selected, by_opponent)
    hard_opponents = sorted(best_by_opponent, key=lambda row: (row["win_rate"], row["wins"], row["opponent"]))

    return {
        "candidate_count": len(candidates),
        "opponent_count": len(by_opponent),
        "top_candidates": candidate_rows[:20],
        "best_by_opponent": best_by_opponent,
        "hard_opponents": hard_opponents,
        "greedy_portfolio": {
            "selected": [
                {
                    "candidate_id": candidate.candidate_id,
                    "candidate": candidate.candidate,
                    "family": candidate.family,
                    "source": candidate.source,
                    "main_path": candidate.main_path,
                    "deck_path": candidate.deck_path,
                    "wins": candidate.wins,
                    "finished": candidate.finished,
                    "win_rate": candidate.win_rate,
                    "weighted_win_rate": candidate.weighted_win_rate,
                    "leaderboard_score": candidate.leaderboard_score,
                    "hard_gate_collapses": candidate.hard_gate_collapses,
                    "promotable": candidate.promotable,
                    "errors": candidate.errors,
                }
                for candidate in selected
            ],
            "opponents": portfolio,
            "aggregate": {
                "best_wins": sum(row["wins"] for row in portfolio),
                "best_finished": sum(row["finished"] for row in portfolio),
                "best_win_rate": (
                    sum(row["wins"] for row in portfolio) / sum(row["finished"] for row in portfolio)
                    if sum(row["finished"] for row in portfolio)
                    else 0.0
                ),
            },
        },
    }


def _portfolio_value(selected: list[CandidateScore], by_opponent: dict[str, list[dict]]) -> tuple[float, int]:
    selected_ids = {candidate.candidate_id for candidate in selected}
    rate_sum = 0.0
    wins_sum = 0
    for rows in by_opponent.values():
        eligible = [row for row in rows if row["candidate_id"] in selected_ids]
        if not eligible:
            continue
        best = max(eligible, key=lambda row: (row["win_rate"], row["wins"], -row["errors"]))
        rate_sum += float(best["win_rate"])
        wins_sum += int(best["wins"])
    return rate_sum, wins_sum


def _portfolio_rows(selected: list[CandidateScore], by_opponent: dict[str, list[dict]]) -> list[dict]:
    selected_ids = {candidate.candidate_id for candidate in selected}
    rows_out = []
    for opponent, rows in sorted(by_opponent.items()):
        eligible = [row for row in rows if row["candidate_id"] in selected_ids]
        if not eligible:
            continue
        best = max(eligible, key=lambda row: (row["win_rate"], row["wins"], -row["errors"]))
        rows_out.append({"opponent": opponent, **best})
    return rows_out


def _default_gauntlets(root: Path) -> list[Path]:
    return sorted(root.glob("artifacts/candidates/**/promotion_gauntlet.json"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize PTCG candidate public-agent coverage.")
    parser.add_argument("--gauntlet", action="append", type=Path, dest="gauntlets")
    parser.add_argument("--output", type=Path, default=Path("artifacts/candidates/coverage_summary.json"))
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    paths = args.gauntlets or _default_gauntlets(Path("."))
    if not paths:
        raise SystemExit("No promotion_gauntlet.json files found.")

    candidates = load_gauntlets(paths)
    summary = summarize(candidates, args.top_k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "candidate_count": summary["candidate_count"],
        "opponent_count": summary["opponent_count"],
        "output": str(args.output),
        "portfolio": summary["greedy_portfolio"]["aggregate"],
    }))
    print("SELECTED")
    for row in summary["greedy_portfolio"]["selected"]:
        print(json.dumps(row))
    print("HARDEST")
    for row in summary["hard_opponents"][:8]:
        print(json.dumps({
            "opponent": row["opponent"],
            "candidate": row["candidate"],
            "source": row["source"],
            "wins": row["wins"],
            "finished": row["finished"],
            "win_rate": row["win_rate"],
        }))


if __name__ == "__main__":
    main()
