from __future__ import annotations

import csv
import hashlib
import importlib
import json
import random
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from ptcg.benchmark_compatibility import BENCHMARK_SCHEMA_VERSION, benchmark_config_hash, file_sha256_or_none
from ptcg.kaggle_agent_runner import decode_agent_action
from ptcg.kaggle_archive_validator import validate_archive_startup
from ptcg.benchmark_stats import summarize_counts
from ptcg.failure_taxonomy import classify_failure
from ptcg.native_eval import _load_agent, _pushd, _seed_runtime
from ptcg.round_robin import PreparedSubmission, prepare_submission_packages
from ptcg.seed_schedule import build_seed_schedule, parse_seed_list, save_seed_schedule


class BenchmarkConfigError(RuntimeError):
    pass


def run_benchmark_league(
    *,
    archive: Path | str,
    config_path: Path | str,
    output_dir: Path | str,
    command: str | None = None,
    explicit_seeds: list[int] | str | None = None,
    target_games_per_matchup: int | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    archive_path = Path(archive).resolve()
    config_file = Path(config_path).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = _load_config(config_file)
    _reject_broad_inputs(config)

    configured_games_per_matchup = int(config.get("games_per_matchup", 1))
    games_per_matchup = int(target_games_per_matchup or configured_games_per_matchup)
    max_steps = int(config.get("max_steps", 1000))
    sdk_path = _resolve_path(config.get("sdk_path", "data/official"), config_file.parent)
    base_seed = config.get("base_seed")
    seed_values = parse_seed_list(explicit_seeds if explicit_seeds is not None else config.get("seed_list"))
    if seed_values and len(seed_values) < games_per_matchup and base_seed is not None:
        seed_values = []

    candidate_validation = validate_archive_startup(archive_path)
    candidate_packages = prepare_submission_packages([archive_path], extract_root=output / "prepared" / "candidate")
    candidate_package = candidate_packages[0]
    registry, runnable_opponents = _build_opponent_registry(config, config_file=config_file, output_dir=output)
    available_opponents = [row for row in registry if row["available"]]
    unavailable_opponents = [row for row in registry if not row["available"]]

    matchups = [
        {"candidate": candidate_package.name, "opponent": opponent["name"]}
        for opponent in available_opponents
    ]
    schedule = build_seed_schedule(
        matchups,
        games_per_matchup=games_per_matchup,
        base_seed=int(base_seed) if base_seed is not None else None,
        explicit_seeds=seed_values or None,
    )
    save_seed_schedule(schedule, output / "seed_schedule.json")

    resume_rows = _load_resume_rows(output, archive_path, config_file) if resume else []
    scheduled_games = select_pending_scheduled_games(
        schedule["games"],
        resume_rows,
        target_games_per_matchup=games_per_matchup,
    )
    game_rows: list[dict[str, Any]] = _dedupe_game_rows(resume_rows)
    failures: list[dict[str, Any]] = []
    for scheduled in scheduled_games:
        opponent = runnable_opponents[scheduled["opponent"]]
        row = _run_scheduled_game(
            candidate=candidate_package,
            opponent=opponent,
            seed=int(scheduled["seed"]),
            game_index=int(scheduled["game_index"]),
            sdk_path=sdk_path,
            max_steps=max_steps,
        )
        row.update(
            {
                "matchup_id": scheduled["matchup_id"],
                "matchup_index": scheduled["matchup_index"],
                "candidate": scheduled["candidate"],
                "opponent": scheduled["opponent"],
            }
        )
        game_rows.append(row)
        if _truthy(row["error"]):
            failures.append(
                {
                    "stage": "game",
                    "category": row["error_category"],
                    "archive": str(archive_path),
                    "candidate": scheduled["candidate"],
                    "matchup": scheduled["opponent"],
                    "opponent": scheduled["opponent"],
                    "game_index": scheduled["game_index"],
                    "seed": scheduled["seed"],
                    "message": row["error_message"],
                    "error_type": row["error_type"],
                    "traceback": row.get("traceback", ""),
                }
            )
    game_rows = _dedupe_game_rows(game_rows)

    matchup_rows = _aggregate_matchups(game_rows)
    _write_csv(output / "results_by_game.csv", game_rows, _GAME_FIELDS)
    _write_csv(output / "results_by_matchup.csv", matchup_rows, _MATCHUP_FIELDS)
    _write_json(output / "opponent_registry.json", registry)
    _write_json(output / "failures.json", failures)

    summary = {
        "workflow": "benchmark_league_v1",
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "status": "completed",
        "candidate_archive": str(archive_path),
        "candidate_archive_sha256": _sha256_file(archive_path),
        "candidate_validation": candidate_validation,
        "config_path": str(config_file),
        "output_dir": str(output.resolve()),
        "command": command,
        "benchmark_config_sha256": benchmark_config_hash(config_file),
        "opponent_registry_sha256": file_sha256_or_none(output / "opponent_registry.json"),
        "seed_schedule_sha256": file_sha256_or_none(output / "seed_schedule.json"),
        "required_matchups": [row["name"] for row in available_opponents],
        "engine": "official_cg_sdk",
        "engine_path": str(sdk_path.resolve()),
        "engine_parity_status": "Kaggle-like raw archive startup plus official cg.game local execution; full official seed control is unavailable.",
        "configured_games_per_matchup": configured_games_per_matchup,
        "games_per_matchup": games_per_matchup,
        "target_games_per_matchup": games_per_matchup,
        "resume": bool(resume),
        "resumed_game_rows": len(resume_rows),
        "newly_scheduled_games": len(scheduled_games),
        "max_steps": max_steps,
        "opponent_count": len(registry),
        "available_opponent_count": len(available_opponents),
        "unavailable_opponent_count": len(unavailable_opponents),
        "unavailable_opponents": unavailable_opponents,
        "scheduled_games": len(game_rows),
        "finished_games": sum(1 for row in game_rows if _truthy(row["finished"])),
        "wins": sum(1 for row in game_rows if row["result"] == "win"),
        "losses": sum(1 for row in game_rows if row["result"] == "loss"),
        "draws": sum(1 for row in game_rows if row["result"] == "draw"),
        "errors": sum(1 for row in game_rows if _truthy(row["error"])),
        "invalid_actions": sum(1 for row in game_rows if _truthy(row["invalid_action"])),
        "timeouts": sum(1 for row in game_rows if _truthy(row["timeout"])),
        "diagnostics": _aggregate_diagnostics(game_rows, max_steps=max_steps),
        "aggregate_stats": summarize_counts(
            games=len(game_rows),
            finished=sum(1 for row in game_rows if _truthy(row["finished"])),
            wins=sum(1 for row in game_rows if row["result"] == "win"),
            losses=sum(1 for row in game_rows if row["result"] == "loss"),
            draws=sum(1 for row in game_rows if row["result"] == "draw"),
            errors=sum(1 for row in game_rows if _truthy(row["error"])),
            invalid_actions=sum(1 for row in game_rows if _truthy(row["invalid_action"])),
            timeouts=sum(1 for row in game_rows if _truthy(row["timeout"])),
        ),
        "gameplay_logs_read": 0,
        "used_broad_replay_globs": False,
        "official_sdk_seed_control": False,
        "crn_available": False,
        "sample_model": "seed-labeled independent batch",
        "git_status": _git_status(),
        "report_paths": {
            "results_by_game": str((output / "results_by_game.csv").resolve()),
            "results_by_matchup": str((output / "results_by_matchup.csv").resolve()),
            "summary": str((output / "summary.json").resolve()),
            "failures": str((output / "failures.json").resolve()),
            "seed_schedule": str((output / "seed_schedule.json").resolve()),
            "opponent_registry": str((output / "opponent_registry.json").resolve()),
        },
        "kaggle_submission_made": False,
    }
    _write_json(output / "summary.json", summary)
    return {
        "summary": summary,
        "game_rows": game_rows,
        "matchup_rows": matchup_rows,
        "failures": failures,
        "report_paths": summary["report_paths"],
        "kaggle_submission_made": False,
    }


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BenchmarkConfigError(f"missing benchmark config: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise BenchmarkConfigError("benchmark config must be a JSON object")
    if not isinstance(config.get("opponents"), list):
        raise BenchmarkConfigError("benchmark config must include opponents list")
    return config


def _reject_broad_inputs(config: dict[str, Any]) -> None:
    blocked_top = {"archive_glob", "replay_glob", "replay_dir", "replay_root"}
    present = sorted(key for key in blocked_top if key in config)
    if present:
        raise BenchmarkConfigError(f"broad glob or replay input is not allowed in benchmark config: {present}")
    for opponent in config.get("opponents") or []:
        if not isinstance(opponent, dict):
            raise BenchmarkConfigError("each opponent must be a JSON object")
        kind = opponent.get("kind", "archive")
        if kind in {"archive_glob", "replay_glob"} or "archive_glob" in opponent or "replay_dir" in opponent:
            raise BenchmarkConfigError("broad glob opponent definitions are not allowed")


def _build_opponent_registry(
    config: dict[str, Any],
    *,
    config_file: Path,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    registry: list[dict[str, Any]] = []
    runnable: dict[str, dict[str, Any]] = {}
    archive_sources: list[tuple[str, Path, dict[str, Any]]] = []

    for raw in config.get("opponents") or []:
        name = _safe_name(raw.get("name") or raw.get("archive") or raw.get("kind"))
        kind = str(raw.get("kind", "archive"))
        if kind == "random":
            row = {
                "name": name,
                "kind": kind,
                "available": True,
                "source_path": "builtin:random_legal_baseline",
                "source_sha256": None,
                "strict_validation_ok": None,
                "warnings": [],
                "description": raw.get("description", "Legal random option chooser using the candidate deck."),
            }
            registry.append(row)
            runnable[name] = {"kind": "random", "registry": row}
            continue
        if kind != "archive":
            raise BenchmarkConfigError(f"unsupported opponent kind: {kind}")
        archive_value = raw.get("archive")
        if not archive_value:
            registry.append(
                {
                    "name": name,
                    "kind": kind,
                    "available": False,
                    "source_path": None,
                    "source_sha256": None,
                    "strict_validation_ok": False,
                    "warnings": ["missing_archive_path"],
                    "unavailable_reason": "missing archive path",
                }
            )
            continue
        path = _resolve_path(archive_value, config_file.parent)
        if not path.exists():
            registry.append(
                {
                    "name": name,
                    "kind": kind,
                    "available": False,
                    "source_path": str(path),
                    "source_sha256": None,
                    "strict_validation_ok": False,
                    "warnings": ["missing_archive"],
                    "unavailable_reason": "archive not found",
                }
            )
            continue
        archive_sources.append((name, path, raw))

    if archive_sources:
        packages = prepare_submission_packages(
            [source[1] for source in archive_sources],
            extract_root=output_dir / "prepared" / "opponents",
        )
        for (name, path, raw), package in zip(archive_sources, packages):
            row = {
                "name": name,
                "kind": "archive",
                "available": bool(package.eligible_for_round_robin),
                "source_path": package.source_path,
                "source_sha256": package.source_sha256,
                "strict_validation_ok": package.strict_validation_ok,
                "warnings": list(package.warnings),
                "description": raw.get("description"),
            }
            if not package.eligible_for_round_robin:
                row["unavailable_reason"] = package.validation_error or "not eligible for local round robin"
            registry.append(row)
            if package.eligible_for_round_robin:
                runnable[name] = {"kind": "archive", "package": package, "registry": row}
    registry.sort(key=lambda row: str(row["name"]))
    return registry, runnable


def _run_scheduled_game(
    *,
    candidate: PreparedSubmission,
    opponent: dict[str, Any],
    seed: int,
    game_index: int,
    sdk_path: Path,
    max_steps: int,
) -> dict[str, Any]:
    candidate_first = game_index % 2 == 0
    base = {
        "game_index": game_index,
        "seed": seed,
        "candidate_first": candidate_first,
        "finished": False,
        "result": "error",
        "turns": "",
        "error": False,
        "error_type": "",
        "error_message": "",
        "error_category": "",
        "traceback": "",
        "invalid_action": False,
        "timeout": False,
        "prizes_taken": "",
        "prizes_allowed": "",
        "prize_differential": "",
        "early_loss": False,
        "no_progress": False,
        "timeout_adjacent_long_game": False,
        "invalid_action_type": "",
    }
    try:
        return {**base, **_play_one_game(candidate, opponent, seed, candidate_first, sdk_path, max_steps)}
    except Exception as exc:
        return {
            **base,
            "error": True,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "error_category": classify_failure("game", type(exc).__name__, str(exc)),
            "traceback": traceback.format_exc(limit=5),
        }


def _play_one_game(
    candidate: PreparedSubmission,
    opponent: dict[str, Any],
    seed: int,
    candidate_first: bool,
    sdk_path: Path,
    max_steps: int,
) -> dict[str, Any]:
    sdk = str(sdk_path.resolve())
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    game_module = importlib.import_module("cg.game")
    api_module = importlib.import_module("cg.api")
    battle_start = game_module.battle_start
    battle_select = game_module.battle_select
    battle_finish = game_module.battle_finish
    to_observation_class = api_module.to_observation_class

    candidate_deck = _read_deck(Path(candidate.deck_path))
    candidate_agent = _load_agent(Path(candidate.main_path), "ptcg_bench_candidate")
    opponent_kind = opponent["kind"]
    opponent_package = opponent.get("package")
    opponent_deck = candidate_deck if opponent_kind == "random" else _read_deck(Path(opponent_package.deck_path))
    opponent_agent = None if opponent_kind == "random" else _load_agent(Path(opponent_package.main_path), "ptcg_bench_opponent")
    rng = random.Random(seed)
    obs = None
    try:
        _seed_runtime(seed)
        deck0 = candidate_deck if candidate_first else opponent_deck
        deck1 = opponent_deck if candidate_first else candidate_deck
        obs, start_data = battle_start(deck0, deck1)
        if obs is None:
            return {
                "error": True,
                "error_type": "battle_start_failed",
                "error_message": f"{start_data.errorPlayer}:{start_data.errorType}",
                "error_category": classify_failure("game", "battle_start_failed", f"{start_data.errorPlayer}:{start_data.errorType}"),
                "invalid_action": False,
                "timeout": False,
                "finished": False,
                "result": "error",
                "turns": 0,
            }
        for turn_index in range(max_steps):
            obs_class = to_observation_class(obs)
            result = obs_class.current.result
            if result >= 0:
                candidate_index = 0 if candidate_first else 1
                if result == 2:
                    candidate_result = "draw"
                elif result == candidate_index:
                    candidate_result = "win"
                else:
                    candidate_result = "loss"
                diagnostics = _game_diagnostics(
                    obs,
                    candidate_index=candidate_index,
                    result=candidate_result,
                    turns=turn_index,
                    max_steps=max_steps,
                )
                return {
                    "finished": True,
                    "result": candidate_result,
                    "turns": turn_index,
                    "error": False,
                    "error_type": "",
                    "error_message": "",
                    "error_category": "",
                    "invalid_action": False,
                    "timeout": False,
                    **diagnostics,
                }
            active_is_candidate = (obs_class.current.yourIndex == 0) == candidate_first
            if active_is_candidate:
                with _pushd(Path(candidate.main_path).parent):
                    action = candidate_agent(obs)
            elif opponent_kind == "random":
                action = _random_action(obs, rng, to_observation_class)
            else:
                with _pushd(Path(opponent_package.main_path).parent):
                    action = opponent_agent(obs)
            invalid = _invalid_action_detail(action, obs)
            if invalid["reason"]:
                return {
                    "finished": False,
                    "result": "error",
                    "turns": turn_index,
                    "error": True,
                    "error_type": "invalid_action",
                    "error_message": invalid["reason"],
                    "error_category": "invalid_action",
                    "invalid_action": True,
                    "timeout": False,
                    "invalid_action_type": invalid["action_type"],
                }
            obs = battle_select(action)
        return {
            "finished": False,
            "result": "error",
            "turns": max_steps,
            "error": True,
            "error_type": "timeout",
            "error_message": "max_steps",
            "error_category": "timeout",
            "invalid_action": False,
            "timeout": True,
            "timeout_adjacent_long_game": True,
        }
    finally:
        if obs is not None:
            battle_finish()


def _random_action(obs: dict[str, Any], rng: random.Random, to_observation_class: Any) -> list[int]:
    obs_class = to_observation_class(obs)
    if obs_class.select is None:
        return []
    option_count = len(obs_class.select.option)
    return rng.sample(range(option_count), obs_class.select.maxCount)


def _invalid_action_detail(action: Any, obs: dict[str, Any]) -> dict[str, str]:
    select = obs.get("select") if isinstance(obs, dict) else None
    options = select.get("option") if isinstance(select, dict) else None
    if not isinstance(options, list):
        return {"reason": "", "action_type": ""}
    decision = decode_agent_action(action, obs)
    matched = decision.get("matched_option") or {}
    action_type = str(matched.get("type") or "") if isinstance(matched, dict) else ""
    return {"reason": "" if decision["legal"] else str(decision["invalid_reason"]), "action_type": action_type}


def _aggregate_matchups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_matchup: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_matchup.setdefault(row["matchup_id"], []).append(row)
    summaries: list[dict[str, Any]] = []
    for matchup_id, grouped in sorted(by_matchup.items()):
        finished_rows = [row for row in grouped if _truthy(row["finished"])]
        turns = [int(row["turns"]) for row in finished_rows if row["turns"] != ""]
        prize_diffs = [_to_int(row.get("prize_differential")) for row in finished_rows if row.get("prize_differential") != ""]
        prizes_taken = [_to_int(row.get("prizes_taken")) for row in finished_rows if row.get("prizes_taken") != ""]
        prizes_allowed = [_to_int(row.get("prizes_allowed")) for row in finished_rows if row.get("prizes_allowed") != ""]
        wins = sum(1 for row in grouped if row["result"] == "win")
        losses = sum(1 for row in grouped if row["result"] == "loss")
        draws = sum(1 for row in grouped if row["result"] == "draw")
        errors = sum(1 for row in grouped if _truthy(row["error"]))
        finished = len(finished_rows)
        summaries.append(
            {
                "matchup_id": matchup_id,
                "candidate": grouped[0]["candidate"],
                "opponent": grouped[0]["opponent"],
                **summarize_counts(
                    games=len(grouped),
                    finished=finished,
                    wins=wins,
                    losses=losses,
                    draws=draws,
                    errors=errors,
                    invalid_actions=sum(1 for row in grouped if _truthy(row["invalid_action"])),
                    timeouts=sum(1 for row in grouped if _truthy(row["timeout"])),
                ),
                "non_loss_rate": _rate(wins + draws, finished),
                "average_turns": round(sum(turns) / len(turns), 3) if turns else "",
                "average_prizes_taken": round(sum(prizes_taken) / len(prizes_taken), 3) if prizes_taken else "",
                "average_prizes_allowed": round(sum(prizes_allowed) / len(prizes_allowed), 3) if prizes_allowed else "",
                "average_prize_differential": round(sum(prize_diffs) / len(prize_diffs), 3) if prize_diffs else "",
                "early_losses": sum(1 for row in grouped if _truthy(row.get("early_loss"))),
                "no_progress_games": sum(1 for row in grouped if _truthy(row.get("no_progress"))),
                "timeout_adjacent_long_games": sum(1 for row in grouped if _truthy(row.get("timeout_adjacent_long_game"))),
                "invalid_action_count_by_action_type": _invalid_action_counts(grouped),
                "prize_progress_available": bool(prizes_taken or prizes_allowed),
            }
        )
    return summaries


def select_pending_scheduled_games(
    schedule_games: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    *,
    target_games_per_matchup: int,
) -> list[dict[str, Any]]:
    completed: dict[str, set[int]] = {}
    for row in existing_rows:
        if not _truthy(row.get("finished")):
            continue
        matchup_id = str(row.get("matchup_id") or "")
        completed.setdefault(matchup_id, set()).add(_to_int(row.get("game_index")))

    selected: list[dict[str, Any]] = []
    for row in schedule_games:
        matchup_id = str(row.get("matchup_id") or "")
        game_index = _to_int(row.get("game_index"))
        if game_index >= int(target_games_per_matchup):
            continue
        if game_index in completed.get(matchup_id, set()):
            continue
        selected.append(row)
    return selected


def _load_resume_rows(output: Path, archive_path: Path, config_file: Path) -> list[dict[str, Any]]:
    summary_path = output / "summary.json"
    game_path = output / "results_by_game.csv"
    if not summary_path.exists() or not game_path.exists():
        return []
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_sha = _sha256_file(archive_path)
    if str(summary.get("candidate_archive_sha256") or "").upper() != expected_sha:
        raise BenchmarkConfigError("cannot resume benchmark: existing result archive SHA does not match")
    recorded_config_hash = summary.get("benchmark_config_sha256")
    if recorded_config_hash and recorded_config_hash != benchmark_config_hash(config_file):
        raise BenchmarkConfigError("cannot resume benchmark: existing result benchmark config hash does not match")
    with game_path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _dedupe_game_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("matchup_id") or ""), _to_int(row.get("game_index")))
        by_key[key] = row
    return [by_key[key] for key in sorted(by_key)]


def _game_diagnostics(
    obs: dict[str, Any],
    *,
    candidate_index: int,
    result: str,
    turns: int,
    max_steps: int,
) -> dict[str, Any]:
    players = ((obs.get("current") or {}).get("players") or []) if isinstance(obs, dict) else []
    if not isinstance(players, list) or len(players) <= candidate_index:
        return {
            "prizes_taken": "",
            "prizes_allowed": "",
            "prize_differential": "",
            "early_loss": result == "loss" and int(turns) <= 20,
            "no_progress": False,
            "timeout_adjacent_long_game": int(turns) >= int(max_steps * 0.9),
        }
    opponent_index = 1 - int(candidate_index)
    try:
        candidate_prizes_left = len(players[candidate_index].get("prize") or [])
        opponent_prizes_left = len(players[opponent_index].get("prize") or [])
    except (AttributeError, IndexError, TypeError):
        return {
            "prizes_taken": "",
            "prizes_allowed": "",
            "prize_differential": "",
            "early_loss": result == "loss" and int(turns) <= 20,
            "no_progress": False,
            "timeout_adjacent_long_game": int(turns) >= int(max_steps * 0.9),
        }
    prizes_taken = max(0, 6 - int(candidate_prizes_left))
    prizes_allowed = max(0, 6 - int(opponent_prizes_left))
    return {
        "prizes_taken": prizes_taken,
        "prizes_allowed": prizes_allowed,
        "prize_differential": prizes_taken - prizes_allowed,
        "early_loss": result == "loss" and int(turns) <= 20,
        "no_progress": result in {"loss", "draw"} and prizes_taken == 0,
        "timeout_adjacent_long_game": int(turns) >= int(max_steps * 0.9),
    }


def _aggregate_diagnostics(rows: list[dict[str, Any]], *, max_steps: int) -> dict[str, Any]:
    finished = [row for row in rows if _truthy(row.get("finished"))]
    prize_taken_values = [_to_int(row.get("prizes_taken")) for row in finished if row.get("prizes_taken") != ""]
    prize_allowed_values = [_to_int(row.get("prizes_allowed")) for row in finished if row.get("prizes_allowed") != ""]
    diff_values = [_to_int(row.get("prize_differential")) for row in finished if row.get("prize_differential") != ""]
    return {
        "average_prizes_taken": round(sum(prize_taken_values) / len(prize_taken_values), 3) if prize_taken_values else None,
        "average_prizes_allowed": round(sum(prize_allowed_values) / len(prize_allowed_values), 3) if prize_allowed_values else None,
        "average_prize_differential": round(sum(diff_values) / len(diff_values), 3) if diff_values else None,
        "average_turns": _average([_to_int(row.get("turns")) for row in finished if row.get("turns") != ""]),
        "early_loss_count": sum(1 for row in rows if _truthy(row.get("early_loss"))),
        "no_progress_games": sum(1 for row in rows if _truthy(row.get("no_progress"))),
        "timeout_adjacent_long_games": sum(1 for row in rows if _truthy(row.get("timeout_adjacent_long_game"))),
        "invalid_action_count_by_action_type": _invalid_action_counts(rows),
        "diagnostic_limitations": (
            "Prize diagnostics use public prize-count deltas only. Prize-card identities are not used. "
            f"Timeout-adjacent long games are turns >= {int(max_steps * 0.9)}."
        ),
    }


def _invalid_action_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if not _truthy(row.get("invalid_action")):
            continue
        action_type = str(row.get("invalid_action_type") or "unknown")
        counts[action_type] = counts.get(action_type, 0) + 1
    return counts


def _average(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).lower() in {"1", "true", "yes", "y"}


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


_GAME_FIELDS = [
    "matchup_id",
    "matchup_index",
    "candidate",
    "opponent",
    "game_index",
    "seed",
    "candidate_first",
    "finished",
    "result",
    "turns",
    "error",
    "error_type",
    "error_message",
    "error_category",
    "traceback",
    "invalid_action",
    "timeout",
    "prizes_taken",
    "prizes_allowed",
    "prize_differential",
    "early_loss",
    "no_progress",
    "timeout_adjacent_long_game",
    "invalid_action_type",
]

_MATCHUP_FIELDS = [
    "matchup_id",
    "candidate",
    "opponent",
    "games",
    "finished",
    "wins",
    "losses",
    "draws",
    "errors",
    "invalid_actions",
    "timeouts",
    "crash_count",
    "win_rate",
    "lower_ci",
    "upper_ci",
    "non_loss_rate",
    "invalid_action_rate",
    "timeout_rate",
    "crash_rate",
    "average_turns",
    "average_prizes_taken",
    "average_prizes_allowed",
    "average_prize_differential",
    "early_losses",
    "no_progress_games",
    "timeout_adjacent_long_games",
    "invalid_action_count_by_action_type",
    "prize_progress_available",
]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_path(value: Any, base_dir: Path) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path.resolve()
    cwd_path = (Path.cwd() / path).resolve()
    if cwd_path.exists():
        return cwd_path
    return (base_dir / path).resolve()


def _read_deck(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _safe_name(value: Any) -> str:
    raw = str(value or "opponent")
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in raw).strip("_") or "opponent"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _rate(count: int, total: int) -> float:
    return round(float(count) / float(total), 6) if total else 0.0


def _git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else result.stderr
