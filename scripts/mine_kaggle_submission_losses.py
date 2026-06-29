from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.kaggle_loss_mining import (
    EpisodeActorRecord,
    SubmissionRecord,
    build_episode_actor_records,
    submission_record_from_api,
    write_loss_dataset,
)


META_URL = "https://ptcg-kaggle-meta.vercel.app/api/meta?page=1"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "to_json"):
        return value.to_json()
    if hasattr(value, "__dict__"):
        return {key.lstrip("_"): _jsonable(item) for key, item in vars(value).items()}
    return str(value)


def _episode_to_json(episode: Any) -> dict[str, Any]:
    agents = []
    for agent in getattr(episode, "agents", []) or []:
        agents.append(
            {
                "submission_id": getattr(agent, "submission_id", None),
                "index": getattr(agent, "index", None),
                "reward": getattr(agent, "reward", None),
                "state": str(getattr(agent, "state", "")),
                "team_name": getattr(agent, "team_name", ""),
                "team_id": getattr(agent, "team_id", None),
            }
        )
    return {
        "id": getattr(episode, "id", None),
        "create_time": str(getattr(episode, "create_time", "")),
        "end_time": str(getattr(episode, "end_time", "")),
        "state": str(getattr(episode, "state", "")),
        "type": str(getattr(episode, "type", "")),
        "agents": agents,
    }


def _load_meta_snapshot() -> dict[str, Any]:
    with urlopen(META_URL, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("meta API did not return an object")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_jsonable(row), sort_keys=True, ensure_ascii=False) + "\n")


def _submission_ids(records: list[SubmissionRecord], *, complete_only: bool) -> set[int]:
    if complete_only:
        return {record.submission_id for record in records if record.status == "complete"}
    return {record.submission_id for record in records}


def _own_team_id_from_episode(episode: Any, submission_ids: set[int]) -> int | None:
    for agent in getattr(episode, "agents", []) or []:
        if getattr(agent, "submission_id", None) in submission_ids:
            team_id = getattr(agent, "team_id", None)
            return int(team_id) if team_id is not None else None
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull recent Kaggle PTCG submission episodes and build sanitized loss/flaw research labels."
    )
    parser.add_argument("--competition", default="pokemon-tcg-ai-battle")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ptcg_research/current/kaggle_loss_mining"),
    )
    parser.add_argument("--submission-limit", type=int, default=12)
    parser.add_argument(
        "--episodes-per-submission",
        type=int,
        default=0,
        help="0 means all public episodes returned by Kaggle for each submission.",
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--include-error-submissions", action="store_true")
    parser.add_argument("--skip-replay-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    replay_dir = args.output_dir / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)

    meta_snapshot = _load_meta_snapshot()
    submissions_raw = api.competition_submissions(args.competition, page_size=args.page_size) or []
    submissions = [submission_record_from_api(item) for item in submissions_raw]
    submissions = submissions[: args.submission_limit]
    episode_submission_ids = _submission_ids(submissions, complete_only=not args.include_error_submissions)
    submissions_by_id = {record.submission_id: record for record in submissions}

    episodes_json: list[dict[str, Any]] = []
    actor_records: list[EpisodeActorRecord] = []
    download_failures: list[dict[str, Any]] = []

    for submission in submissions:
        if submission.submission_id not in episode_submission_ids:
            continue
        try:
            episodes = api.competition_list_episodes(submission.submission_id) or []
        except Exception as exc:
            download_failures.append(
                {"submission_id": submission.submission_id, "stage": "list_episodes", "error": f"{type(exc).__name__}:{exc}"}
            )
            continue
        if args.episodes_per_submission > 0:
            episodes = episodes[: args.episodes_per_submission]
        for episode in episodes:
            episode_id = int(getattr(episode, "id"))
            episode_payload = _episode_to_json(episode)
            episode_payload["source_submission_id"] = submission.submission_id
            episodes_json.append(episode_payload)
            replay_path = replay_dir / f"episode-{episode_id}-replay.json"
            if not args.skip_replay_download and not replay_path.exists():
                try:
                    api.competition_episode_replay(episode_id, path=str(replay_dir), quiet=True)
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
            if replay_path.exists():
                own_team_id = _own_team_id_from_episode(episode, {submission.submission_id})
                if own_team_id is not None:
                    actor_records.extend(
                        build_episode_actor_records(
                            episode,
                            replay_path=replay_path,
                            submissions_by_id=submissions_by_id,
                            own_team_id=own_team_id,
                        )
                    )

    _write_json(args.output_dir / "meta_snapshot.json", meta_snapshot)
    _write_json(args.output_dir / "submissions_raw.json", [_jsonable(item) for item in submissions_raw[: args.submission_limit]])
    _write_json(args.output_dir / "submissions.json", [record.to_json() for record in submissions])
    _write_jsonl(args.output_dir / "episodes.jsonl", episodes_json)
    _write_jsonl(args.output_dir / "episode_actors.jsonl", [record.to_json() for record in actor_records])

    dataset_report = write_loss_dataset(
        output_dir=args.output_dir / "dataset",
        submissions=submissions,
        actor_records=actor_records,
        meta_snapshot=meta_snapshot,
        command=" ".join(sys.argv),
    )
    run_manifest = {
        "command": " ".join(sys.argv),
        "competition": args.competition,
        "output_dir": str(args.output_dir),
        "submission_records": len(submissions),
        "episode_records": len(episodes_json),
        "actor_records": len(actor_records),
        "download_failures": download_failures,
        "dataset_report": dataset_report,
        "meta": {
            "date": meta_snapshot.get("date"),
            "latestDate": meta_snapshot.get("latestDate"),
            "redirected": meta_snapshot.get("redirected"),
            "totalDecks": meta_snapshot.get("totalDecks"),
            "source": meta_snapshot.get("source"),
        },
        "kaggle_submission_made": False,
    }
    _write_json(args.output_dir / "run_manifest.json", run_manifest)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "submissions": len(submissions),
                "episodes": len(episodes_json),
                "actor_records": len(actor_records),
                "decision_rows": dataset_report["decision_rows"],
                "heuristic_patch_rows": dataset_report["heuristic_patch_rows"],
                "failures": len(download_failures),
                "report": dataset_report["paths"]["markdown_report"],
                "kaggle_submission_made": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
