from __future__ import annotations

import csv
import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from ptcg.benchmark_compatibility import BENCHMARK_SCHEMA_VERSION, benchmark_config_hash
from ptcg.benchmark_comparison import compare_candidate_archives, load_gate_policy
from ptcg.benchmark_index import benchmark_run_id, update_benchmark_index


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


def _write_benchmark_result(
    root: Path,
    *,
    archive: Path,
    rows: list[dict[str, object]],
    unavailable: list[str] | None = None,
    config_path: Path | None = None,
) -> Path:
    root.mkdir(parents=True)
    fieldnames = [
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
        "win_rate",
        "non_loss_rate",
        "average_turns",
        "prize_progress_available",
    ]
    with (root / "results_by_matchup.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**{name: "" for name in fieldnames}, **row})
    total_games = sum(int(row["games"]) for row in rows)
    finished = sum(int(row["finished"]) for row in rows)
    wins = sum(int(row["wins"]) for row in rows)
    losses = sum(int(row["losses"]) for row in rows)
    draws = sum(int(row.get("draws", 0)) for row in rows)
    errors = sum(int(row.get("errors", 0)) for row in rows)
    invalid = sum(int(row.get("invalid_actions", 0)) for row in rows)
    timeouts = sum(int(row.get("timeouts", 0)) for row in rows)
    config_hash = benchmark_config_hash(config_path or root / "config.json")
    seed_schedule_path = root / "seed_schedule.json"
    opponent_registry_path = root / "opponent_registry.json"
    seed_schedule_path.write_text(
        json.dumps({"games": [{"seed": index} for index in range(total_games)]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    opponent_registry_path.write_text(
        json.dumps(
            [
                {"name": str(row["opponent"]), "available": True}
                for row in rows
            ]
            + [{"name": name, "available": False} for name in (unavailable or [])],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "workflow": "benchmark_league_v1",
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "status": "completed",
        "candidate_archive": str(archive.resolve()),
        "candidate_archive_sha256": _sha256_file(archive),
        "config_path": str((config_path or root / "config.json").resolve()),
        "benchmark_config_sha256": config_hash,
        "opponent_registry_sha256": _sha256_file(opponent_registry_path),
        "seed_schedule_sha256": _sha256_file(seed_schedule_path),
        "scheduled_games": total_games,
        "finished_games": finished,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "errors": errors,
        "invalid_actions": invalid,
        "timeouts": timeouts,
        "unavailable_opponent_count": len(unavailable or []),
        "unavailable_opponents": [{"name": name, "available": False} for name in (unavailable or [])],
        "required_matchups": sorted({str(row["opponent"]) for row in rows} | set(unavailable or [])),
        "report_paths": {
            "summary": str((root / "summary.json").resolve()),
            "results_by_matchup": str((root / "results_by_matchup.csv").resolve()),
            "opponent_registry": str(opponent_registry_path.resolve()),
            "seed_schedule": str(seed_schedule_path.resolve()),
        },
        "kaggle_submission_made": False,
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return root


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_gate(path: Path, **overrides: object) -> Path:
    policy = {
        "version": 1,
        "minimum_total_games": 20,
        "minimum_games_per_required_matchup": 10,
        "maximum_invalid_action_rate": 0.0,
        "maximum_timeout_rate": 0.0,
        "maximum_crash_rate": 0.0,
        "minimum_aggregate_win_rate_delta_vs_baseline": 0.0,
        "minimum_candidate_lower_ci": 0.30,
        "required_hard_gate_opponents": ["lucario"],
        "allowed_unavailable_optional_opponents": ["optional_missing"],
        "maximum_required_matchup_regression": -0.05,
        "random_opponent_names": ["random"],
    }
    policy.update(overrides)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_compare_candidate_archives_from_loaded_results_writes_outputs_and_deltas(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate")
    baseline = _write_archive(tmp_path, "baseline")
    gate = _write_gate(tmp_path / "gate.json", minimum_candidate_lower_ci=0.20)
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    candidate_results = _write_benchmark_result(
        tmp_path / "candidate_results",
        archive=candidate,
        rows=[
            {"matchup_id": "c_vs_random", "candidate": "candidate", "opponent": "random", "games": 10, "finished": 10, "wins": 8, "losses": 2, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0},
            {"matchup_id": "c_vs_lucario", "candidate": "candidate", "opponent": "lucario", "games": 10, "finished": 10, "wins": 5, "losses": 5, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0},
        ],
        config_path=config,
    )
    baseline_results = _write_benchmark_result(
        tmp_path / "baseline_results",
        archive=baseline,
        rows=[
            {"matchup_id": "b_vs_random", "candidate": "baseline", "opponent": "random", "games": 10, "finished": 10, "wins": 5, "losses": 5, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0},
            {"matchup_id": "b_vs_lucario", "candidate": "baseline", "opponent": "lucario", "games": 10, "finished": 10, "wins": 4, "losses": 6, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0},
        ],
        config_path=config,
    )

    report = compare_candidate_archives(
        candidate_archive=candidate,
        baseline_archive=baseline,
        benchmark_config_path=config,
        gate_config_path=gate,
        output_dir=tmp_path / "comparison",
        candidate_results_dir=candidate_results,
        baseline_results_dir=baseline_results,
        index_path=tmp_path / "benchmark_index.json",
        command="pytest comparison",
    )

    assert report["decision"]["status"] == "PASS"
    assert Path(report["report_paths"]["candidate_summary"]).exists()
    assert Path(report["report_paths"]["baseline_summary"]).exists()
    assert Path(report["report_paths"]["comparison_by_matchup"]).exists()
    assert Path(report["report_paths"]["comparison_summary"]).exists()
    assert Path(report["report_paths"]["decision"]).exists()

    rows = list(csv.DictReader(Path(report["report_paths"]["comparison_by_matchup"]).open(newline="", encoding="utf-8")))
    lucario = next(row for row in rows if row["opponent"] == "lucario")
    assert float(lucario["win_rate_delta"]) == pytest.approx(0.1)
    assert {"candidate_lower_ci", "candidate_upper_ci", "baseline_lower_ci", "baseline_upper_ci"} <= set(lucario)
    summary = json.loads(Path(report["report_paths"]["comparison_summary"]).read_text(encoding="utf-8"))
    assert summary["aggregate"]["candidate"]["games"] == 20
    assert summary["aggregate"]["candidate"]["invalid_action_rate"] == 0.0
    assert summary["aggregate_delta"]["win_rate_delta"] == pytest.approx(0.2)


def test_benchmark_gate_fails_on_too_few_games(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate")
    baseline = _write_archive(tmp_path, "baseline")
    gate = _write_gate(tmp_path / "gate.json", minimum_total_games=100)
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    rows = [{"matchup_id": "vs_lucario", "candidate": "x", "opponent": "lucario", "games": 10, "finished": 10, "wins": 6, "losses": 4, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0}]
    result_dir = _write_benchmark_result(tmp_path / "result", archive=candidate, rows=rows, config_path=config)
    baseline_dir = _write_benchmark_result(tmp_path / "baseline_result", archive=baseline, rows=rows, config_path=config)

    report = compare_candidate_archives(
        candidate_archive=candidate,
        baseline_archive=baseline,
        benchmark_config_path=config,
        gate_config_path=gate,
        output_dir=tmp_path / "comparison",
        candidate_results_dir=result_dir,
        baseline_results_dir=baseline_dir,
        index_path=tmp_path / "benchmark_index.json",
    )

    assert report["decision"]["status"] == "FAIL"
    assert any(check["reason"] == "minimum_total_games" for check in report["decision"]["checks"])


def test_benchmark_gate_fails_on_invalid_actions_and_timeout_crash_regression(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate")
    baseline = _write_archive(tmp_path, "baseline")
    gate = _write_gate(tmp_path / "gate.json")
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    candidate_rows = [{"matchup_id": "vs_lucario", "candidate": "candidate", "opponent": "lucario", "games": 20, "finished": 17, "wins": 12, "losses": 5, "draws": 0, "errors": 3, "invalid_actions": 1, "timeouts": 1}]
    baseline_rows = [{"matchup_id": "vs_lucario", "candidate": "baseline", "opponent": "lucario", "games": 20, "finished": 20, "wins": 10, "losses": 10, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0}]
    candidate_dir = _write_benchmark_result(tmp_path / "candidate_result", archive=candidate, rows=candidate_rows, config_path=config)
    baseline_dir = _write_benchmark_result(tmp_path / "baseline_result", archive=baseline, rows=baseline_rows, config_path=config)

    report = compare_candidate_archives(
        candidate_archive=candidate,
        baseline_archive=baseline,
        benchmark_config_path=config,
        gate_config_path=gate,
        output_dir=tmp_path / "comparison",
        candidate_results_dir=candidate_dir,
        baseline_results_dir=baseline_dir,
        index_path=tmp_path / "benchmark_index.json",
    )

    assert report["decision"]["status"] == "FAIL"
    reasons = {check["reason"] for check in report["decision"]["checks"]}
    assert "invalid_action_rate" in reasons
    assert "timeout_regression" in reasons
    assert "crash_regression" in reasons


def test_benchmark_gate_is_inconclusive_when_required_opponent_unavailable(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate")
    baseline = _write_archive(tmp_path, "baseline")
    gate = _write_gate(tmp_path / "gate.json", required_hard_gate_opponents=["lucario"])
    config = tmp_path / "benchmark.json"
    config.write_text('{"opponents":[]}\n', encoding="utf-8")
    rows = [{"matchup_id": "vs_random", "candidate": "x", "opponent": "random", "games": 20, "finished": 20, "wins": 15, "losses": 5, "draws": 0, "errors": 0, "invalid_actions": 0, "timeouts": 0}]
    candidate_dir = _write_benchmark_result(tmp_path / "candidate_result", archive=candidate, rows=rows, unavailable=["lucario"], config_path=config)
    baseline_dir = _write_benchmark_result(tmp_path / "baseline_result", archive=baseline, rows=rows, unavailable=["lucario"], config_path=config)

    report = compare_candidate_archives(
        candidate_archive=candidate,
        baseline_archive=baseline,
        benchmark_config_path=config,
        gate_config_path=gate,
        output_dir=tmp_path / "comparison",
        candidate_results_dir=candidate_dir,
        baseline_results_dir=baseline_dir,
        index_path=tmp_path / "benchmark_index.json",
    )

    assert report["decision"]["status"] == "INCONCLUSIVE"
    assert any(check["reason"] == "required_opponent_unavailable" for check in report["decision"]["checks"])


def test_benchmark_index_writes_valid_json_and_stable_run_id(tmp_path: Path) -> None:
    schedule = tmp_path / "seed_schedule.json"
    schedule.write_text('{"games":[{"seed":1}]}\n', encoding="utf-8")
    summary = {
        "candidate_archive": "artifacts/candidate.tar.gz",
        "candidate_archive_sha256": "ABC",
        "config_path": "configs/benchmark_league.json",
        "scheduled_games": 20,
        "wins": 12,
        "finished_games": 20,
        "errors": 0,
        "invalid_actions": 0,
        "timeouts": 0,
        "report_paths": {"summary": "artifacts/benchmarks/run/summary.json", "seed_schedule": str(schedule)},
    }

    first = update_benchmark_index(tmp_path / "benchmark_index.json", summary)
    second = update_benchmark_index(tmp_path / "benchmark_index.json", summary)

    assert first["run_id"] == second["run_id"]
    assert first["run_id"] == benchmark_run_id(summary)
    payload = json.loads((tmp_path / "benchmark_index.json").read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["aggregate_win_rate"] == 0.6


def test_load_gate_policy_requires_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "bad_gate.json"
    path.write_text('{"minimum_total_games": 10}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="missing gate policy"):
        load_gate_policy(path)
