from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_heuristic_candidates import _pick_deck, _write_candidate
from scripts.tune_heuristic_rng import BASE_CONFIGS


BASIC_ENERGY_IDS = {2, 3, 5, 6, 7, 17, 19}


FAMILY_VARIANTS = {
    "lucario": [
        ("max_riolu", {676: 1}, {6: 1}),
        ("max_lucario_line", {676: 1, 677: 1}, {6: 2}),
        ("extra_energy", {6: 2}, {1159: 1, 1182: 1}),
        ("extra_setup_less_disruption", {1152: 0, 1227: 0, 1192: 0, 1123: 1}, {1182: 1}),
        ("thin_disruption_energy", {6: 1, 676: 1}, {1182: 1, 1252: 1}),
        ("mirror_race_density", {676: 1, 677: 1, 6: 1}, {1159: 1, 1182: 1, 1252: 1}),
    ],
    "dragapult": [
        ("max_basic_chain", {119: 0, 120: 0, 121: 1}, {1260: 1}),
        ("extra_energy", {2: 1, 5: 1}, {1159: 1, 1197: 1}),
        ("anti_lucario_targets", {1182: 1, 1198: 1}, {1260: 2}),
        ("draw_setup_density", {235: 1, 1227: 0}, {1159: 1}),
    ],
    "alakazam": [
        ("max_alakazam_line", {743: 1}, {1079: 1}),
        ("extra_energy", {5: 1, 19: 1}, {1079: 1, 1225: 1}),
        ("less_disruption_more_setup", {1086: 0, 1152: 0, 1225: 1}, {1079: 1}),
        ("mirror_stabilizer", {743: 1, 5: 1}, {1079: 1, 1156: 1}),
    ],
    "shell666": [
        ("basic_density", {1030: 1, 1031: 1}, {3: 1, 1223: 1}),
        ("backup_attacker", {1030: 1, 1031: 1}, {3: 1, 1225: 1}),
        ("bench_over_energy", {1030: 1, 1031: 1}, {3: 2}),
        ("max_chain", {1030: 1, 1031: 1}, {1159: 1, 1223: 1}),
        ("draw_to_attackers", {1030: 1, 1031: 1}, {1097: 1, 1225: 1}),
        ("low_flex_more_basics", {1030: 1}, {1182: 1}),
    ],
}


def _card_limit(card_id: int) -> int:
    return 64 if card_id in BASIC_ENERGY_IDS else 4


def _deck_from_counts(counts: Counter[int]) -> list[int]:
    deck: list[int] = []
    for card_id in sorted(counts):
        count = counts[card_id]
        if count < 0:
            raise ValueError(f"negative count for {card_id}: {count}")
        if count > _card_limit(card_id):
            raise ValueError(f"too many copies of {card_id}: {count}")
        deck.extend([card_id] * count)
    if len(deck) != 60:
        raise ValueError(f"deck has {len(deck)} cards, expected 60")
    return deck


def _apply_variant(base_deck: list[int], plus: dict[int, int], minus: dict[int, int]) -> list[int]:
    counts = Counter(base_deck)
    for card_id, delta in plus.items():
        counts[int(card_id)] += int(delta)
    for card_id, delta in minus.items():
        counts[int(card_id)] -= int(delta)
    return _deck_from_counts(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate family-aware deck-structure variants from scout decks.")
    parser.add_argument("--scout-decks", type=Path, default=Path("artifacts/candidates/scout_decks.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--families", default="lucario,dragapult,alakazam")
    parser.add_argument("--prefix", default="familyshape")
    args = parser.parse_args()

    scout = json.loads(args.scout_decks.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for family_name in [item.strip() for item in args.families.split(",") if item.strip()]:
        if family_name not in BASE_CONFIGS:
            raise ValueError(f"unknown family: {family_name}")
        if family_name not in FAMILY_VARIANTS:
            raise ValueError(f"no deck variants for family: {family_name}")
        base_config = dict(BASE_CONFIGS[family_name])
        base_deck = _pick_deck(scout, base_config["family"])
        for index, (variant_name, plus, minus) in enumerate(FAMILY_VARIANTS[family_name]):
            try:
                deck = _apply_variant(base_deck, plus, minus)
            except ValueError as exc:
                rows.append(
                    {
                        "candidate": f"{args.prefix}_{family_name}_{index:02d}_{variant_name}",
                        "family": family_name,
                        "wins": 0,
                        "finished": 0,
                        "win_rate": 0.0,
                        "errors": [str(exc)],
                        "variant": variant_name,
                        "plus": plus,
                        "minus": minus,
                        "skipped": True,
                    }
                )
                continue
            config = dict(base_config)
            config["strategy"] = f"{base_config['strategy']} deck-shape {variant_name}"
            candidate_name = f"{args.prefix}_{family_name}_{index:02d}_{variant_name}"
            candidate = _write_candidate(args.output_dir, candidate_name, deck, config)
            rows.append(
                {
                    "candidate": candidate_name,
                    "family": family_name,
                    "main_path": candidate["main_path"],
                    "deck_path": candidate["deck_path"],
                    "wins": 0,
                    "finished": 0,
                    "win_rate": 0.0,
                    "errors": [],
                    "variant": variant_name,
                    "plus": plus,
                    "minus": minus,
                    "top_cards": candidate["top_cards"],
                }
            )
    output = args.output_dir / "family_deck_candidates.json"
    output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "candidates": len(rows)}))


if __name__ == "__main__":
    main()
