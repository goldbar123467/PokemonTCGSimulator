from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.teacher_evaluator import DEFAULT_SEED_GAME_LABELS
from ptcg.teacher_evaluator import write_labeled_decision_windows


def _parse_game_labels(values: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--game-label must be replay_id=label, got {value!r}")
        replay_id, label = value.split("=", 1)
        replay_id = replay_id.strip()
        label = label.strip()
        if not replay_id or not label:
            raise ValueError(f"--game-label must be replay_id=label, got {value!r}")
        labels[replay_id] = label
    return labels


def _resolve_replay_paths(replay_dir: Path, replay_ids: list[str]) -> list[Path]:
    paths: list[Path] = []
    for replay_id in replay_ids:
        replay_id = replay_id.strip()
        if not replay_id:
            continue
        exact = replay_dir / f"{replay_id}.json"
        if exact.exists():
            paths.append(exact)
            continue
        matches = sorted(replay_dir.glob(f"{replay_id}*.json"))
        if not matches:
            raise FileNotFoundError(f"replay not found for id {replay_id!r} in {replay_dir}")
        paths.append(matches[0])
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weak-teacher decision-window labels from public PTCG replays.")
    parser.add_argument("--replay-dir", type=Path, default=Path("data/Pokemon-Replays-Public"))
    parser.add_argument(
        "--replay-ids",
        default=",".join(DEFAULT_SEED_GAME_LABELS),
        help="Comma-separated replay ids. Defaults to the five seed labeled games.",
    )
    parser.add_argument(
        "--game-label",
        action="append",
        default=[],
        help="Optional replay_id=whole_game_label override. Can be repeated.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/manual_labels/teacher_decision_windows_seed.jsonl"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    replay_ids = [item.strip() for item in args.replay_ids.split(",") if item.strip()]
    game_labels = _parse_game_labels(args.game_label)
    replay_paths = _resolve_replay_paths(args.replay_dir, replay_ids)
    summary = write_labeled_decision_windows(replay_paths, args.output, game_labels=game_labels)
    summary.update(
        {
            "replay_ids": replay_ids,
            "replay_paths": [str(path) for path in replay_paths],
            "game_labels": {**DEFAULT_SEED_GAME_LABELS, **game_labels},
            "summary_path": str(args.output.with_suffix(".summary.json")),
            "legal_scope": "public local replay observations only; no hidden prize identities; no Kaggle submission",
        }
    )
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
