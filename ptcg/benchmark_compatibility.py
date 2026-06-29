from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from ptcg.archive_registry import sha256_file


BENCHMARK_SCHEMA_VERSION = "benchmark_league_v2"


class BenchmarkCompatibilityError(RuntimeError):
    pass


def benchmark_config_hash(path: Path | str) -> str:
    config_path = Path(path)
    raw = config_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        canonical = raw.encode("utf-8")
    else:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest().upper()


def file_sha256_or_none(path: Path | str | None) -> str | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    return sha256_file(target)


def check_result_compatibility(
    *,
    result_dir: Path | str,
    archive: Path | str,
    config_path: Path | str,
    expected_config_sha256: str | None = None,
    required_matchups: list[str] | None = None,
    target_games_per_matchup: int | None = None,
    expected_role: str | None = None,
    required_schema_version: str | None = BENCHMARK_SCHEMA_VERSION,
) -> dict[str, Any]:
    root = Path(result_dir)
    summary_path = root / "summary.json"
    rows_path = root / "results_by_matchup.csv"
    checks: list[dict[str, Any]] = []
    if not summary_path.exists():
        return _status(False, [_check("summary_json", False, "missing summary.json")])
    if not rows_path.exists():
        return _status(False, [_check("results_by_matchup", False, "missing results_by_matchup.csv")])

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = _read_rows(rows_path)
    actual_archive_sha = sha256_file(Path(archive))
    expected_config = expected_config_sha256 or benchmark_config_hash(config_path)

    checks.append(
        _check(
            "archive_sha256",
            str(summary.get("candidate_archive_sha256") or "").upper() == actual_archive_sha,
            f"expected {actual_archive_sha}, found {summary.get('candidate_archive_sha256')}",
        )
    )
    checks.append(
        _check(
            "benchmark_config_sha256",
            str(summary.get("benchmark_config_sha256") or "").upper() == str(expected_config).upper(),
            f"expected {expected_config}, found {summary.get('benchmark_config_sha256')}",
        )
    )
    if required_schema_version is not None:
        checks.append(
            _check(
                "benchmark_schema_version",
                summary.get("benchmark_schema_version") == required_schema_version,
                f"expected {required_schema_version}, found {summary.get('benchmark_schema_version')}",
            )
        )
    if expected_role is not None and summary.get("comparison_role") is not None:
        checks.append(
            _check(
                "comparison_role",
                summary.get("comparison_role") == expected_role,
                f"expected {expected_role}, found {summary.get('comparison_role')}",
            )
        )

    report_paths = summary.get("report_paths") or {}
    opponent_registry_path = report_paths.get("opponent_registry")
    seed_schedule_path = report_paths.get("seed_schedule")
    recorded_opponent_hash = summary.get("opponent_registry_sha256")
    if recorded_opponent_hash:
        checks.append(
            _check(
                "opponent_registry_sha256",
                recorded_opponent_hash == file_sha256_or_none(opponent_registry_path),
                "opponent registry hash mismatch",
            )
        )
    recorded_seed_hash = summary.get("seed_schedule_sha256")
    if recorded_seed_hash:
        checks.append(
            _check(
                "seed_schedule_sha256",
                recorded_seed_hash == file_sha256_or_none(seed_schedule_path),
                "seed schedule hash mismatch",
            )
        )

    unavailable = {
        str(row.get("name"))
        for row in summary.get("unavailable_opponents", [])
        if isinstance(row, dict)
    }
    rows_by_opponent = {str(row.get("opponent")): row for row in rows}
    for opponent in required_matchups or []:
        row = rows_by_opponent.get(str(opponent))
        checks.append(
            _check(
                f"required_matchup:{opponent}",
                row is not None or str(opponent) in unavailable,
                "required matchup missing",
            )
        )
        if row is not None and target_games_per_matchup is not None:
            games = _to_int(row.get("games"))
            checks.append(
                _check(
                    f"target_games_per_matchup:{opponent}",
                    games >= int(target_games_per_matchup),
                    f"expected >= {target_games_per_matchup}, found {games}",
                )
            )

    return _status(all(check["passed"] for check in checks), checks, summary=summary)


def require_compatible_result(**kwargs: Any) -> dict[str, Any]:
    status = check_result_compatibility(**kwargs)
    if not status["compatible"]:
        failed = [check for check in status["checks"] if not check["passed"]]
        raise BenchmarkCompatibilityError(f"incompatible benchmark result: {failed}")
    return status


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _check(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "message": message}


def _status(compatible: bool, checks: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    return {"compatible": bool(compatible), "checks": checks, **fields}


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))
