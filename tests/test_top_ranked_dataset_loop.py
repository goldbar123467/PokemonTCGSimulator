from __future__ import annotations

import json
from pathlib import Path

from ptcg.top_ranked_dataset_loop import build_per_game_trend_summary
from ptcg.top_ranked_dataset_loop import scan_top_ranked_episodes
from ptcg.top_ranked_dataset_loop import trend_tags_for_decision


def _card(card_id: int, name: str = "Card") -> dict:
    return {"id": card_id, "name": name}


def _decision_obs(*, your_index: int, deck_count: int = 20) -> dict:
    players = [
        {
            "active": [_card(677, "Riolu")],
            "bench": [],
            "hand": [_card(1152, "Poke Pad")],
            "deck": [_card(1000 + index, "Deck") for index in range(deck_count)],
            "discard": [],
            "prize": [None] * 6,
        },
        {
            "active": [_card(119, "Dreepy")],
            "bench": [_card(120, "Drakloak")],
            "hand": [],
            "deck": [],
            "discard": [],
            "prize": [None] * 6,
        },
    ]
    return {
        "current": {"turn": 4, "yourIndex": your_index, "players": players},
        "select": {
            "option": [
                {"type": 7, "area": 2, "index": 0, "playerIndex": your_index},
                {"type": 13, "attackId": 1},
            ]
        },
    }


def _episode(path: Path, *, episode_id: int, teams: list[str], rewards: list[int], decisions: int) -> Path:
    steps = [
        [
            {"action": [677, 678] + [6] * 58, "observation": {}, "reward": 0, "status": "ACTIVE"},
            {"action": [119, 120, 121] + [1] * 57, "observation": {}, "reward": 0, "status": "ACTIVE"},
        ]
    ]
    for turn in range(decisions):
        steps.append(
            [
                {
                    "action": [turn % 2],
                    "observation": _decision_obs(your_index=0),
                    "reward": rewards[0],
                    "status": "ACTIVE",
                },
                {
                    "action": [0],
                    "observation": _decision_obs(your_index=1),
                    "reward": rewards[1],
                    "status": "INACTIVE",
                },
            ]
        )
    path.write_text(
        json.dumps(
            {
                "configuration": {"seed": episode_id},
                "info": {"EpisodeId": episode_id, "TeamNames": teams},
                "rewards": rewards,
                "steps": steps,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_scan_top_ranked_episodes_writes_progress_and_rankings(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _episode(dataset / "100.json", episode_id=100, teams=["Alpha", "Beta"], rewards=[1, -1], decisions=3)
    _episode(dataset / "101.json", episode_id=101, teams=["Gamma", "Beta"], rewards=[1, -1], decisions=7)
    leaderboard = tmp_path / "leaderboard.csv"
    leaderboard.write_text("teamName,score\nAlpha,1000\nBeta,1200\nGamma,1400\n", encoding="utf-8")

    report = scan_top_ranked_episodes(
        dataset_dir=dataset,
        leaderboard_csv=leaderboard,
        output_dir=tmp_path / "scan",
        top_limit=2,
        command="pytest",
    )

    assert report["scanned_count"] == 2
    assert report["error_count"] == 0
    assert report["top_episodes"][0]["episode_id"] == 101
    assert Path(report["paths"]["rankings_json"]).exists()
    progress_lines = Path(report["paths"]["scan_progress_jsonl"]).read_text(encoding="utf-8").splitlines()
    assert len(progress_lines) == 2
    assert json.loads(progress_lines[0])["status"] == "ok"
    assert report["kaggle_submission_made"] is False


def test_trend_tags_for_decision_maps_existing_labels() -> None:
    row = {
        "outcome": "loss",
        "opponent_archetype": "dragapult_spread",
        "flaw_tags": ["missed_setup", "attack_without_backup", "active_overattach"],
        "pipeline_labels": ["draw/search/thin"],
        "observation": _decision_obs(your_index=0, deck_count=5),
        "actor_index": 0,
    }

    tags = trend_tags_for_decision(row)

    assert "setup_failure" in tags
    assert "attack_without_backup" in tags
    assert "energy_overcommit_active" in tags
    assert "dragapult_spread_posture_gap" in tags
    assert "low_deck_churn" in tags


def test_build_per_game_trend_summary_groups_phase_counts(tmp_path: Path) -> None:
    labels = tmp_path / "hard_labels.jsonl"
    rows = [
        {
            "episode_id": "1",
            "source_file": "one.json",
            "source_sha256": "abc",
            "team_name": "Alpha",
            "actor_archetype": "lucario",
            "opponent_archetype": "hop_trevenant",
            "matchup_tag": "hop_trevenant",
            "outcome": "loss",
            "phase": "opening",
            "step_index": 12,
            "flaw_tags": ["attack_without_backup"],
            "pipeline_labels": ["bench_develop"],
            "score_delta_teacher_minus_selected": 2.5,
            "sample_weight": 1.5,
            "legal_scope": "public replay",
        },
        {
            "episode_id": "1",
            "source_file": "one.json",
            "source_sha256": "abc",
            "team_name": "Alpha",
            "actor_archetype": "lucario",
            "opponent_archetype": "hop_trevenant",
            "matchup_tag": "hop_trevenant",
            "outcome": "loss",
            "phase": "finish",
            "step_index": 40,
            "flaw_tags": ["missed_setup"],
            "pipeline_labels": ["setup"],
            "score_delta_teacher_minus_selected": 1.0,
            "sample_weight": 1.0,
            "legal_scope": "public replay",
        },
    ]
    labels.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    summary = build_per_game_trend_summary(labels, tmp_path / "trends.json", command="pytest")

    game = summary["games"][0]
    assert game["episode_id"] == "1"
    assert game["trend_counts"]["hop_trevenant_second_swing_gap"] >= 1
    assert game["phase_counts"]["opening"]["attack_without_backup"] == 1
    assert game["primary_failure_family"] == "hop_trevenant_second_swing_gap"
    assert summary["aggregate_trend_counts"]["setup_failure"] == 2
    assert summary["kaggle_submission_made"] is False
