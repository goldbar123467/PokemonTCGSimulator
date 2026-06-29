from __future__ import annotations

import argparse
import json
from pathlib import Path


LUCARIO_REFS = {
    "naoto714/mega-lucario-hop-alakazam-target-en",
    "naoto714/mega-lucario-hop-alakazam-target-ja",
}

SECONDARY_REFS = {
    "aristophanivan/multiply-agent-best-940-lb",
    "aristophanivan/probability-agent",
    "nursrijan/pok-mon-tcg-advanced-heuristic-planning-agent",
    "borealis27/elo-1150-rule-based-agent-matchup-tests",
    "kokinnwakashuu/ptcg-lucario-public-lab-anti-crustle-log",
}


def _opponent_wins(row: dict, refs: set[str]) -> int:
    return sum(int(opponent.get("wins", 0)) for opponent in row.get("opponents", []) if opponent.get("opponent") in refs)


def _covered_refs(row: dict, refs: set[str]) -> int:
    return sum(1 for opponent in row.get("opponents", []) if opponent.get("opponent") in refs and int(opponent.get("wins", 0)) > 0)


def score_row(row: dict) -> tuple[int, int, int, float, str]:
    lucario_wins = _opponent_wins(row, LUCARIO_REFS)
    secondary_wins = _opponent_wins(row, SECONDARY_REFS)
    coverage = _covered_refs(row, LUCARIO_REFS | SECONDARY_REFS)
    return (
        lucario_wins,
        secondary_wins,
        coverage,
        float(row.get("win_rate", 0.0)),
        str(row.get("candidate", "")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Select candidates that cover hard public PTCG gates.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top", type=int, default=6)
    parser.add_argument("--require-lucario-win", action="store_true")
    parser.add_argument("--require-secondary-win", action="store_true")
    args = parser.parse_args()

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    selected = []
    for row in rows:
        lucario_wins = _opponent_wins(row, LUCARIO_REFS)
        secondary_wins = _opponent_wins(row, SECONDARY_REFS)
        if args.require_lucario_win and lucario_wins <= 0:
            continue
        if args.require_secondary_win and secondary_wins <= 0:
            continue
        row = dict(row)
        row["hard_gate_score"] = {
            "lucario_wins": lucario_wins,
            "secondary_wins": secondary_wins,
            "covered_hard_refs": _covered_refs(row, LUCARIO_REFS | SECONDARY_REFS),
        }
        selected.append(row)
    selected.sort(key=score_row, reverse=True)
    selected = selected[: args.top]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    for row in selected:
        print(json.dumps({
            "candidate": row["candidate"],
            "wins": row.get("wins"),
            "finished": row.get("finished"),
            "hard_gate_score": row["hard_gate_score"],
            "main_path": row["main_path"],
            "deck_path": row["deck_path"],
        }))


if __name__ == "__main__":
    main()
