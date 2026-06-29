from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from ptcg.local_kaggle_parity import LocalKaggleParityError, run_local_kaggle_parity


def _write_archive(root: Path, name: str, *, include_cg: bool = True, hidden_path: bool = False) -> Path:
    deck_ids = [673, 673, 674, 6, 1227] + [6] * 55
    package = root / name
    package.mkdir()
    marker = "HIDDEN = 'C:/Users/Clark/private.csv'\n" if hidden_path else ""
    (package / "main.py").write_text(
        marker
        + f"DECK = {deck_ids!r}\n"
        + "def agent(obs, config=None):\n"
        + "    if isinstance(obs, dict) and obs.get('select') is None:\n"
        + "        return DECK\n"
        + "    return [0]\n",
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


def test_local_parity_accepts_minimal_valid_archive_and_writes_artifacts(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "candidate")
    output_dir = tmp_path / "parity"

    report = run_local_kaggle_parity(
        archive=archive,
        output_dir=output_dir,
        smoke_games=0,
        seed=7,
        max_steps=4,
        command="pytest parity",
    )

    assert report["summary"]["status"] == "passed"
    assert report["summary"]["archive_validation"]["strict_raw_exec_without_file_or_syspath"] is True
    assert report["summary"]["required_files"]["main.py"] is True
    assert report["summary"]["required_files"]["deck.csv"] is True
    assert report["summary"]["required_files"]["cg/api.py"] is True
    assert report["summary"]["hidden_local_path_markers"] == []
    assert report["summary"]["kaggle_submission_made"] is False
    assert report["failures"] == []

    for name in ("parity_summary.json", "parity_events.jsonl", "failures.json", "run_config.json"):
        assert (output_dir / name).exists()
    assert json.loads((output_dir / "parity_summary.json").read_text(encoding="utf-8"))["status"] == "passed"
    assert json.loads((output_dir / "failures.json").read_text(encoding="utf-8")) == []
    assert (output_dir / "parity_events.jsonl").read_text(encoding="utf-8").count("\n") >= 3


def test_local_parity_rejects_broken_archive_but_preserves_failure_artifacts(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "candidate_without_cg", include_cg=False)
    output_dir = tmp_path / "parity_failed"

    with pytest.raises(LocalKaggleParityError, match="validation failed"):
        run_local_kaggle_parity(archive=archive, output_dir=output_dir, smoke_games=0, command="pytest parity")

    summary = json.loads((output_dir / "parity_summary.json").read_text(encoding="utf-8"))
    failures = json.loads((output_dir / "failures.json").read_text(encoding="utf-8"))

    assert summary["status"] == "failed"
    assert summary["kaggle_submission_made"] is False
    assert failures[0]["stage"] == "archive_validation"
    assert "cg/api.py" in failures[0]["message"]


def test_local_parity_rejects_hidden_local_path_markers(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "candidate_with_hidden_path", hidden_path=True)
    output_dir = tmp_path / "parity_hidden"

    with pytest.raises(LocalKaggleParityError, match="hidden local path"):
        run_local_kaggle_parity(archive=archive, output_dir=output_dir, smoke_games=0)

    summary = json.loads((output_dir / "parity_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["hidden_local_path_markers"][0]["path"].endswith("main.py")
