from __future__ import annotations

import csv
import json
import tarfile
from pathlib import Path

import pytest

from ptcg.benchmark_league import BenchmarkConfigError, run_benchmark_league


def _write_archive(root: Path, name: str, *, action_index: int = 0, include_cg: bool = True) -> Path:
    deck_ids = [673, 673, 674, 6, 1227] + [6] * 55
    package = root / name
    package.mkdir()
    (package / "main.py").write_text(
        f"DECK = {deck_ids!r}\n"
        + "def agent(obs, config=None):\n"
        + "    if isinstance(obs, dict) and obs.get('select') is None:\n"
        + "        return DECK\n"
        + f"    return [{action_index}]\n",
        encoding="utf-8",
    )
    (package / "deck.csv").write_text("\n".join(str(card_id) for card_id in deck_ids) + "\n", encoding="utf-8")
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


def test_benchmark_league_writes_required_artifacts_and_unavailable_opponents(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate", action_index=0)
    opponent = _write_archive(tmp_path, "opponent", action_index=0)
    config_path = tmp_path / "benchmark_league.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "games_per_matchup": 2,
                "seed_list": [21, 22],
                "max_steps": 4,
                "opponents": [
                    {"name": "stable_archive", "kind": "archive", "archive": str(opponent)},
                    {"name": "missing_dragapult", "kind": "archive", "archive": str(tmp_path / "missing.tar.gz")},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "bench"

    report = run_benchmark_league(
        archive=candidate,
        config_path=config_path,
        output_dir=output_dir,
        command="pytest benchmark",
    )

    for name in (
        "results_by_game.csv",
        "results_by_matchup.csv",
        "summary.json",
        "failures.json",
        "seed_schedule.json",
        "opponent_registry.json",
    ):
        assert (output_dir / name).exists()

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    schedule = json.loads((output_dir / "seed_schedule.json").read_text(encoding="utf-8"))
    registry = json.loads((output_dir / "opponent_registry.json").read_text(encoding="utf-8"))
    game_rows = list(csv.DictReader((output_dir / "results_by_game.csv").open(newline="", encoding="utf-8")))
    matchup_rows = list(csv.DictReader((output_dir / "results_by_matchup.csv").open(newline="", encoding="utf-8")))

    assert report["summary"]["kaggle_submission_made"] is False
    assert summary["status"] == "completed"
    assert summary["candidate_archive"] == str(candidate.resolve())
    assert summary["available_opponent_count"] == 1
    assert summary["unavailable_opponent_count"] == 1
    assert summary["unavailable_opponents"][0]["name"] == "missing_dragapult"
    assert summary["official_sdk_seed_control"] is False
    assert summary["crn_available"] is False
    assert schedule["explicit_seeds"] == [21, 22]
    assert len(schedule["games"]) == 2
    assert {row["name"] for row in registry} == {"stable_archive", "missing_dragapult"}
    assert len(game_rows) == 2
    assert len(matchup_rows) == 1
    assert game_rows[0]["seed"] == "21"
    assert game_rows[1]["seed"] == "22"
    assert {"lower_ci", "upper_ci", "invalid_action_rate", "timeout_rate", "crash_rate"} <= set(matchup_rows[0])
    assert {"games", "wins", "losses", "draws", "win_rate", "lower_ci", "upper_ci"} <= set(summary["aggregate_stats"])


def test_benchmark_league_rejects_broad_glob_config(tmp_path: Path) -> None:
    candidate = _write_archive(tmp_path, "candidate")
    config_path = tmp_path / "bad_benchmark_league.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "games_per_matchup": 1,
                "base_seed": 1,
                "archive_glob": "artifacts/*.tar.gz",
                "opponents": [{"name": "broad", "kind": "archive_glob", "archive_glob": "artifacts/*.tar.gz"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(BenchmarkConfigError, match="broad glob"):
        run_benchmark_league(archive=candidate, config_path=config_path, output_dir=tmp_path / "bench")
