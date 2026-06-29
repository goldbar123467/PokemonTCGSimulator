from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_heuristic_candidates import _write_candidate


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("deck_variant_source", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _deck_from_counts(counts: dict[int, int]) -> list[int]:
    deck: list[int] = []
    for card_id, count in counts.items():
        if count > 4 and card_id not in {3, 17}:
            raise ValueError(f"too many copies of {card_id}: {count}")
        deck.extend([card_id] * count)
    if len(deck) != 60:
        raise ValueError(f"deck has {len(deck)} cards, expected 60: {counts}")
    return deck


def _base_config(main_path: Path) -> dict:
    module = _load_module(main_path)
    return {
        "strategy": f"deck structure variant from {main_path.parent.name}",
        "key_cards": sorted(getattr(module, "KEY_CARDS", set())),
        "setup_cards": sorted(getattr(module, "SETUP_CARDS", set())),
        "attackers": sorted(getattr(module, "ATTACKERS", set())),
        "evolvers": sorted(getattr(module, "EVOLVERS", set())),
        "disruption": sorted(getattr(module, "DISRUPTION", set())),
        "energy_ids": sorted(getattr(module, "ENERGY_IDS", set())),
        "gate_targets": sorted(getattr(module, "GATE_TARGETS", set())),
        "rng_noise": float(getattr(module, "RNG_NOISE", 20.0)),
        "weights": dict(getattr(module, "WEIGHTS", {})),
    }


def _variant_counts(base_deck: list[int]) -> list[tuple[str, dict[int, int]]]:
    base = Counter(base_deck)
    variants: list[tuple[str, dict[int, int]]] = []

    def add(name: str, plus: dict[int, int], minus: dict[int, int]) -> None:
        counts = Counter(base)
        for card_id, count in plus.items():
            counts[card_id] += count
        for card_id, count in minus.items():
            counts[card_id] -= count
            if counts[card_id] < 0:
                raise ValueError(f"{name} removed too many {card_id}")
        variants.append((name, dict(counts)))

    add(
        "basic_density",
        plus={1030: 1, 1031: 1},
        minus={3: 1, 1223: 1},
    )
    add(
        "backup_attacker",
        plus={1030: 1, 1031: 1},
        minus={3: 1, 1225: 1},
    )
    add(
        "bench_over_energy",
        plus={1030: 1, 1031: 1},
        minus={3: 2},
    )
    add(
        "max_chain",
        plus={1030: 1, 1031: 1},
        minus={1159: 1, 1223: 1},
    )
    add(
        "draw_to_attackers",
        plus={1030: 1, 1031: 1},
        minus={1097: 1, 1225: 1},
    )
    add(
        "low_flex_more_basics",
        plus={1030: 1},
        minus={1182: 1},
    )
    return variants


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deck-structure variants around an elite heuristic candidate.")
    parser.add_argument("--elite-main", type=Path, required=True)
    parser.add_argument("--elite-deck", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prefix", default="deckshape")
    args = parser.parse_args()

    base_deck = [int(line.strip()) for line in args.elite_deck.read_text(encoding="utf-8").splitlines() if line.strip()]
    base_config = _base_config(args.elite_main)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for index, (variant_name, counts) in enumerate(_variant_counts(base_deck)):
        deck = _deck_from_counts(counts)
        config = dict(base_config)
        config["strategy"] = f"{base_config['strategy']} {variant_name}"
        candidate_name = f"{args.prefix}_{index:02d}_{variant_name}"
        candidate = _write_candidate(args.output_dir, candidate_name, deck, config)
        rows.append(
            {
                "candidate": candidate_name,
                "family": "deck_structure",
                "main_path": candidate["main_path"],
                "deck_path": candidate["deck_path"],
                "wins": 0,
                "finished": 0,
                "win_rate": 0.0,
                "errors": [],
                "deck_counts": counts,
            }
        )

    output = args.output_dir / "deck_structure_candidates.json"
    output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "candidates": len(rows)}))


if __name__ == "__main__":
    main()
