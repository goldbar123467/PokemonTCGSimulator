from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ChampionRegistryError(RuntimeError):
    pass


class ArchiveRegistryError(RuntimeError):
    pass


def validate_champion_registry(
    registry_path: Path | str = Path("configs/champion_registry.json"),
    *,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    path = Path(registry_path)
    if not path.is_absolute():
        path = (root / path).resolve()
    registry = _read_json(path)
    archive = _resolve_path(registry.get("archive_path"), root)
    if not archive.exists():
        raise ChampionRegistryError(f"champion archive does not exist: {archive}")
    expected_sha = str(registry.get("archive_sha256") or "").upper()
    if not expected_sha:
        raise ChampionRegistryError("champion registry is missing archive_sha256")
    actual_sha = sha256_file(archive)
    if actual_sha != expected_sha:
        raise ChampionRegistryError(
            f"champion archive hash mismatch for {archive}: expected {expected_sha}, actual {actual_sha}"
        )
    return {
        **registry,
        "registry_path": str(path),
        "archive_path": str(archive),
        "actual_archive_sha256": actual_sha,
        "hash_matches": True,
        "human_promotion_instructions": champion_promotion_instructions(path),
    }


def champion_promotion_instructions(registry_path: Path | str = Path("configs/champion_registry.json")) -> str:
    return (
        f"Do not update {registry_path} automatically. To promote a new champion, a human must edit the registry "
        "with the new archive path, SHA256, known evidence, validation status, and notes after reviewing gate and "
        "historical-calibration reports."
    )


def resolve_archive_registry(
    registry_path: Path | str = Path("configs/archive_registry.json"),
    *,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    path = Path(registry_path)
    if not path.is_absolute():
        path = (root / path).resolve()
    payload = _read_json(path)
    archives = payload.get("archives")
    if not isinstance(archives, list):
        raise ArchiveRegistryError("archive registry must include an archives list")

    resolved: list[dict[str, Any]] = []
    for raw in archives:
        if not isinstance(raw, dict):
            raise ArchiveRegistryError("archive registry records must be JSON objects")
        archive = _resolve_path(raw.get("archive_path"), root)
        exists = archive.exists()
        actual_sha = sha256_file(archive) if exists else None
        expected_sha = _upper_or_none(raw.get("archive_sha256"))
        known_score, known_score_basis = _known_score(raw)
        sha_matches = None if expected_sha is None or actual_sha is None else expected_sha == actual_sha
        if not exists:
            status = "missing_archive"
        elif sha_matches is False:
            status = "sha_mismatch"
        else:
            status = "resolved"
        resolved.append(
            {
                **raw,
                "archive_path": str(archive),
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "exists": exists,
                "sha_matches": sha_matches,
                "known_score": known_score,
                "known_score_basis": known_score_basis,
                "resolution_status": status,
            }
        )
    return {
        "version": payload.get("version", 1),
        "registry_path": str(path),
        "archives": resolved,
        "kaggle_submission_made": False,
    }


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ArchiveRegistryError(f"missing registry: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ArchiveRegistryError(f"registry must be a JSON object: {path}")
    return payload


def _resolve_path(value: Any, root: Path) -> Path:
    if not value:
        return root / "__missing_archive_path__"
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _upper_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).upper()


def _known_score(row: dict[str, Any]) -> tuple[float | None, str | None]:
    for key in ("known_public_score", "known_private_score", "known_local_score"):
        value = row.get(key)
        if value in (None, "", "unknown"):
            continue
        try:
            return float(value), key
        except (TypeError, ValueError):
            continue
    return None, None
