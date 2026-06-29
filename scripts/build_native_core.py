from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_core import (
    BENCH_SIZE,
    DECK_SIZE,
    HAND_SIZE,
    PRIZE_SIZE,
    CARD_CATALOG_PATH,
    HEADER_PATH,
    SOURCE_PATH,
    NativeDeck,
    NativeCore,
    build_native_core,
)


SETUP_HAND_SIZE = 7
PARITY_CONTRACT = {
    "deck_source": "deck.csv",
    "core": "clean-room C shared library",
    "verified_scope": "deck.csv load, public setup/main rules, and official-observed ordered-zone replay",
    "one_to_one_status": "not_1_to_1_standalone",
    "remaining_gap": "standalone official shuffle/RNG reproduction from deck.csv is not proven",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exported_functions() -> list[str]:
    header = HEADER_PATH.read_text(encoding="utf-8")
    return sorted(
        set(re.findall(r"PTCG_API\s+(?:const\s+char\s+\*|int)\s+(ptcg_[A-Za-z0-9_]+)\s*\(", header))
    )


def _deck_cards_summary(core: NativeCore, deck: NativeDeck) -> dict[str, object]:
    summary = core.deck_summary(deck)
    return {
        "first_card_ids": list(deck.cards[:10]),
        "unique_count": summary.unique_count,
        "basic_pokemon_count": summary.basic_pokemon_count,
        "energy_count": summary.energy_count,
        "named_counts": list(summary.named_counts),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the clean-room PTCG native core library.")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the library is already current.")
    parser.add_argument("--build-dir", type=Path, default=Path("artifacts/native_api"))
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--setup-seed", type=int, default=17)
    parser.add_argument("--deck-only", action="store_true", help="Only inspect deck.csv and the compiled API.")
    args = parser.parse_args(argv)

    library_path = build_native_core(build_dir=args.build_dir, force=args.force)
    core = NativeCore(library_path)
    deck = core.load_deck_csv(args.deck)
    opponent_deck = args.opponent_deck or args.deck
    exported_functions = _exported_functions()
    payload = {
        "library": str(library_path),
        "version": core.version,
        "deck": str(args.deck),
        "opponent_deck": str(opponent_deck),
        "card_count": deck.card_count,
        "deck_sha256": deck.sha256,
        "deck_cards": _deck_cards_summary(core, deck),
        "api_manifest": {
            "deck_source": str(args.deck),
            "library_sha256": _sha256(library_path),
            "source_sha256": _sha256(SOURCE_PATH),
            "header_sha256": _sha256(HEADER_PATH),
            "catalog_sha256": _sha256(CARD_CATALOG_PATH),
            "function_count": len(exported_functions),
            "exported_functions": exported_functions,
            "abi_constants": {
                "deck_size": DECK_SIZE,
                "setup_hand_size": SETUP_HAND_SIZE,
                "hand_size": HAND_SIZE,
                "prize_size": PRIZE_SIZE,
                "bench_size": BENCH_SIZE,
            },
            "parity_contract": {
                **PARITY_CONTRACT,
                "deck_source": str(args.deck),
            },
        },
        "kaggle_submission_made": False,
    }
    if not args.deck_only:
        setup = core.start_battle_setup(args.deck, opponent_deck, seed=args.setup_seed)
        payload["setup"] = {
            "seed": args.setup_seed,
            "first_player": setup.first_player,
            "current_player": setup.current_player,
            "players": [
                {
                    "deck_count": player.deck_count,
                    "hand_count": player.hand_count,
                    "prize_count": player.prize_count,
                }
                for player in setup.players
            ],
        }
    print(
        json.dumps(
            payload,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
