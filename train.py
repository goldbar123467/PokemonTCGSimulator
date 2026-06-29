from __future__ import annotations

import argparse
import glob
import json
import shlex
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.gameplay_log_guard import GameplayLogGateError, assert_training_gameplay_logs_allowed
from ptcg.round_robin import prepare_submission_packages, run_round_robin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kaggle readiness workflow: validate local submission archives, "
            "write provenance reports, and optionally run a no-submit round robin."
        )
    )
    parser.add_argument("--archive", action="append", type=Path, default=[], help="Submission .tar.gz or .zip path.")
    parser.add_argument("--archive-glob", action="append", default=[], help="Glob for submission archives.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/kaggle_readiness"))
    parser.add_argument("--games-per-pair", "--games", dest="games_per_pair", type=int, default=1)
    parser.add_argument("--sdk-path", type=Path, default=Path("data/official"))
    parser.add_argument("--workflow-config", type=Path, default=Path("configs/current_workflow.json"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--run-benchmark", action="store_true", help="Run the configured benchmark league for one archive.")
    parser.add_argument("--benchmark-config", type=Path, default=Path("configs/benchmark_league.json"))
    parser.add_argument("--benchmark-target-games-per-matchup", type=int, default=None)
    parser.add_argument("--benchmark-resume", action="store_true")
    parser.add_argument("--seeds", default=None, help="Comma-separated benchmark seed list override.")
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="Only expand archives and write validation/provenance metadata; do not run games.",
    )
    args = parser.parse_args(argv)

    try:
        allowed_gameplay_logs = assert_training_gameplay_logs_allowed(
            project_root=ROOT,
            config_path=args.workflow_config,
        )
    except GameplayLogGateError as exc:
        parser.error(str(exc))

    archives = _expand_archives(args.archive, args.archive_glob)
    if not archives:
        parser.error("No archives supplied. Use --archive or --archive-glob.")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.run_benchmark:
        if len(archives) != 1:
            parser.error("--run-benchmark requires exactly one archive")
        report = _run_benchmark_readiness(
            archive=archives[0],
            output_dir=output_dir,
            benchmark_config=args.benchmark_config,
            benchmark_target_games_per_matchup=args.benchmark_target_games_per_matchup,
            benchmark_resume=args.benchmark_resume,
            seed_list=args.seeds,
            gameplay_log_count=len(allowed_gameplay_logs),
        )
        print(
            json.dumps(
                {
                    "output_dir": str(output_dir),
                    "package_count": report["summary"]["package_count"],
                    "eligible_package_count": report["summary"]["eligible_package_count"],
                    "matchup_count": report["summary"]["matchup_count"],
                    "report_paths": report["summary"]["report_paths"],
                    "kaggle_submission_made": False,
                },
                sort_keys=True,
            )
        )
        return 0

    packages = prepare_submission_packages(archives, extract_root=output_dir / "prepared")

    if args.registry_only:
        report = _write_registry_only_report(
            packages=packages,
            output_dir=output_dir,
            sdk_path=args.sdk_path,
            gameplay_log_count=len(allowed_gameplay_logs),
        )
    else:
        report = run_round_robin(
            packages,
            output_dir=output_dir,
            games_per_pair=args.games_per_pair,
            seed=args.seed,
            sdk_path=args.sdk_path,
            max_steps=args.max_steps,
            command=_command_string(),
        )
        summary_path = Path(report["report_paths"]["summary"])
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.update(_readiness_metadata(gameplay_log_count=len(allowed_gameplay_logs)))
        summary["eligible_package_count"] = sum(1 for package in packages if package.eligible_for_round_robin)
        summary["matchup_count"] = len(report["matchup_matrix"])
        summary["report_paths"] = report["report_paths"]
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["summary"] = summary

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "package_count": report["summary"]["package_count"],
                "eligible_package_count": report["summary"]["eligible_package_count"],
                "matchup_count": report["summary"]["matchup_count"],
                "report_paths": report["summary"]["report_paths"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_benchmark_readiness(
    *,
    archive: Path,
    output_dir: Path,
    benchmark_config: Path,
    benchmark_target_games_per_matchup: int | None,
    benchmark_resume: bool,
    seed_list: str | None,
    gameplay_log_count: int,
) -> dict[str, object]:
    from ptcg.benchmark_league import run_benchmark_league
    from ptcg.seed_schedule import parse_seed_list

    benchmark_output = output_dir / "benchmark_league"
    benchmark_report = run_benchmark_league(
        archive=archive,
        config_path=benchmark_config,
        output_dir=benchmark_output,
        explicit_seeds=parse_seed_list(seed_list) if seed_list is not None else None,
        target_games_per_matchup=benchmark_target_games_per_matchup,
        resume=benchmark_resume,
        command=_command_string(),
    )
    summary_path = output_dir / "summary.json"
    benchmark_summary = benchmark_report["summary"]
    summary = {
        "workflow": "kaggle_readiness",
        **_readiness_metadata(gameplay_log_count=gameplay_log_count),
        "engine": benchmark_summary["engine"],
        "engine_path": benchmark_summary["engine_path"],
        "package_count": 1,
        "eligible_package_count": 1,
        "opponent_count": benchmark_summary["opponent_count"],
        "matchup_count": len(benchmark_report["matchup_rows"]),
        "command": _command_string(),
        "git_status": _git_status(),
        "package_paths": [str(Path(archive).resolve())],
        "sha256s": {Path(archive).name: benchmark_summary["candidate_archive_sha256"]},
        "benchmark": {
            "status": benchmark_summary["status"],
            "scheduled_games": benchmark_summary["scheduled_games"],
            "finished_games": benchmark_summary["finished_games"],
            "errors": benchmark_summary["errors"],
            "available_opponent_count": benchmark_summary["available_opponent_count"],
            "unavailable_opponent_count": benchmark_summary["unavailable_opponent_count"],
            "report_paths": benchmark_summary["report_paths"],
            "kaggle_submission_made": False,
        },
        "report_paths": {
            "summary": str(summary_path.resolve()),
            "benchmark_summary": benchmark_summary["report_paths"]["summary"],
            "benchmark_results_by_game": benchmark_summary["report_paths"]["results_by_game"],
            "benchmark_results_by_matchup": benchmark_summary["report_paths"]["results_by_matchup"],
            "benchmark_seed_schedule": benchmark_summary["report_paths"]["seed_schedule"],
            "benchmark_opponent_registry": benchmark_summary["report_paths"]["opponent_registry"],
        },
        "kaggle_submission_made": False,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": summary}


def _write_registry_only_report(
    *,
    packages: list,
    output_dir: Path,
    sdk_path: Path,
    gameplay_log_count: int,
) -> dict[str, object]:
    registry_path = output_dir / "submission_registry.json"
    summary_path = output_dir / "summary.json"
    registry_path.write_text(
        json.dumps([asdict(package) for package in packages], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "workflow": "kaggle_readiness",
        **_readiness_metadata(gameplay_log_count=gameplay_log_count),
        "engine": "official_cg_sdk",
        "engine_path": str(sdk_path.resolve()),
        "package_count": len(packages),
        "eligible_package_count": sum(1 for package in packages if package.eligible_for_round_robin),
        "opponent_count": len(packages),
        "replay_count": 0,
        "matchup_count": 0,
        "command": _command_string(),
        "git_status": _git_status(),
        "package_paths": [package.source_path for package in packages],
        "sha256s": {package.name: package.source_sha256 for package in packages},
        "report_paths": {
            "submission_registry": str(registry_path.resolve()),
            "summary": str(summary_path.resolve()),
        },
        "kaggle_submission_made": False,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": summary}


def _readiness_metadata(*, gameplay_log_count: int) -> dict[str, object]:
    return {
        "workflow": "kaggle_readiness",
        "gameplay_log_gate": "data_manifest/current_gameplay_logs.txt",
        "eligible_gameplay_log_count": gameplay_log_count,
        "official_sdk_seed_control": False,
        "crn_available": False,
        "sample_model": "independent_batch",
        "kaggle_submission_made": False,
    }


def _expand_archives(archives: list[Path], archive_globs: list[str]) -> list[Path]:
    paths = [path.resolve() for path in archives if path.exists()]
    for pattern in archive_globs:
        paths.extend(Path(match).resolve() for match in glob.glob(pattern))
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else result.stderr


def _command_string() -> str:
    return " ".join(shlex.quote(part) for part in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
