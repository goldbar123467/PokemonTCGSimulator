from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ptcg.archive_registry import validate_champion_registry
from ptcg.benchmark_index import update_benchmark_index
from ptcg.benchmark_league import run_benchmark_league
from ptcg.benchmark_stats import aggregate_rows, row_stats
from ptcg.benchmark_compatibility import benchmark_config_hash, require_compatible_result
from ptcg.kaggle_archive_validator import validate_archive_startup


GATE_POLICY_KEYS = {
    "minimum_total_games",
    "minimum_games_per_required_matchup",
    "maximum_invalid_action_rate",
    "maximum_timeout_rate",
    "maximum_crash_rate",
    "minimum_aggregate_win_rate_delta_vs_baseline",
    "minimum_candidate_lower_ci",
    "required_hard_gate_opponents",
    "allowed_unavailable_optional_opponents",
    "maximum_required_matchup_regression",
    "random_opponent_names",
}


def load_gate_policy(path: Path | str) -> dict[str, Any]:
    policy_path = Path(path)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    missing = sorted(GATE_POLICY_KEYS - set(policy))
    if missing:
        raise ValueError(f"missing gate policy keys: {missing}")
    return policy


def compare_candidate_archives(
    *,
    candidate_archive: Path | str,
    baseline_archive: Path | str,
    benchmark_config_path: Path | str,
    gate_config_path: Path | str,
    output_dir: Path | str,
    candidate_results_dir: Path | str | None = None,
    baseline_results_dir: Path | str | None = None,
    index_path: Path | str = Path("artifacts/benchmark_lab/benchmark_index.json"),
    champion_registry_path: Path | str | None = Path("configs/champion_registry.json"),
    command: str | None = None,
) -> dict[str, Any]:
    candidate_path = Path(candidate_archive).resolve()
    baseline_path = Path(baseline_archive).resolve()
    benchmark_config = Path(benchmark_config_path).resolve()
    gate_config = Path(gate_config_path).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    candidate_validation = validate_archive_startup(candidate_path)
    baseline_validation = validate_archive_startup(baseline_path)
    policy = load_gate_policy(gate_config)
    champion_status = _maybe_validate_champion_registry(champion_registry_path, baseline_path)

    candidate_result = _load_or_run_result(
        archive=candidate_path,
        config_path=benchmark_config,
        policy=policy,
        expected_role="candidate",
        result_dir=Path(candidate_results_dir).resolve() if candidate_results_dir else None,
        output_dir=output / "candidate_benchmark",
        command=command,
    )
    baseline_result = _load_or_run_result(
        archive=baseline_path,
        config_path=benchmark_config,
        policy=policy,
        expected_role="baseline",
        result_dir=Path(baseline_results_dir).resolve() if baseline_results_dir else None,
        output_dir=output / "baseline_benchmark",
        command=command,
    )

    candidate_result["summary"]["archive_validation"] = candidate_validation
    baseline_result["summary"]["archive_validation"] = baseline_validation
    comparison_rows = _compare_matchups(candidate_result, baseline_result, policy)
    candidate_aggregate = aggregate_rows(candidate_result["rows"])
    baseline_aggregate = aggregate_rows(baseline_result["rows"])
    comparison_summary = {
        "workflow": "benchmark_candidate_comparison_v1",
        "candidate_archive": str(candidate_path),
        "baseline_archive": str(baseline_path),
        "benchmark_config_path": str(benchmark_config),
        "gate_config_path": str(gate_config),
        "command": command,
        "aggregate": {
            "candidate": candidate_aggregate,
            "baseline": baseline_aggregate,
        },
        "aggregate_delta": _delta_stats(candidate_aggregate, baseline_aggregate),
        "candidate_unavailable_opponents": candidate_result["summary"].get("unavailable_opponents", []),
        "baseline_unavailable_opponents": baseline_result["summary"].get("unavailable_opponents", []),
        "champion_registry": champion_status,
        "result_compatibility": {
            "candidate": candidate_result.get("compatibility_status"),
            "baseline": baseline_result.get("compatibility_status"),
        },
        "kaggle_submission_made": False,
    }
    decision = evaluate_gate(
        comparison_rows=comparison_rows,
        comparison_summary=comparison_summary,
        policy=policy,
    )
    comparison_summary["decision"] = decision["status"]

    candidate_summary_path = output / "candidate_summary.json"
    baseline_summary_path = output / "baseline_summary.json"
    comparison_rows_path = output / "comparison_by_matchup.csv"
    comparison_summary_path = output / "comparison_summary.json"
    decision_path = output / "decision.json"

    _write_json(candidate_summary_path, _summary_payload(candidate_result, candidate_aggregate))
    _write_json(baseline_summary_path, _summary_payload(baseline_result, baseline_aggregate))
    _write_comparison_csv(comparison_rows_path, comparison_rows)
    _write_json(comparison_summary_path, comparison_summary)
    _write_json(decision_path, decision)
    candidate_index_entry = update_benchmark_index(index_path, candidate_result["summary"])
    baseline_index_entry = update_benchmark_index(index_path, baseline_result["summary"])

    report_paths = {
        "candidate_summary": str(candidate_summary_path.resolve()),
        "baseline_summary": str(baseline_summary_path.resolve()),
        "comparison_by_matchup": str(comparison_rows_path.resolve()),
        "comparison_summary": str(comparison_summary_path.resolve()),
        "decision": str(decision_path.resolve()),
        "benchmark_index": str(Path(index_path).resolve()),
    }
    return {
        "candidate_summary": _summary_payload(candidate_result, candidate_aggregate),
        "baseline_summary": _summary_payload(baseline_result, baseline_aggregate),
        "comparison_rows": comparison_rows,
        "comparison_summary": comparison_summary,
        "decision": decision,
        "index_entries": {
            "candidate": candidate_index_entry,
            "baseline": baseline_index_entry,
        },
        "report_paths": report_paths,
        "kaggle_submission_made": False,
    }


def evaluate_gate(
    *,
    comparison_rows: list[dict[str, Any]],
    comparison_summary: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    candidate = comparison_summary["aggregate"]["candidate"]
    baseline = comparison_summary["aggregate"]["baseline"]
    aggregate_delta = comparison_summary["aggregate_delta"]
    rows_by_opponent = {str(row["opponent"]): row for row in comparison_rows}
    required = [str(name) for name in policy.get("required_hard_gate_opponents", [])]
    unavailable = {
        str(row.get("name"))
        for row in comparison_summary.get("candidate_unavailable_opponents", [])
        + comparison_summary.get("baseline_unavailable_opponents", [])
    }

    for opponent in required:
        if opponent in unavailable or opponent not in rows_by_opponent:
            checks.append(_check("INCONCLUSIVE", "required_opponent_unavailable", opponent=opponent))
    if checks and any(check["status"] == "INCONCLUSIVE" for check in checks):
        return _decision("INCONCLUSIVE", checks, policy)

    min_total = int(policy["minimum_total_games"])
    if int(candidate["games"]) < min_total or int(baseline["games"]) < min_total:
        checks.append(_check("FAIL", "minimum_total_games", candidate_games=candidate["games"], baseline_games=baseline["games"], threshold=min_total))

    max_invalid = float(policy["maximum_invalid_action_rate"])
    if float(candidate["invalid_action_rate"]) > max_invalid:
        checks.append(_check("FAIL", "invalid_action_rate", actual=candidate["invalid_action_rate"], threshold=max_invalid))
    if int(candidate["invalid_actions"]) > int(baseline["invalid_actions"]) and int(baseline["invalid_actions"]) == 0:
        checks.append(_check("FAIL", "invalid_action_regression", candidate_invalid_actions=candidate["invalid_actions"], baseline_invalid_actions=baseline["invalid_actions"]))

    max_timeout = float(policy["maximum_timeout_rate"])
    if float(candidate["timeout_rate"]) > max_timeout:
        checks.append(_check("FAIL", "timeout_rate", actual=candidate["timeout_rate"], threshold=max_timeout))
    if int(candidate["timeouts"]) > int(baseline["timeouts"]):
        checks.append(_check("FAIL", "timeout_regression", candidate_timeouts=candidate["timeouts"], baseline_timeouts=baseline["timeouts"]))

    max_crash = float(policy["maximum_crash_rate"])
    if float(candidate["crash_rate"]) > max_crash:
        checks.append(_check("FAIL", "crash_rate", actual=candidate["crash_rate"], threshold=max_crash))
    if int(candidate["crash_count"]) > int(baseline["crash_count"]):
        checks.append(_check("FAIL", "crash_regression", candidate_crashes=candidate["crash_count"], baseline_crashes=baseline["crash_count"]))

    min_delta = float(policy["minimum_aggregate_win_rate_delta_vs_baseline"])
    if float(aggregate_delta["win_rate_delta"]) < min_delta:
        checks.append(_check("FAIL", "aggregate_win_rate_delta", actual=aggregate_delta["win_rate_delta"], threshold=min_delta))

    min_lower = float(policy["minimum_candidate_lower_ci"])
    if float(candidate["lower_ci"]) < min_lower:
        checks.append(_check("FAIL", "candidate_lower_ci", actual=candidate["lower_ci"], threshold=min_lower))

    min_required_games = int(policy["minimum_games_per_required_matchup"])
    max_regression = float(policy["maximum_required_matchup_regression"])
    for opponent in required:
        row = rows_by_opponent[opponent]
        if int(row["candidate_games"]) < min_required_games or int(row["baseline_games"]) < min_required_games:
            checks.append(_check("FAIL", "minimum_games_per_required_matchup", opponent=opponent, candidate_games=row["candidate_games"], baseline_games=row["baseline_games"], threshold=min_required_games))
        if float(row["win_rate_delta"]) < max_regression:
            checks.append(_check("FAIL", "required_hard_gate_regression", opponent=opponent, actual=row["win_rate_delta"], threshold=max_regression))

    random_names = {str(name) for name in policy.get("random_opponent_names", [])}
    real_rows = [row for row in comparison_rows if row["opponent"] not in random_names and row["available_for_comparison"]]
    random_rows = [row for row in comparison_rows if row["opponent"] in random_names and row["available_for_comparison"]]
    if random_rows and real_rows:
        random_delta = _weighted_delta(random_rows)
        real_delta = _weighted_delta(real_rows)
        if random_delta > 0 and real_delta < 0:
            checks.append(_check("FAIL", "random_only_improvement", random_win_rate_delta=random_delta, real_win_rate_delta=real_delta))

    if any(check["status"] == "FAIL" for check in checks):
        return _decision("FAIL", checks, policy)
    checks.append(_check("PASS", "all_configured_thresholds_met"))
    return _decision("PASS", checks, policy)


def _load_or_run_result(
    *,
    archive: Path,
    config_path: Path,
    policy: dict[str, Any],
    expected_role: str,
    result_dir: Path | None,
    output_dir: Path,
    command: str | None,
) -> dict[str, Any]:
    if result_dir is not None:
        compatibility = require_compatible_result(
            result_dir=result_dir,
            archive=archive,
            config_path=config_path,
            expected_config_sha256=benchmark_config_hash(config_path),
            required_matchups=[str(name) for name in policy.get("required_hard_gate_opponents", [])],
            expected_role=expected_role,
        )
        result = load_benchmark_result(result_dir)
        result["compatibility_status"] = {**compatibility, "reused": True}
        return result
    report = run_benchmark_league(
        archive=archive,
        config_path=config_path,
        output_dir=output_dir,
        command=command,
    )
    return {
        "summary": report["summary"],
        "rows": report["matchup_rows"],
        "result_dir": output_dir,
        "compatibility_status": {"compatible": True, "checks": [], "reused": False},
    }


def load_benchmark_result(result_dir: Path | str) -> dict[str, Any]:
    root = Path(result_dir)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    rows = _read_matchup_rows(root / "results_by_matchup.csv")
    return {
        "summary": summary,
        "rows": rows,
        "result_dir": root,
    }


def _read_matchup_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    for row in rows:
        stats = row_stats(row)
        for key, value in stats.items():
            row.setdefault(key, value)
    return rows


def _compare_matchups(
    candidate_result: dict[str, Any],
    baseline_result: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    required = {str(name) for name in policy.get("required_hard_gate_opponents", [])}
    candidate_by_opponent = {str(row["opponent"]): row for row in candidate_result["rows"]}
    baseline_by_opponent = {str(row["opponent"]): row for row in baseline_result["rows"]}
    opponents = sorted(set(candidate_by_opponent) | set(baseline_by_opponent))
    rows: list[dict[str, Any]] = []
    for opponent in opponents:
        candidate_row = candidate_by_opponent.get(opponent)
        baseline_row = baseline_by_opponent.get(opponent)
        candidate_stats = row_stats(candidate_row or {})
        baseline_stats = row_stats(baseline_row or {})
        rows.append(
            {
                "opponent": opponent,
                "required": opponent in required,
                "available_for_comparison": candidate_row is not None and baseline_row is not None,
                "candidate_games": candidate_stats["games"],
                "candidate_wins": candidate_stats["wins"],
                "candidate_losses": candidate_stats["losses"],
                "candidate_draws": candidate_stats["draws"],
                "candidate_errors": candidate_stats["errors"],
                "candidate_invalid_actions": candidate_stats["invalid_actions"],
                "candidate_timeouts": candidate_stats["timeouts"],
                "candidate_crash_count": candidate_stats["crash_count"],
                "candidate_win_rate": candidate_stats["win_rate"],
                "candidate_lower_ci": candidate_stats["lower_ci"],
                "candidate_upper_ci": candidate_stats["upper_ci"],
                "candidate_invalid_action_rate": candidate_stats["invalid_action_rate"],
                "candidate_timeout_rate": candidate_stats["timeout_rate"],
                "candidate_crash_rate": candidate_stats["crash_rate"],
                "baseline_games": baseline_stats["games"],
                "baseline_wins": baseline_stats["wins"],
                "baseline_losses": baseline_stats["losses"],
                "baseline_draws": baseline_stats["draws"],
                "baseline_errors": baseline_stats["errors"],
                "baseline_invalid_actions": baseline_stats["invalid_actions"],
                "baseline_timeouts": baseline_stats["timeouts"],
                "baseline_crash_count": baseline_stats["crash_count"],
                "baseline_win_rate": baseline_stats["win_rate"],
                "baseline_lower_ci": baseline_stats["lower_ci"],
                "baseline_upper_ci": baseline_stats["upper_ci"],
                "baseline_invalid_action_rate": baseline_stats["invalid_action_rate"],
                "baseline_timeout_rate": baseline_stats["timeout_rate"],
                "baseline_crash_rate": baseline_stats["crash_rate"],
                "win_rate_delta": round(candidate_stats["win_rate"] - baseline_stats["win_rate"], 6),
                "error_delta": candidate_stats["errors"] - baseline_stats["errors"],
                "invalid_action_delta": candidate_stats["invalid_actions"] - baseline_stats["invalid_actions"],
                "timeout_delta": candidate_stats["timeouts"] - baseline_stats["timeouts"],
                "crash_delta": candidate_stats["crash_count"] - baseline_stats["crash_count"],
            }
        )
    return rows


def _summary_payload(result: dict[str, Any], aggregate: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": result["summary"],
        "aggregate_stats": aggregate,
        "matchup_stats": [
            {
                "opponent": row.get("opponent"),
                **row_stats(row),
            }
            for row in result["rows"]
        ],
    }


def _delta_stats(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "win_rate_delta": round(candidate["win_rate"] - baseline["win_rate"], 6),
        "lower_ci_delta": round(candidate["lower_ci"] - baseline["lower_ci"], 6),
        "upper_ci_delta": round(candidate["upper_ci"] - baseline["upper_ci"], 6),
        "errors_delta": candidate["errors"] - baseline["errors"],
        "invalid_actions_delta": candidate["invalid_actions"] - baseline["invalid_actions"],
        "timeouts_delta": candidate["timeouts"] - baseline["timeouts"],
        "crash_count_delta": candidate["crash_count"] - baseline["crash_count"],
    }


def _weighted_delta(rows: list[dict[str, Any]]) -> float:
    candidate_finished = sum(int(row["candidate_games"]) for row in rows)
    baseline_finished = sum(int(row["baseline_games"]) for row in rows)
    candidate_wins = sum(int(row["candidate_wins"]) for row in rows)
    baseline_wins = sum(int(row["baseline_wins"]) for row in rows)
    candidate_rate = float(candidate_wins) / float(candidate_finished) if candidate_finished else 0.0
    baseline_rate = float(baseline_wins) / float(baseline_finished) if baseline_finished else 0.0
    return round(candidate_rate - baseline_rate, 6)


def _write_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["opponent"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check(status: str, reason: str, **fields: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **fields}


def _decision(status: str, checks: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "checks": checks,
        "policy": policy,
        "kaggle_submission_made": False,
    }


def _maybe_validate_champion_registry(registry_path: Path | str | None, baseline_path: Path) -> dict[str, Any] | None:
    if registry_path is None:
        return None
    path = Path(registry_path)
    if not path.exists():
        return None
    champion = validate_champion_registry(path)
    if Path(champion["archive_path"]).resolve() == baseline_path.resolve():
        return {
            "status": "validated",
            "champion_name": champion.get("champion_name"),
            "archive_path": champion["archive_path"],
            "archive_sha256": champion["actual_archive_sha256"],
            "human_promotion_instructions": champion["human_promotion_instructions"],
        }
    return {
        "status": "validated_not_baseline",
        "champion_name": champion.get("champion_name"),
        "archive_path": champion["archive_path"],
        "archive_sha256": champion["actual_archive_sha256"],
    }
