from __future__ import annotations

from collections import Counter, defaultdict
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from ptcg.daily_episode_labeling import load_leaderboard_scores
from ptcg.daily_episode_labeling import rank_episode_summaries
from ptcg.daily_episode_labeling import summarize_episode


TREND_TAGS = (
    "setup_failure",
    "attack_without_backup",
    "energy_overcommit_active",
    "target_gust_error",
    "dragapult_spread_posture_gap",
    "hop_trevenant_second_swing_gap",
    "wall_control_zero_conversion",
    "low_deck_churn",
)

TREND_PRIORITY = {
    "wall_control_zero_conversion": 100,
    "hop_trevenant_second_swing_gap": 95,
    "dragapult_spread_posture_gap": 90,
    "setup_failure": 80,
    "attack_without_backup": 75,
    "energy_overcommit_active": 60,
    "target_gust_error": 55,
    "low_deck_churn": 40,
}

WALL_ARCHETYPE_MARKERS = ("wall", "stall", "crustle", "waitress", "control")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _safe_git_status() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        return f"git status unavailable: {type(exc).__name__}:{exc}"
    return result.stdout.strip()


def _json_files(path: Path) -> list[Path]:
    return sorted(item for item in path.rglob("*.json") if item.is_file())


def _dataset_stats(path: Path) -> dict[str, Any]:
    files = [item for item in path.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    return {
        "dataset_dir": str(path),
        "file_count": len(files),
        "json_file_count": sum(1 for item in files if item.suffix.lower() == ".json"),
        "total_bytes": total_bytes,
        "total_gib": total_bytes / (1024**3),
    }


def scan_top_ranked_episodes(
    *,
    dataset_dir: Path,
    leaderboard_csv: Path,
    output_dir: Path,
    top_limit: int = 50,
    max_games: int | None = None,
    command: str = "",
    meta_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scan replay files one at a time and rank the strongest known-leaderboard games."""

    dataset_dir = Path(dataset_dir)
    leaderboard_csv = Path(leaderboard_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "scan_progress.jsonl"
    if progress_path.exists():
        progress_path.unlink()

    scores = load_leaderboard_scores(leaderboard_csv)
    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    paths = _json_files(dataset_dir)
    if max_games is not None:
        paths = paths[: max(0, max_games)]

    for ordinal, replay_path in enumerate(paths, start=1):
        try:
            summary = summarize_episode(replay_path, scores)
            summaries.append(summary)
            _append_jsonl(
                progress_path,
                {
                    "ordinal": ordinal,
                    "path": str(replay_path),
                    "episode_id": summary.get("episode_id"),
                    "decision_count": summary.get("decision_count"),
                    "active_decision_count": summary.get("active_decision_count"),
                    "known_leaderboard_score_sum": summary.get("known_leaderboard_score_sum"),
                    "status": "ok",
                },
            )
        except Exception as exc:
            error = {"ordinal": ordinal, "path": str(replay_path), "error": f"{type(exc).__name__}:{exc}"}
            errors.append(error)
            _append_jsonl(progress_path, {**error, "status": "error"})

    ranked = rank_episode_summaries(summaries)
    top_episodes = ranked[:top_limit]
    rankings_path = output_dir / "episode_rankings_top50.json"
    top_paths_path = output_dir / "top_episode_paths.txt"
    report = {
        "command": command,
        "git_status": _safe_git_status(),
        "dataset": _dataset_stats(dataset_dir),
        "leaderboard_csv": str(leaderboard_csv),
        "meta_snapshot": meta_snapshot or {},
        "scanned_count": len(summaries),
        "candidate_file_count": len(paths),
        "error_count": len(errors),
        "errors": errors,
        "ranking_rule": (
            "Rank full-dataset episodes by exact current leaderboard team-name matches, sum of matched leaderboard "
            "scores, winner matched score, active decision count, then step count."
        ),
        "top_episodes": top_episodes,
        "paths": {
            "scan_progress_jsonl": str(progress_path),
            "rankings_json": str(rankings_path),
            "top_episode_paths_txt": str(top_paths_path),
        },
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }
    _write_json(rankings_path, report)
    top_paths_path.write_text(
        "".join(str(row.get("path")) + "\n" for row in top_episodes if row.get("path")),
        encoding="utf-8",
    )
    return report


def _current_player(row: dict[str, Any]) -> dict[str, Any]:
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    index = row.get("actor_index", row.get("agent_index", current.get("yourIndex", 0)))
    try:
        actor_index = int(index)
    except (TypeError, ValueError):
        actor_index = 0
    if 0 <= actor_index < len(players) and isinstance(players[actor_index], dict):
        return players[actor_index]
    return {}


def _deck_count(row: dict[str, Any]) -> int | None:
    player = _current_player(row)
    for key in ("deck_count", "deckCount"):
        value = player.get(key)
        if isinstance(value, int):
            return value
    deck = player.get("deck")
    if isinstance(deck, list):
        return len(deck)
    return None


def _has_any(values: Iterable[str], needles: Iterable[str]) -> bool:
    haystack = set(values)
    return any(needle in haystack for needle in needles)


def trend_tags_for_decision(row: dict[str, Any]) -> list[str]:
    flaws = set(str(value) for value in row.get("flaw_tags") or [])
    pipeline = set(str(value) for value in row.get("pipeline_labels") or [])
    selected_penalties = set(str(value) for value in row.get("selected_penalties") or [])
    matchup = str(row.get("matchup_tag") or row.get("opponent_archetype") or "unknown")
    opponent = str(row.get("opponent_archetype") or matchup)
    outcome = str(row.get("outcome") or "")
    tags: list[str] = []

    if _has_any(flaws, ("missed_setup", "anti_lucario_setup_or_trap_gap")) or (
        outcome == "loss" and _has_any(pipeline, ("setup", "bench_develop"))
    ):
        tags.append("setup_failure")
    if "attack_without_backup" in flaws or "attack_without_backup" in selected_penalties:
        tags.append("attack_without_backup")
    if "active_overattach" in flaws or "active_overattach" in selected_penalties or (
        outcome == "loss" and "energy_attach_active" in pipeline
    ):
        tags.append("energy_overcommit_active")
    if _has_any(flaws, ("missed_trap_turn", "teacher_preferred_alternative")) and _has_any(
        pipeline, ("gust_target", "stall_or_denial", "disruption")
    ):
        tags.append("target_gust_error")
    if "dragapult" in opponent and (
        _has_any(tags, ("setup_failure", "attack_without_backup", "target_gust_error"))
        or _has_any(pipeline, ("bench_develop", "preserve_resources", "gust_target"))
    ):
        tags.append("dragapult_spread_posture_gap")
    if "hop_trevenant" in opponent and (
        _has_any(tags, ("setup_failure", "attack_without_backup", "energy_overcommit_active"))
        or _has_any(pipeline, ("retreat_switch", "preserve_resources", "bench_develop"))
    ):
        tags.append("hop_trevenant_second_swing_gap")
    if any(marker in opponent or marker in matchup for marker in WALL_ARCHETYPE_MARKERS) and (
        _has_any(flaws, ("unconverted_decision", "teacher_preferred_alternative"))
        or _has_any(pipeline, ("attack_prize_race", "stall_or_denial"))
    ):
        tags.append("wall_control_zero_conversion")
    deck_count = _deck_count(row)
    if deck_count is not None and deck_count <= 8 and "draw/search/thin" in pipeline:
        tags.append("low_deck_churn")

    return [tag for tag in TREND_TAGS if tag in set(tags)]


def _primary_failure(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return sorted(counter, key=lambda tag: (TREND_PRIORITY.get(tag, 0), counter[tag], tag), reverse=True)[0]


def build_per_game_trend_summary(
    hard_labels_jsonl: Path,
    output_path: Path,
    *,
    command: str = "",
) -> dict[str, Any]:
    games: dict[str, dict[str, Any]] = {}
    aggregate = Counter()
    total_rows = 0

    with Path(hard_labels_jsonl).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            total_rows += 1
            row = json.loads(line)
            episode_id = str(row.get("episode_id") or row.get("replay_id") or "unknown")
            game = games.setdefault(
                episode_id,
                {
                    "episode_id": episode_id,
                    "source_file": row.get("source_file") or row.get("replay_path"),
                    "source_sha256": row.get("source_sha256"),
                    "legal_scope": row.get("legal_scope"),
                    "agent_family": row.get("team_name") or row.get("agent_family"),
                    "actor_archetype": row.get("actor_archetype"),
                    "opponent_archetype": row.get("opponent_archetype"),
                    "matchup_tag": row.get("matchup_tag"),
                    "outcome": row.get("outcome"),
                    "phase_counts": defaultdict(Counter),
                    "trend_counts": Counter(),
                    "evidence_steps": [],
                    "sample_weight_total": 0.0,
                    "research_role": "game_trend_breakdown",
                    "kaggle_submission_made": False,
                },
            )
            tags = trend_tags_for_decision(row)
            phase = str(row.get("phase") or "unknown")
            for tag in tags:
                game["trend_counts"][tag] += 1
                game["phase_counts"][phase][tag] += 1
                aggregate[tag] += 1
            try:
                game["sample_weight_total"] += float(row.get("sample_weight") or 0.0)
            except (TypeError, ValueError):
                pass
            if tags and len(game["evidence_steps"]) < 20:
                game["evidence_steps"].append(
                    {
                        "step_index": row.get("step_index"),
                        "phase": phase,
                        "decision_window": row.get("decision_window"),
                        "trend_tags": tags,
                        "flaw_tags": row.get("flaw_tags") or [],
                        "pipeline_labels": row.get("pipeline_labels") or [],
                        "teacher_score_delta": row.get("score_delta_teacher_minus_selected"),
                    }
                )

    output_games = []
    for game in games.values():
        trend_counts = Counter(game["trend_counts"])
        primary = _primary_failure(trend_counts)
        output_games.append(
            {
                **{key: value for key, value in game.items() if key not in {"phase_counts", "trend_counts"}},
                "phase_counts": {
                    phase: dict(sorted(counter.items())) for phase, counter in sorted(game["phase_counts"].items())
                },
                "trend_counts": {tag: int(trend_counts.get(tag, 0)) for tag in TREND_TAGS},
                "trend_tags": [tag for tag in TREND_TAGS if trend_counts.get(tag, 0)],
                "primary_failure_family": primary,
                "patch_priority": TREND_PRIORITY.get(primary, 0),
            }
        )
    output_games.sort(key=lambda item: (int(item["patch_priority"]), sum(item["trend_counts"].values())), reverse=True)
    report = {
        "command": command,
        "input_path": str(hard_labels_jsonl),
        "game_count": len(output_games),
        "decision_rows": total_rows,
        "aggregate_trend_counts": {tag: int(aggregate.get(tag, 0)) for tag in TREND_TAGS},
        "games": output_games,
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }
    _write_json(Path(output_path), report)
    return report
