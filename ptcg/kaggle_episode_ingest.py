from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse
import re

from ptcg.kaggle_loss_mining import submission_record_from_api


@dataclass(frozen=True)
class SubmissionEpisodeRef:
    submission_id: int
    episode_id: int
    source_url: str


def parse_submission_episode_ref(value: str) -> SubmissionEpisodeRef:
    text = value.strip()
    parsed = urlparse(text)
    query = parsed.query if parsed.query else text
    params = parse_qs(query)

    submission_values = params.get("submissionId") or params.get("submission_id")
    episode_values = params.get("episodeId") or params.get("episode_id")
    if not submission_values:
        match = re.search(r"submissionId=(\d+)", text)
        submission_values = [match.group(1)] if match else None
    if not episode_values:
        match = re.search(r"episodeId=(\d+)", text)
        episode_values = [match.group(1)] if match else None
    if not submission_values or not episode_values:
        raise ValueError(f"could not parse submissionId and episodeId from {value!r}")
    return SubmissionEpisodeRef(
        submission_id=int(submission_values[0]),
        episode_id=int(episode_values[0]),
        source_url=text,
    )


def parse_submission_episode_refs(values: Iterable[str]) -> list[SubmissionEpisodeRef]:
    refs: list[SubmissionEpisodeRef] = []
    pattern = re.compile(r"https?://\S+|submissionId=\d+&episodeId=\d+")
    for value in values:
        for match in pattern.findall(value):
            refs.append(parse_submission_episode_ref(match))
    if not refs:
        raise ValueError("no submissionId/episodeId pairs found")
    return refs


def own_agent_indices(episode: Any, submission_id: int) -> list[int]:
    indices: list[int] = []
    for agent in getattr(episode, "agents", []) or []:
        if int(getattr(agent, "submission_id", -1)) != int(submission_id):
            continue
        index = getattr(agent, "index", None)
        if index is not None:
            indices.append(int(index))
    return sorted(set(indices))


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "to_json"):
        return _jsonable(value.to_json())
    if hasattr(value, "__dict__"):
        return {key.lstrip("_"): _jsonable(item) for key, item in vars(value).items()}
    return str(value)


def _episode_record(ref: SubmissionEpisodeRef, episode: Any, replay_path: Path, log_paths: list[Path]) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
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
        "submission_id": ref.submission_id,
        "episode_id": ref.episode_id,
        "source_url": ref.source_url,
        "create_time": str(getattr(episode, "create_time", "")),
        "end_time": str(getattr(episode, "end_time", "")),
        "state": str(getattr(episode, "state", "")),
        "type": str(getattr(episode, "type", "")),
        "replay_path": str(replay_path),
        "agent_log_paths": [str(path) for path in log_paths],
        "agents": agents,
    }


def _meta_record(meta_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": meta_snapshot.get("date"),
        "latestDate": meta_snapshot.get("latestDate"),
        "redirected": meta_snapshot.get("redirected"),
        "totalDecks": meta_snapshot.get("totalDecks"),
        "source": meta_snapshot.get("source"),
    }


def build_ingest_manifest(
    *,
    refs: list[SubmissionEpisodeRef],
    submissions: dict[int, Any],
    episodes: dict[int, Any],
    replay_paths: dict[int, Path],
    agent_log_paths: dict[int, list[Path]],
    output_dir: Path,
    meta_snapshot: dict[str, Any],
    command: str,
) -> dict[str, Any]:
    submission_records = []
    for submission_id in sorted({ref.submission_id for ref in refs}):
        submission = submissions.get(submission_id)
        if submission is not None:
            submission_records.append(submission_record_from_api(submission).to_json())
        else:
            submission_records.append({"submission_id": submission_id, "status": "unknown"})

    episode_records = [
        _episode_record(
            ref,
            episodes.get(ref.episode_id),
            replay_paths[ref.episode_id],
            agent_log_paths.get(ref.episode_id, []),
        )
        for ref in refs
    ]
    return {
        "command": command,
        "output_dir": str(output_dir),
        "submission_episode_refs": [asdict(ref) for ref in refs],
        "submission_records": submission_records,
        "episode_records": episode_records,
        "submission_count": len(submission_records),
        "episode_count": len(episode_records),
        "meta": _meta_record(meta_snapshot),
        "kaggle_submission_made": False,
    }


def jsonable_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return _jsonable(manifest)
