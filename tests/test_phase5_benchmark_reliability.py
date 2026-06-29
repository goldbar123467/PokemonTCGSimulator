from __future__ import annotations

import csv
import json
import tarfile
from pathlib import Path

from ptcg.benchmark_compatibility import check_result_compatibility
from ptcg.benchmark_league import _aggregate_matchups, select_pending_scheduled_games
from ptcg.failure_taxonomy import classify_failure
from ptcg.historical_calibration import run_historical_calibration


def _write_archive(root: Path, name: str) -> Path:
    package = root / name
    package.mkdir()
    (package / "main.py").write_text(
        "DECK = [9] * 60\n"
        "def agent(obs, config=None):\n"
        "    if isinstance(obs, dict) and obs.get('select') is None:\n"
        "        return DECK\n"
        "    return [0]\n",
        encoding="utf-8",
    )
    (package / "deck.csv").write_text("\n".join("9" for _ in range(60)) + "\n", encoding="utf-8")
    cg = package / "cg"
    cg.mkdir()
    (cg / "__init__.py").write_text("", encoding="utf-8")
    (cg / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = root / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))
    return archive


def _sha(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_result_dir(root: Path, *, archive: Path, config: Path, config_hash: str = "CONFIG") -> Path:
    root.mkdir(parents=True)
    (root / "opponent_registry.json").write_text('[{"name":"lucario","available":true}]\n', encoding="utf-8")
    (root / "seed_schedule.json").write_text(
        json.dumps(
            {
                "games_per_matchup": 1,
                "games": [
                    {
                        "matchup_id": "candidate__vs__lucario",
                        "candidate": "candidate",
                        "opponent": "lucario",
                        "game_index": 0,
                        "seed": 7,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (root / "results_by_matchup.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "matchup_id",
                "candidate",
                "opponent",
                "games",
                "finished",
                "wins",
                "losses",
                "draws",
                "errors",
                "invalid_actions",
                "timeouts",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "matchup_id": "candidate__vs__lucario",
                "candidate": "candidate",
                "opponent": "lucario",
                "games": 1,
                "finished": 1,
                "wins": 1,
                "losses": 0,
                "draws": 0,
                "errors": 0,
                "invalid_actions": 0,
                "timeouts": 0,
            }
        )
    summary = {
        "workflow": "benchmark_league_v1",
        "benchmark_schema_version": "benchmark_league_v2",
        "candidate_archive": str(archive.resolve()),
        "candidate_archive_sha256": _sha(archive),
        "config_path": str(config.resolve()),
        "benchmark_config_sha256": config_hash,
        "opponent_registry_sha256": None,
        "seed_schedule_sha256": None,
        "scheduled_games": 1,
        "finished_games": 1,
        "wins": 1,
        "losses": 0,
        "draws": 0,
        "errors": 0,
        "invalid_actions": 0,
        "timeouts": 0,
        "required_matchups": ["lucario"],
        "report_paths": {
            "summary": str((root / "summary.json").resolve()),
            "results_by_matchup": str((root / "results_by_matchup.csv").resolve()),
            "opponent_registry": str((root / "opponent_registry.json").resolve()),
            "seed_schedule": str((root / "seed_schedule.json").resolve()),
        },
        "kaggle_submission_made": False,
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return root


def test_result_reuse_rejects_config_hash_mismatch(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "candidate")
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    result_dir = _write_result_dir(tmp_path / "result", archive=archive, config=config, config_hash="OLD")

    status = check_result_compatibility(
        result_dir=result_dir,
        archive=archive,
        config_path=config,
        expected_config_sha256="NEW",
        required_matchups=["lucario"],
    )

    assert status["compatible"] is False
    assert any(check["name"] == "benchmark_config_sha256" and not check["passed"] for check in status["checks"])


def test_result_reuse_accepts_compatible_completed_results(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "candidate")
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    result_dir = _write_result_dir(tmp_path / "result", archive=archive, config=config, config_hash="MATCH")

    status = check_result_compatibility(
        result_dir=result_dir,
        archive=archive,
        config_path=config,
        expected_config_sha256="MATCH",
        required_matchups=["lucario"],
    )

    assert status["compatible"] is True


def test_failure_taxonomy_records_expected_categories() -> None:
    assert classify_failure("validation", "ArchiveValidationError", "archive missing required members") == "archive_validation_error"
    assert classify_failure("game", "invalid_action", "duplicate option indexes are not legal") == "invalid_action"
    assert classify_failure("game", "timeout", "max_steps") == "timeout"
    assert classify_failure("game", "ImportError", "No module named cg") == "import_error"


def test_run_until_n_does_not_double_count_completed_games() -> None:
    schedule = [
        {"matchup_id": "a__vs__b", "game_index": 0, "seed": 1},
        {"matchup_id": "a__vs__b", "game_index": 1, "seed": 2},
        {"matchup_id": "a__vs__b", "game_index": 2, "seed": 3},
    ]
    existing = [
        {"matchup_id": "a__vs__b", "game_index": "0", "finished": "True", "result": "win"},
        {"matchup_id": "a__vs__b", "game_index": "0", "finished": "True", "result": "win"},
    ]

    selected = select_pending_scheduled_games(schedule, existing, target_games_per_matchup=2)

    assert [row["game_index"] for row in selected] == [1]


def test_resumed_csv_false_strings_do_not_count_as_errors() -> None:
    rows = [
        {
            "matchup_id": "a__vs__b",
            "candidate": "a",
            "opponent": "b",
            "game_index": "0",
            "finished": "True",
            "result": "win",
            "turns": "10",
            "error": "False",
            "invalid_action": "False",
            "timeout": "False",
            "prizes_taken": "6",
            "prizes_allowed": "0",
            "prize_differential": "6",
            "early_loss": "False",
            "no_progress": "False",
            "timeout_adjacent_long_game": "False",
            "invalid_action_type": "",
        }
    ]

    matchup = _aggregate_matchups(rows)[0]

    assert matchup["errors"] == 0
    assert matchup["invalid_actions"] == 0
    assert matchup["timeouts"] == 0
    assert matchup["invalid_action_rate"] == 0.0


def test_historical_calibration_handles_unknown_labels_as_inconclusive(tmp_path: Path) -> None:
    known = _write_archive(tmp_path, "known")
    unknown = _write_archive(tmp_path, "unknown")
    registry = tmp_path / "archive_registry.json"
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": [
                    {
                        "name": "known",
                        "archive_path": str(known),
                        "archive_sha256": _sha(known),
                        "role": "historical",
                        "known_public_score": 900.0,
                        "known_private_score": None,
                        "known_local_score": None,
                        "eligible_for_calibration": True,
                    },
                    {
                        "name": "unknown",
                        "archive_path": str(unknown),
                        "archive_sha256": _sha(unknown),
                        "role": "unknown",
                        "known_public_score": None,
                        "known_private_score": None,
                        "known_local_score": None,
                        "eligible_for_calibration": True,
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    gate = tmp_path / "gate.json"
    gate.write_text('{"required_hard_gate_opponents":[]}\n', encoding="utf-8")

    report = run_historical_calibration(
        registry_path=registry,
        config_path=config,
        gate_path=gate,
        output_dir=tmp_path / "calibration",
        load_only=True,
    )

    assert report["summary"]["status"] == "completed"
    assert report["summary"]["pair_status_counts"]["INCONCLUSIVE"] >= 1
    assert Path(report["report_paths"]["calibration_pairs"]).exists()
    assert Path(report["report_paths"]["archive_registry_resolved"]).exists()
