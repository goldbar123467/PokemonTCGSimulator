from pathlib import Path

import pytest

from ptcg.prize_mapping import iter_prize_map_decisions, rank_openings, write_rankings
from ptcg.replays import UnsafeReplayDirectoryError


def test_iter_prize_map_decisions_extracts_observable_opening_features():
    decisions = list(
        iter_prize_map_decisions(
            replay_paths=[Path("data/Pokemon-Replays-Public/81519581.json")],
            max_replays=1,
            opening_steps=12,
        )
    )

    assert decisions
    assert all(decision.replay_id for decision in decisions)
    assert all(decision.our_prizes_left >= 0 for decision in decisions)
    assert all(decision.opponent_prizes_left >= 0 for decision in decisions)
    assert all(decision.option_count > 0 for decision in decisions)


def test_rank_openings_orders_by_xg_and_writes_csv(tmp_path):
    decisions = list(
        iter_prize_map_decisions(
            replay_paths=[
                Path("data/Pokemon-Replays-Public/81519581.json"),
                Path("data/Pokemon-Replays-Public/81126644.json"),
            ],
            max_replays=2,
            opening_steps=16,
        )
    )

    rankings = rank_openings(decisions)
    output = tmp_path / "rankings.csv"
    write_rankings(output, rankings[:5])

    assert rankings
    assert rankings[0].rank == 1
    assert output.read_text(encoding="utf-8").startswith("rank,key,games,decisions,avg_xg")


def test_iter_prize_map_decisions_refuses_raw_directory_globbing(tmp_path):
    with pytest.raises(UnsafeReplayDirectoryError):
        list(iter_prize_map_decisions(tmp_path))
