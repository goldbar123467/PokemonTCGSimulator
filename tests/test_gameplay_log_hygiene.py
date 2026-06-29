from __future__ import annotations

import json
from pathlib import Path

from ptcg.gameplay_log_hygiene import build_manifest, filter_current_logs, validate_manifest, write_current_log_allowlist


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


def test_build_manifest_classifies_current_stale_corrupt_and_duplicate_logs(tmp_path: Path) -> None:
    current = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    stale = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-25_first_two" / "episode_2" / "episode-2-replay.json"
    duplicate = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1_copy" / "episode_1" / "episode-1-replay.json"
    corrupt = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_bad" / "episode_bad" / "episode-bad-replay.json"
    _write_replay(current, episode_id=1)
    _write_replay(stale, episode_id=2)
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_text(current.read_text(encoding="utf-8"), encoding="utf-8")
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("{not-json", encoding="utf-8")

    manifest = build_manifest(
        roots=[tmp_path / "data" / "kaggle_public_leaderboard"],
        project_root=tmp_path,
        current_min_date="2026-06-27",
    )

    by_path = {row["relative_path"]: row for row in manifest["logs"]}
    assert by_path["data/kaggle_public_leaderboard/2026-06-28_submission_1/episode_1/episode-1-replay.json"]["status"] == "current"
    assert by_path["data/kaggle_public_leaderboard/2026-06-25_first_two/episode_2/episode-2-replay.json"]["status"] == "archive"
    assert by_path["data/kaggle_public_leaderboard/2026-06-28_submission_1_copy/episode_1/episode-1-replay.json"]["status"] == "quarantine"
    assert by_path["data/kaggle_public_leaderboard/2026-06-28_submission_bad/episode_bad/episode-bad-replay.json"]["status"] == "quarantine"
    assert manifest["summary"]["current"] == 1
    assert manifest["summary"]["archive"] == 1
    assert manifest["summary"]["quarantine"] == 2
    assert manifest["kaggle_submission_made"] is False


def test_validate_manifest_fails_when_no_current_logs_exist(tmp_path: Path) -> None:
    stale = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-25_first_two" / "episode_2" / "episode-2-replay.json"
    _write_replay(stale, episode_id=2)
    manifest = build_manifest(
        roots=[tmp_path / "data" / "kaggle_public_leaderboard"],
        project_root=tmp_path,
        current_min_date="2026-06-27",
    )

    validation = validate_manifest(manifest)

    assert validation["ok"] is False
    assert "no_current_valid_logs" in validation["errors"]


def test_filter_current_logs_returns_only_current_valid_unique_replays(tmp_path: Path) -> None:
    current = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    stale = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-25_first_two" / "episode_2" / "episode-2-replay.json"
    _write_replay(current, episode_id=1)
    _write_replay(stale, episode_id=2)
    manifest = build_manifest(
        roots=[tmp_path / "data" / "kaggle_public_leaderboard"],
        project_root=tmp_path,
        current_min_date="2026-06-27",
    )

    filtered = filter_current_logs(manifest)

    assert filtered == ["data/kaggle_public_leaderboard/2026-06-28_submission_1/episode_1/episode-1-replay.json"]


def test_write_current_log_allowlist_updates_manifest_integrity_metadata(tmp_path: Path) -> None:
    current = tmp_path / "data" / "kaggle_public_leaderboard" / "2026-06-28_submission_1" / "episode_1" / "episode-1-replay.json"
    _write_replay(current, episode_id=1)
    manifest = build_manifest(
        roots=[tmp_path / "data" / "kaggle_public_leaderboard"],
        project_root=tmp_path,
        current_min_date="2026-06-27",
    )
    manifest_path = tmp_path / "data_manifest" / "gameplay_logs.json"
    allowlist_path = tmp_path / "data_manifest" / "current_gameplay_logs.txt"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_current_log_allowlist(manifest_path=manifest_path, allowlist_path=allowlist_path)

    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert allowlist_path.read_text(encoding="utf-8").splitlines() == [
        "data/kaggle_public_leaderboard/2026-06-28_submission_1/episode_1/episode-1-replay.json"
    ]
    assert updated_manifest["allowlist"]["path"] == "data_manifest/current_gameplay_logs.txt"
    assert updated_manifest["allowlist"]["file_count"] == 1
    assert updated_manifest["allowlist"]["file_size"] == allowlist_path.stat().st_size
    assert updated_manifest["allowlist"]["generated_at"]
