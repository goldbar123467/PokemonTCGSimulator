from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _deck_counts(path: Path) -> Counter[int]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return Counter()
    first = text.splitlines()[0]
    if "," not in first and first.strip().isdigit():
        return Counter(int(line.strip()) for line in text.splitlines() if line.strip())
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    card_field = "card_id" if rows and "card_id" in rows[0] else "id"
    count_field = "count" if rows and "count" in rows[0] else None
    counts: Counter[int] = Counter()
    for row in rows:
        multiplier = int(row[count_field]) if count_field else 1
        counts[int(row[card_field])] += multiplier
    return counts


def test_hop_petrel_secretbox_v2_1_uses_requested_benchmark_shell() -> None:
    deck_path = ROOT / "artifacts" / "hop_petrel_secretbox_v2_1" / "deck.csv"
    counts = _deck_counts(deck_path)

    assert sum(counts.values()) == 60
    assert counts[1219] == 4  # Team Rocket's Petrel
    assert counts[1092] == 1  # Secret Box
    assert counts[1134] == 4  # Team Rocket's Transceiver
    assert counts[1197] == 2  # Xerosic's Machinations
    assert counts[878] == 4
    assert counts[879] == 4
    assert counts[1115] == 4
    assert counts[311] == 3
    assert counts[304] == 2


def test_starmie_v2_1_is_legal_sixty_card_benchmark_with_redundant_starmie_line() -> None:
    deck_path = ROOT / "artifacts" / "starmie_v2_1" / "deck.csv"
    counts = _deck_counts(deck_path)

    assert sum(counts.values()) == 60
    assert counts[1030] == 4  # Staryu
    assert counts[1031] == 4  # Mega Starmie ex
    assert counts[666] <= 3  # Cinderace support is no longer the whole deck
    assert counts[1182] >= 2  # Boss's Orders for bridge removal/mirror control
    assert counts[1097] >= 2  # Night Stretcher for rebuilds
