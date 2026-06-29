from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.hop_strategy_report import build_hop_strategy_rows
from ptcg.hop_strategy_report import choose_latest_completed_episodes
from ptcg.hop_strategy_report import select_latest_complete_submissions
from ptcg.hop_strategy_report import summarize_hop_strategy
from ptcg.hop_strategy_report import write_hop_strategy_report_bundle
from ptcg.kaggle_episode_ingest import SubmissionEpisodeRef
from ptcg.kaggle_episode_ingest import build_ingest_manifest
from ptcg.kaggle_episode_ingest import jsonable_manifest
from ptcg.kaggle_episode_ingest import own_agent_indices
from ptcg.kaggle_loss_mining import build_episode_actor_records
from ptcg.kaggle_loss_mining import submission_record_from_api
from ptcg.kaggle_loss_mining import write_loss_dataset


META_URL = "https://ptcg-kaggle-meta.vercel.app/api/meta?page=1"


def _load_meta_snapshot() -> dict[str, Any]:
    with urlopen(META_URL, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("meta API did not return an object")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _files(path: Path) -> set[Path]:
    if not path.exists():
        return set()
    return {item for item in path.rglob("*") if item.is_file()}


def _capture_download(callable_obj: Any, target_dir: Path, preferred_name: str, attempts: int = 4) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / preferred_name
    if target.exists() and target.stat().st_size > 0:
        return target
    before = _files(target_dir)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            callable_obj(str(target_dir))
            break
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(min(2**attempt, 10))
    after = _files(target_dir)
    candidates = list(after - before)
    if not candidates:
        candidates = [path for path in after if preferred_name in path.name]
    if not candidates:
        if last_error is not None:
            raise FileNotFoundError(f"download failed for {preferred_name}: {last_error}") from last_error
        raise FileNotFoundError(f"download did not create a file matching {preferred_name}")
    source = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def _copy_raw(source: Path, target_dir: Path, preferred_name: str | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (preferred_name or source.name)
    shutil.copy2(source, target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _own_team_id(episode: Any, submission_id: int) -> int | None:
    for agent in getattr(episode, "agents", []) or []:
        if int(getattr(agent, "submission_id", -1)) != int(submission_id):
            continue
        team_id = getattr(agent, "team_id", None)
        return int(team_id) if team_id is not None else None
    return None


def _git_status() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return f"git_status_error:{type(exc).__name__}:{exc}"
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    today = date.today().isoformat()
    parser = argparse.ArgumentParser(
        description="Download one game from each of the latest two complete Kaggle submissions and label Hop strategy."
    )
    parser.add_argument("--competition", default="pokemon-tcg-ai-battle")
    parser.add_argument("--submission-limit", type=int, default=2)
    parser.add_argument("--submission-id", type=int, action="append", help="Specific submission id to include.")
    parser.add_argument("--episodes-per-submission", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data") / "kaggle_public_leaderboard" / f"{today}_last_two_hop_strategy",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("artifacts") / "ptcg_research" / "current" / f"hop_latest_two_strategy_{today.replace('-', '_')}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from kaggle.api.kaggle_api_extended import KaggleApi

    command = " ".join(sys.argv)
    api = KaggleApi()
    api.authenticate()
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)

    meta_snapshot = _load_meta_snapshot()
    raw_submissions = api.competition_submissions(args.competition, page_size=args.page_size) or []
    submission_records = [submission_record_from_api(item) for item in raw_submissions]
    if args.submission_id:
        wanted = {int(value) for value in args.submission_id}
        selected_submissions = [
            record
            for record in submission_records
            if record.submission_id in wanted and record.status == "complete"
        ]
        selected_submissions = sorted(
            selected_submissions,
            key=lambda record: args.submission_id.index(record.submission_id),
        )
        missing = wanted - {record.submission_id for record in selected_submissions}
        if missing:
            raise RuntimeError(f"complete submissions not found on first page: {sorted(missing)}")
    else:
        selected_submissions = select_latest_complete_submissions(submission_records, limit=args.submission_limit)
    if not selected_submissions:
        raise RuntimeError("no complete submissions found")

    raw_submission_by_id = {int(getattr(item, "ref")): item for item in raw_submissions}
    selected_raw_submissions = {
        record.submission_id: raw_submission_by_id[record.submission_id] for record in selected_submissions
    }
    submission_record_by_id = {record.submission_id: record for record in selected_submissions}

    refs: list[SubmissionEpisodeRef] = []
    episodes_by_id: dict[int, Any] = {}
    replay_paths: dict[int, Path] = {}
    log_paths: dict[int, list[Path]] = {}
    source_file_by_replay_id: dict[str, str] = {}
    source_hash_by_replay_id: dict[str, str] = {}
    log_paths_by_episode_id: dict[int, list[str]] = {}
    download_failures: list[dict[str, Any]] = []
    actor_records = []

    for submission in selected_submissions:
        episodes = api.competition_list_episodes(submission.submission_id) or []
        selected_episodes = choose_latest_completed_episodes(
            episodes,
            submission_id=submission.submission_id,
            limit=args.episodes_per_submission,
        )
        if not selected_episodes:
            download_failures.append(
                {
                    "submission_id": submission.submission_id,
                    "stage": "select_episode",
                    "error": "no completed episode listed for submission",
                }
            )
            continue
        for episode in selected_episodes:
            episode_id = int(getattr(episode, "id"))
            episodes_by_id[episode_id] = episode
            refs.append(
                SubmissionEpisodeRef(
                    submission_id=submission.submission_id,
                    episode_id=episode_id,
                    source_url=f"submissionId={submission.submission_id}&episodeId={episode_id}",
                )
            )
            data_raw_dir = args.output_root / f"submission_{submission.submission_id}" / f"episode_{episode_id}"
            artifact_raw_dir = args.artifact_dir / "raw" / f"submission_{submission.submission_id}" / f"episode_{episode_id}"

            try:
                replay_data_path = _capture_download(
                    lambda path, eid=episode_id: api.competition_episode_replay(eid, path=path, quiet=True),
                    data_raw_dir,
                    f"episode-{episode_id}-replay.json",
                )
                replay_artifact_path = _copy_raw(
                    replay_data_path,
                    artifact_raw_dir,
                    preferred_name=f"episode-{episode_id}-replay.json",
                )
                replay_paths[episode_id] = replay_artifact_path
                source_file_by_replay_id[str(episode_id)] = str(replay_artifact_path)
                source_hash_by_replay_id[str(episode_id)] = _sha256(replay_artifact_path)
            except Exception as exc:
                download_failures.append(
                    {
                        "submission_id": submission.submission_id,
                        "episode_id": episode_id,
                        "stage": "download_replay",
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
                continue

            episode_logs: list[Path] = []
            for agent_index in own_agent_indices(episode, submission.submission_id):
                try:
                    log_data_path = _capture_download(
                        lambda path, eid=episode_id, index=agent_index: api.competition_episode_agent_logs(
                            eid, index, path=path, quiet=True
                        ),
                        data_raw_dir,
                        f"episode-{episode_id}-agent-{agent_index}.log",
                    )
                    episode_logs.append(
                        _copy_raw(
                            log_data_path,
                            artifact_raw_dir,
                            preferred_name=f"episode-{episode_id}-agent-{agent_index}.log",
                        )
                    )
                except Exception as exc:
                    download_failures.append(
                        {
                            "submission_id": submission.submission_id,
                            "episode_id": episode_id,
                            "agent_index": agent_index,
                            "stage": "download_agent_log",
                            "error": f"{type(exc).__name__}:{exc}",
                        }
                    )
            log_paths[episode_id] = episode_logs
            log_paths_by_episode_id[episode_id] = [str(path) for path in episode_logs]

            own_team_id = _own_team_id(episode, submission.submission_id)
            if own_team_id is not None:
                actor_records.extend(
                    build_episode_actor_records(
                        episode,
                        replay_path=replay_paths[episode_id],
                        submissions_by_id=submission_record_by_id,
                        own_team_id=own_team_id,
                    )
                )

    if not refs:
        raise RuntimeError("no episodes were selected or downloaded")

    manifest = build_ingest_manifest(
        refs=refs,
        submissions=selected_raw_submissions,
        episodes=episodes_by_id,
        replay_paths=replay_paths,
        agent_log_paths=log_paths,
        output_dir=args.artifact_dir,
        meta_snapshot=meta_snapshot,
        command=command,
    )
    manifest["download_failures"] = download_failures
    manifest["actor_records"] = len(actor_records)
    _write_json(args.output_root / "ingest_manifest.json", jsonable_manifest(manifest))
    _write_json(args.artifact_dir / "ingest_manifest.json", jsonable_manifest(manifest))
    _write_json(args.artifact_dir / "meta_snapshot.json", meta_snapshot)

    dataset_report = write_loss_dataset(
        output_dir=args.artifact_dir / "dataset",
        submissions=selected_submissions,
        actor_records=actor_records,
        meta_snapshot=meta_snapshot,
        command=command,
    )
    decision_rows = _load_jsonl(Path(dataset_report["paths"]["decision_labels_jsonl"]))
    strategy_rows = build_hop_strategy_rows(
        decision_rows,
        source_file_by_replay_id=source_file_by_replay_id,
        source_hash_by_replay_id=source_hash_by_replay_id,
        log_paths_by_episode_id=log_paths_by_episode_id,
    )
    summary = summarize_hop_strategy(
        strategy_rows=strategy_rows,
        submissions=selected_submissions,
        meta_snapshot=meta_snapshot,
        command=command,
        download_failures=download_failures,
    )
    summary["replay_count"] = len(replay_paths)
    summary["agent_log_count"] = sum(len(paths) for paths in log_paths.values())
    summary["input_paths"] = {
        "output_root": str(args.output_root),
        "artifact_dir": str(args.artifact_dir),
        "raw_replay_paths": {str(key): str(path) for key, path in replay_paths.items()},
        "agent_log_paths": {str(key): [str(path) for path in paths] for key, paths in log_paths.items()},
    }
    summary["dataset_report"] = dataset_report
    summary["ingest_manifest"] = str(args.artifact_dir / "ingest_manifest.json")
    summary["git_status_short"] = _git_status()

    bundle = write_hop_strategy_report_bundle(
        summary=summary,
        strategy_rows=strategy_rows,
        output_dir=args.artifact_dir,
    )
    run_report = {
        "command": command,
        "bundle": bundle,
        "summary_json": bundle["summary_json"],
        "strategy_labels_jsonl": bundle["strategy_labels_jsonl"],
        "markdown_report": bundle["markdown_report"],
        "ingest_manifest": str(args.artifact_dir / "ingest_manifest.json"),
        "dataset_report": dataset_report,
        "kaggle_submission_made": False,
    }
    _write_json(args.artifact_dir / "run_report.json", run_report)
    print(
        json.dumps(
            {
                "artifact_dir": str(args.artifact_dir),
                "selected_submissions": [record.submission_id for record in selected_submissions],
                "selected_episodes": [ref.episode_id for ref in refs],
                "decision_rows": len(decision_rows),
                "strategy_rows": len(strategy_rows),
                "agent_logs": summary["agent_log_count"],
                "download_failures": len(download_failures),
                "markdown_report": bundle["markdown_report"],
                "summary_json": bundle["summary_json"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
