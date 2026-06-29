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
from ptcg.native_core import NativeCore, build_native_core
from scripts.native_official_parity_audit import native_setup_active_frame, ordered_zone_sync_summary


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
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def official_post_isfirst_frame(deck0: list[int], deck1: list[int], *, first_player: int) -> dict[str, Any]:
    started = False
    try:
        _observation, start_data = game.battle_start(deck0, deck1)
        started = True
        if not getattr(start_data, "battlePtr", None):
            raise RuntimeError(
                f"official BattleStart failed: player={int(start_data.errorPlayer)} type={int(start_data.errorType)}"
            )
        game.battle_select([first_player])
        frames = json.loads(game.visualize_data())
        if not isinstance(frames, list) or len(frames) < 2:
            raise TypeError("official VisualizeData did not return the post-IsFirst startup frame")
        frame = frames[1]
        if frame.get("select", {}).get("context") != "SetupActivePokemon":
            raise RuntimeError("official post-IsFirst frame is not a setup Active prompt")
        return frame
    finally:
        if started:
            game.battle_finish()


def comparison_status(official_summary: dict[str, Any], native_summary: dict[str, Any]) -> str:
    checks = [
        official_summary["context"] == native_summary["context"],
        official_summary["yourIndex"] == native_summary["yourIndex"],
        official_summary["players"] == native_summary["players"],
        official_summary["selector_option_card_ids"] == native_summary["selector_option_card_ids"],
        official_summary["selector_option_indexes"] == native_summary["selector_option_indexes"],
        official_summary["selector_option_serials"] == native_summary["selector_option_serials"],
        official_summary["unresolved_option_count"] == 0,
        native_summary["unresolved_option_count"] == 0,
    ]
    return "pass" if all(checks) else "fail"


def observed_setup_prompt_player(official_summary: dict[str, Any], *, first_player: int) -> int:
    raw_prompt_player = official_summary.get("yourIndex")
    if raw_prompt_player is None:
        return first_player
    prompt_player = int(raw_prompt_player)
    if prompt_player not in {0, 1}:
        raise ValueError(f"official setup prompt player must be 0 or 1, got {prompt_player}")
    return prompt_player


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start native from the official VisualizeData observed startup card order."
    )
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--first-player", type=int, choices=(0, 1), default=1)
    parser.add_argument("--build-dir", type=Path, default=Path("artifacts/native_api"))
    args = parser.parse_args(argv)

    opponent_deck = args.opponent_deck or args.deck
    deck0 = read_deck(args.deck)
    deck1 = read_deck(opponent_deck)
    official_frame = official_post_isfirst_frame(deck0, deck1, first_player=args.first_player)
    official_summary = ordered_zone_sync_summary(
        official_frame,
        source="official VisualizeData observed ordered hand/deck zones",
    )
    official_players = official_summary["players"]
    prompt_player = observed_setup_prompt_player(
        official_summary,
        first_player=args.first_player,
    )

    library_path = build_native_core(build_dir=args.build_dir)
    native_core = NativeCore(library_path)
    native_setup = native_core.start_battle_setup_from_ordered_zones(
        player0_hand_card_ids=official_players[0]["hand_card_ids"],
        player0_deck_card_ids=official_players[0]["deck_card_ids"],
        player0_hand_serials=official_players[0]["hand_serials"],
        player0_deck_serials=official_players[0]["deck_serials"],
        player1_hand_card_ids=official_players[1]["hand_card_ids"],
        player1_deck_card_ids=official_players[1]["deck_card_ids"],
        player1_hand_serials=official_players[1]["hand_serials"],
        player1_deck_serials=official_players[1]["deck_serials"],
        first_player=args.first_player,
    )
    native_frame = native_setup_active_frame(
        native_setup,
        native_core,
        acting_player=prompt_player,
        turn_action_count=2,
    )
    native_summary = ordered_zone_sync_summary(
        native_frame,
        source="native clean-room replay from official observed ordered zones",
    )
    status = comparison_status(official_summary, native_summary)

    payload = {
        "source": "native official-observed startup replay",
        "status": "observed_order_replay_match" if status == "pass" else "observed_order_replay_mismatch",
        "command": [
            sys.executable,
            "scripts/native_official_observed_startup.py",
            *(argv if argv is not None else sys.argv[1:]),
        ],
        "input_paths": {
            "deck": str(args.deck.resolve()),
            "opponent_deck": str(opponent_deck.resolve()),
        },
        "decks": {
            "player": deck_summary(args.deck, deck0),
            "opponent": deck_summary(opponent_deck, deck1),
        },
        "official": {
            "source": "official cg.VisualizeData",
            "first_player": args.first_player,
            "prompt_player": prompt_player,
            "frame": official_frame,
        },
        "native": {
            "wrapper": "clean-room C native core",
            "started_from": "official_observed_ordered_zones",
            "library": str(library_path),
            "frame": native_frame,
        },
        "comparison": {
            "status": status,
            "matched_fields": [
                "context",
                "yourIndex",
                "players",
                "selector_option_card_ids",
                "selector_option_indexes",
                "selector_option_serials",
            ],
            "official": official_summary,
            "native": native_summary,
            "note": (
                "Native can exactly replay the official observed post-IsFirst startup order. "
                "This does not prove standalone official RNG reproduction."
            ),
        },
        "kaggle_submission_made": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
