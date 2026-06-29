from __future__ import annotations

from scripts.generate_starmie_start_guard_report import matchup_delta_rows, win_rate


def test_win_rate_uses_finished_games() -> None:
    assert win_rate({"wins": 7, "finished": 10, "games": 99}) == 0.7
    assert win_rate({"wins": 0, "finished": 0, "games": 0}) == 0.0


def test_matchup_delta_rows_pair_parent_and_candidate_by_gate() -> None:
    rows = [
        {"candidate": "parent", "gate_ref": "a", "archetype": "lucario", "wins": 4, "finished": 10},
        {"candidate": "start", "gate_ref": "a", "archetype": "lucario", "wins": 7, "finished": 10},
        {"candidate": "parent", "gate_ref": "b", "archetype": "dragapult", "wins": 8, "finished": 10},
        {"candidate": "start", "gate_ref": "b", "archetype": "dragapult", "wins": 6, "finished": 10},
    ]

    deltas = matchup_delta_rows(rows, parent="parent", candidate="start")

    assert deltas == [
        {
            "archetype": "lucario",
            "candidate_win_rate": 0.7,
            "delta": 0.29999999999999993,
            "gate_ref": "a",
            "parent_win_rate": 0.4,
        },
        {
            "archetype": "dragapult",
            "candidate_win_rate": 0.6,
            "delta": -0.20000000000000007,
            "gate_ref": "b",
            "parent_win_rate": 0.8,
        },
    ]
