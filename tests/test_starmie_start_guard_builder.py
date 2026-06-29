from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

from scripts.build_starmie_start_guard_candidates import (
    SOURCE_DIR,
    build_starmie_start_guard_candidate,
)


def _parent_deck() -> list[int]:
    return [int(line) for line in (SOURCE_DIR / "deck.csv").read_text(encoding="utf-8").splitlines() if line]


def test_start_guard_deck_biases_staryu_start_without_policy_patch(tmp_path: Path) -> None:
    candidate = build_starmie_start_guard_candidate(tmp_path)
    deck = [int(line) for line in candidate["deck_path"].read_text(encoding="utf-8").splitlines() if line]
    counts = Counter(deck)
    parent_counts = Counter(_parent_deck())

    assert len(deck) == 60
    assert counts[1030] == parent_counts[1030] + 1
    assert counts[666] == parent_counts[666] - 1
    assert counts[1031] == parent_counts[1031]
    assert counts[1229] == parent_counts[1229]
    assert counts[1223] == parent_counts[1223]
    assert counts[1121] == parent_counts[1121]
    assert counts[1182] == parent_counts[1182]
    assert all(count <= 4 for card_id, count in counts.items() if card_id != 3)


def test_start_guard_archive_validates_startup_shape(tmp_path: Path) -> None:
    candidate = build_starmie_start_guard_candidate(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ptcg.kaggle_archive_validator",
            "--archive",
            str(candidate["archive_path"]),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
