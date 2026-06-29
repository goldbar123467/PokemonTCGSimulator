from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from ptcg.meta_archetypes import classify_deck
from ptcg.teacher_evaluator import label_selected_decision


@dataclass(frozen=True)
class SubmissionRecord:
    submission_id: int
    file_name: str
    status: str
    public_score: float | None
    private_score: float | None
    error_description: str | None
    description: str
    team_name: str
    submitted_by: str
    total_bytes: int | None
    date: str | None
    agent_family: str

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        if row.get("date") is not None:
            row["date"] = str(row["date"])
        return row


@dataclass(frozen=True)
class EpisodeActorRecord:
    episode_id: int
    submission_id: int
    actor_index: int
    opponent_index: int
    outcome: str
    reward: float
    opponent_reward: float
    actor_archetype: str
    opponent_archetype: str
    replay_path: str
    agent_family: str
    create_time: str | None = None
    end_time: str | None = None
    team_name: str = ""
    team_id: int | None = None
    opponent_submission_id: int | None = None
    opponent_team_name: str = ""
    opponent_team_id: int | None = None
    submission_public_score: float | None = None

    def to_json(self) -> dict[str, Any]:
        row = asdict(self)
        if row.get("create_time") is not None:
            row["create_time"] = str(row["create_time"])
        if row.get("end_time") is not None:
            row["end_time"] = str(row["end_time"])
        return row


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_status(status: Any) -> str:
    raw = str(status or "").split(".")[-1].strip().lower()
    if raw == "complete":
        return "complete"
    if raw == "error":
        return "error"
    return raw or "unknown"


def _agent_family(file_name: str) -> str:
    name = Path(file_name or "unknown").name
    if name.endswith(".tar.gz"):
        name = name[:-7]
    else:
        name = Path(name).stem
    return name.replace("_", "-").lower() or "unknown"


def submission_record_from_api(submission: Any) -> SubmissionRecord:
    return SubmissionRecord(
        submission_id=int(getattr(submission, "ref")),
        file_name=str(getattr(submission, "file_name", "")),
        status=_normalized_status(getattr(submission, "status", None)),
        public_score=_as_float(getattr(submission, "public_score", None)),
        private_score=_as_float(getattr(submission, "private_score", None)),
        error_description=getattr(submission, "error_description", None),
        description=str(getattr(submission, "description", "")),
        team_name=str(getattr(submission, "team_name", "")),
        submitted_by=str(getattr(submission, "submitted_by", "")),
        total_bytes=getattr(submission, "total_bytes", None),
        date=getattr(submission, "date", None),
        agent_family=_agent_family(str(getattr(submission, "file_name", ""))),
    )


def _load_replay(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _initial_deck_ids(replay: dict[str, Any], actor_index: int) -> list[int]:
    steps = replay.get("steps") or []
    for step in steps[:8]:
        if not isinstance(step, list) or actor_index >= len(step):
            continue
        agent_step = step[actor_index]
        if not isinstance(agent_step, dict):
            continue
        action = agent_step.get("action") or []
        if isinstance(action, list) and len(action) == 60:
            return [int(card_id) for card_id in action if isinstance(card_id, int) or str(card_id).isdigit()]
    return []


def _outcome(reward: float, opponent_reward: float) -> str:
    if reward > opponent_reward:
        return "win"
    if reward < opponent_reward:
        return "loss"
    return "draw"


def build_episode_actor_records(
    episode: Any,
    *,
    replay_path: Path,
    submissions_by_id: dict[int, SubmissionRecord],
    own_team_id: int,
) -> list[EpisodeActorRecord]:
    replay = _load_replay(replay_path)
    records: list[EpisodeActorRecord] = []
    agents = list(getattr(episode, "agents", []) or [])
    for agent in agents:
        if int(getattr(agent, "team_id", -1)) != int(own_team_id):
            continue
        actor_index = int(getattr(agent, "index"))
        opponent = next((candidate for candidate in agents if int(getattr(candidate, "index")) != actor_index), None)
        if opponent is None:
            continue
        submission_id = int(getattr(agent, "submission_id"))
        submission = submissions_by_id.get(submission_id)
        actor_archetype = classify_deck(_initial_deck_ids(replay, actor_index)).primary
        opponent_archetype = classify_deck(_initial_deck_ids(replay, int(getattr(opponent, "index")))).primary
        reward = float(getattr(agent, "reward", 0) or 0)
        opponent_reward = float(getattr(opponent, "reward", 0) or 0)
        records.append(
            EpisodeActorRecord(
                episode_id=int(getattr(episode, "id")),
                submission_id=submission_id,
                actor_index=actor_index,
                opponent_index=int(getattr(opponent, "index")),
                outcome=_outcome(reward, opponent_reward),
                reward=reward,
                opponent_reward=opponent_reward,
                actor_archetype=actor_archetype,
                opponent_archetype=opponent_archetype,
                replay_path=str(replay_path),
                agent_family=submission.agent_family if submission else "unknown",
                create_time=getattr(episode, "create_time", None),
                end_time=getattr(episode, "end_time", None),
                team_name=str(getattr(agent, "team_name", "")),
                team_id=int(getattr(agent, "team_id")) if getattr(agent, "team_id", None) is not None else None,
                opponent_submission_id=(
                    int(getattr(opponent, "submission_id")) if getattr(opponent, "submission_id", None) is not None else None
                ),
                opponent_team_name=str(getattr(opponent, "team_name", "")),
                opponent_team_id=(
                    int(getattr(opponent, "team_id")) if getattr(opponent, "team_id", None) is not None else None
                ),
                submission_public_score=submission.public_score if submission else None,
            )
        )
    return records


def _sanitize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(observation)
    players = sanitized.get("current", {}).get("players", [])
    for player in players:
        deck = player.pop("deck", [])
        prize = player.pop("prize", [])
        player["deck_count"] = len(deck) if isinstance(deck, list) else 0
        player["prize_count"] = len(prize) if isinstance(prize, list) else 0
    return sanitized


def _decision_flaws(actor: EpisodeActorRecord, observation: dict[str, Any]) -> list[str]:
    flaws: list[str] = []
    if actor.outcome != "loss":
        return flaws
    current = observation.get("current", {})
    players = current.get("players", [])
    if actor.actor_index < len(players):
        own = players[actor.actor_index]
        own_cards = json.dumps(own)
        if actor.actor_archetype == "lucario" and any(card_id in own_cards for card_id in ('"id": 677', '"id": 678')):
            flaws.append("missed_setup")
    select = observation.get("select") if isinstance(observation.get("select"), dict) else {}
    options = select.get("option", [])
    if options and not flaws:
        flaws.append("unconverted_decision")
    return flaws


LABEL_TO_PIPELINE = {
    "setup_next_attacker": ("setup", "bench_develop"),
    "punish_overpowered_active": ("attack_prize_race",),
    "trap_active": ("stall_or_denial", "gust_target"),
    "sleep_tempo": ("stall_or_denial", "disruption"),
    "spread_pressure": ("attack_prize_race",),
    "tempo_reversal": ("attack_prize_race", "risk_behind_high_variance"),
    "behind_on_prizes_recovery": ("risk_behind_high_variance",),
    "direct_aggression_with_backup": ("attack_prize_race", "energy_attach_bench_next_attacker"),
}

PENALTY_TO_FLAW = {
    "end_with_constructive_setup": ("missed_setup", "preserve_resources"),
    "dead_or_random_move": ("dead_or_random_move", "unclear_or_forced"),
    "attack_without_backup": ("attack_without_backup", "bench_develop"),
    "active_overattach": ("active_overattach", "energy_attach_active"),
}


def _unique_ordered(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _teacher_labels_to_pipeline(label_row: dict[str, Any]) -> list[str]:
    mapped: list[str] = []
    for label in list(label_row.get("selected_labels") or []) + list(label_row.get("teacher_labels") or []):
        mapped.extend(LABEL_TO_PIPELINE.get(str(label), (str(label),)))
    return _unique_ordered(mapped)


def _teacher_flaws(actor: EpisodeActorRecord, label_row: dict[str, Any], observation: dict[str, Any]) -> list[str]:
    flaws = _decision_flaws(actor, observation)
    for penalty in label_row.get("selected_penalties") or []:
        flaws.extend(PENALTY_TO_FLAW.get(str(penalty), (str(penalty),)))
    selected_score = float(label_row.get("selected_score") or 0.0)
    teacher_score = float(label_row.get("teacher_score") or 0.0)
    if teacher_score > selected_score + 0.01:
        flaws.append("teacher_preferred_alternative")
    return _unique_ordered(flaws)


def _winner_side(actor: EpisodeActorRecord) -> int | None:
    if actor.outcome == "win":
        return actor.actor_index
    if actor.outcome == "loss":
        return actor.opponent_index
    return None


def _kaggle_owner(team_name: str) -> str:
    if team_name.casefold() == "Clark Kitchen".casefold():
        return "Clark Kitchen"
    if team_name:
        return "external_kaggle_team"
    return "unknown_kaggle_team"


def _is_active_replay_entry(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or "").split(".")[-1].upper()
    return status in {"", "ACTIVE"}


def _next_recorded_action(
    steps: list[Any],
    *,
    step_index: int,
    actor_index: int,
) -> tuple[list[Any], int | None]:
    for future_index in range(step_index + 1, len(steps)):
        future_step = steps[future_index]
        if not isinstance(future_step, list) or actor_index >= len(future_step):
            continue
        future_entry = future_step[actor_index]
        if not isinstance(future_entry, dict):
            continue
        action = future_entry.get("action") or []
        if isinstance(action, list) and action:
            return list(action), future_index
    return [], None


def build_decision_label_rows(replay_path: Path, actor: EpisodeActorRecord) -> list[dict[str, Any]]:
    replay = _load_replay(replay_path)
    replay_id = str((replay.get("info") or {}).get("EpisodeId") or actor.episode_id)
    steps = replay.get("steps") or []
    rows: list[dict[str, Any]] = []
    for step_index, step in enumerate(steps):
        if not isinstance(step, list):
            continue
        if actor.actor_index >= len(step):
            continue
        entry = step[actor.actor_index]
        if not isinstance(entry, dict):
            continue
        if not _is_active_replay_entry(entry):
            continue
        observation = entry.get("observation") or {}
        select = observation.get("select") if isinstance(observation.get("select"), dict) else {}
        options = select.get("option") or []
        action, action_step_index = _next_recorded_action(steps, step_index=step_index, actor_index=actor.actor_index)
        if not options or not action:
            continue
        sanitized = _sanitize_observation(observation)
        label_row = label_selected_decision(
            replay_id,
            step_index=step_index,
            agent_index=actor.actor_index,
            observation=observation,
            action_indices=action,
            game_label=f"{actor.agent_family}:{actor.opponent_archetype}:{actor.outcome}",
        )
        flaw_tags = _teacher_flaws(actor, label_row, observation)
        sample_weight = 2.0 if actor.outcome == "loss" and flaw_tags else (1.25 if actor.outcome == "loss" else 1.0)
        rows.append(
            {
                "episode_id": actor.episode_id,
                "replay_id": replay_id,
                "step_index": step_index,
                "submission_id": actor.submission_id,
                "agent_family": actor.agent_family,
                "team_name": actor.team_name,
                "data_source": "kaggle_public_episode",
                "actor_owner": _kaggle_owner(actor.team_name),
                "actor_index": actor.actor_index,
                "agent_index": actor.actor_index,
                "opponent_index": actor.opponent_index,
                "action_step_index": action_step_index,
                "opponent_submission_id": actor.opponent_submission_id,
                "opponent_team_name": actor.opponent_team_name,
                "opponent_owner": _kaggle_owner(actor.opponent_team_name),
                "outcome": actor.outcome,
                "winner_side": _winner_side(actor),
                "reward": actor.reward,
                "matchup_tag": actor.opponent_archetype,
                "actor_archetype": actor.actor_archetype,
                "opponent_archetype": actor.opponent_archetype,
                "observation": sanitized,
                "legal_actions": options,
                "chosen_action": action,
                "teacher_action": list(label_row["teacher_action"]),
                "teacher_agrees": bool(label_row["teacher_agrees"]),
                "selected_labels": list(label_row["selected_labels"]),
                "selected_penalties": list(label_row["selected_penalties"]),
                "teacher_labels": list(label_row["teacher_labels"]),
                "teacher_penalties": list(label_row["teacher_penalties"]),
                "selected_score": float(label_row["selected_score"]),
                "teacher_score": float(label_row["teacher_score"]),
                "decision_window": label_row["decision_window"],
                "teacher_decision_window": label_row["teacher_decision_window"],
                "pipeline_labels": _teacher_labels_to_pipeline(label_row),
                "flaw_tags": flaw_tags,
                "sample_weight": sample_weight,
                "research_role": "loss_correction_patch"
                if actor.outcome == "loss" and flaw_tags
                else ("winning_reference" if actor.outcome == "win" else "neutral_observation"),
                "leaderboard_score": actor.submission_public_score,
                "legal_scope": "public Kaggle episode replay observation sanitized to remove hidden deck/prize identities; no submission",
            }
        )
    return rows


def analyze_loss_trends(rows: list[dict[str, Any]]) -> dict[str, Any]:
    losses_by_matchup: Counter[str] = Counter()
    flaw_counts: Counter[str] = Counter()
    pipeline_counts: Counter[str] = Counter()
    submission_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0})
    family_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0})

    for row in rows:
        outcome = str(row.get("outcome", "draw"))
        submission_id = str(row.get("submission_id", "unknown"))
        family = str(row.get("agent_family", "unknown"))
        if outcome == "loss":
            losses_by_matchup[str(row.get("matchup_tag", "unknown"))] += 1
            flaw_counts.update(str(tag) for tag in row.get("flaw_tags", []))
        pipeline_counts.update(str(label) for label in row.get("pipeline_labels", []))
        if outcome not in {"win", "loss"}:
            outcome = "draw"
        key = "losses" if outcome == "loss" else f"{outcome}s"
        submission_summary[submission_id][key] += 1
        family_summary[family][key] += 1

    loss_rows = sum(1 for row in rows if row.get("outcome") == "loss")
    win_rows = sum(1 for row in rows if row.get("outcome") == "win")
    return {
        "total_rows": len(rows),
        "loss_rows": loss_rows,
        "win_rows": win_rows,
        "loss_rate_rows": loss_rows / len(rows) if rows else 0.0,
        "losses_by_matchup": dict(losses_by_matchup),
        "flaw_counts": dict(flaw_counts),
        "pipeline_label_counts": dict(pipeline_counts),
        "submission_loss_summary": dict(submission_summary),
        "agent_family_summary": dict(family_summary),
        "highest_signal_flaws": [
            {"flaw": flaw, "count": count} for flaw, count in flaw_counts.most_common(12)
        ],
        "worst_matchups": [
            {"matchup_tag": matchup, "loss_decision_rows": count}
            for matchup, count in losses_by_matchup.most_common(12)
        ],
        "kaggle_submission_made": False,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _heuristic_patch_row(row: dict[str, Any]) -> dict[str, Any]:
    source_action = list(row["chosen_action"])
    teacher_action = list(row.get("teacher_action") or source_action)
    return {
        "episode_id": row["episode_id"],
        "replay_id": row.get("replay_id"),
        "step_index": row["step_index"],
        "action_step_index": row.get("action_step_index"),
        "submission_id": row["submission_id"],
        "actor_index": row.get("actor_index", row.get("agent_index")),
        "winner_side": row.get("winner_side"),
        "agent_family": row["agent_family"],
        "source_action": source_action,
        "teacher_action": teacher_action,
        "teacher_agrees": bool(row.get("teacher_agrees")),
        "matchup_tag": row["matchup_tag"],
        "actor_archetype": row["actor_archetype"],
        "opponent_archetype": row["opponent_archetype"],
        "leaderboard_score": row.get("leaderboard_score"),
        "sample_weight": row["sample_weight"],
        "research_role": row.get("research_role"),
        "flaw_tags": row.get("flaw_tags", []),
        "pipeline_labels": row.get("pipeline_labels", []),
        "legal_scope": row.get("legal_scope"),
    }


def write_loss_dataset(
    *,
    output_dir: Path,
    submissions: list[SubmissionRecord],
    actor_records: list[EpisodeActorRecord],
    meta_snapshot: dict[str, Any],
    command: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_rows: list[dict[str, Any]] = []
    for actor in actor_records:
        decision_rows.extend(build_decision_label_rows(Path(actor.replay_path), actor))

    patch_rows = [
        _heuristic_patch_row(row)
        for row in decision_rows
        if row.get("flaw_tags") or row.get("teacher_agrees") is False
    ]
    loss_report = analyze_loss_trends(decision_rows)

    paths = {
        "decision_labels_jsonl": output_dir / "decision_labels.jsonl",
        "heuristic_patch_map_jsonl": output_dir / "heuristic_patch_map.jsonl",
        "analysis_json": output_dir / "loss_trends.json",
        "submissions_json": output_dir / "submissions.json",
        "episode_actors_jsonl": output_dir / "episode_actors.jsonl",
        "markdown_report": output_dir / "loss_dataset_report.md",
    }
    _write_jsonl(paths["decision_labels_jsonl"], decision_rows)
    _write_jsonl(paths["heuristic_patch_map_jsonl"], patch_rows)
    _write_jsonl(paths["episode_actors_jsonl"], [actor.to_json() for actor in actor_records])
    paths["analysis_json"].write_text(
        json.dumps(loss_report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["submissions_json"].write_text(
        json.dumps([submission.to_json() for submission in submissions], indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    markdown = "\n".join(
        [
            "# Kaggle Loss Dataset",
            "",
            f"- Command: `{command}`",
            f"- Meta date: `{meta_snapshot.get('date', 'unknown')}`",
            f"- Dataset source: `{meta_snapshot.get('source', {}).get('datasetUrl', 'unknown')}`",
            f"- Submissions: {len(submissions)}",
            f"- Actor records: {len(actor_records)}",
            f"- Decision rows: {len(decision_rows)}",
            f"- Loss rows: {loss_report['loss_rows']}",
            "",
            "Kaggle submission made: no",
            "",
        ]
    )
    paths["markdown_report"].write_text(markdown, encoding="utf-8")

    return {
        "command": command,
        "meta_snapshot": meta_snapshot,
        "submissions": len(submissions),
        "actor_records": len(actor_records),
        "decision_rows": len(decision_rows),
        "heuristic_patch_rows": len(patch_rows),
        "loss_report": loss_report,
        "paths": {key: str(value) for key, value in paths.items()},
        "kaggle_submission_made": False,
    }
