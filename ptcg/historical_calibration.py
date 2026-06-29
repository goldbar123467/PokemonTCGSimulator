from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ptcg.archive_registry import resolve_archive_registry
from ptcg.benchmark_comparison import compare_candidate_archives
from ptcg.benchmark_compatibility import BenchmarkCompatibilityError
from ptcg.kaggle_archive_validator import validate_archive_startup


def run_historical_calibration(
    *,
    registry_path: Path | str,
    config_path: Path | str,
    gate_path: Path | str,
    output_dir: Path | str,
    load_only: bool = False,
    max_pairs: int | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    resolved = resolve_archive_registry(registry_path)
    failures: list[dict[str, Any]] = []
    reuse_rows: list[dict[str, Any]] = []

    eligible = [
        row
        for row in resolved["archives"]
        if row.get("eligible_for_calibration") is True and row.get("exists") is True and row.get("sha_matches") is not False
    ]
    for row in eligible:
        try:
            validation = validate_archive_startup(Path(row["archive_path"]))
            row["package_validation_status"] = "passed"
            row["package_validation"] = validation
        except Exception as exc:
            row["package_validation_status"] = "failed"
            failures.append(
                {
                    "category": "archive_validation_error",
                    "archive": row.get("name"),
                    "message": str(exc),
                }
            )

    runnable_eligible = [row for row in eligible if row.get("package_validation_status") != "failed"]
    pair_rows = _build_pair_rows(runnable_eligible)
    if max_pairs is not None:
        pair_rows = pair_rows[: int(max_pairs)]

    completed_pairs: list[dict[str, Any]] = []
    for pair in pair_rows:
        if pair["status"] == "INCONCLUSIVE":
            completed_pairs.append(pair)
            continue
        if load_only:
            completed_pairs.append(
                {
                    **pair,
                    "status": "INCONCLUSIVE",
                    "inconclusive_reason": "load_only_no_comparison_run",
                    "comparison_status": None,
                    "local_order_agrees": None,
                }
            )
            continue
        pair_dir = output / "pairwise" / f"{pair['stronger_name']}__gt__{pair['weaker_name']}"
        try:
            comparison = compare_candidate_archives(
                candidate_archive=pair["stronger_archive_path"],
                baseline_archive=pair["weaker_archive_path"],
                benchmark_config_path=config_path,
                gate_config_path=gate_path,
                output_dir=pair_dir,
                command=command,
            )
            delta = float(comparison["comparison_summary"]["aggregate_delta"]["win_rate_delta"])
            local_order_agrees = delta > 0.0 if delta != 0.0 else None
            completed_pairs.append(
                {
                    **pair,
                    "status": comparison["decision"]["status"],
                    "comparison_status": comparison["decision"]["status"],
                    "local_win_rate_delta": delta,
                    "local_order_agrees": local_order_agrees,
                    "comparison_dir": str(pair_dir.resolve()),
                }
            )
        except BenchmarkCompatibilityError as exc:
            reuse_rows.append({"pair": pair["pair_id"], "compatible": False, "message": str(exc)})
            completed_pairs.append({**pair, "status": "INCONCLUSIVE", "inconclusive_reason": "incompatible_reuse"})
        except Exception as exc:
            failures.append({"category": "runtime_exception", "pair": pair["pair_id"], "message": str(exc)})
            completed_pairs.append({**pair, "status": "INCONCLUSIVE", "inconclusive_reason": "comparison_failed"})

    paths = {
        "calibration_pairs": output / "calibration_pairs.csv",
        "calibration_summary": output / "calibration_summary.json",
        "archive_registry_resolved": output / "archive_registry_resolved.json",
        "failures": output / "failures.json",
        "result_reuse_report": output / "result_reuse_report.json",
    }
    _write_csv(paths["calibration_pairs"], completed_pairs)
    _write_json(paths["archive_registry_resolved"], resolved)
    _write_json(paths["failures"], failures)
    _write_json(paths["result_reuse_report"], reuse_rows)
    summary = {
        "workflow": "historical_benchmark_calibration_v1",
        "status": "completed",
        "registry_path": str(Path(registry_path).resolve()),
        "benchmark_config_path": str(Path(config_path).resolve()),
        "gate_config_path": str(Path(gate_path).resolve()),
        "archive_count": len(resolved["archives"]),
        "eligible_archive_count": len(eligible),
        "runnable_eligible_archive_count": len(runnable_eligible),
        "pair_count": len(completed_pairs),
        "pair_status_counts": _status_counts(completed_pairs),
        "load_only": load_only,
        "failures": len(failures),
        "result_compatibility": reuse_rows,
        "local_benchmark_is_leaderboard_truth": False,
        "kaggle_submission_made": False,
    }
    _write_json(paths["calibration_summary"], summary)
    return {
        "summary": summary,
        "pairs": completed_pairs,
        "resolved_registry": resolved,
        "failures": failures,
        "report_paths": {key: str(path.resolve()) for key, path in paths.items()},
        "kaggle_submission_made": False,
    }


def _build_pair_rows(eligible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left_index, left in enumerate(eligible):
        for right in eligible[left_index + 1 :]:
            left_score = left.get("known_score")
            right_score = right.get("known_score")
            left_basis = left.get("known_score_basis")
            right_basis = right.get("known_score_basis")
            pair_id = f"{left.get('name')}__vs__{right.get('name')}"
            base = {
                "pair_id": pair_id,
                "left_name": left.get("name"),
                "right_name": right.get("name"),
                "left_known_score": left_score,
                "right_known_score": right_score,
                "known_score_basis": left_basis if left_basis == right_basis else None,
            }
            if left_score is None or right_score is None:
                rows.append({**base, "status": "INCONCLUSIVE", "inconclusive_reason": "missing_known_label"})
                continue
            if left_basis != right_basis:
                rows.append({**base, "status": "INCONCLUSIVE", "inconclusive_reason": "different_known_score_basis"})
                continue
            if float(left_score) == float(right_score):
                rows.append({**base, "status": "INCONCLUSIVE", "inconclusive_reason": "known_scores_tied"})
                continue
            stronger, weaker = (left, right) if float(left_score) > float(right_score) else (right, left)
            rows.append(
                {
                    **base,
                    "status": "PENDING",
                    "inconclusive_reason": "",
                    "stronger_name": stronger.get("name"),
                    "weaker_name": weaker.get("name"),
                    "stronger_archive_path": stronger.get("archive_path"),
                    "weaker_archive_path": weaker.get("archive_path"),
                    "known_stronger_score": stronger.get("known_score"),
                    "known_weaker_score": weaker.get("known_score"),
                    "comparison_status": None,
                    "local_order_agrees": None,
                }
            )
    if not rows and eligible:
        for row in eligible:
            rows.append(
                {
                    "pair_id": str(row.get("name")),
                    "left_name": row.get("name"),
                    "right_name": None,
                    "status": "INCONCLUSIVE",
                    "inconclusive_reason": "no_known_pair",
                    "known_score_basis": row.get("known_score_basis"),
                }
            )
    return rows


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row} or {"pair_id", "status"})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
