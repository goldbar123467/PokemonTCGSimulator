from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def benchmark_run_id(summary: dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(summary.get("candidate_archive_sha256") or ""),
            str(summary.get("config_path") or ""),
            _seed_schedule_hash(summary),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()[:16]


def benchmark_index_entry(summary: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    finished = _to_int(summary.get("finished_games"))
    wins = _to_int(summary.get("wins"))
    return {
        "run_id": benchmark_run_id(summary),
        "archive_path": str(summary.get("candidate_archive") or ""),
        "archive_sha256": str(summary.get("candidate_archive_sha256") or ""),
        "config_path": str(summary.get("config_path") or ""),
        "seed_schedule_hash": _seed_schedule_hash(summary),
        "total_games": _to_int(summary.get("scheduled_games")),
        "aggregate_win_rate": round(float(wins) / float(finished), 6) if finished else 0.0,
        "errors": _to_int(summary.get("errors")),
        "invalid_actions": _to_int(summary.get("invalid_actions")),
        "timeouts": _to_int(summary.get("timeouts")),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "summary_path": str((summary.get("report_paths") or {}).get("summary") or ""),
    }


def update_benchmark_index(path: Path | str, summary: dict[str, Any]) -> dict[str, Any]:
    index_path = Path(path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_index(index_path)
    runs = [row for row in payload.get("runs", []) if isinstance(row, dict)]
    run_id = benchmark_run_id(summary)
    existing = next((row for row in runs if row.get("run_id") == run_id), None)
    entry = benchmark_index_entry(summary, created_at=existing.get("created_at") if existing else None)
    runs = [row for row in runs if row.get("run_id") != run_id]
    runs.append(entry)
    runs.sort(key=lambda row: str(row.get("run_id")))
    index_path.write_text(json.dumps({"version": 1, "runs": runs}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return entry


def _read_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "runs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "runs": []}
    if not isinstance(payload, dict):
        return {"version": 1, "runs": []}
    payload.setdefault("version", 1)
    payload.setdefault("runs", [])
    return payload


def _seed_schedule_hash(summary: dict[str, Any]) -> str:
    schedule_path = (summary.get("report_paths") or {}).get("seed_schedule")
    if not schedule_path:
        return ""
    path = Path(str(schedule_path))
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))
