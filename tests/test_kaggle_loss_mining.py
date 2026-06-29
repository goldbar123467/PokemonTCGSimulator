from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ptcg.kaggle_loss_mining import (
    analyze_loss_trends,
    build_decision_label_rows,
    build_episode_actor_records,
    submission_record_from_api,
    write_loss_dataset,
)


def _agent(submission_id: int, index: int, reward: int, team_name: str = "Clark Kitchen") -> SimpleNamespace:
    return SimpleNamespace(
        submission_id=submission_id,
        index=index,
        reward=reward,
        state="EPISODE_AGENT_STATE_UNSPECIFIED",
        team_name=team_name,
        team_id=16395686 if team_name == "Clark Kitchen" else 123,
    )


def _submission(
    ref: int,
    *,
    file_name: str = "agent.tar.gz",
    status: str = "SubmissionStatus.COMPLETE",
    score: str | None = "713.0",
    error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        ref=ref,
        file_name=file_name,
        status=status,
        public_score=score,
        private_score=None,
        error_description=error,
        description="test run",
        team_name="Clark Kitchen",
        submitted_by="clarkkitchen",
        total_bytes=42,
        date="2026-06-25 17:22:41",
    )


def _decision_obs() -> dict:
    players = [
        {
            "active": [{"id": 10, "name": "Active A", "hp": 120, "maxHp": 120}],
            "bench": [],
            "hand": [{"id": 677, "name": "Riolu"}],
            "deck": [{"id": 999, "name": "Hidden Deck Card"}],
            "discard": [],
            "prize": [{"id": 888, "name": "Hidden Prize Card"}],
        },
        {
            "active": [{"id": 20, "name": "Active B"}],
            "bench": [],
            "hand": [],
            "deck": [],
            "discard": [],
            "prize": [],
        },
    ]
    return {
        "current": {"turn": 3, "yourIndex": 0, "players": players},
        "search_begin_input": "state",
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "area": 2, "index": 0, "playerIndex": 0},
                {"type": 14},
            ],
        },
    }


def _one_option_obs() -> dict:
    return {
        "current": {"turn": 3, "yourIndex": 0, "players": [{"active": [], "bench": [], "hand": [], "discard": []}, {}]},
        "select": {"minCount": 1, "maxCount": 1, "option": [{"type": 14}]},
    }


def _four_option_obs() -> dict:
    obs = _decision_obs()
    obs["select"]["option"] = [
        {"index": 0, "type": 7},
        {"index": 1, "type": 7},
        {"index": 2, "type": 7},
        {"area": 5, "index": 1, "type": 10},
    ]
    return obs


def _write_replay(path: Path) -> Path:
    episode = {
        "info": {"EpisodeId": 1234, "TeamNames": ["Clark Kitchen", "Opponent"]},
        "configuration": {"seed": 7},
        "rewards": [-1, 1],
        "steps": [
            [
                {"action": [677] * 60, "observation": {}, "reward": 0, "status": "ACTIVE"},
                {"action": [119, 120, 121] + [1] * 57, "observation": {}, "reward": 0, "status": "ACTIVE"},
            ],
            [
                {"action": [], "observation": _decision_obs(), "reward": 0, "status": "ACTIVE"},
                {"action": [], "observation": {}, "reward": 0, "status": "INACTIVE"},
            ],
            [
                {
                    "action": [1],
                    "observation": {"select": None, "current": {"yourIndex": 0, "players": []}},
                    "reward": 0,
                    "status": "ACTIVE",
                },
                {"action": [], "observation": {}, "reward": 0, "status": "INACTIVE"},
            ],
        ],
    }
    path.write_text(json.dumps(episode), encoding="utf-8")
    return path


def _write_shifted_replay(path: Path) -> Path:
    episode = {
        "info": {"EpisodeId": 2345, "TeamNames": ["Clark Kitchen", "Opponent"]},
        "configuration": {"seed": 8},
        "rewards": [-1, 1],
        "steps": [
            [
                {"action": [677] * 60, "observation": {}, "reward": 0, "status": "ACTIVE"},
                {"action": [119, 120, 121] + [1] * 57, "observation": {}, "reward": 0, "status": "ACTIVE"},
            ],
            [
                {"action": [], "observation": _four_option_obs(), "reward": 0, "status": "ACTIVE"},
                {"action": [], "observation": {}, "reward": 0, "status": "INACTIVE"},
            ],
            [
                {"action": [3], "observation": _one_option_obs(), "reward": 0, "status": "ACTIVE"},
                {"action": [], "observation": {}, "reward": 0, "status": "INACTIVE"},
            ],
        ],
    }
    path.write_text(json.dumps(episode), encoding="utf-8")
    return path


def test_submission_record_from_api_preserves_complete_and_error_state() -> None:
    complete = submission_record_from_api(_submission(54048478, file_name="hop.tar.gz"))
    failed = submission_record_from_api(
        _submission(54048281, status="SubmissionStatus.ERROR", score=None, error="Validation Episode failed.")
    )

    assert complete.submission_id == 54048478
    assert complete.status == "complete"
    assert complete.public_score == 713.0
    assert complete.agent_family == "hop"
    assert failed.status == "error"
    assert failed.error_description == "Validation Episode failed."


def test_build_episode_actor_records_uses_submission_reward_and_opponent_archetype(tmp_path: Path) -> None:
    replay_path = _write_replay(tmp_path / "episode-1234-replay.json")
    episode = SimpleNamespace(
        id=1234,
        create_time="2026-06-25 18:00:00",
        end_time="2026-06-25 18:03:00",
        state="EpisodeState.COMPLETED",
        type="EpisodeType.EPISODE_TYPE_PUBLIC",
        agents=[_agent(54048478, 0, -1), _agent(54099999, 1, 1, team_name="Opponent")],
    )
    submissions = {54048478: submission_record_from_api(_submission(54048478, file_name="hop.tar.gz"))}

    records = build_episode_actor_records(
        episode,
        replay_path=replay_path,
        submissions_by_id=submissions,
        own_team_id=16395686,
    )

    assert len(records) == 1
    assert records[0].submission_id == 54048478
    assert records[0].outcome == "loss"
    assert records[0].actor_archetype == "lucario"
    assert records[0].opponent_archetype == "dragapult_spread"


def test_build_episode_actor_records_finds_initial_deck_after_empty_step_zero(tmp_path: Path) -> None:
    replay_path = _write_replay(tmp_path / "episode-1234-replay.json")
    episode_payload = json.loads(replay_path.read_text(encoding="utf-8"))
    episode_payload["steps"].insert(
        0,
        [
            {"action": [], "observation": {}, "reward": 0, "status": "ACTIVE"},
            {"action": [], "observation": {}, "reward": 0, "status": "ACTIVE"},
        ],
    )
    replay_path.write_text(json.dumps(episode_payload), encoding="utf-8")
    episode = SimpleNamespace(
        id=1234,
        create_time="2026-06-25 18:00:00",
        end_time="2026-06-25 18:03:00",
        state="EpisodeState.COMPLETED",
        type="EpisodeType.EPISODE_TYPE_PUBLIC",
        agents=[_agent(54048478, 0, -1), _agent(54099999, 1, 1, team_name="Opponent")],
    )

    records = build_episode_actor_records(
        episode,
        replay_path=replay_path,
        submissions_by_id={54048478: submission_record_from_api(_submission(54048478))},
        own_team_id=16395686,
    )

    assert records[0].actor_archetype == "lucario"
    assert records[0].opponent_archetype == "dragapult_spread"


def test_build_decision_label_rows_sanitizes_hidden_zones_and_flags_loss_flaw(tmp_path: Path) -> None:
    replay_path = _write_replay(tmp_path / "episode-1234-replay.json")
    actor = build_episode_actor_records(
        SimpleNamespace(
            id=1234,
            create_time="2026-06-25 18:00:00",
            end_time="2026-06-25 18:03:00",
            state="EpisodeState.COMPLETED",
            type="EpisodeType.EPISODE_TYPE_PUBLIC",
            agents=[_agent(54048478, 0, -1), _agent(54099999, 1, 1, team_name="Opponent")],
        ),
        replay_path=replay_path,
        submissions_by_id={54048478: submission_record_from_api(_submission(54048478))},
        own_team_id=16395686,
    )[0]

    rows = build_decision_label_rows(replay_path, actor)

    assert len(rows) == 1
    row = rows[0]
    assert row["step_index"] == 1
    assert row["action_step_index"] == 2
    assert row["outcome"] == "loss"
    assert row["data_source"] == "kaggle_public_episode"
    assert row["actor_owner"] == "Clark Kitchen"
    assert row["opponent_owner"] == "external_kaggle_team"
    assert row["matchup_tag"] == "dragapult_spread"
    assert "missed_setup" in row["flaw_tags"]
    assert row["sample_weight"] > 1.0
    assert "Hidden Deck Card" not in json.dumps(row["observation"])
    assert "Hidden Prize Card" not in json.dumps(row["observation"])
    assert row["observation"]["current"]["players"][0]["deck_count"] == 1
    assert row["observation"]["current"]["players"][0]["prize_count"] == 1


def test_build_decision_label_rows_skips_steps_with_null_select(tmp_path: Path) -> None:
    replay_path = _write_replay(tmp_path / "episode-1234-replay.json")
    episode = json.loads(replay_path.read_text(encoding="utf-8"))
    episode["steps"].append(
        [
            {
                "action": [0],
                "observation": {"select": None, "current": {"yourIndex": 0, "players": []}},
                "reward": 0,
                "status": "ACTIVE",
            },
            {"action": [], "observation": {}, "reward": 0, "status": "INACTIVE"},
        ]
    )
    replay_path.write_text(json.dumps(episode), encoding="utf-8")
    actor = build_episode_actor_records(
        SimpleNamespace(
            id=1234,
            create_time="2026-06-25 18:00:00",
            end_time="2026-06-25 18:03:00",
            state="EpisodeState.COMPLETED",
            type="EpisodeType.EPISODE_TYPE_PUBLIC",
            agents=[_agent(54048478, 0, -1), _agent(54099999, 1, 1, team_name="Opponent")],
        ),
        replay_path=replay_path,
        submissions_by_id={54048478: submission_record_from_api(_submission(54048478))},
        own_team_id=16395686,
    )[0]

    rows = build_decision_label_rows(replay_path, actor)

    assert len(rows) == 1
    assert rows[0]["step_index"] == 1
    assert rows[0]["action_step_index"] == 2


def test_build_decision_label_rows_pairs_next_step_action_with_current_observation(tmp_path: Path) -> None:
    replay_path = _write_shifted_replay(tmp_path / "episode-2345-replay.json")
    actor = build_episode_actor_records(
        SimpleNamespace(
            id=2345,
            create_time="2026-06-25 18:00:00",
            end_time="2026-06-25 18:03:00",
            state="EpisodeState.COMPLETED",
            type="EpisodeType.EPISODE_TYPE_PUBLIC",
            agents=[_agent(54048478, 0, -1), _agent(54099999, 1, 1, team_name="Opponent")],
        ),
        replay_path=replay_path,
        submissions_by_id={54048478: submission_record_from_api(_submission(54048478))},
        own_team_id=16395686,
    )[0]

    rows = build_decision_label_rows(replay_path, actor)

    assert len(rows) == 1
    row = rows[0]
    assert row["step_index"] == 1
    assert row["action_step_index"] == 2
    assert row["chosen_action"] == [3]
    assert row["legal_actions"] == _four_option_obs()["select"]["option"]


def test_analyze_loss_trends_summarizes_by_submission_matchup_and_flaw() -> None:
    rows = [
        {
            "submission_id": 1,
            "agent_family": "hop",
            "outcome": "loss",
            "matchup_tag": "dragapult_spread",
            "flaw_tags": ["missed_setup", "active_overattach"],
        },
        {
            "submission_id": 1,
            "agent_family": "hop",
            "outcome": "win",
            "matchup_tag": "lucario",
            "flaw_tags": [],
        },
        {
            "submission_id": 2,
            "agent_family": "agent4",
            "outcome": "loss",
            "matchup_tag": "lucario",
            "flaw_tags": ["attack_without_backup"],
        },
    ]

    report = analyze_loss_trends(rows)

    assert report["total_rows"] == 3
    assert report["loss_rows"] == 2
    assert report["losses_by_matchup"]["dragapult_spread"] == 1
    assert report["flaw_counts"]["missed_setup"] == 1
    assert report["submission_loss_summary"]["1"]["losses"] == 1
    assert report["agent_family_summary"]["hop"]["wins"] == 1


def test_write_loss_dataset_emits_research_patch_map(tmp_path: Path) -> None:
    replay_path = _write_replay(tmp_path / "episode-1234-replay.json")
    submission = submission_record_from_api(_submission(54048478))
    actor = build_episode_actor_records(
        SimpleNamespace(
            id=1234,
            create_time="2026-06-25 18:00:00",
            end_time="2026-06-25 18:03:00",
            state="EpisodeState.COMPLETED",
            type="EpisodeType.EPISODE_TYPE_PUBLIC",
            agents=[_agent(54048478, 0, -1), _agent(54099999, 1, 1, team_name="Opponent")],
        ),
        replay_path=replay_path,
        submissions_by_id={54048478: submission},
        own_team_id=16395686,
    )

    report = write_loss_dataset(
        output_dir=tmp_path / "dataset",
        submissions=[submission],
        actor_records=actor,
        meta_snapshot={"date": "2026-06-24", "source": {"datasetUrl": "https://example.invalid/dataset"}},
        command="pytest",
    )

    assert report["decision_rows"] == 1
    assert report["heuristic_patch_rows"] == 1
    assert Path(report["paths"]["decision_labels_jsonl"]).exists()
    patch_rows = Path(report["paths"]["heuristic_patch_map_jsonl"]).read_text(encoding="utf-8").splitlines()
    assert len(patch_rows) == 1
    patch_payload = json.loads(patch_rows[0])
    assert patch_payload["step_index"] == 1
    assert patch_payload["source_action"] == [1]
    assert patch_payload["teacher_action"]
    assert patch_payload["matchup_tag"] == "dragapult_spread"
    assert patch_payload["research_role"] == "loss_correction_patch"
    assert "Kaggle submission made: no" in Path(report["paths"]["markdown_report"]).read_text(encoding="utf-8")
