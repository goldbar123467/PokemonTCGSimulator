from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


CURRENT_GAMEPLAY_SCHEMA_VERSION = "kaggle_episode_steps_v1"
DEFAULT_CURRENT_MIN_DATE = "2026-06-27"

DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ReplayInspection:
    path: Path
    relative_path: str
    sha256: str
    created_date: str | None
    schema_version: str
    engine_version: str
    simulator_version: str
    policy_version: str | None
    deck_ruleset_version: str
    reward_format: str
    completed: bool
    compatible: bool
    duplicate_of: str | None
    status: str
    reasons: tuple[str, ...]
    episode_id: str | None
    step_count: int
    decision_count: int
    file_size: int


def build_manifest(
    *,
    roots: Iterable[Path | str],
    project_root: Path | str = Path("."),
    current_min_date: str = DEFAULT_CURRENT_MIN_DATE,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    rows: list[ReplayInspection] = []
    first_by_hash: dict[str, str] = {}
    for root in roots:
        root_path = Path(root)
        if not root_path.is_absolute():
            root_path = project / root_path
        for path in sorted(root_path.rglob("*-replay.json")):
            row = inspect_replay(path, project_root=project, current_min_date=current_min_date)
            duplicate_of = first_by_hash.get(row.sha256)
            if duplicate_of is None:
                first_by_hash[row.sha256] = row.relative_path
                rows.append(row)
                continue
            rows.append(
                ReplayInspection(
                    **{
                        **row.__dict__,
                        "duplicate_of": duplicate_of,
                        "status": "quarantine",
                        "reasons": (*row.reasons, "duplicate_replay"),
                    }
                )
            )

    summary = Counter(row.status for row in rows)
    return {
        "schema_version": "gameplay_log_manifest_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project),
        "current_min_date": current_min_date,
        "current_gameplay_schema_version": CURRENT_GAMEPLAY_SCHEMA_VERSION,
        "logs": [_jsonable(row) for row in rows],
        "summary": {
            "total": len(rows),
            "current": summary.get("current", 0),
            "archive": summary.get("archive", 0),
            "quarantine": summary.get("quarantine", 0),
        },
        "kaggle_submission_made": False,
    }


def inspect_replay(path: Path, *, project_root: Path, current_min_date: str) -> ReplayInspection:
    relative = _relative_path(path, project_root)
    digest = _sha256(path)
    created_date = _date_from_path(relative)
    reasons: list[str] = []
    episode_id: str | None = None
    step_count = 0
    decision_count = 0
    completed = False
    compatible = False
    schema_version = CURRENT_GAMEPLAY_SCHEMA_VERSION
    reward_format = "unknown"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            reasons.append("not_json_object")
        steps = payload.get("steps") if isinstance(payload, dict) else None
        if not isinstance(steps, list) or not steps:
            reasons.append("missing_steps")
        else:
            step_count = len(steps)
            decision_count = _decision_count(steps)
            completed = True
            compatible = decision_count > 0
            if not compatible:
                reasons.append("no_valid_decisions")
        info = payload.get("info") if isinstance(payload, dict) else None
        episode_id = str(info.get("EpisodeId")) if isinstance(info, dict) and info.get("EpisodeId") else path.stem
        reward_format = _reward_format(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        reasons.append("corrupt_json")

    if created_date is None:
        reasons.append("missing_date_in_path")
    if created_date is not None and created_date < current_min_date:
        status = "archive"
        reasons.append("older_than_current_min_date")
    elif reasons or not compatible:
        status = "quarantine"
    else:
        status = "current"

    if "corrupt_json" in reasons or "missing_steps" in reasons or "not_json_object" in reasons:
        status = "quarantine"
        compatible = False
        completed = False

    return ReplayInspection(
        path=path.resolve(),
        relative_path=relative,
        sha256=digest,
        created_date=created_date,
        schema_version=schema_version,
        engine_version="kaggle_public_episode",
        simulator_version="competition_public_replay",
        policy_version=_policy_version_from_path(relative),
        deck_ruleset_version="competition_simulator_current",
        reward_format=reward_format,
        completed=completed,
        compatible=compatible,
        duplicate_of=None,
        status=status,
        reasons=tuple(reasons),
        episode_id=episode_id,
        step_count=step_count,
        decision_count=decision_count,
        file_size=path.stat().st_size,
    )


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    logs = manifest.get("logs")
    if not isinstance(logs, list):
        errors.append("missing_logs")
        logs = []
    current = [row for row in logs if row.get("status") == "current"]
    if not current:
        errors.append("no_current_valid_logs")
    if any(row.get("status") == "current" and row.get("duplicate_of") for row in logs):
        errors.append("duplicate_marked_current")
    return {"ok": not errors, "errors": errors, "current_count": len(current)}


def filter_current_logs(manifest: dict[str, Any]) -> list[str]:
    logs = manifest.get("logs") if isinstance(manifest.get("logs"), list) else []
    return [
        str(row["relative_path"])
        for row in logs
        if row.get("status") == "current"
        and row.get("compatible") is True
        and not row.get("duplicate_of")
    ]


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_current_log_allowlist(*, manifest_path: Path, allowlist_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_logs = filter_current_logs(manifest)
    allowlist_path.parent.mkdir(parents=True, exist_ok=True)
    allowlist_path.write_text("".join(f"{path}\n" for path in current_logs), encoding="utf-8")
    project = Path(manifest.get("project_root") or ".").resolve()
    manifest["allowlist"] = {
        "path": _relative_path(allowlist_path, project),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(current_logs),
        "file_size": allowlist_path.stat().st_size,
        "sha256": _sha256(allowlist_path),
    }
    write_manifest(manifest_path, manifest)
    return current_logs


def _decision_count(steps: list[Any]) -> int:
    count = 0
    for step in steps:
        if not isinstance(step, list):
            continue
        for agent_step in step:
            if not isinstance(agent_step, dict):
                continue
            observation = agent_step.get("observation")
            select = observation.get("select") if isinstance(observation, dict) else None
            options = select.get("option") if isinstance(select, dict) else None
            action = agent_step.get("action")
            if isinstance(options, list) and options and isinstance(action, list):
                count += 1
    return count


def _reward_format(payload: dict[str, Any]) -> str:
    rewards: list[Any] = []
    for step in payload.get("steps") or []:
        if not isinstance(step, list):
            continue
        for agent_step in step:
            if isinstance(agent_step, dict) and "reward" in agent_step:
                rewards.append(agent_step.get("reward"))
    if not rewards:
        return "absent"
    if all(isinstance(item, (int, float)) for item in rewards):
        return "numeric"
    return "mixed"


def _policy_version_from_path(relative: str) -> str | None:
    for part in Path(relative).parts:
        if part.startswith("submission_"):
            return part
    return None


def _date_from_path(relative: str) -> str | None:
    match = DATE_RE.search(relative)
    return match.group(0) if match else None


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _jsonable(row: ReplayInspection) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in row.__dict__.items()
        if key != "path"
    }
    payload["absolute_path"] = str(row.path)
    payload["reasons"] = list(row.reasons)
    return payload
