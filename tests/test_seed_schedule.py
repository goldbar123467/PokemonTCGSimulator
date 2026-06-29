from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg.seed_schedule import build_seed_schedule, parse_seed_list, save_seed_schedule


def test_base_seed_schedule_is_reproducible_for_same_config() -> None:
    matchups = [
        {"candidate": "candidate", "opponent": "lucario"},
        {"candidate": "candidate", "opponent": "dragapult"},
    ]

    schedule_a = build_seed_schedule(matchups, games_per_matchup=3, base_seed=42)
    schedule_b = build_seed_schedule(matchups, games_per_matchup=3, base_seed=42)
    schedule_c = build_seed_schedule(matchups, games_per_matchup=3, base_seed=43)

    assert schedule_a == schedule_b
    assert schedule_a != schedule_c
    assert schedule_a["base_seed"] == 42
    assert schedule_a["games_per_matchup"] == 3
    assert schedule_a["official_sdk_seed_control"] is False
    assert schedule_a["crn_available"] is False
    assert [row["game_index"] for row in schedule_a["games"][:3]] == [0, 1, 2]
    assert len({row["seed"] for row in schedule_a["games"]}) == 6


def test_explicit_seed_list_is_applied_to_each_matchup_and_saved(tmp_path: Path) -> None:
    schedule = build_seed_schedule(
        [{"candidate": "candidate", "opponent": "hop_trevenant"}],
        games_per_matchup=3,
        explicit_seeds=[10, 11, 12],
    )

    assert [row["seed"] for row in schedule["games"]] == [10, 11, 12]
    assert parse_seed_list("10, 11,12") == [10, 11, 12]

    output = tmp_path / "seed_schedule.json"
    save_seed_schedule(schedule, output)

    assert json.loads(output.read_text(encoding="utf-8")) == schedule


def test_seed_schedule_refuses_unseeded_or_short_configs() -> None:
    with pytest.raises(ValueError, match="base_seed or explicit_seeds"):
        build_seed_schedule([{"candidate": "candidate", "opponent": "lucario"}], games_per_matchup=1)

    with pytest.raises(ValueError, match="at least games_per_matchup"):
        build_seed_schedule(
            [{"candidate": "candidate", "opponent": "lucario"}],
            games_per_matchup=3,
            explicit_seeds=[1, 2],
        )
