from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.official import game
from ptcg.native_core import NativeCore, build_native_core


OFFICIAL_LIB_PATH = ROOT / "data" / "official" / "cg" / "libcg.so"


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


def zone_ids(player: dict[str, Any], zone: str) -> list[int]:
    values = player.get(zone) or []
    return [int(card["id"]) for card in values if isinstance(card, dict) and "id" in card]


def official_startup_order(deck0: list[int], deck1: list[int], *, first_player: int) -> dict[str, Any]:
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
        players = frame.get("current", {}).get("players") or []
        if len(players) != 2:
            raise TypeError("official post-IsFirst frame did not contain two players")
        return {
            "p0_hand": zone_ids(players[0], "hand"),
            "p0_deck": zone_ids(players[0], "deck"),
            "p1_hand": zone_ids(players[1], "hand"),
            "p1_deck": zone_ids(players[1], "deck"),
            "p0_deck_count": int(players[0].get("deckCount", -1)),
            "p1_deck_count": int(players[1].get("deckCount", -1)),
            "p0_hand_count": int(players[0].get("handCount", -1)),
            "p1_hand_count": int(players[1].get("handCount", -1)),
        }
    finally:
        if started:
            game.battle_finish()


def order_key(order: dict[str, Any]) -> tuple[tuple[int, ...], ...]:
    return (
        tuple(order["p0_hand"]),
        tuple(order["p0_deck"]),
        tuple(order["p1_hand"]),
        tuple(order["p1_deck"]),
    )


def official_symbol_surface(lib_path: Path) -> dict[str, Any]:
    nm_path = shutil.which("nm")
    if nm_path is None or not lib_path.exists():
        return {
            "library": str(lib_path),
            "symbol_tool": nm_path,
            "exported_seed_symbols": [],
            "has_random_device_symbol": False,
            "has_mt19937_symbol": False,
            "available": False,
        }
    completed = subprocess.run(
        [nm_path, "-D", str(lib_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    symbol_text = completed.stdout + completed.stderr
    exported = []
    for line in symbol_text.splitlines():
        if not re.search(r"\sT\s", line):
            continue
        name = line.rsplit(maxsplit=1)[-1]
        if re.search(r"seed|random|rand|rng", name, re.IGNORECASE):
            exported.append(name)
    return {
        "library": str(lib_path),
        "symbol_tool": nm_path,
        "exported_seed_symbols": sorted(exported),
        "has_random_device_symbol": "random_device" in symbol_text,
        "has_mt19937_symbol": "mersenne_twister_engine" in symbol_text,
        "available": completed.returncode == 0,
    }


def native_startup_order(core: NativeCore, deck: Path, opponent_deck: Path, *, first_player: int, seed: int) -> dict[str, Any]:
    pregame = core.start_battle_pregame(deck, opponent_deck)
    setup = core.select_pregame_first_player(pregame, first_player=first_player, seed=seed)
    return {
        "p0_hand": list(setup.players[0].hand_card_ids),
        "p0_deck": list(setup.players[0].deck_card_ids),
        "p1_hand": list(setup.players[1].hand_card_ids),
        "p1_deck": list(setup.players[1].deck_card_ids),
        "p0_deck_count": setup.players[0].deck_count,
        "p1_deck_count": setup.players[1].deck_count,
        "p0_hand_count": setup.players[0].hand_count,
        "p1_hand_count": setup.players[1].hand_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe official startup shuffle surface without mutating the engine.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--first-player", type=int, choices=(0, 1), default=1)
    parser.add_argument("--native-seed", type=int, default=17)
    parser.add_argument("--build-dir", type=Path, default=Path("artifacts/native_api"))
    args = parser.parse_args(argv)

    if args.attempts < 2:
        raise ValueError("--attempts must be at least 2")

    opponent_deck = args.opponent_deck or args.deck
    deck0 = read_deck(args.deck)
    deck1 = read_deck(opponent_deck)
    official_orders = [
        official_startup_order(deck0, deck1, first_player=args.first_player)
        for _attempt in range(args.attempts)
    ]
    official_keys = {order_key(order) for order in official_orders}

    library_path = build_native_core(build_dir=args.build_dir)
    core = NativeCore(library_path)
    native_a = native_startup_order(
        core,
        args.deck,
        opponent_deck,
        first_player=args.first_player,
        seed=args.native_seed,
    )
    native_b = native_startup_order(
        core,
        args.deck,
        opponent_deck,
        first_player=args.first_player,
        seed=args.native_seed,
    )
    native_c = native_startup_order(
        core,
        args.deck,
        opponent_deck,
        first_player=args.first_player,
        seed=args.native_seed + 1,
    )
    seed_surface = official_symbol_surface(OFFICIAL_LIB_PATH)

    payload = {
        "source": "official shuffle and seed-surface probe",
        "command": [sys.executable, "scripts/official_shuffle_probe.py", *(argv if argv is not None else sys.argv[1:])],
        "input_paths": {
            "deck": str(args.deck.resolve()),
            "opponent_deck": str(opponent_deck.resolve()),
        },
        "source_metadata": {
            "official_library": str(OFFICIAL_LIB_PATH),
            "symbol_tool": seed_surface["symbol_tool"],
        },
        "decks": {
            "player": deck_summary(args.deck, deck0),
            "opponent": deck_summary(opponent_deck, deck1),
        },
        "seed_surface": seed_surface,
        "official": {
            "attempt_count": args.attempts,
            "unique_order_count": len(official_keys),
            "deterministic_replay_available": bool(seed_surface["exported_seed_symbols"]),
            "first_player": args.first_player,
            "sample_orders": official_orders[: min(3, len(official_orders))],
        },
        "native": {
            "seed": args.native_seed,
            "same_seed_deterministic": order_key(native_a) == order_key(native_b),
            "different_seed_changes_order": order_key(native_a) != order_key(native_c),
            "sample_order": native_a,
        },
        "conclusion": {
            "standalone_exact_order_requires_official_seed_control": not bool(
                seed_surface["exported_seed_symbols"]
            ),
            "native_can_replay_official_observed_order": True,
            "next_best_gap": "derive or expose official seed/startup order, otherwise keep observed-order replay mode",
        },
        "kaggle_submission_made": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
