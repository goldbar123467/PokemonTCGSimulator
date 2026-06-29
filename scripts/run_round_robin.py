from __future__ import annotations

import argparse
import glob
import json
from dataclasses import asdict
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.round_robin import prepare_submission_packages, run_round_robin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare and optionally run a PTCG submission round robin.")
    parser.add_argument("--archive", action="append", type=Path, default=[])
    parser.add_argument("--archive-glob", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--games-per-pair", "--games", dest="games_per_pair", type=int, default=1)
    parser.add_argument("--sdk-path", type=Path, default=Path("data/official"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--registry-only", action="store_true")
    args = parser.parse_args(argv)

    archives = _expand_archives(args.archive, args.archive_glob)
    if not archives:
        raise SystemExit("No archives supplied. Use --archive or --archive-glob.")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    packages = prepare_submission_packages(archives, extract_root=output_dir / "prepared")

    if args.registry_only:
        registry_path = output_dir / "submission_registry.json"
        summary_path = output_dir / "summary.json"
        registry_path.write_text(
            json.dumps([asdict(package) for package in packages], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary = {
            "engine": "official_cg_sdk",
            "engine_path": str(args.sdk_path.resolve()),
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
        print(
            json.dumps(
                {
                    "output_dir": str(output_dir),
                    "package_count": len(packages),
                    "eligible_package_count": summary["eligible_package_count"],
                    "matchup_count": 0,
                    "report_paths": summary["report_paths"],
                    "kaggle_submission_made": False,
                },
                sort_keys=True,
            )
        )
        return 0

    report = run_round_robin(
        packages,
        output_dir=output_dir,
        games_per_pair=args.games_per_pair,
        seed=args.seed,
        sdk_path=args.sdk_path,
        max_steps=args.max_steps,
        command=_command_string(),
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "package_count": report["summary"]["package_count"],
                "eligible_package_count": report["summary"]["package_count"],
                "matchup_count": len(report["matchup_matrix"]),
                "report_paths": report["report_paths"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )
    return 0


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
