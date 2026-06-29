from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.official import game


def read_deck(path: Path) -> list[int]:
    cards = [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cards) != 60:
        raise ValueError(f"deck must contain 60 cards: {path} has {len(cards)}")
    return cards


def deck_summary(path: Path, cards: list[int]) -> dict[str, Any]:
    canonical = "".join(f"{card_id}\n" for card_id in cards).encode("ascii")
    return {
        "path": str(path.resolve()),
        "count": len(cards),
        "sha256": hashlib.sha256(canonical).hexdigest().upper(),
    }


def parse_select(raw: str) -> list[int]:
    if raw.strip() == "":
        return []
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit official cg.VisualizeData frames for deck.csv battle startup.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--select", action="append", default=[], help="Comma-separated option indexes to apply.")
    parser.add_argument("--max-frames", type=int, default=8)
    args = parser.parse_args(argv)

    deck0 = read_deck(args.deck)
    opponent_deck_path = args.opponent_deck or args.deck
    deck1 = read_deck(opponent_deck_path)
    started = False
    try:
        observation, start_data = game.battle_start(deck0, deck1)
        started = True
        for raw_select in args.select:
            observation = game.battle_select(parse_select(raw_select))
        frames = json.loads(game.visualize_data())
        if not isinstance(frames, list):
            raise TypeError("official VisualizeData did not return a JSON list")
        max_frames = max(1, args.max_frames)
        payload = {
            "source": "official cg.VisualizeData",
            "decks": {
                "player": deck_summary(args.deck, deck0),
                "opponent": deck_summary(opponent_deck_path, deck1),
            },
            "start_data": {
                "battle_ptr_present": bool(getattr(start_data, "battlePtr", None)),
                "error_player": int(start_data.errorPlayer),
                "error_type": int(start_data.errorType),
            },
            "observation": observation,
            "visualizer": {
                "frame_count": len(frames),
                "frames": frames[:max_frames],
                "truncated": len(frames) > max_frames,
            },
            "kaggle_submission_made": False,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    finally:
        if started:
            game.battle_finish()


if __name__ == "__main__":
    raise SystemExit(main())
