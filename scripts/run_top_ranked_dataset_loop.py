from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.leaderboard_breakdown import build_label_dataset
from ptcg.top_ranked_dataset_loop import build_per_game_trend_summary
from ptcg.top_ranked_dataset_loop import scan_top_ranked_episodes


META_URL = "https://ptcg-kaggle-meta.vercel.app/api/meta?page=1"
PUBLIC_BULK_NO_FOCUS_TEAM = "__public_bulk_no_focus_team__"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_meta(path: Path | None) -> dict:
    if path and path.exists():
        return _load_json(path)
    with urlopen(META_URL, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("meta API returned a non-object payload")
    return payload


def _find_leaderboard_csv(path: Path) -> Path:
    if path.is_file():
        return path
    candidates = sorted(path.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    archives = sorted(path.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    for archive in archives:
        with zipfile.ZipFile(archive) as zipped:
            names = [name for name in zipped.namelist() if name.lower().endswith(".csv")]
            if not names:
                continue
            target = path / Path(names[0]).name.replace(":", "_")
            if not target.exists():
                with zipped.open(names[0]) as source, target.open("wb") as dest:
                    dest.write(source.read())
            return target
    raise FileNotFoundError(f"no leaderboard CSV found in {path}")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a no-RL top-ranked PTCG replay scan and trend loop.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--leaderboard", type=Path, required=True, help="Leaderboard CSV or directory containing it.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--meta-json", type=Path, default=None)
    parser.add_argument("--top-limit", type=int, default=50)
    parser.add_argument("--label-limit", type=int, default=12)
    parser.add_argument("--max-scan-games", type=int, default=None)
    parser.add_argument("--focus-team", default=None)
    parser.add_argument("--skip-labels", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = " ".join(sys.argv)
    meta = _load_meta(args.meta_json)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "meta_snapshot.json", meta)
    leaderboard_csv = _find_leaderboard_csv(args.leaderboard)

    scan = scan_top_ranked_episodes(
        dataset_dir=args.dataset_dir,
        leaderboard_csv=leaderboard_csv,
        output_dir=args.output_dir / "full_scan",
        top_limit=args.top_limit,
        max_games=args.max_scan_games,
        command=command,
        meta_snapshot=meta,
    )
    label_result = None
    trend_result = None
    selected_paths = [Path(row["path"]) for row in scan["top_episodes"][: max(0, args.label_limit)] if row.get("path")]
    if selected_paths and not args.skip_labels:
        label_result = build_label_dataset(
            selected_paths,
            output_dir=args.output_dir / "labels",
            focus_team=args.focus_team or PUBLIC_BULK_NO_FOCUS_TEAM,
            meta_snapshot=meta,
            command=command,
        )
        trend_result = build_per_game_trend_summary(
            Path(label_result["paths"]["hard_labels_jsonl"]),
            args.output_dir / "trends" / "per_game_trends.json",
            command=command,
        )

    report = {
        "command": command,
        "dataset_dir": str(args.dataset_dir),
        "leaderboard_csv": str(leaderboard_csv),
        "meta": {
            "date": meta.get("date"),
            "latestDate": meta.get("latestDate"),
            "redirected": meta.get("redirected"),
            "totalDecks": meta.get("totalDecks"),
            "source": meta.get("source"),
        },
        "scan": {
            "scanned_count": scan["scanned_count"],
            "candidate_file_count": scan["candidate_file_count"],
            "error_count": scan["error_count"],
            "top_episode_count": len(scan["top_episodes"]),
            "paths": scan["paths"],
        },
        "labels": {
            "selected_replay_count": len(selected_paths),
            "summary": (label_result or {}).get("summary"),
            "paths": (label_result or {}).get("paths"),
        },
        "trends": {
            "game_count": (trend_result or {}).get("game_count"),
            "decision_rows": (trend_result or {}).get("decision_rows"),
            "aggregate_trend_counts": (trend_result or {}).get("aggregate_trend_counts"),
            "path": str(args.output_dir / "trends" / "per_game_trends.json") if trend_result else None,
        },
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }
    _write_json(args.output_dir / "run_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
