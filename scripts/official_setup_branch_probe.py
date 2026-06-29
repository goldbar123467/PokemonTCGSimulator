from __future__ import annotations

import argparse
from collections import Counter
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


def _frame_summary(frame: dict[str, Any]) -> dict[str, Any]:
    current = frame.get("current", {})
    players = current.get("players") or []
    return {
        "context": frame.get("select", {}).get("context"),
        "type": frame.get("select", {}).get("type"),
        "option_count": len(frame.get("select", {}).get("option") or []),
        "turn": current.get("turn"),
        "turnActionCount": current.get("turnActionCount"),
        "yourIndex": current.get("yourIndex"),
        "players": [
            {
                "deckCount": player.get("deckCount"),
                "handCount": player.get("handCount"),
                "prizeCount": len(player.get("prize") or []),
                "activeCount": len(player.get("active") or []),
                "benchCount": len(player.get("bench") or []),
            }
            for player in players
        ],
    }


def _truncated_frames(frames: list[dict[str, Any]], max_frames: int) -> dict[str, Any]:
    limit = max(1, max_frames)
    return {
        "frame_count": len(frames),
        "frames": frames[:limit],
        "truncated": len(frames) > limit,
    }


def _select_first_setup_path(first_player: int, active_choice: int, next_active_choice: int) -> list[dict[str, Any]]:
    game.battle_select([first_player])
    game.battle_select([active_choice])
    game.battle_select([next_active_choice])
    frames = json.loads(game.visualize_data())
    if not isinstance(frames, list):
        raise TypeError("official VisualizeData did not return a JSON list")
    return frames


def probe_setup_branches(
    deck0: list[int],
    deck1: list[int],
    *,
    attempts: int = 80,
    first_player: int = 1,
    active_choice: int = 0,
    next_active_choice: int = 0,
    draw_count_choice: int = 0,
    max_frames: int = 6,
) -> dict[str, Any]:
    branch_counts: Counter[str] = Counter()
    examples: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for attempt in range(1, max(1, attempts) + 1):
        started = False
        try:
            _observation, start_data = game.battle_start(deck0, deck1)
            started = True
            if not getattr(start_data, "battlePtr", None):
                branch_counts["start_error"] += 1
                continue
            frames = _select_first_setup_path(first_player, active_choice, next_active_choice)
            fourth_frame = frames[3] if len(frames) > 3 else {}
            context = fourth_frame.get("select", {}).get("context") or "missing_fourth_frame"
            branch_counts[str(context)] += 1
            if context not in examples:
                example: dict[str, Any] = {
                    "attempt": attempt,
                    "fourth_frame_summary": _frame_summary(fourth_frame),
                    "fourth_frame": fourth_frame,
                    "frames": _truncated_frames(frames, max_frames),
                }
                if context == "DrawCount":
                    options = fourth_frame.get("select", {}).get("option") or []
                    allowed_numbers = [option.get("number") for option in options if "number" in option]
                    selected_number = draw_count_choice if draw_count_choice in allowed_numbers else allowed_numbers[0]
                    game.battle_select([int(selected_number)])
                    after_frames = json.loads(game.visualize_data())
                    if not isinstance(after_frames, list):
                        raise TypeError("official VisualizeData did not return a JSON list after DrawCount")
                    example["draw_count_choice"] = int(selected_number)
                    example["after_draw_count"] = _truncated_frames(after_frames, max_frames)
                    example["after_draw_count_last_frame_summary"] = _frame_summary(after_frames[-1])
                examples[str(context)] = example
        except Exception as exc:  # pragma: no cover - kept in payload for live cg.dll diagnostics.
            branch_counts["error"] += 1
            if len(errors) < 5:
                errors.append({"attempt": attempt, "type": type(exc).__name__, "message": str(exc)})
        finally:
            if started:
                try:
                    game.battle_finish()
                except Exception:
                    pass
    for key in ("DrawCount", "SetupBenchPokemon", "Main"):
        branch_counts.setdefault(key, 0)
    return {
        "attempts": max(1, attempts),
        "first_player": first_player,
        "active_choice": active_choice,
        "next_active_choice": next_active_choice,
        "draw_count_choice": draw_count_choice,
        "branch_counts": dict(sorted(branch_counts.items())),
        "examples": examples,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe official cg.dll setup branch contexts after Active choices.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--attempts", type=int, default=80)
    parser.add_argument("--first-player", type=int, choices=(0, 1), default=1)
    parser.add_argument("--active-choice", type=int, default=0)
    parser.add_argument("--next-active-choice", type=int, default=0)
    parser.add_argument("--draw-count-choice", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=6)
    args = parser.parse_args(argv)

    opponent_deck_path = args.opponent_deck or args.deck
    deck0 = read_deck(args.deck)
    deck1 = read_deck(opponent_deck_path)
    payload = {
        "source": "official cg setup branch probe",
        "decks": {
            "player": deck_summary(args.deck, deck0),
            "opponent": deck_summary(opponent_deck_path, deck1),
        },
        **probe_setup_branches(
            deck0,
            deck1,
            attempts=args.attempts,
            first_player=args.first_player,
            active_choice=args.active_choice,
            next_active_choice=args.next_active_choice,
            draw_count_choice=args.draw_count_choice,
            max_frames=args.max_frames,
        ),
        "kaggle_submission_made": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
