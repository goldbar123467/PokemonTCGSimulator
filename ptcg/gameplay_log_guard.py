from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from ptcg.gameplay_log_hygiene import validate_manifest


BLOCKED_PATH_PARTS = {
    "archive",
    "archived",
    "quarantine",
    "duplicate",
    "duplicates",
    "duplicate_replays",
    "old",
    "stale_debug",
    "failed_experiment",
    "failed_experiments",
}


class GameplayLogGateError(RuntimeError):
    """Raised when gameplay logs are not safe to consume."""


def assert_training_gameplay_logs_allowed(
    *,
    project_root: Path | str = Path("."),
    config_path: Path | str = Path("configs/current_workflow.json"),
) -> list[Path]:
    project = Path(project_root).resolve()
    config_path = Path(config_path)
    config_file = config_path.resolve() if config_path.is_absolute() else _resolve_under_project(project, config_path)
    if not config_file.exists():
        raise GameplayLogGateError(f"missing workflow config: {_display(config_file, project)}")
    config = json.loads(config_file.read_text(encoding="utf-8"))

    manifest_path = _resolve_under_project(project, Path(_required_config(config, "gameplay_manifest")))
    allowlist_path = _resolve_under_project(project, Path(_required_config(config, "current_gameplay_allowlist")))
    expected_schema = str(_required_config(config, "gameplay_schema_version"))

    if not manifest_path.exists():
        raise GameplayLogGateError(f"missing gameplay manifest: {_display(manifest_path, project)}")
    if not allowlist_path.exists():
        raise GameplayLogGateError(f"missing current gameplay log list: {_display(allowlist_path, project)}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_schema = manifest.get("current_gameplay_schema_version")
    if manifest_schema != expected_schema:
        raise GameplayLogGateError(f"gameplay schema mismatch: manifest={manifest_schema!r} config={expected_schema!r}")

    validation = validate_manifest(manifest)
    if not validation["ok"]:
        raise GameplayLogGateError(f"gameplay manifest failed validation: {validation['errors']}")

    rows = manifest.get("logs") if isinstance(manifest.get("logs"), list) else []
    by_relative = {
        str(row.get("relative_path")): row
        for row in rows
        if isinstance(row, dict) and row.get("relative_path")
    }
    listed = _read_allowlist(allowlist_path)
    if not listed:
        raise GameplayLogGateError("no eligible gameplay logs in current allowlist")
    _assert_allowlist_integrity(manifest, allowlist_path, listed, project)

    allowed: list[Path] = []
    for relative in listed:
        _assert_safe_relative_path(relative)
        row = by_relative.get(relative)
        if row is None:
            raise GameplayLogGateError(f"allowlist entry missing from manifest: {relative}")
        if row.get("status") != "current":
            raise GameplayLogGateError(f"allowlist entry is not current: {relative} status={row.get('status')}")
        if row.get("compatible") is not True:
            raise GameplayLogGateError(f"allowlist entry is not schema-compatible: {relative}")
        if row.get("duplicate_of"):
            raise GameplayLogGateError(f"allowlist entry is duplicate replay: {relative}")
        if row.get("schema_version") != expected_schema:
            raise GameplayLogGateError(f"allowlist entry schema mismatch: {relative}")
        absolute = _resolve_under_project(project, Path(relative))
        if not absolute.exists():
            raise GameplayLogGateError(f"listed gameplay log is missing: {relative}")
        if _file_size(absolute) != int(row.get("file_size", _file_size(absolute))):
            raise GameplayLogGateError(f"listed gameplay log changed since manifest: {relative}")
        allowed.append(absolute)

    return allowed


def _assert_allowlist_integrity(
    manifest: dict[str, Any],
    allowlist_path: Path,
    listed: list[str],
    project: Path,
) -> None:
    metadata = manifest.get("allowlist")
    if not isinstance(metadata, dict):
        return
    expected_count = metadata.get("file_count")
    if expected_count is not None and int(expected_count) != len(listed):
        raise GameplayLogGateError(
            f"allowlist file count mismatch: manifest={expected_count} actual={len(listed)}"
        )
    expected_size = metadata.get("file_size")
    if expected_size is not None and int(expected_size) != _file_size(allowlist_path):
        raise GameplayLogGateError("allowlist file size mismatch")
    expected_sha256 = metadata.get("sha256")
    if expected_sha256 is not None and str(expected_sha256).upper() != _sha256(allowlist_path):
        raise GameplayLogGateError("allowlist sha256 mismatch")
    expected_path = metadata.get("path")
    if expected_path and _resolve_under_project(project, Path(str(expected_path))) != allowlist_path.resolve():
        raise GameplayLogGateError(f"allowlist path mismatch: {expected_path}")


def _read_allowlist(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped.replace("\\", "/"))
    return lines


def _assert_safe_relative_path(relative: str) -> None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise GameplayLogGateError(f"allowlist path must stay under project root: {relative}")
    lowered_parts = {part.lower() for part in Path(relative).parts}
    blocked = sorted(BLOCKED_PATH_PARTS & lowered_parts)
    if blocked:
        raise GameplayLogGateError(f"allowlist path contains blocked segment {blocked[0]}: {relative}")
    lowered = relative.lower()
    for blocked_text in ("stale_debug", "failed experiment", "failed_experiment"):
        if blocked_text in lowered:
            raise GameplayLogGateError(f"allowlist path contains blocked segment {blocked_text}: {relative}")


def _resolve_under_project(project: Path, path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (project / path).resolve()
    try:
        resolved.relative_to(project)
    except ValueError as exc:
        raise GameplayLogGateError(f"path escapes project root: {path}") from exc
    return resolved


def _required_config(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise GameplayLogGateError(f"missing workflow config key: {key}")
    return value


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _display(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project).as_posix()
    except ValueError:
        return str(path)
