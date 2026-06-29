from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Iterator

from ptcg.gameplay_log_guard import assert_training_gameplay_logs_allowed


class UnsafeReplayDirectoryError(ValueError):
    """Raised when callers try to load replay data by broad directory glob."""


@dataclass(frozen=True)
class ReplaySample:
    replay_id: str
    step_index: int
    agent_index: int
    search_begin_input: str
    select: dict
    action_indices: tuple[int, ...]
    option_count: int


@dataclass(frozen=True)
class ReplayDecision:
    replay_id: str
    step_index: int
    agent_index: int
    observation: dict
    action_indices: tuple[int, ...]
    option_count: int


def iter_replay_samples(path: Path) -> Iterator[ReplaySample]:
    """Yield supervised decision samples from one Kaggle episode JSON."""
    try:
        episode = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(episode, dict) or "steps" not in episode:
        return

    replay_id = str(episode.get("info", {}).get("EpisodeId") or path.stem)
    for step_index, step in enumerate(episode.get("steps") or []):
        if not isinstance(step, list):
            continue
        for agent_index, agent_step in enumerate(step):
            if not isinstance(agent_step, dict):
                continue
            observation = agent_step.get("observation") or {}
            select = observation.get("select")
            options = select.get("option") if isinstance(select, dict) else None
            action = agent_step.get("action")
            if not isinstance(options, list) or not isinstance(action, list):
                continue
            if not options or not action:
                continue
            if not all(isinstance(item, int) for item in action):
                continue
            if not all(0 <= item < len(options) for item in action):
                continue
            search_begin_input = observation.get("search_begin_input")
            if not isinstance(search_begin_input, str) or not search_begin_input:
                continue
            yield ReplaySample(
                replay_id=replay_id,
                step_index=step_index,
                agent_index=agent_index,
                search_begin_input=search_begin_input,
                select=select,
                action_indices=tuple(action),
                option_count=len(options),
            )


def iter_replay_decisions(path: Path, *, include_optional_pass: bool = False) -> Iterator[ReplayDecision]:
    """Yield full observation/action decisions from one Kaggle episode JSON."""
    try:
        episode = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(episode, dict) or "steps" not in episode:
        return

    replay_id = str(episode.get("info", {}).get("EpisodeId") or path.stem)
    for step_index, step in enumerate(episode.get("steps") or []):
        if not isinstance(step, list):
            continue
        for agent_index, agent_step in enumerate(step):
            if not isinstance(agent_step, dict):
                continue
            observation = agent_step.get("observation")
            select = observation.get("select") if isinstance(observation, dict) else None
            options = select.get("option") if isinstance(select, dict) else None
            action = agent_step.get("action")
            if not isinstance(observation, dict) or not isinstance(options, list) or not isinstance(action, list):
                continue
            if not options:
                continue
            if not action:
                min_count = select.get("minCount", select.get("min_count"))
                if include_optional_pass and int(min_count or 0) == 0:
                    yield ReplayDecision(
                        replay_id=replay_id,
                        step_index=step_index,
                        agent_index=agent_index,
                        observation=observation,
                        action_indices=(),
                        option_count=len(options),
                    )
                continue
            if not all(isinstance(item, int) for item in action):
                continue
            if not all(0 <= item < len(options) for item in action):
                continue
            yield ReplayDecision(
                replay_id=replay_id,
                step_index=step_index,
                agent_index=agent_index,
                observation=observation,
                action_indices=tuple(action),
                option_count=len(options),
            )


def load_replay_samples(
    replay_dir: Path | None = None,
    *,
    replay_paths: Iterable[Path] | None = None,
    max_replays: int | None = None,
    max_samples: int | None = None,
    project_root: Path = Path("."),
    config_path: Path = Path("configs/current_workflow.json"),
) -> list[ReplaySample]:
    samples: list[ReplaySample] = []
    replay_count = 0
    for path in _resolve_loader_paths(
        replay_dir=replay_dir,
        replay_paths=replay_paths,
        project_root=project_root,
        config_path=config_path,
    ):
        before = len(samples)
        for sample in iter_replay_samples(path):
            samples.append(sample)
            if max_samples is not None and len(samples) >= max_samples:
                return samples
        if len(samples) > before:
            replay_count += 1
            if max_replays is not None and replay_count >= max_replays:
                return samples
    return samples


def load_replay_decisions(
    replay_dir: Path | None = None,
    *,
    replay_paths: Iterable[Path] | None = None,
    max_replays: int | None = None,
    max_decisions: int | None = None,
    include_optional_pass: bool = False,
    project_root: Path = Path("."),
    config_path: Path = Path("configs/current_workflow.json"),
) -> list[ReplayDecision]:
    decisions: list[ReplayDecision] = []
    replay_count = 0
    for path in _resolve_loader_paths(
        replay_dir=replay_dir,
        replay_paths=replay_paths,
        project_root=project_root,
        config_path=config_path,
    ):
        before = len(decisions)
        for decision in iter_replay_decisions(path, include_optional_pass=include_optional_pass):
            decisions.append(decision)
            if max_decisions is not None and len(decisions) >= max_decisions:
                return decisions
        if len(decisions) > before:
            replay_count += 1
            if max_replays is not None and replay_count >= max_replays:
                return decisions
    return decisions


def load_replay_observations(
    replay_dir: Path | None = None,
    *,
    replay_paths: Iterable[Path] | None = None,
    max_observations: int = 100,
    project_root: Path = Path("."),
    config_path: Path = Path("configs/current_workflow.json"),
) -> list[dict]:
    observations: list[dict] = []
    for path in _resolve_loader_paths(
        replay_dir=replay_dir,
        replay_paths=replay_paths,
        project_root=project_root,
        config_path=config_path,
    ):
        try:
            episode = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for step in episode.get("steps") or []:
            if not isinstance(step, list):
                continue
            for agent_step in step:
                if not isinstance(agent_step, dict):
                    continue
                observation = agent_step.get("observation")
                action = agent_step.get("action")
                select = observation.get("select") if isinstance(observation, dict) else None
                options = select.get("option") if isinstance(select, dict) else None
                if isinstance(options, list) and isinstance(action, list) and options:
                    observations.append(observation)
                    if len(observations) >= max_observations:
                        return observations
    return observations


def _resolve_loader_paths(
    *,
    replay_dir: Path | None,
    replay_paths: Iterable[Path] | None,
    project_root: Path,
    config_path: Path,
) -> list[Path]:
    if replay_paths is not None:
        return sorted(Path(path) for path in replay_paths)
    if replay_dir is not None:
        raise UnsafeReplayDirectoryError(
            "raw replay directory globbing is disabled; pass replay_paths from "
            "data_manifest/current_gameplay_logs.txt or omit replay_dir to use the configured allowlist"
        )
    return assert_training_gameplay_logs_allowed(project_root=project_root, config_path=config_path)
