from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from ptcg.archive_registry import (
    ChampionRegistryError,
    resolve_archive_registry,
    validate_champion_registry,
)


def _write_archive(root: Path, name: str) -> Path:
    package = root / name
    package.mkdir()
    deck = [9] * 60
    (package / "main.py").write_text(
        "DECK = [9] * 60\n"
        "def agent(obs, config=None):\n"
        "    if isinstance(obs, dict) and obs.get('select') is None:\n"
        "        return DECK\n"
        "    return [0]\n",
        encoding="utf-8",
    )
    (package / "deck.csv").write_text("\n".join(str(card) for card in deck) + "\n", encoding="utf-8")
    cg = package / "cg"
    cg.mkdir()
    (cg / "__init__.py").write_text("", encoding="utf-8")
    (cg / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = root / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))
    return archive


def test_champion_registry_refuses_sha_mismatch_and_does_not_mutate(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "champion")
    registry = tmp_path / "champion_registry.json"
    payload = {
        "version": 1,
        "champion_name": "test_champion",
        "archive_path": str(archive),
        "archive_sha256": "WRONG",
        "known_submission_id": None,
        "known_public_score": None,
        "deck_archetype_label": "test",
        "registered_at": "2026-06-29T00:00:00Z",
        "package_validation": {"status": "unknown"},
        "benchmark_config_hash": None,
        "notes": "unit test",
    }
    registry.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = registry.read_text(encoding="utf-8")

    with pytest.raises(ChampionRegistryError, match="hash mismatch"):
        validate_champion_registry(registry, project_root=tmp_path)

    assert registry.read_text(encoding="utf-8") == before


def test_archive_registry_resolves_known_archives_and_unknown_labels(tmp_path: Path) -> None:
    archive = _write_archive(tmp_path, "known")
    registry = tmp_path / "archive_registry.json"
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "archives": [
                    {
                        "name": "known_good",
                        "archive_path": str(archive),
                        "archive_sha256": None,
                        "role": "historical",
                        "known_submission_id": None,
                        "known_public_score": 900.0,
                        "known_private_score": None,
                        "known_local_score": None,
                        "notes": "score is enough for calibration ordering",
                        "eligible_for_calibration": True,
                    },
                    {
                        "name": "unknown",
                        "archive_path": str(tmp_path / "missing.tar.gz"),
                        "archive_sha256": None,
                        "role": "unknown",
                        "known_submission_id": None,
                        "known_public_score": None,
                        "known_private_score": None,
                        "known_local_score": None,
                        "notes": "intentionally unknown",
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

    resolved = resolve_archive_registry(registry, project_root=tmp_path)

    by_name = {row["name"]: row for row in resolved["archives"]}
    assert by_name["known_good"]["exists"] is True
    assert by_name["known_good"]["actual_sha256"]
    assert by_name["known_good"]["known_score_basis"] == "known_public_score"
    assert by_name["unknown"]["exists"] is False
    assert by_name["unknown"]["known_score_basis"] is None
