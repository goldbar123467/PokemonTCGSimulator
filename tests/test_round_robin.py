from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from ptcg.round_robin import prepare_submission_packages, run_round_robin


def _write_main(path: Path, deck_ids: list[int], *, action_index: int = 0, import_cg: bool = False) -> None:
    import_line = (
        "import inspect, os, sys\n"
        "_FRAME = inspect.currentframe()\n"
        "_MODULE_FILE = globals().get('__file__') or (_FRAME.f_code.co_filename if _FRAME is not None else 'main.py')\n"
        "_ROOT = os.path.dirname(os.path.abspath(_MODULE_FILE))\n"
        "if _ROOT not in sys.path:\n"
        "    sys.path.insert(0, _ROOT)\n"
        "from cg.api import to_observation_class\n"
        if import_cg
        else ""
    )
    path.write_text(
        import_line
        + f"DECK = {deck_ids!r}\n"
        + "def agent(obs, config=None):\n"
        + "    if isinstance(obs, dict) and obs.get('select') is None:\n"
        + "        return DECK\n"
        + f"    return [{action_index}]\n",
        encoding="utf-8",
    )


def _write_deck(path: Path, deck_ids: list[int]) -> None:
    path.write_text("\n".join(str(card_id) for card_id in deck_ids) + "\n", encoding="utf-8")


def _write_archive(root: Path, name: str, deck_ids: list[int], *, include_cg: bool) -> Path:
    package = root / name
    package.mkdir()
    _write_main(package / "main.py", deck_ids, import_cg=include_cg)
    _write_deck(package / "deck.csv", deck_ids)
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


def test_prepare_submission_packages_accepts_zip_wrapper_and_notes_external_cg_fallback(tmp_path: Path) -> None:
    deck_ids = [673, 673, 674, 6, 1227] + [6] * 55
    source_dir = tmp_path / "megastarmie_submission"
    source_dir.mkdir()
    _write_main(source_dir / "main.py", deck_ids, import_cg=True)
    _write_deck(source_dir / "deck.csv", deck_ids)
    nested = source_dir / "submission.tar.gz"
    with tarfile.open(nested, "w:gz") as tf:
        tf.add(source_dir / "main.py", arcname="main.py")
        tf.add(source_dir / "deck.csv", arcname="deck.csv")
    zip_path = tmp_path / "megastarmie_submission.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in source_dir.rglob("*"):
            zf.write(path, arcname=path.relative_to(tmp_path))

    packages = prepare_submission_packages([zip_path], extract_root=tmp_path / "prepared")

    assert len(packages) == 1
    package = packages[0]
    assert package.name == "megastarmie_submission"
    assert package.source_format == "zip"
    assert package.eligible_for_round_robin is True
    assert package.strict_validation_ok is False
    assert "strict_validation_failed" in package.warnings
    assert "uses_external_official_cg" in package.warnings
    assert package.deck_len == 60
    assert Path(package.main_path).exists()
    assert Path(package.deck_path).exists()


def test_prepare_submission_packages_accepts_strict_tarball_with_bundled_cg(tmp_path: Path) -> None:
    deck_ids = [673, 673, 674, 6, 1227] + [6] * 55
    archive = _write_archive(tmp_path, "agent_with_cg", deck_ids, include_cg=True)

    packages = prepare_submission_packages([archive], extract_root=tmp_path / "prepared")

    assert packages[0].name == "agent_with_cg"
    assert packages[0].source_format == "tar.gz"
    assert packages[0].bundled_cg is True
    assert packages[0].strict_validation_ok is True
    assert packages[0].eligible_for_round_robin is True
    assert packages[0].warnings == ()


def test_run_round_robin_writes_pairwise_matrix_with_required_no_submit_metadata(tmp_path: Path) -> None:
    deck_a = [673, 673, 674, 6, 1227] + [6] * 55
    deck_b = [677, 677, 678, 6, 1227] + [6] * 55
    archive_a = _write_archive(tmp_path, "alpha", deck_a, include_cg=False)
    archive_b = _write_archive(tmp_path, "beta", deck_b, include_cg=False)
    packages = prepare_submission_packages([archive_a, archive_b], extract_root=tmp_path / "prepared")

    report = run_round_robin(
        packages,
        output_dir=tmp_path / "round_robin",
        games_per_pair=1,
        seed=99,
        max_steps=4,
        command="pytest-round-robin",
    )

    summary_path = Path(report["report_paths"]["summary"])
    matrix_path = Path(report["report_paths"]["matchup_matrix"])
    assert summary_path.exists()
    assert matrix_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))

    assert summary["kaggle_submission_made"] is False
    assert summary["engine"] == "official_cg_sdk"
    assert summary["package_count"] == 2
    assert summary["games_per_pair"] == 1
    assert summary["seed"] == 99
    assert summary["totals"]["scheduled_games"] == 2
    assert summary["command"] == "pytest-round-robin"
    assert summary["opponent_count"] == 2
    assert summary["replay_count"] == 0
    assert len(summary["package_paths"]) == 2
    assert set(summary["sha256s"]) == {"alpha", "beta"}
    assert len(matrix) == 2
    assert {row["candidate"] for row in matrix} == {"alpha", "beta"}
    assert all(row["opponent"] in {"alpha", "beta"} for row in matrix)


def test_run_round_robin_cli_writes_registry_only_report(tmp_path: Path) -> None:
    deck_a = [673, 673, 674, 6, 1227] + [6] * 55
    deck_b = [677, 677, 678, 6, 1227] + [6] * 55
    archive_a = _write_archive(tmp_path, "alpha", deck_a, include_cg=False)
    archive_b = _write_archive(tmp_path, "beta", deck_b, include_cg=False)
    output_dir = tmp_path / "cli_report"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_round_robin.py",
            "--archive",
            str(archive_a),
            "--archive",
            str(archive_b),
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
    assert payload["output_dir"] == str(output_dir)
    assert payload["package_count"] == 2
    assert payload["matchup_count"] == 0
    assert payload["kaggle_submission_made"] is False
    assert (output_dir / "submission_registry.json").exists()
    assert (output_dir / "summary.json").exists()
