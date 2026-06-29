from __future__ import annotations

import argparse
import glob
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.internal_leaderboard import (
    CURRENT_META_URL,
    benchmark_candidates,
    build_candidate_registry,
    build_gate_rows,
    build_submit_offer,
    load_json_path_or_url,
    rank_candidates,
    render_markdown_report,
)


def _expand_archives(patterns: list[str]) -> list[Path]:
    archives: list[Path] = []
    for pattern in patterns:
        matches = sorted(Path(match) for match in glob.glob(pattern))
        if matches:
            archives.extend(matches)
            continue
        path = Path(pattern)
        if path.exists():
            archives.append(path)
    seen: set[Path] = set()
    unique: list[Path] = []
    for archive in archives:
        resolved = archive.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return result.stderr.strip()
    return result.stdout


def _command_string() -> str:
    return " ".join(shlex.quote(part) for part in sys.argv)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an internal no-submit leaderboard over local PTCG submission archives."
    )
    parser.add_argument("--archive-glob", action="append", default=["artifacts/submission*.tar.gz"])
    parser.add_argument(
        "--gate-manifest",
        action="append",
        type=Path,
        default=None,
        help="Gate/opponent manifest JSON. Repeatable.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/internal_leaderboard/current"))
    parser.add_argument("--meta-json", type=Path)
    parser.add_argument("--meta-url", default=CURRENT_META_URL)
    parser.add_argument("--no-meta-fetch", action="store_true")
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--seed", type=int, default=62027)
    parser.add_argument("--hard-gate-floor", type=float, default=0.35)
    parser.add_argument("--registry-only", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    archives = _expand_archives(args.archive_glob)
    if not archives:
        raise SystemExit("No archives found for --archive-glob.")

    if args.meta_json:
        meta_snapshot = load_json_path_or_url(args.meta_json)
    elif args.no_meta_fetch:
        meta_snapshot = None
    else:
        meta_snapshot = load_json_path_or_url(args.meta_url)

    manifest_paths = args.gate_manifest or [
        Path("artifacts/kaggle_submission_54024037_strategy/gates/current_meta_manifest.json"),
        Path("artifacts/public_meta/opponents_manifest.json"),
    ]

    candidate_registry = build_candidate_registry(archives, extract_root=output_dir / "extracted_candidates")
    gate_rows = build_gate_rows(manifest_paths, meta_snapshot=meta_snapshot)
    runnable_gates = [gate for gate in gate_rows if gate.get("available") and gate.get("ok")]
    if args.registry_only:
        matchup_rows = []
    else:
        matchup_rows = benchmark_candidates(
            [row for row in candidate_registry if row.get("eligible_for_benchmark")],
            runnable_gates,
            games=args.games,
            seed=args.seed,
        )
    leaderboard = rank_candidates(candidate_registry, matchup_rows, hard_gate_floor=args.hard_gate_floor)
    blocking_gate_gaps = [
        gate
        for gate in gate_rows
        if gate.get("hard_gate") and not gate.get("available") and float(gate.get("gate_weight") or 0.0) > 0.0
    ]
    submit_offer = build_submit_offer(leaderboard, blocking_gate_gaps=blocking_gate_gaps)
    git_status = _git_status()
    command = _command_string()

    totals = {
        "wins": sum(int(row.get("wins") or 0) for row in matchup_rows),
        "losses": sum(int(row.get("losses") or 0) for row in matchup_rows),
        "draws": sum(int(row.get("draws") or 0) for row in matchup_rows),
        "finished": sum(int(row.get("finished") or 0) for row in matchup_rows),
        "errors": sum(len(row.get("errors") or []) for row in matchup_rows),
    }
    run_summary = {
        "command": command,
        "git_status": git_status,
        "meta_date": (meta_snapshot or {}).get("date"),
        "latest_date": (meta_snapshot or {}).get("latestDate"),
        "redirected": (meta_snapshot or {}).get("redirected"),
        "total_decks": (meta_snapshot or {}).get("totalDecks"),
        "dataset_url": ((meta_snapshot or {}).get("source") or {}).get("datasetUrl"),
        "candidate_archive_count": len(candidate_registry),
        "eligible_candidate_count": sum(1 for row in candidate_registry if row.get("eligible_for_benchmark")),
        "opponent_count": len(runnable_gates),
        "gate_count": len(gate_rows),
        "seed": args.seed,
        "games": 0 if args.registry_only else args.games,
        "matchup_count": len(matchup_rows),
        "replay_count": 0,
        "totals": totals,
        "package_paths": [row.get("archive") for row in candidate_registry],
        "sha256s": {row["name"]: row.get("sha256") for row in candidate_registry},
        "kaggle_submission_made": False,
    }

    files = {
        "meta_snapshot.json": meta_snapshot or {},
        "candidate_registry.json": candidate_registry,
        "gate_manifest.json": gate_rows,
        "matchup_matrix.json": matchup_rows,
        "internal_leaderboard.json": leaderboard,
        "submit_offer.json": submit_offer,
        "run_summary.json": run_summary,
    }
    for name, payload in files.items():
        (output_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "internal_leaderboard.md").write_text(
        render_markdown_report(
            meta_snapshot=meta_snapshot,
            candidate_registry=candidate_registry,
            gate_rows=gate_rows,
            leaderboard=leaderboard,
            submit_offer=submit_offer,
            command=command,
            git_status=git_status,
            games=0 if args.registry_only else args.games,
            seed=args.seed,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "candidates": len(candidate_registry),
                "eligible": run_summary["eligible_candidate_count"],
                "gates": len(gate_rows),
                "available_gates": len(runnable_gates),
                "matchups": len(matchup_rows),
                "recommend_submit": submit_offer["recommend_submit"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
