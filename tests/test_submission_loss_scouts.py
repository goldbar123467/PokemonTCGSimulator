from __future__ import annotations

import json
from pathlib import Path

from ptcg.submission_loss_scouts import write_submission_loss_scouts


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def test_write_submission_loss_scouts_emits_per_episode_reports(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    output_dir = tmp_path / "scouts"
    actor_rows = [
        {
            "episode_id": 111,
            "submission_id": 54121782,
            "actor_index": 0,
            "actor_archetype": "mega_starmie",
            "opponent_index": 1,
            "opponent_archetype": "dragapult_spread",
            "opponent_team_name": "Opponent",
            "outcome": "loss",
            "reward": -1.0,
            "opponent_reward": 1.0,
            "create_time": "2026-06-27 22:00:00",
            "replay_path": "episode-111-replay.json",
            "submission_public_score": 645.0,
        },
        {
            "episode_id": 222,
            "submission_id": 54121782,
            "actor_index": 0,
            "actor_archetype": "mega_starmie",
            "opponent_index": 1,
            "opponent_archetype": "lucario",
            "opponent_team_name": "Winner",
            "outcome": "win",
            "reward": 1.0,
            "opponent_reward": -1.0,
            "create_time": "2026-06-27 22:04:00",
            "replay_path": "episode-222-replay.json",
            "submission_public_score": 645.0,
        },
    ]
    label_rows = [
        {
            "episode_id": 111,
            "step_index": 7,
            "outcome": "loss",
            "flaw_tags": ["teacher_preferred_alternative", "attack_without_backup"],
            "pipeline_labels": ["setup", "bench_develop"],
            "selected_labels": [],
            "teacher_labels": ["setup_next_attacker"],
            "selected_penalties": ["attack_without_backup"],
            "teacher_penalties": [],
            "chosen_action": [0],
            "teacher_action": [1],
            "observation": {
                "current": {
                    "turn": 2,
                    "players": [
                        {"active": [{"id": 1030, "hp": 70, "maxHp": 70}], "bench": [], "handCount": 4, "deckCount": 42},
                        {"active": [{"id": 344, "hp": 70, "maxHp": 70}], "bench": [], "handCount": 3, "deckCount": 43},
                    ],
                }
            },
        }
    ]

    _write_jsonl(dataset_dir / "episode_actors.jsonl", actor_rows)
    _write_jsonl(dataset_dir / "decision_labels.jsonl", label_rows)
    (dataset_dir / "loss_trends.json").write_text(
        json.dumps({"total_rows": 1, "loss_rows": 1, "kaggle_submission_made": False}),
        encoding="utf-8",
    )

    summary = write_submission_loss_scouts(
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        submission_id=54121782,
        scope="pytest scope",
        command="pytest",
    )

    assert summary["submission_id"] == 54121782
    assert summary["loss_game_count"] == 1
    assert summary["aggregate_flaws"]["teacher_preferred_alternative"] == 1
    assert summary["aggregate_labels"]["setup"] == 1
    assert summary["kaggle_submission_made"] is False
    assert (output_dir / "episode_111_scout.md").exists()
    markdown = (output_dir / "loss_scout_summary.md").read_text(encoding="utf-8")
    assert "Submission 54121782 Loss Scout Summary" in markdown
    assert "Kaggle submission made: no" in markdown

