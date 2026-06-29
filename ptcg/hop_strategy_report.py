from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ptcg.kaggle_loss_mining import SubmissionRecord


COLORS = {
    "ink": "#222222",
    "muted": "#626970",
    "blue": "#2f5f8f",
    "green": "#2e8b57",
    "gold": "#d4a017",
    "orange": "#d9793d",
    "red": "#b94747",
    "purple": "#6a4c93",
    "gray": "#9aa0a6",
}

ATTACK_INTENTS = {
    1267: "corner_trap_lock",
    1266: "horrifying_revenge_swing",
    1488: "sleep_tempo",
    1240: "sleep_tempo",
    153: "spread_pressure",
}

LABEL_INTENTS = {
    "setup_next_attacker": "setup_next_trevenant_or_backup",
    "punish_overpowered_active": "deny_powered_attacker",
    "trap_active": "corner_trap_lock",
    "sleep_tempo": "sleep_tempo",
    "spread_pressure": "spread_pressure",
    "tempo_reversal": "horrifying_revenge_swing",
    "behind_on_prizes_recovery": "behind_recovery_line",
    "direct_aggression_with_backup": "attack_with_backup",
    "setup": "setup_next_trevenant_or_backup",
    "bench_develop": "setup_next_trevenant_or_backup",
    "energy_attach_bench_next_attacker": "backup_energy_plan",
    "energy_attach_active": "active_energy_commit",
    "attack_prize_race": "prize_race_pressure",
    "gust_target": "gust_or_trap_targeting",
    "disruption": "hand_or_tempo_disruption",
    "stall_or_denial": "control_denial_plan",
    "preserve_resources": "resource_preservation",
    "risk_ahead_conservative": "protect_lead",
    "risk_behind_high_variance": "behind_swing_attempt",
}

PENALTY_INTENTS = {
    "active_overattach": "flaw_active_overattach",
    "attack_without_backup": "flaw_attack_without_backup",
    "end_with_constructive_setup": "flaw_missed_setup",
    "dead_or_random_move": "flaw_low_conversion_action",
    "teacher_preferred_alternative": "flaw_teacher_preferred_alternative",
    "missed_setup": "flaw_missed_setup",
}


def _parse_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min
    text = text.replace("Z", "+00:00")
    for candidate in (text, text.split("+", 1)[0]):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return datetime.min


def _state_text(value: Any) -> str:
    return str(value or "").split(".")[-1].strip().casefold()


def select_latest_complete_submissions(records: Iterable[SubmissionRecord], *, limit: int = 2) -> list[SubmissionRecord]:
    complete = [record for record in records if str(record.status).casefold() == "complete"]
    return sorted(
        complete,
        key=lambda record: (_parse_datetime(record.date), int(record.submission_id)),
        reverse=True,
    )[:limit]


def _episode_has_submission(episode: Any, submission_id: int) -> bool:
    for agent in getattr(episode, "agents", []) or []:
        if int(getattr(agent, "submission_id", -1)) == int(submission_id):
            return True
    return False


def choose_latest_completed_episode(episodes: Iterable[Any], *, submission_id: int) -> Any | None:
    selected = choose_latest_completed_episodes(episodes, submission_id=submission_id, limit=1)
    return selected[0] if selected else None


def choose_latest_completed_episodes(episodes: Iterable[Any], *, submission_id: int, limit: int) -> list[Any]:
    candidates = [
        episode
        for episode in episodes
        if "completed" in _state_text(getattr(episode, "state", ""))
        and _episode_has_submission(episode, submission_id)
    ]
    return sorted(
        candidates,
        key=lambda episode: (
            _parse_datetime(getattr(episode, "end_time", None) or getattr(episode, "create_time", None)),
            int(getattr(episode, "id", 0) or 0),
        ),
        reverse=True,
    )[:limit]


def _owner_label(team_name: Any) -> str:
    name = str(team_name or "").strip()
    if name.casefold() == "Clark Kitchen".casefold():
        return "clark_kitchen"
    if name:
        return "external_kaggle_team"
    return "unknown_kaggle_team"


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _selected_options(row: dict[str, Any]) -> list[dict[str, Any]]:
    options = row.get("legal_actions") if isinstance(row.get("legal_actions"), list) else []
    action = row.get("chosen_action") if isinstance(row.get("chosen_action"), list) else []
    selected: list[dict[str, Any]] = []
    for index in action:
        if isinstance(index, int) and 0 <= index < len(options) and isinstance(options[index], dict):
            selected.append(options[index])
    return selected


def _strategy_intents(row: dict[str, Any]) -> list[str]:
    intents: list[str] = []
    for option in _selected_options(row):
        attack_id = option.get("attackId")
        if isinstance(attack_id, int):
            intents.append(ATTACK_INTENTS.get(attack_id, "attack_or_action"))
    for label in list(row.get("selected_labels") or []) + list(row.get("teacher_labels") or []):
        intents.append(LABEL_INTENTS.get(str(label), str(label)))
    for label in row.get("pipeline_labels") or []:
        intents.append(LABEL_INTENTS.get(str(label), str(label)))
    for flaw in list(row.get("selected_penalties") or []) + list(row.get("flaw_tags") or []):
        intents.append(PENALTY_INTENTS.get(str(flaw), f"flaw_{flaw}"))
    if not intents:
        intents.append("low_context_or_forced_choice")
    return _unique(intents)


def _strategy_tags(row: dict[str, Any], intents: list[str]) -> list[str]:
    tags = ["hop_trevenant_control"] if str(row.get("actor_archetype")) == "hop_trevenant" else []
    matchup = str(row.get("matchup_tag") or row.get("opponent_archetype") or "unknown")
    if matchup:
        tags.append(f"vs_{matchup}")
    if any(intent in {"corner_trap_lock", "sleep_tempo", "control_denial_plan"} for intent in intents):
        tags.append("trap_status_denial")
    if any(intent in {"setup_next_trevenant_or_backup", "backup_energy_plan"} for intent in intents):
        tags.append("backup_setup")
    if any(intent.startswith("flaw_") for intent in intents):
        tags.append("patch_candidate")
    return _unique(tags)


def build_hop_strategy_rows(
    decision_rows: Iterable[dict[str, Any]],
    *,
    source_file_by_replay_id: dict[str, str],
    source_hash_by_replay_id: dict[str, str],
    log_paths_by_episode_id: dict[int, list[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in decision_rows:
        replay_id = str(row.get("replay_id") or row.get("episode_id") or "")
        episode_id = int(row.get("episode_id") or 0)
        intents = _strategy_intents(row)
        tags = _strategy_tags(row, intents)
        teacher_agrees = bool(row.get("teacher_agrees"))
        flaw_tags = list(row.get("flaw_tags") or [])
        rows.append(
            {
                "data_source": row.get("data_source", "kaggle_public_episode"),
                "replay_id": replay_id,
                "episode_id": episode_id,
                "source_file": source_file_by_replay_id.get(replay_id, ""),
                "source_hash": source_hash_by_replay_id.get(replay_id, ""),
                "agent_log_paths": log_paths_by_episode_id.get(episode_id, []),
                "submission_id": row.get("submission_id"),
                "agent_family": row.get("agent_family"),
                "leaderboard_score": row.get("leaderboard_score"),
                "team_name": row.get("team_name", ""),
                "actor_owner_label": _owner_label(row.get("team_name")),
                "opponent_team_name": row.get("opponent_team_name", ""),
                "opponent_owner_label": _owner_label(row.get("opponent_team_name")),
                "actor_index": row.get("actor_index", row.get("agent_index")),
                "opponent_index": row.get("opponent_index"),
                "step_index": row.get("step_index"),
                "action_step_index": row.get("action_step_index"),
                "outcome": row.get("outcome"),
                "winner_side": row.get("winner_side"),
                "actor_archetype": row.get("actor_archetype"),
                "opponent_archetype": row.get("opponent_archetype"),
                "matchup_tag": row.get("matchup_tag"),
                "sample_weight": row.get("sample_weight", 1.0),
                "chosen_action": row.get("chosen_action", []),
                "teacher_action": row.get("teacher_action", []),
                "teacher_agrees": teacher_agrees,
                "selected_labels": list(row.get("selected_labels") or []),
                "selected_penalties": list(row.get("selected_penalties") or []),
                "teacher_labels": list(row.get("teacher_labels") or []),
                "teacher_penalties": list(row.get("teacher_penalties") or []),
                "pipeline_labels": list(row.get("pipeline_labels") or []),
                "flaw_tags": flaw_tags,
                "hop_strategy_intents": intents,
                "hop_strategy_tags": tags,
                "research_role": "hop_strategy_patch_candidate"
                if flaw_tags or not teacher_agrees
                else "hop_strategy_reference",
                "key_decision": bool(flaw_tags or not teacher_agrees or intents),
                "legal_scope": (
                    "public Kaggle episode replay observation sanitized by upstream dataset builder; "
                    "no hidden prize/deck identities used; no submission"
                ),
            }
        )
    return rows


def _count_list_values(rows: Iterable[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(str(value) for value in row.get(key, []) if value)
    return dict(counter.most_common())


def _game_key(row: dict[str, Any]) -> tuple[int, int]:
    return (int(row.get("submission_id") or 0), int(row.get("episode_id") or 0))


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _top_counts(rows: Iterable[dict[str, Any]], key: str, *, limit: int = 8) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(key) or "") for row in rows if row.get(key) not in (None, ""))
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def _submission_by_id(submissions: Iterable[SubmissionRecord]) -> dict[int, SubmissionRecord]:
    return {int(record.submission_id): record for record in submissions}


def _summarize_submission_games(game_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for game in game_rows:
        grouped[int(game.get("submission_id") or 0)].append(game)

    output: dict[str, dict[str, Any]] = {}
    for submission_id, games in sorted(grouped.items(), reverse=True):
        outcome_counts = Counter(str(game.get("outcome") or "unknown") for game in games)
        matchup_counts = Counter(str(game.get("matchup_tag") or "unknown") for game in games)
        intent_counts: Counter[str] = Counter()
        flaw_counts: Counter[str] = Counter()
        decision_rows = 0
        agreement_total = 0.0
        for game in games:
            decision_rows += int(game.get("decision_rows") or 0)
            agreement_total += float(game.get("teacher_agreement_rate") or 0.0)
            intent_counts.update(
                {str(row["intent"]): int(row["count"]) for row in game.get("top_strategy_intents", [])}
            )
            flaw_counts.update({str(row["flaw"]): int(row["count"]) for row in game.get("top_flaws", [])})
        output[str(submission_id)] = {
            "submission_id": submission_id,
            "agent_family": games[0].get("agent_family"),
            "file_name": games[0].get("file_name"),
            "public_score": games[0].get("public_score"),
            "game_count": len(games),
            "decision_rows": decision_rows,
            "outcome_counts": dict(outcome_counts),
            "matchup_counts": dict(matchup_counts),
            "avg_teacher_agreement_rate": agreement_total / len(games) if games else 0.0,
            "top_strategy_intents": [
                {"intent": intent, "count": count} for intent, count in intent_counts.most_common(10)
            ],
            "top_flaws": [{"flaw": flaw, "count": count} for flaw, count in flaw_counts.most_common(10)],
            "episodes": [game.get("episode_id") for game in games],
        }
    return output


def summarize_hop_strategy(
    *,
    strategy_rows: list[dict[str, Any]],
    submissions: list[SubmissionRecord],
    meta_snapshot: dict[str, Any],
    command: str,
    download_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    by_submission = _submission_by_id(submissions)
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in strategy_rows:
        grouped[_game_key(row)].append(row)

    game_rows: list[dict[str, Any]] = []
    for (submission_id, episode_id), rows in sorted(grouped.items(), reverse=True):
        submission = by_submission.get(submission_id)
        agrees = sum(1 for row in rows if row.get("teacher_agrees"))
        intent_counts = Counter(intent for row in rows for intent in row.get("hop_strategy_intents", []))
        flaw_counts = Counter(flaw for row in rows for flaw in row.get("flaw_tags", []))
        first = rows[0]
        game_rows.append(
            {
                "submission_id": submission_id,
                "episode_id": episode_id,
                "agent_family": first.get("agent_family"),
                "file_name": submission.file_name if submission else "",
                "public_score": submission.public_score if submission else first.get("leaderboard_score"),
                "submission_date": str(submission.date) if submission else None,
                "outcome": first.get("outcome"),
                "opponent_team_name": first.get("opponent_team_name"),
                "opponent_archetype": first.get("opponent_archetype"),
                "matchup_tag": first.get("matchup_tag"),
                "actor_index": first.get("actor_index"),
                "opponent_index": first.get("opponent_index"),
                "decision_rows": len(rows),
                "teacher_agreement_rate": _rate(agrees, len(rows)),
                "top_strategy_intents": [
                    {"intent": intent, "count": count} for intent, count in intent_counts.most_common(8)
                ],
                "top_flaws": [{"flaw": flaw, "count": count} for flaw, count in flaw_counts.most_common(8)],
                "agent_log_paths": first.get("agent_log_paths", []),
                "source_file": first.get("source_file", ""),
                "source_hash": first.get("source_hash", ""),
            }
        )

    outcome_counts = Counter(str(row.get("outcome") or "unknown") for row in game_rows)
    teacher_agrees = sum(1 for row in strategy_rows if row.get("teacher_agrees"))
    return {
        "command": command,
        "selected_submission_count": len(submissions),
        "selected_game_count": len(game_rows),
        "decision_rows": len(strategy_rows),
        "teacher_agreement_rate": _rate(teacher_agrees, len(strategy_rows)),
        "outcome_counts": dict(outcome_counts),
        "game_summaries": game_rows,
        "submission_summaries": _summarize_submission_games(game_rows),
        "strategy_intent_counts": _count_list_values(strategy_rows, "hop_strategy_intents"),
        "strategy_tag_counts": _count_list_values(strategy_rows, "hop_strategy_tags"),
        "pipeline_label_counts": _count_list_values(strategy_rows, "pipeline_labels"),
        "flaw_counts": _count_list_values(strategy_rows, "flaw_tags"),
        "research_role_counts": _top_counts(strategy_rows, "research_role"),
        "submissions": [record.to_json() for record in submissions],
        "download_failures": download_failures,
        "meta": {
            "date": meta_snapshot.get("date"),
            "latestDate": meta_snapshot.get("latestDate"),
            "redirected": meta_snapshot.get("redirected"),
            "totalDecks": meta_snapshot.get("totalDecks"),
            "source": meta_snapshot.get("source"),
        },
        "package_path": None,
        "package_sha256": None,
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _set_plot_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "font.family": "DejaVu Sans",
            "axes.facecolor": "#fbfbfb",
            "figure.facecolor": "white",
            "axes.edgecolor": "#d9d9d9",
            "axes.labelcolor": COLORS["ink"],
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
            "grid.color": "#e5e5e5",
            "grid.linewidth": 0.8,
        }
    )


def _save_figure(fig: Any, out: Path) -> None:
    fig.subplots_adjust(left=0.18, right=0.98, top=0.88, bottom=0.24)
    with plt.rc_context({"savefig.bbox": None}):
        fig.savefig(out, bbox_inches=None)
    plt.close(fig)


def _short(value: Any, *, max_len: int = 32) -> str:
    text = str(value or "unknown").encode("ascii", errors="ignore").decode("ascii").strip() or "unknown"
    return text if len(text) <= max_len else text[: max_len - 1] + "."


def _figure_outcomes(summary: dict[str, Any], out: Path) -> None:
    games = summary.get("game_summaries") or []
    labels = [_short(f"{game['submission_id']}\n{game.get('outcome')}") for game in games]
    scores = [float(game.get("public_score") or 0.0) for game in games]
    colors = [COLORS["green"] if game.get("outcome") == "win" else COLORS["red"] for game in games]
    fig, ax = plt.subplots(figsize=(12.5, 5.8))
    ax.bar(labels, scores, color=colors)
    ax.set_title("Selected Hop Submissions: Public Score And Sample Outcome")
    ax.set_ylabel("Public score")
    ax.grid(axis="y", alpha=0.75)
    for index, game in enumerate(games):
        ax.text(index, scores[index] + 8, str(game.get("episode_id")), ha="center", fontsize=9)
    _save_figure(fig, out)


def _figure_counter(counter: dict[str, int], out: Path, *, title: str, color: str) -> None:
    rows = list(counter.items())[:10]
    if not rows:
        rows = [("none", 1)]
    names = [_short(name, max_len=36) for name, _ in rows]
    counts = [count for _, count in rows]
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    y = list(range(len(rows)))
    ax.barh(y, counts, color=color)
    ax.set_title(title)
    ax.set_xlabel("Decision labels")
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.75)
    for yi, count in enumerate(counts):
        ax.text(count + max(counts) * 0.02, yi, str(count), va="center", fontsize=9)
    _save_figure(fig, out)


def _figure_teacher_agreement(summary: dict[str, Any], out: Path) -> None:
    games = summary.get("game_summaries") or []
    labels = [_short(game.get("submission_id")) for game in games]
    rates = [float(game.get("teacher_agreement_rate") or 0.0) for game in games]
    fig, ax = plt.subplots(figsize=(12.5, 5.4))
    ax.bar(labels, rates, color=COLORS["purple"])
    ax.set_title("Teacher Agreement By Selected Game")
    ax.set_ylabel("Agreement rate")
    ax.set_ylim(0, 1.0)
    ax.grid(axis="y", alpha=0.75)
    for index, rate in enumerate(rates):
        ax.text(index, min(0.98, rate + 0.03), f"{rate * 100:.1f}%", ha="center", fontsize=9)
    _save_figure(fig, out)


def create_figures(summary: dict[str, Any], figure_dir: Path) -> dict[str, str]:
    figure_dir.mkdir(parents=True, exist_ok=True)
    _set_plot_style()
    figures = {
        "outcomes": figure_dir / "01_submission_outcomes.png",
        "intents": figure_dir / "02_hop_strategy_intents.png",
        "pipeline": figure_dir / "03_pipeline_label_counts.png",
        "teacher": figure_dir / "04_teacher_agreement.png",
        "flaws": figure_dir / "05_flaw_counts.png",
    }
    _figure_outcomes(summary, figures["outcomes"])
    _figure_counter(
        summary.get("strategy_intent_counts") or {},
        figures["intents"],
        title="Hop Strategy Intents Across Selected Decisions",
        color=COLORS["blue"],
    )
    _figure_counter(
        summary.get("pipeline_label_counts") or {},
        figures["pipeline"],
        title="Pipeline Labels Across Selected Decisions",
        color=COLORS["orange"],
    )
    _figure_teacher_agreement(summary, figures["teacher"])
    _figure_counter(
        summary.get("flaw_counts") or {},
        figures["flaws"],
        title="Patch Signals And Flaws",
        color=COLORS["red"],
    )
    return {key: str(path) for key, path in figures.items()}


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def _counter_table(counter: dict[str, int], *, limit: int = 8) -> str:
    rows = [[key, value] for key, value in list(counter.items())[:limit]]
    return _md_table(["Label", "Count"], rows) if rows else "No rows."


def write_markdown_report(summary: dict[str, Any], out: Path, figure_rel_paths: dict[str, str]) -> None:
    games = summary.get("game_summaries") or []
    submission_summaries = summary.get("submission_summaries") or {}
    game_table = _md_table(
        ["Submission", "Episode", "Score", "Outcome", "Opponent", "Matchup", "Rows", "Agree"],
        [
            [
                game.get("submission_id"),
                game.get("episode_id"),
                game.get("public_score"),
                game.get("outcome"),
                _short(game.get("opponent_team_name"), max_len=24),
                game.get("matchup_tag"),
                game.get("decision_rows"),
                f"{float(game.get('teacher_agreement_rate') or 0.0) * 100:.1f}%",
            ]
            for game in games
        ],
    )
    how_lines = []
    for game in games:
        intents = ", ".join(f"{row['intent']} ({row['count']})" for row in game.get("top_strategy_intents", [])[:4])
        flaws = ", ".join(f"{row['flaw']} ({row['count']})" for row in game.get("top_flaws", [])[:4]) or "none flagged"
        how_lines.append(
            f"- Submission `{game.get('submission_id')}` in episode `{game.get('episode_id')}` "
            f"{game.get('outcome')} into `{game.get('matchup_tag')}`. "
            f"Main labels: {intents or 'low context only'}. Patch signals: {flaws}."
        )
    submission_lines = []
    for submission_id, item in submission_summaries.items():
        intents = ", ".join(
            f"{row['intent']} ({row['count']})" for row in item.get("top_strategy_intents", [])[:5]
        )
        flaws = ", ".join(f"{row['flaw']} ({row['count']})" for row in item.get("top_flaws", [])[:5]) or "none"
        submission_lines.append(
            f"- Submission `{submission_id}` 10-game set: {item.get('outcome_counts')} across "
            f"{item.get('matchup_counts')}; {item.get('decision_rows')} labeled decisions; "
            f"avg teacher agreement {float(item.get('avg_teacher_agreement_rate') or 0.0) * 100:.1f}%. "
            f"Top strategy labels: {intents or 'none'}. Patch signals: {flaws}."
        )
    log_lines = []
    for game in games:
        logs = game.get("agent_log_paths") or []
        log_lines.append(
            f"- Episode `{game.get('episode_id')}` agent logs: "
            + (", ".join(f"`{path}`" for path in logs) if logs else "none downloaded")
        )
    failure_lines = "\n".join(
        f"- {failure.get('stage')}: submission {failure.get('submission_id')}, "
        f"episode {failure.get('episode_id')}, error {failure.get('error')}"
        for failure in summary.get("download_failures", [])
    ) or "- None."
    meta = summary.get("meta") or {}
    source = meta.get("source") or {}
    report = f"""# Hop/Trevenant Latest Two Submission Game Labels

## Source Boundary

- Command: `{summary.get('command')}`.
- Selected submissions: {summary.get('selected_submission_count')}.
- Selected games: {summary.get('selected_game_count')}.
- Decision rows labeled: {summary.get('decision_rows')}.
- Meta API date: `{meta.get('date')}`, latestDate `{meta.get('latestDate')}`, redirected `{meta.get('redirected')}`, totalDecks `{meta.get('totalDecks')}`.
- Meta dataset URL: `{source.get('datasetUrl', 'unknown')}`.
- Package path: `none`.
- Package SHA256: `none`.
- Kaggle submission made: `no`.
- Learned-policy claim: `no`.

## How They Fared

{game_table}

{chr(10).join(how_lines)}

## Per-Submission Findings

{chr(10).join(submission_lines) or 'No per-submission rows.'}

![Submission outcomes]({figure_rel_paths.get('outcomes', '')})

## Hop Strategy Labels

The labels are per visible decision row and keep replay provenance, source hash, owner labels, actor/opponent indexes, outcome, matchup tag, sample weight, selected action, teacher comparison, and Hop strategy intent.

![Hop strategy intents]({figure_rel_paths.get('intents', '')})

{_counter_table(summary.get('strategy_intent_counts') or {})}

## Pipeline Label Shape

![Pipeline labels]({figure_rel_paths.get('pipeline', '')})

{_counter_table(summary.get('pipeline_label_counts') or {})}

## Teacher Agreement

![Teacher agreement]({figure_rel_paths.get('teacher', '')})

Overall teacher agreement rate: {float(summary.get('teacher_agreement_rate') or 0.0) * 100:.1f}%.

## Patch Signals

![Patch signals]({figure_rel_paths.get('flaws', '')})

{_counter_table(summary.get('flaw_counts') or {})}

## Agent Logs

{chr(10).join(log_lines)}

## Download Failures

{failure_lines}

## Machine-Readable Files

- Summary JSON: `summary.json`.
- Per-decision Hop labels: `hop_strategy_decision_labels.jsonl`.
- Figures: `figures/`.

Kaggle submission made: `no`.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")


def write_hop_strategy_report_bundle(
    *,
    summary: dict[str, Any],
    strategy_rows: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    label_path = output_dir / "hop_strategy_decision_labels.jsonl"
    summary_path = output_dir / "summary.json"
    markdown_path = output_dir / "hop_strategy_report.md"
    _write_jsonl(label_path, strategy_rows)
    figures = create_figures(summary, output_dir / "figures")
    rel_figures = {key: str(Path(path).relative_to(output_dir)).replace("\\", "/") for key, path in figures.items()}
    write_markdown_report(summary, markdown_path, rel_figures)
    summary_with_paths = dict(summary)
    summary_with_paths["figure_paths"] = figures
    summary_with_paths["strategy_labels_jsonl"] = str(label_path)
    summary_with_paths["markdown_report"] = str(markdown_path)
    _write_json(summary_path, summary_with_paths)
    return {
        "markdown_report": str(markdown_path),
        "summary_json": str(summary_path),
        "strategy_labels_jsonl": str(label_path),
        "figures": figures,
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }
