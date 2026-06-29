from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from ptcg.hop_strategy_report import (
    build_hop_strategy_rows,
    choose_latest_completed_episode,
    choose_latest_completed_episodes,
    select_latest_complete_submissions,
    summarize_hop_strategy,
    write_hop_strategy_report_bundle,
)
from ptcg.kaggle_loss_mining import SubmissionRecord


def _submission(ref: int, date: str, *, status: str = "complete", score: float = 700.0) -> SubmissionRecord:
    return SubmissionRecord(
        submission_id=ref,
        file_name=f"submission_{ref}.tar.gz",
        status=status,
        public_score=score,
        private_score=None,
        error_description=None,
        description="hop test",
        team_name="Clark Kitchen",
        submitted_by="clark",
        total_bytes=42,
        date=date,
        agent_family=f"submission-{ref}",
    )


def _agent(submission_id: int, index: int = 0, reward: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        submission_id=submission_id,
        index=index,
        reward=reward,
        team_name="Clark Kitchen" if submission_id < 900 else "Opponent",
        team_id=123 if submission_id < 900 else 999,
    )


def _episode(
    episode_id: int,
    submission_id: int,
    end_time: str,
    *,
    state: str = "EpisodeState.COMPLETED",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=episode_id,
        create_time=end_time,
        end_time=end_time,
        state=state,
        agents=[_agent(submission_id, index=0, reward=1), _agent(999001, index=1, reward=-1)],
    )


def test_select_latest_complete_submissions_sorts_by_submission_date() -> None:
    records = [
        _submission(10, "2026-06-27 01:00:00"),
        _submission(20, "2026-06-28 02:00:00"),
        _submission(30, "2026-06-28 03:00:00"),
        _submission(40, "2026-06-28 04:00:00", status="error"),
    ]

    selected = select_latest_complete_submissions(records, limit=2)

    assert [record.submission_id for record in selected] == [30, 20]


def test_choose_latest_completed_episode_requires_own_agent() -> None:
    episodes = [
        _episode(100, 30, "2026-06-28 01:00:00"),
        _episode(200, 31, "2026-06-28 03:00:00"),
        _episode(300, 30, "2026-06-28 02:00:00", state="EpisodeState.RUNNING"),
        _episode(400, 30, "2026-06-28 02:30:00"),
    ]

    selected = choose_latest_completed_episode(episodes, submission_id=30)

    assert selected is not None
    assert selected.id == 400


def test_choose_latest_completed_episodes_returns_last_n_for_submission() -> None:
    episodes = [
        _episode(100, 30, "2026-06-28 01:00:00"),
        _episode(200, 30, "2026-06-28 04:00:00"),
        _episode(300, 31, "2026-06-28 05:00:00"),
        _episode(400, 30, "2026-06-28 03:00:00"),
        _episode(500, 30, "2026-06-28 02:00:00", state="EpisodeState.RUNNING"),
    ]

    selected = choose_latest_completed_episodes(episodes, submission_id=30, limit=2)

    assert [episode.id for episode in selected] == [200, 400]


def test_build_hop_strategy_rows_adds_provenance_and_strategy_intents() -> None:
    decision_rows = [
        {
            "episode_id": 824,
            "replay_id": "824",
            "step_index": 12,
            "action_step_index": 13,
            "submission_id": 541,
            "agent_family": "submission-hop",
            "team_name": "Clark Kitchen",
            "opponent_team_name": "Opponent",
            "data_source": "kaggle_public_episode",
            "actor_index": 0,
            "agent_index": 0,
            "opponent_index": 1,
            "outcome": "win",
            "winner_side": 0,
            "matchup_tag": "lucario",
            "actor_archetype": "hop_trevenant",
            "opponent_archetype": "lucario",
            "chosen_action": [0],
            "teacher_action": [0],
            "teacher_agrees": True,
            "selected_labels": ["trap_active"],
            "selected_penalties": [],
            "teacher_labels": ["trap_active"],
            "teacher_penalties": [],
            "pipeline_labels": ["stall_or_denial", "gust_target"],
            "flaw_tags": [],
            "sample_weight": 1.0,
            "legal_actions": [{"type": 13, "attackId": 1267}],
            "leaderboard_score": 794.6,
        }
    ]

    rows = build_hop_strategy_rows(
        decision_rows,
        source_file_by_replay_id={"824": "artifacts/raw/episode-824-replay.json"},
        source_hash_by_replay_id={"824": "abc123"},
        log_paths_by_episode_id={824: ["artifacts/raw/episode-824-agent-0.log"]},
    )

    assert rows[0]["actor_owner_label"] == "clark_kitchen"
    assert rows[0]["source_hash"] == "abc123"
    assert rows[0]["agent_log_paths"] == ["artifacts/raw/episode-824-agent-0.log"]
    assert "corner_trap_lock" in rows[0]["hop_strategy_intents"]
    assert "hop_trevenant_control" in rows[0]["hop_strategy_tags"]


def test_summarize_and_write_report_bundle(tmp_path: Path) -> None:
    rows = build_hop_strategy_rows(
        [
            {
                "episode_id": 824,
                "replay_id": "824",
                "step_index": 12,
                "submission_id": 541,
                "agent_family": "submission-hop",
                "team_name": "Clark Kitchen",
                "opponent_team_name": "Opponent",
                "data_source": "kaggle_public_episode",
                "actor_index": 0,
                "opponent_index": 1,
                "outcome": "loss",
                "winner_side": 1,
                "matchup_tag": "dragapult_spread",
                "actor_archetype": "hop_trevenant",
                "opponent_archetype": "dragapult_spread",
                "chosen_action": [0],
                "teacher_action": [1],
                "teacher_agrees": False,
                "selected_labels": ["setup_next_attacker"],
                "selected_penalties": ["active_overattach"],
                "teacher_labels": ["setup_next_attacker"],
                "teacher_penalties": [],
                "pipeline_labels": ["setup", "bench_develop"],
                "flaw_tags": ["active_overattach"],
                "sample_weight": 2.0,
                "legal_actions": [{"type": 8, "inPlayArea": 4}],
                "leaderboard_score": 784.0,
            }
        ]
        * 2
        + [
            {
                "episode_id": 825,
                "replay_id": "825",
                "step_index": 4,
                "submission_id": 542,
                "agent_family": "submission-hop-b",
                "team_name": "Clark Kitchen",
                "opponent_team_name": "Opponent B",
                "data_source": "kaggle_public_episode",
                "actor_index": 1,
                "opponent_index": 0,
                "outcome": "win",
                "winner_side": 1,
                "matchup_tag": "alakazam",
                "actor_archetype": "hop_trevenant",
                "opponent_archetype": "alakazam",
                "chosen_action": [0],
                "teacher_action": [0],
                "teacher_agrees": True,
                "selected_labels": ["trap_active"],
                "selected_penalties": [],
                "teacher_labels": ["trap_active"],
                "teacher_penalties": [],
                "pipeline_labels": ["stall_or_denial", "gust_target"],
                "flaw_tags": [],
                "sample_weight": 1.0,
                "legal_actions": [{"type": 13, "attackId": 1267}],
                "leaderboard_score": 794.0,
            }
        ],
        source_file_by_replay_id={"824": "raw.json", "825": "raw-b.json"},
        source_hash_by_replay_id={"824": "hash", "825": "hash-b"},
        log_paths_by_episode_id={824: ["agent.log"], 825: ["agent-b.log"]},
    )
    submissions = [
        _submission(541, "2026-06-28 03:00:00", score=784.0),
        _submission(542, "2026-06-28 04:00:00", score=794.0),
    ]
    meta = {
        "date": "2026-06-28",
        "latestDate": "2026-06-28",
        "redirected": False,
        "totalDecks": 100,
        "source": {"datasetUrl": "https://example.invalid/meta.json"},
    }

    summary = summarize_hop_strategy(
        strategy_rows=rows,
        submissions=submissions,
        meta_snapshot=meta,
        command="pytest",
        download_failures=[],
    )
    result = write_hop_strategy_report_bundle(summary=summary, strategy_rows=rows, output_dir=tmp_path)

    assert summary["selected_game_count"] == 2
    assert summary["outcome_counts"]["loss"] == 1
    assert summary["submission_summaries"]["541"]["game_count"] == 1
    assert summary["submission_summaries"]["541"]["decision_rows"] == 2
    assert summary["submission_summaries"]["542"]["outcome_counts"]["win"] == 1
    assert summary["kaggle_submission_made"] is False
    assert Path(result["markdown_report"]).exists()
    assert Path(result["summary_json"]).exists()
    assert Path(result["strategy_labels_jsonl"]).exists()
    assert result["figures"]
    text = Path(result["markdown_report"]).read_text(encoding="utf-8")
    assert "Kaggle submission made: `no`" in text
    assert "active_overattach" in text
    assert json.loads(Path(result["summary_json"]).read_text(encoding="utf-8"))["selected_game_count"] == 2


def test_multi_game_figures_keep_sane_dimensions(tmp_path: Path) -> None:
    rows = []
    for episode_id in range(1000, 1020):
        submission_id = 541 if episode_id < 1010 else 542
        rows.extend(
            build_hop_strategy_rows(
                [
                    {
                        "episode_id": episode_id,
                        "replay_id": str(episode_id),
                        "step_index": 1,
                        "submission_id": submission_id,
                        "agent_family": f"submission-hop-{submission_id}",
                        "team_name": "Clark Kitchen",
                        "opponent_team_name": "Very Long Opponent Name For Chart Layout",
                        "data_source": "kaggle_public_episode",
                        "actor_index": 0,
                        "opponent_index": 1,
                        "outcome": "win" if episode_id % 2 else "loss",
                        "winner_side": 0,
                        "matchup_tag": "hop_trevenant",
                        "actor_archetype": "hop_trevenant",
                        "opponent_archetype": "hop_trevenant",
                        "chosen_action": [0],
                        "teacher_action": [0],
                        "teacher_agrees": True,
                        "selected_labels": ["trap_active"],
                        "selected_penalties": [],
                        "teacher_labels": ["trap_active"],
                        "teacher_penalties": [],
                        "pipeline_labels": ["stall_or_denial"],
                        "flaw_tags": [],
                        "sample_weight": 1.0,
                        "legal_actions": [{"type": 13, "attackId": 1267}],
                        "leaderboard_score": 794.0,
                    }
                ],
                source_file_by_replay_id={str(episode_id): "raw.json"},
                source_hash_by_replay_id={str(episode_id): "hash"},
                log_paths_by_episode_id={episode_id: ["agent.log"]},
            )
        )
    summary = summarize_hop_strategy(
        strategy_rows=rows,
        submissions=[
            _submission(541, "2026-06-28 03:00:00", score=784.0),
            _submission(542, "2026-06-28 04:00:00", score=794.0),
        ],
        meta_snapshot={"date": "2026-06-28", "source": {}},
        command="pytest",
        download_failures=[],
    )

    result = write_hop_strategy_report_bundle(summary=summary, strategy_rows=rows, output_dir=tmp_path)

    for path in result["figures"].values():
        width, height = Image.open(path).size
        assert width <= 5000
        assert height <= 3000
