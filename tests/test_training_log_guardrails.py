from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg.gameplay_log_guard import GameplayLogGateError, assert_training_gameplay_logs_allowed
from ptcg.gameplay_log_hygiene import build_manifest, filter_current_logs, write_manifest


def _write_replay(path: Path, *, episode_id: int = 1, action: list[int] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "info": {"EpisodeId": episode_id},
                "steps": [
                    [
                        {
                            "observation": {
                                "search_begin_input": "state",
                                "select": {
                                    "minCount": 1,
                                    "maxCount": 1,
                                    "option": [{"type": 1}, {"type": 2}],
                                },
                            },
                            "action": action or [0],
                        }
                    ]
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_config(project: Path) -> Path:
    config = {
        "workflow": "no_rl_kaggle_readiness",
        "random_seed": 0,
        "gameplay_schema_version": "kaggle_episode_steps_v1",
        "current_gameplay_min_date": "2026-06-27",
        "data_root": "data/kaggle_public_leaderboard",
        "gameplay_manifest": "data_manifest/gameplay_logs.json",
        "current_gameplay_allowlist": "data_manifest/current_gameplay_logs.txt",
        "artifact_root": "artifacts",
        "readiness_output_root": "artifacts/kaggle_readiness",
        "kaggle_input_root": "/kaggle/input",
        "kaggle_working_root": "/kaggle/working",
        "kaggle_submission_path": "/kaggle/working/submission.csv",
        "submission_allowed_without_user_approval": False,
    }
    path = project / "configs" / "current_workflow.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def _write_manifest_and_allowlist(project: Path, replay_paths: list[Path]) -> tuple[Path, Path]:
    manifest = build_manifest(
        roots=[project / "data" / "kaggle_public_leaderboard"],
        project_root=project,
        current_min_date="2026-06-27",
    )
    manifest_path = project / "data_manifest" / "gameplay_logs.json"
    allowlist_path = project / "data_manifest" / "current_gameplay_logs.txt"
    write_manifest(manifest_path, manifest)
    allowed = filter_current_logs(manifest)
    if replay_paths:
        allowed = [path.relative_to(project).as_posix() for path in replay_paths]
    allowlist_path.write_text("".join(f"{path}\n" for path in allowed), encoding="utf-8")
    return manifest_path, allowlist_path


def test_training_gate_accepts_valid_current_log_fixture(tmp_path: Path) -> None:
    _write_config(tmp_path)
    replay = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    _write_replay(replay)
    _write_manifest_and_allowlist(tmp_path, [])

    allowed = assert_training_gameplay_logs_allowed(project_root=tmp_path)

    assert allowed == [replay]


def test_training_gate_refuses_missing_manifest_and_does_not_fallback_to_globbing(tmp_path: Path) -> None:
    _write_config(tmp_path)
    _write_replay(
        tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    )

    with pytest.raises(GameplayLogGateError, match="missing gameplay manifest"):
        assert_training_gameplay_logs_allowed(project_root=tmp_path)


@pytest.mark.parametrize(
    ("bad_part", "message"),
    [
        ("logs/quarantine/duplicate_replays/2026-06-28_submission_1/episode_1/episode-1-replay.json", "quarantine"),
        ("logs/archived/old_public_replays/2026-06-25_first_two/episode_1/episode-1-replay.json", "archived"),
        ("data/kaggle_public_leaderboard/duplicate_replays/2026-06-28_submission_1/episode_1/episode-1-replay.json", "duplicate"),
    ],
)
def test_training_gate_refuses_blocked_path_segments(tmp_path: Path, bad_part: str, message: str) -> None:
    _write_config(tmp_path)
    current = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    _write_replay(current)
    bad = tmp_path / bad_part
    _write_replay(bad)
    _write_manifest_and_allowlist(tmp_path, [bad])

    with pytest.raises(GameplayLogGateError, match=message):
        assert_training_gameplay_logs_allowed(project_root=tmp_path)


def test_training_gate_refuses_schema_mismatch(tmp_path: Path) -> None:
    _write_config(tmp_path)
    replay = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    _write_replay(replay)
    manifest_path, _ = _write_manifest_and_allowlist(tmp_path, [])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["current_gameplay_schema_version"] = "old_schema"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(GameplayLogGateError, match="schema"):
        assert_training_gameplay_logs_allowed(project_root=tmp_path)


def test_training_gate_refuses_allowlist_stale_relative_to_manifest(tmp_path: Path) -> None:
    _write_config(tmp_path)
    replay = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    _write_replay(replay)
    manifest_path, allowlist_path = _write_manifest_and_allowlist(tmp_path, [])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["allowlist"] = {"path": "data_manifest/current_gameplay_logs.txt", "file_count": 2}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    allowlist_path.write_text(replay.relative_to(tmp_path).as_posix() + "\n", encoding="utf-8")

    with pytest.raises(GameplayLogGateError, match="allowlist"):
        assert_training_gameplay_logs_allowed(project_root=tmp_path)


def test_training_gate_refuses_allowlist_hash_mismatch(tmp_path: Path) -> None:
    _write_config(tmp_path)
    replay = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    _write_replay(replay)
    manifest_path, allowlist_path = _write_manifest_and_allowlist(tmp_path, [])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["allowlist"] = {
        "path": "data_manifest/current_gameplay_logs.txt",
        "file_count": 1,
        "file_size": allowlist_path.stat().st_size,
        "sha256": "BAD",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(GameplayLogGateError, match="allowlist"):
        assert_training_gameplay_logs_allowed(project_root=tmp_path)
