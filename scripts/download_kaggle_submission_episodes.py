from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.kaggle_episode_ingest import build_ingest_manifest
from ptcg.kaggle_episode_ingest import jsonable_manifest
from ptcg.kaggle_episode_ingest import own_agent_indices
from ptcg.kaggle_episode_ingest import parse_submission_episode_refs
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
    last_error: Exception | None = None
    before = _files(target_dir)
    for attempt in range(1, attempts + 1):
        try:
            callable_obj(str(target_dir))
            break
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(min(2 ** attempt, 10))
    after = _files(target_dir)
    candidates = list(after - before)
    if not candidates:
        candidates = [path for path in after if preferred_name in path.name]
    if not candidates:
        if last_error is not None:
            raise FileNotFoundError(f"download failed for {preferred_name} in {target_dir}: {last_error}") from last_error
        raise FileNotFoundError(f"download did not create a file matching {preferred_name} in {target_dir}")
    source = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def _list_submissions(api: Any, competition: str, needed_ids: set[int]) -> dict[int, Any]:
    submissions: dict[int, Any] = {}
    for page_number in range(1, 16):
        page = api.competition_submissions(competition, page_number=page_number, page_size=100) or []
        if not page:
            break
        for item in page:
            if item is None:
                continue
            submission_id = int(getattr(item, "ref"))
            if submission_id in needed_ids:
                submissions[submission_id] = item
        if needed_ids.issubset(submissions):
            break
    return submissions


def _find_episode(api: Any, submission_id: int, episode_id: int) -> Any | None:
    for episode in api.competition_list_episodes(submission_id) or []:
        if int(getattr(episode, "id")) == int(episode_id):
            return episode
    return None


def _own_team_id(episode: Any, submission_id: int) -> int | None:
    for agent in getattr(episode, "agents", []) or []:
        if int(getattr(agent, "submission_id", -1)) == int(submission_id):
            team_id = getattr(agent, "team_id", None)
            return int(team_id) if team_id is not None else None
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download exact Kaggle PTCG submission episodes and agent logs.")
    parser.add_argument("--competition", default="pokemon-tcg-ai-battle")
    parser.add_argument("--ref", action="append", required=True, help="Kaggle URL or submissionId=...&episodeId=...")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/kaggle_public_leaderboard/manual_ingest"),
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("artifacts/ptcg_research/current/first_two_public_leaderboard"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from kaggle.api.kaggle_api_extended import KaggleApi

    refs = parse_submission_episode_refs(args.ref)
    api = KaggleApi()
    api.authenticate()

    args.output_root.mkdir(parents=True, exist_ok=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    meta_snapshot = _load_meta_snapshot()
    submissions = _list_submissions(api, args.competition, {ref.submission_id for ref in refs})
    submission_records = {
        submission_id: submission_record_from_api(submission)
        for submission_id, submission in submissions.items()
    }

    episodes: dict[int, Any] = {}
    replay_paths: dict[int, Path] = {}
    log_paths: dict[int, list[Path]] = {}
    download_failures: list[dict[str, Any]] = []
    actor_records = []

    for ref in refs:
        episode = _find_episode(api, ref.submission_id, ref.episode_id)
        if episode is None:
            raise RuntimeError(f"episode {ref.episode_id} was not listed for submission {ref.submission_id}")
        episodes[ref.episode_id] = episode
        raw_dir = args.output_root / f"submission_{ref.submission_id}" / f"episode_{ref.episode_id}"

        replay_path = _capture_download(
            lambda path: api.competition_episode_replay(ref.episode_id, path=path, quiet=True),
            raw_dir,
            f"episode-{ref.episode_id}-replay.json",
        )
        replay_paths[ref.episode_id] = replay_path

        episode_logs: list[Path] = []
        for agent_index in own_agent_indices(episode, ref.submission_id):
            try:
                episode_logs.append(
                    _capture_download(
                        lambda path, index=agent_index: api.competition_episode_agent_logs(
                            ref.episode_id, index, path=path, quiet=True
                        ),
                        raw_dir,
                        f"episode-{ref.episode_id}-agent-{agent_index}.log",
                    )
                )
            except Exception as exc:
                download_failures.append(
                    {
                        "submission_id": ref.submission_id,
                        "episode_id": ref.episode_id,
                        "agent_index": agent_index,
                        "stage": "download_agent_log",
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
        log_paths[ref.episode_id] = episode_logs

        own_team_id = _own_team_id(episode, ref.submission_id)
        if own_team_id is not None:
            actor_records.extend(
                build_episode_actor_records(
                    episode,
                    replay_path=replay_path,
                    submissions_by_id=submission_records,
                    own_team_id=own_team_id,
                )
            )

    manifest = build_ingest_manifest(
        refs=refs,
        submissions=submissions,
        episodes=episodes,
        replay_paths=replay_paths,
        agent_log_paths=log_paths,
        output_dir=args.output_root,
        meta_snapshot=meta_snapshot,
        command=" ".join(sys.argv),
    )
    manifest["download_failures"] = download_failures
    manifest["actor_records"] = len(actor_records)
    _write_json(args.output_root / "ingest_manifest.json", jsonable_manifest(manifest))
    _write_json(args.artifact_dir / "ingest_manifest.json", jsonable_manifest(manifest))

    dataset_report = write_loss_dataset(
        output_dir=args.artifact_dir / "dataset",
        submissions=list(submission_records.values()),
        actor_records=actor_records,
        meta_snapshot=meta_snapshot,
        command=" ".join(sys.argv),
    )
    run_report = {
        "command": " ".join(sys.argv),
        "data_manifest": str(args.output_root / "ingest_manifest.json"),
        "artifact_manifest": str(args.artifact_dir / "ingest_manifest.json"),
        "dataset_report": dataset_report,
        "download_failures": download_failures,
        "replay_paths": {str(key): str(value) for key, value in replay_paths.items()},
        "agent_log_paths": {str(key): [str(path) for path in paths] for key, paths in log_paths.items()},
        "kaggle_submission_made": False,
    }
    _write_json(args.artifact_dir / "run_report.json", run_report)
    print(
        json.dumps(
            {
                "data_manifest": str(args.output_root / "ingest_manifest.json"),
                "artifact_manifest": str(args.artifact_dir / "ingest_manifest.json"),
                "dataset_decision_rows": dataset_report["decision_rows"],
                "download_failures": len(download_failures),
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
