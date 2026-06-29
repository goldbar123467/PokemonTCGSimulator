from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from ptcg.kaggle_loss_mining import LABEL_TO_PIPELINE, PENALTY_TO_FLAW
from ptcg.meta_archetypes import classify_deck
from ptcg.replays import ReplayDecision, iter_replay_decisions
from ptcg.teacher_evaluator import label_selected_decision


OPTION_TYPE_NAMES = {
    0: "setup_or_system",
    1: "choose",
    7: "play_card",
    8: "attach_energy",
    9: "evolve",
    12: "retreat_or_switch",
    13: "attack",
    14: "end_turn",
}


@dataclass(frozen=True)
class AgentGameSummary:
    episode_id: str
    source_file: str
    team_name: str
    source_owner: str
    actor_index: int
    opponent_team_name: str
    opponent_index: int
    outcome: str
    reward: float
    opponent_reward: float
    actor_archetype: str
    opponent_archetype: str
    deck_ids: list[int]


def _read_episode(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a Kaggle episode object")
    return value


def _episode_id(path: Path, episode: dict[str, Any]) -> str:
    info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
    return str(info.get("EpisodeId") or path.stem)


def _teams(episode: dict[str, Any]) -> list[str]:
    info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
    return [str(team) for team in info.get("TeamNames") or []]


def _rewards(episode: dict[str, Any]) -> list[float]:
    rewards = []
    for value in episode.get("rewards") or []:
        try:
            rewards.append(float(value))
        except (TypeError, ValueError):
            rewards.append(0.0)
    return rewards


def _outcome(reward: float, opponent_reward: float) -> str:
    if reward > opponent_reward:
        return "win"
    if reward < opponent_reward:
        return "loss"
    return "draw"


def _initial_deck_ids(episode: dict[str, Any], actor_index: int) -> list[int]:
    for step in (episode.get("steps") or [])[:8]:
        if not isinstance(step, list) or actor_index >= len(step):
            continue
        agent_step = step[actor_index]
        if not isinstance(agent_step, dict):
            continue
        action = agent_step.get("action")
        if isinstance(action, list) and len(action) == 60:
            ids: list[int] = []
            for card_id in action:
                try:
                    ids.append(int(card_id))
                except (TypeError, ValueError):
                    continue
            return ids
    return []


def owner_label(team_name: str, *, focus_team: str | None) -> str:
    if team_name.casefold() == "Clark Kitchen".casefold():
        return "clark_kitchen"
    if focus_team and team_name.casefold() == focus_team.casefold():
        return "focus_user_supplied_agent"
    if team_name:
        return "external_kaggle_team"
    return "unknown_kaggle_team"


def infer_focus_team(replay_paths: Iterable[Path]) -> str | None:
    counts: Counter[str] = Counter()
    for path in replay_paths:
        episode = _read_episode(Path(path))
        for team in _teams(episode):
            if team:
                counts[team] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _agent_summaries(path: Path, *, focus_team: str | None) -> list[AgentGameSummary]:
    episode = _read_episode(path)
    episode_id = _episode_id(path, episode)
    teams = _teams(episode)
    rewards = _rewards(episode)
    summaries: list[AgentGameSummary] = []
    for actor_index, team in enumerate(teams[:2]):
        opponent_index = 1 - actor_index
        reward = rewards[actor_index] if actor_index < len(rewards) else 0.0
        opponent_reward = rewards[opponent_index] if opponent_index < len(rewards) else 0.0
        deck_ids = _initial_deck_ids(episode, actor_index)
        opponent_deck_ids = _initial_deck_ids(episode, opponent_index)
        summaries.append(
            AgentGameSummary(
                episode_id=episode_id,
                source_file=str(path),
                team_name=team,
                source_owner=owner_label(team, focus_team=focus_team),
                actor_index=actor_index,
                opponent_team_name=teams[opponent_index] if opponent_index < len(teams) else "",
                opponent_index=opponent_index,
                outcome=_outcome(reward, opponent_reward),
                reward=reward,
                opponent_reward=opponent_reward,
                actor_archetype=classify_deck(deck_ids).primary,
                opponent_archetype=classify_deck(opponent_deck_ids).primary,
                deck_ids=deck_ids,
            )
        )
    return summaries


def _phase_for_ordinal(ordinal: int, total: int) -> str:
    if total <= 0:
        return "unknown"
    if ordinal < (total + 2) // 3:
        return "opening"
    if ordinal < (2 * total + 2) // 3:
        return "midgame"
    return "finish"


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _pipeline_labels(label_row: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for label in list(label_row.get("selected_labels") or []) + list(label_row.get("teacher_labels") or []):
        labels.extend(LABEL_TO_PIPELINE.get(str(label), (str(label),)))
    for penalty in list(label_row.get("selected_penalties") or []):
        labels.extend(PENALTY_TO_FLAW.get(str(penalty), (str(penalty),)))
    return _unique(labels)


def _flaw_tags(
    *,
    summary: AgentGameSummary,
    label_row: dict[str, Any],
    focus_loss: bool,
) -> list[str]:
    flaws: list[str] = []
    for penalty in label_row.get("selected_penalties") or []:
        flaws.extend(PENALTY_TO_FLAW.get(str(penalty), (str(penalty),)))
    selected_score = float(label_row.get("selected_score") or 0.0)
    teacher_score = float(label_row.get("teacher_score") or 0.0)
    if teacher_score > selected_score + 0.01:
        flaws.append("teacher_preferred_alternative")
    teacher_labels = set(str(label) for label in label_row.get("teacher_labels") or [])
    if summary.opponent_archetype == "lucario" and teacher_labels.intersection({"setup_next_attacker", "trap_active"}):
        flaws.append("anti_lucario_setup_or_trap_gap")
    if "setup_next_attacker" in teacher_labels and not set(label_row.get("selected_labels") or []):
        flaws.append("missed_setup")
    if "trap_active" in teacher_labels and "trap_active" not in set(label_row.get("selected_labels") or []):
        flaws.append("missed_trap_turn")
    if "tempo_reversal" in teacher_labels and "tempo_reversal" not in set(label_row.get("selected_labels") or []):
        flaws.append("missed_tempo_reversal")
    if focus_loss and not flaws:
        flaws.append("unconverted_decision")
    return _unique(flaws)


def _selected_option_types(observation: dict[str, Any], indices: Iterable[int]) -> list[str]:
    select = observation.get("select") if isinstance(observation.get("select"), dict) else {}
    options = select.get("option") if isinstance(select.get("option"), list) else []
    values: list[str] = []
    for index in indices:
        if not isinstance(index, int) or not (0 <= index < len(options)):
            continue
        option = options[index]
        if not isinstance(option, dict):
            continue
        option_type = option.get("type")
        values.append(OPTION_TYPE_NAMES.get(option_type, f"type_{option_type}"))
    return values


def _decision_counts_by_actor(path: Path) -> Counter[int]:
    counts: Counter[int] = Counter()
    for decision in iter_replay_decisions(path, include_optional_pass=True):
        counts[decision.agent_index] += 1
    return counts


def _decision_rows_for_path(path: Path, *, focus_team: str | None) -> list[dict[str, Any]]:
    summaries = {summary.actor_index: summary for summary in _agent_summaries(path, focus_team=focus_team)}
    totals = _decision_counts_by_actor(path)
    ordinals: Counter[int] = Counter()
    rows: list[dict[str, Any]] = []
    for decision in iter_replay_decisions(path, include_optional_pass=True):
        summary = summaries.get(decision.agent_index)
        if summary is None:
            continue
        ordinal = ordinals[decision.agent_index]
        ordinals[decision.agent_index] += 1
        focus_loss = summary.source_owner in {"focus_user_supplied_agent", "clark_kitchen"} and summary.outcome == "loss"
        label_row = label_selected_decision(
            summary.episode_id,
            step_index=decision.step_index,
            agent_index=decision.agent_index,
            observation=decision.observation,
            action_indices=decision.action_indices,
            game_label=f"{summary.actor_archetype}_vs_{summary.opponent_archetype}_{summary.outcome}",
        )
        flaw_tags = _flaw_tags(summary=summary, label_row=label_row, focus_loss=focus_loss)
        teacher_action = [int(index) for index in label_row.get("teacher_action") or []]
        chosen_action = [int(index) for index in decision.action_indices]
        needs_patch = bool(
            focus_loss
            and teacher_action
            and (teacher_action != chosen_action)
            and (
                flaw_tags
                or float(label_row.get("teacher_score") or 0.0) > float(label_row.get("selected_score") or 0.0)
            )
        )
        if needs_patch:
            research_role = "focus_loss_heuristic_patch"
            patch_action = teacher_action
        elif summary.source_owner in {"focus_user_supplied_agent", "clark_kitchen"} and summary.outcome == "win":
            research_role = "focus_win_reference"
            patch_action = chosen_action
        elif summary.outcome == "win":
            research_role = "external_winning_reference"
            patch_action = chosen_action
        else:
            research_role = "observation_only"
            patch_action = teacher_action if teacher_action else chosen_action

        rows.append(
            {
                "episode_id": summary.episode_id,
                "source_file": str(path),
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "step_index": decision.step_index,
                "decision_ordinal_for_actor": ordinal,
                "phase": _phase_for_ordinal(ordinal, totals[decision.agent_index]),
                "team_name": summary.team_name,
                "source_owner": summary.source_owner,
                "actor_index": decision.agent_index,
                "opponent_index": summary.opponent_index,
                "opponent_team_name": summary.opponent_team_name,
                "outcome": summary.outcome,
                "reward": summary.reward,
                "opponent_reward": summary.opponent_reward,
                "actor_archetype": summary.actor_archetype,
                "opponent_archetype": summary.opponent_archetype,
                "matchup_tag": summary.opponent_archetype,
                "turn": label_row.get("turn"),
                "decision_window": label_row.get("decision_window"),
                "teacher_decision_window": label_row.get("teacher_decision_window"),
                "chosen_action": chosen_action,
                "teacher_action": teacher_action,
                "patch_action": patch_action,
                "research_role": research_role,
                "needs_heuristic_patch": needs_patch,
                "teacher_agrees": bool(label_row.get("teacher_agrees")),
                "selected_labels": list(label_row.get("selected_labels") or []),
                "selected_penalties": list(label_row.get("selected_penalties") or []),
                "teacher_labels": list(label_row.get("teacher_labels") or []),
                "teacher_penalties": list(label_row.get("teacher_penalties") or []),
                "selected_score": float(label_row.get("selected_score") or 0.0),
                "teacher_score": float(label_row.get("teacher_score") or 0.0),
                "score_delta_teacher_minus_selected": float(label_row.get("teacher_score") or 0.0)
                - float(label_row.get("selected_score") or 0.0),
                "chosen_option_types": _selected_option_types(decision.observation, chosen_action),
                "teacher_option_types": _selected_option_types(decision.observation, teacher_action),
                "option_count": decision.option_count,
                "pipeline_labels": _pipeline_labels(label_row),
                "flaw_tags": flaw_tags,
                "sample_weight": 3.0 if needs_patch else (1.5 if focus_loss else 1.0),
                "observation": decision.observation,
                "legal_actions": (decision.observation.get("select") or {}).get("option") or [],
                "legal_scope": (
                    "user-supplied public leaderboard replay; visible observation/action labels only; "
                    "no Kaggle submission"
                ),
            }
        )
    return rows


def _patch_map_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": row["episode_id"],
        "replay_id": row["episode_id"],
        "step_index": row["step_index"],
        "actor_index": row["actor_index"],
        "winner_side": row["actor_index"] if row["outcome"] == "win" else row["opponent_index"],
        "agent_family": row["team_name"],
        "source_action": row["chosen_action"],
        "teacher_action": row["teacher_action"],
        "patch_action": row["patch_action"],
        "matchup_tag": row["matchup_tag"],
        "actor_archetype": row["actor_archetype"],
        "opponent_archetype": row["opponent_archetype"],
        "sample_weight": row["sample_weight"],
        "research_role": row["research_role"],
        "flaw_tags": row["flaw_tags"],
        "pipeline_labels": row["pipeline_labels"],
        "legal_scope": row["legal_scope"],
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _summarize(rows: list[dict[str, Any]], game_summaries: list[AgentGameSummary]) -> dict[str, Any]:
    flaw_counts: Counter[str] = Counter()
    pipeline_counts: Counter[str] = Counter()
    matchup_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    correction_counts_by_matchup: Counter[str] = Counter()
    for row in rows:
        flaw_counts.update(str(tag) for tag in row.get("flaw_tags") or [])
        pipeline_counts.update(str(label) for label in row.get("pipeline_labels") or [])
        matchup_counts[str(row.get("matchup_tag") or "unknown")] += 1
        role_counts[str(row.get("research_role") or "unknown")] += 1
        owner_counts[str(row.get("source_owner") or "unknown")] += 1
        outcome_counts[str(row.get("outcome") or "unknown")] += 1
        if row.get("needs_heuristic_patch"):
            correction_counts_by_matchup[str(row.get("matchup_tag") or "unknown")] += 1
    focus_rows = [row for row in rows if row.get("source_owner") in {"focus_user_supplied_agent", "clark_kitchen"}]
    patch_rows = [row for row in rows if row.get("needs_heuristic_patch")]
    return {
        "games": len({summary.episode_id for summary in game_summaries}),
        "actor_records": len(game_summaries),
        "decision_rows": len(rows),
        "focus_rows": len(focus_rows),
        "focus_loss_rows": sum(1 for row in focus_rows if row.get("outcome") == "loss"),
        "heuristic_patch_rows": len(patch_rows),
        "needs_heuristic_patch_rows": sum(1 for row in rows if row.get("needs_heuristic_patch")),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "owner_counts": dict(sorted(owner_counts.items())),
        "research_role_counts": dict(sorted(role_counts.items())),
        "matchup_counts": dict(sorted(matchup_counts.items())),
        "correction_counts_by_matchup": dict(sorted(correction_counts_by_matchup.items())),
        "flaw_counts": dict(flaw_counts.most_common()),
        "pipeline_label_counts": dict(pipeline_counts.most_common()),
        "highest_signal_flaws": [{"flaw": flaw, "count": count} for flaw, count in flaw_counts.most_common(12)],
    }


def _write_report(
    path: Path,
    *,
    focus_team: str | None,
    summaries: list[AgentGameSummary],
    summary: dict[str, Any],
    meta_snapshot: dict[str, Any] | None,
    command: str,
) -> None:
    meta_snapshot = meta_snapshot or {}
    lines = [
        "# User Leaderboard Game Breakdown",
        "",
        f"- Command: `{command}`",
        f"- Focus team: `{focus_team or 'unknown'}`",
        f"- Meta date: `{meta_snapshot.get('date', 'unknown')}`",
        f"- Meta latestDate: `{meta_snapshot.get('latestDate', 'unknown')}`",
        f"- Meta redirected: `{meta_snapshot.get('redirected', 'unknown')}`",
        f"- Meta totalDecks: `{meta_snapshot.get('totalDecks', 'unknown')}`",
        f"- Meta datasetUrl: `{(meta_snapshot.get('source') or {}).get('datasetUrl', 'unknown')}`",
        f"- Games: {summary['games']}",
        f"- Decision rows: {summary['decision_rows']}",
        f"- Focus loss rows: {summary['focus_loss_rows']}",
        f"- Heuristic patch rows: {summary['heuristic_patch_rows']}",
        "",
        "## Matchups",
        "",
    ]
    for item in summaries:
        if item.source_owner not in {"focus_user_supplied_agent", "clark_kitchen"}:
            continue
        lines.append(
            f"- `{item.episode_id}` {item.team_name} ({item.actor_archetype}) "
            f"{item.outcome} vs {item.opponent_team_name} ({item.opponent_archetype})"
        )
    lines.extend(["", "## Highest Signal Flaws", ""])
    for item in summary.get("highest_signal_flaws", [])[:12]:
        lines.append(f"- {item['flaw']}: {item['count']}")
    lines.extend(["", "Kaggle submission made: no", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_label_dataset(
    replay_paths: Iterable[Path],
    *,
    output_dir: Path,
    focus_team: str | None = None,
    meta_snapshot: dict[str, Any] | None = None,
    command: str = "",
) -> dict[str, Any]:
    paths = [Path(path) for path in replay_paths]
    if not paths:
        raise ValueError("at least one replay path is required")
    focus = focus_team or infer_focus_team(paths)
    output_dir.mkdir(parents=True, exist_ok=True)
    replay_dir = output_dir / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)
    copied_replays = []
    for path in paths:
        target = replay_dir / path.name
        shutil.copy2(path, target)
        copied_replays.append(target)

    game_summaries = [summary for path in copied_replays for summary in _agent_summaries(path, focus_team=focus)]
    rows = [row for path in copied_replays for row in _decision_rows_for_path(path, focus_team=focus)]
    patch_rows = [_patch_map_row(row) for row in rows if row.get("needs_heuristic_patch")]
    summary = _summarize(rows, game_summaries)

    output_paths = {
        "copied_replay_dir": replay_dir,
        "game_summaries_json": output_dir / "game_summaries.json",
        "hard_labels_jsonl": output_dir / "hard_labels.jsonl",
        "heuristic_patch_map_jsonl": output_dir / "heuristic_patch_map.jsonl",
        "summary_json": output_dir / "summary.json",
        "markdown_report": output_dir / "breakdown_report.md",
    }
    output_paths["game_summaries_json"].write_text(
        json.dumps([asdict(summary_row) for summary_row in game_summaries], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(output_paths["hard_labels_jsonl"], rows)
    _write_jsonl(output_paths["heuristic_patch_map_jsonl"], patch_rows)
    result = {
        "command": command,
        "focus_team": focus,
        "input_paths": [str(path) for path in paths],
        "copied_replays": [str(path) for path in copied_replays],
        "meta_snapshot": meta_snapshot or {},
        "summary": summary,
        "paths": {key: str(value) for key, value in output_paths.items()},
        "kaggle_submission_made": False,
    }
    output_paths["summary_json"].write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_report(
        output_paths["markdown_report"],
        focus_team=focus,
        summaries=game_summaries,
        summary=summary,
        meta_snapshot=meta_snapshot,
        command=command,
    )
    return result


def load_patch_map_decisions(path: Path) -> list[ReplayDecision]:
    decisions: list[ReplayDecision] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            observation = row.get("observation")
            patch_action = row.get("patch_action")
            if not isinstance(patch_action, list) or not all(isinstance(index, int) for index in patch_action):
                raise ValueError(f"{path}:{line_number} invalid patch_action")
            decisions.append(
                ReplayDecision(
                    replay_id=str(row.get("replay_id") or row.get("episode_id") or "unknown"),
                    step_index=int(row.get("step_index") or 0),
                    agent_index=int(row.get("actor_index") or 0),
                    observation=observation if isinstance(observation, dict) else {},
                    action_indices=tuple(int(index) for index in patch_action),
                    option_count=0,
                )
            )
    return decisions
