from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path


def _write_archive(root: Path, name: str, *, include_cg: bool = False) -> Path:
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
    if include_cg:
        cg = package / "cg"
        cg.mkdir()
        (cg / "__init__.py").write_text("", encoding="utf-8")
        (cg / "api.py").write_text("def to_observation_class(obs):\n    return obs\n", encoding="utf-8")
    archive = root / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))
    return archive


def test_train_cli_is_kaggle_readiness_not_legacy_training() -> None:
    completed = subprocess.run(
        [sys.executable, "train.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Kaggle readiness" in completed.stdout
    assert "behavior clone" not in completed.stdout.lower()
    assert "--rl-games" not in completed.stdout


def test_train_cli_writes_registry_only_no_submit_summary(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "agent")
    output_dir = tmp_path / "readiness"

    completed = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--archive",
            str(archive),
            "--output-dir",
            str(output_dir),
            "--registry-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

    assert payload["kaggle_submission_made"] is False
    assert payload["package_count"] == 1
    assert payload["matchup_count"] == 0
    assert summary["workflow"] == "kaggle_readiness"
    assert summary["kaggle_submission_made"] is False
    assert summary["official_sdk_seed_control"] is False
    assert summary["crn_available"] is False
    assert summary["sample_model"] == "independent_batch"
    assert summary["report_paths"]["submission_registry"] == str((output_dir / "submission_registry.json").resolve())


def test_train_cli_refuses_to_run_without_configured_gameplay_allowlist(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "agent")
    config = tmp_path / "current_workflow.json"
    config.write_text(
        json.dumps(
            {
                "workflow": "no_rl_kaggle_readiness",
                "random_seed": 0,
                "gameplay_schema_version": "kaggle_episode_steps_v1",
                "current_gameplay_min_date": "2026-06-27",
                "data_root": "data/kaggle_public_leaderboard",
                "gameplay_manifest": "data_manifest/missing_manifest.json",
                "current_gameplay_allowlist": "data_manifest/missing_allowlist.txt",
                "artifact_root": "artifacts",
                "readiness_output_root": "artifacts/kaggle_readiness",
                "kaggle_input_root": "/kaggle/input",
                "kaggle_working_root": "/kaggle/working",
                "kaggle_submission_path": "/kaggle/working/submission.csv",
                "submission_allowed_without_user_approval": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--archive",
            str(archive),
            "--output-dir",
            str(tmp_path / "readiness"),
            "--registry-only",
            "--workflow-config",
            str(config),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "missing gameplay manifest" in completed.stderr


def test_train_cli_writes_round_robin_no_submit_summary(tmp_path: Path) -> None:
    archive_a = _write_archive(tmp_path, "alpha")
    archive_b = _write_archive(tmp_path, "beta")
    output_dir = tmp_path / "round_robin"

    completed = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--archive",
            str(archive_a),
            "--archive",
            str(archive_b),
            "--output-dir",
            str(output_dir),
            "--games-per-pair",
            "1",
            "--max-steps",
            "4",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

    assert payload["kaggle_submission_made"] is False
    assert payload["package_count"] == 2
    assert payload["eligible_package_count"] == 2
    assert payload["matchup_count"] == 2
    assert summary["workflow"] == "kaggle_readiness"
    assert summary["official_sdk_seed_control"] is False
    assert summary["crn_available"] is False
    assert summary["sample_model"] == "independent_batch"


def test_train_cli_can_orchestrate_benchmark_league_without_bypassing_guard(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate", include_cg=True)
    opponent = _write_archive(tmp_path, "opponent", include_cg=True)
    config = tmp_path / "benchmark_league.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "games_per_matchup": 2,
                "seed_list": [31, 32],
                "max_steps": 4,
                "opponents": [{"name": "opponent", "kind": "archive", "archive": str(opponent)}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "benchmark_readiness"

    completed = subprocess.run(
        [
            sys.executable,
            "train.py",
            "--archive",
            str(candidate),
            "--output-dir",
            str(output_dir),
            "--run-benchmark",
            "--benchmark-config",
            str(config),
            "--seeds",
            "31,32",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

    assert payload["kaggle_submission_made"] is False
    assert payload["matchup_count"] == 1
    assert summary["workflow"] == "kaggle_readiness"
    assert summary["gameplay_log_gate"] == "data_manifest/current_gameplay_logs.txt"
    assert summary["benchmark"]["scheduled_games"] == 2
    assert summary["benchmark"]["kaggle_submission_made"] is False
    assert (output_dir / "benchmark_league" / "results_by_game.csv").exists()
