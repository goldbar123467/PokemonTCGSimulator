from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.lucario_ceiling_audit import build_audit, render_markdown
from ptcg.opponent_pool import parse_leaderboard_zip


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_meta(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as handle:
        return json.load(handle)


def _git_status_short() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return ""
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the Lucario ceiling audit artifacts.")
    parser.add_argument("--meta-api-url", default="https://ptcg-kaggle-meta.vercel.app/api/meta?page=1")
    parser.add_argument("--leaderboard-zip", type=Path, required=True)
    parser.add_argument("--public-manifest", type=Path, default=Path("artifacts/public_meta/opponents_manifest.json"))
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/mining/bootstrap_archetype_coverage.json"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/mining/lucario_ceiling_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/mining/lucario_ceiling_audit.md"),
    )
    args = parser.parse_args()

    meta = _fetch_meta(args.meta_api_url)
    leaderboard = parse_leaderboard_zip(args.leaderboard_zip)
    manifest = _read_json(args.public_manifest)
    coverage = _read_json(args.coverage) if args.coverage.exists() else None

    audit = build_audit(
        meta_items=meta.get("items") or meta.get("archetypes") or [],
        leaderboard_entries=leaderboard,
        public_manifest=manifest,
        coverage=coverage if isinstance(coverage, dict) else None,
        meta_snapshot={key: meta.get(key) for key in ["date", "latestDate", "redirected", "totalDecks", "source"]},
    )
    audit["run"] = {
        "command": sys.argv,
        "git_status_short": _git_status_short(),
        "leaderboard_zip": str(args.leaderboard_zip),
        "public_manifest": str(args.public_manifest),
        "coverage": str(args.coverage),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "markdown": str(args.output_md), "verdict": audit["verdict"]}))


if __name__ == "__main__":
    main()
