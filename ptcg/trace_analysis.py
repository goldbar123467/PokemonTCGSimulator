from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _selected_options(step: dict[str, Any]) -> list[dict[str, Any]]:
    options = step.get("options")
    return [option for option in options if isinstance(option, dict) and option.get("selected")] if isinstance(options, list) else []


def _options(step: dict[str, Any]) -> list[dict[str, Any]]:
    options = step.get("options")
    return [option for option in options if isinstance(option, dict)] if isinstance(options, list) else []


def _energies(card: dict[str, Any] | None) -> int:
    if not isinstance(card, dict):
        return 0
    return _int(card.get("energies"))


def _bench_cards(step: dict[str, Any]) -> list[dict[str, Any]]:
    bench = ((step.get("us") or {}).get("bench") or []) if isinstance(step.get("us"), dict) else []
    return [card for card in bench if isinstance(card, dict)] if isinstance(bench, list) else []


def _bench_powered(step: dict[str, Any]) -> int:
    return sum(1 for card in _bench_cards(step) if _energies(card) > 0)


def _bench_count(step: dict[str, Any]) -> int:
    us = step.get("us") if isinstance(step.get("us"), dict) else {}
    return _int(us.get("bench_count"))


def _active_card(step: dict[str, Any]) -> dict[str, Any] | None:
    us = step.get("us") if isinstance(step.get("us"), dict) else {}
    active = us.get("active")
    return active if isinstance(active, dict) else None


def _them_powered(step: dict[str, Any]) -> int:
    them = step.get("them") if isinstance(step.get("them"), dict) else {}
    return _int(them.get("powered_board"))


def _them_bench_count(step: dict[str, Any]) -> int:
    them = step.get("them") if isinstance(step.get("them"), dict) else {}
    return _int(them.get("bench_count"))


def _active_is_dangerous(step: dict[str, Any]) -> bool:
    active = _active_card(step)
    if not active or _them_powered(step) <= 0:
        return False
    hp = _int(active.get("hp"), _int(active.get("maxHp")))
    max_hp = _int(active.get("maxHp"), hp)
    if max_hp <= 0:
        return False
    return hp <= max(90, int(max_hp * 0.45))


def _selected_signature(step: dict[str, Any], option: dict[str, Any]) -> str:
    source = option.get("source_card") if isinstance(option.get("source_card"), dict) else {}
    target = option.get("target_card") if isinstance(option.get("target_card"), dict) else {}
    return (
        f"context={step.get('select_context')}|type={option.get('type')}|"
        f"source={source.get('id')}|target={target.get('id')}|attack={option.get('attackId')}"
    )


def _failure_tags(metrics: dict[str, int]) -> list[str]:
    tags: list[str] = []
    if metrics["empty_bench_attacks"] > 0:
        tags.append("single_active_attack_race")
    if metrics["active_overattach_steps"] > 0:
        tags.append("overfeeding_active")
    if metrics["bench_attach_available_but_missed"] > 0:
        tags.append("missed_bench_attachment")
    if metrics["end_without_backup_steps"] > 0:
        tags.append("ending_without_backup")
    if metrics["board_pressure_steps"] > 0:
        tags.append("opponent_board_outran_us")
    if metrics["dangerous_active_steps"] > 0 and metrics["no_next_attacker_steps"] > 0:
        tags.append("no_next_attacker_under_pressure")
    return tags


def summarize_trace_report(report: dict[str, Any]) -> dict[str, Any]:
    metrics = Counter()
    selected_types: Counter[str] = Counter()
    selected_signatures: Counter[str] = Counter()
    select_contexts: Counter[str] = Counter()
    per_game: list[dict[str, Any]] = []

    for trace in report.get("traces") or []:
        if not isinstance(trace, dict):
            continue
        game_metrics = Counter()
        steps = [step for step in trace.get("steps") or [] if isinstance(step, dict)]
        for step in steps:
            metrics["candidate_steps"] += 1
            game_metrics["candidate_steps"] += 1
            select_contexts[str(step.get("select_context"))] += 1

            selected = _selected_options(step)
            for option in selected:
                selected_types[str(option.get("type"))] += 1
                selected_signatures[_selected_signature(step, option)] += 1

            has_attack = any(option.get("type") == 13 for option in selected)
            has_end = any(option.get("type") == 14 for option in selected)
            has_active_attach = any(
                option.get("type") == 8 and option.get("inPlayArea") == 4 and _energies(option.get("target_card")) > 0
                for option in selected
            )
            has_bench_attach_option = any(option.get("type") == 8 and option.get("inPlayArea") == 5 for option in _options(step))

            if _bench_count(step) == 0:
                metrics["empty_bench_steps"] += 1
                game_metrics["empty_bench_steps"] += 1
            if _bench_powered(step) == 0:
                metrics["no_powered_bench_steps"] += 1
                game_metrics["no_powered_bench_steps"] += 1
            if _bench_powered(step) == 0 and _them_powered(step) > 0:
                metrics["no_next_attacker_steps"] += 1
                game_metrics["no_next_attacker_steps"] += 1
            if _active_is_dangerous(step):
                metrics["dangerous_active_steps"] += 1
                game_metrics["dangerous_active_steps"] += 1
            if _them_bench_count(step) >= 3 and _bench_count(step) <= 1 and _them_powered(step) > 0:
                metrics["board_pressure_steps"] += 1
                game_metrics["board_pressure_steps"] += 1
            if has_attack:
                metrics["attack_steps"] += 1
                game_metrics["attack_steps"] += 1
                if _bench_count(step) == 0:
                    metrics["empty_bench_attacks"] += 1
                    game_metrics["empty_bench_attacks"] += 1
                if _bench_powered(step) == 0 and _them_powered(step) > 0:
                    metrics["attack_without_powered_backup"] += 1
                    game_metrics["attack_without_powered_backup"] += 1
            if has_end and _bench_powered(step) == 0 and _them_powered(step) > 0:
                metrics["end_without_backup_steps"] += 1
                game_metrics["end_without_backup_steps"] += 1
            if has_active_attach:
                metrics["active_overattach_steps"] += 1
                game_metrics["active_overattach_steps"] += 1
            if has_active_attach and has_bench_attach_option and _bench_powered(step) == 0:
                metrics["bench_attach_available_but_missed"] += 1
                game_metrics["bench_attach_available_but_missed"] += 1

        per_game.append(
            {
                "game_index": trace.get("game_index"),
                "candidate_first": trace.get("candidate_first"),
                "candidate_result": trace.get("candidate_result"),
                "metrics": dict(sorted(game_metrics.items())),
            }
        )

    base = {
        "opponent": report.get("opponent"),
        "games": _int(report.get("games")),
        "finished": _int(report.get("finished")),
        "wins": _int(report.get("wins")),
        "losses": _int(report.get("losses")),
        "draws": _int(report.get("draws")),
        "error_count": len(report.get("errors") or []),
        "metrics": dict(sorted(metrics.items())),
        "failure_tags": _failure_tags(metrics),
        "selected_types": dict(selected_types.most_common()),
        "select_contexts": dict(select_contexts.most_common()),
        "top_selected_signatures": dict(selected_signatures.most_common(20)),
        "games_detail": per_game,
    }
    return base


def summarize_trace_reports(paths: list[Path]) -> dict[str, Any]:
    reports = []
    aggregate = Counter()
    tag_counts: Counter[str] = Counter()
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        summary = summarize_trace_report(report)
        summary["path"] = str(path)
        reports.append(summary)
        aggregate["reports"] += 1
        for key in ("games", "finished", "wins", "losses", "draws"):
            aggregate[key] += _int(summary.get(key))
        aggregate["errors"] += _int(summary.get("error_count"))
        for key, value in summary["metrics"].items():
            aggregate[key] += _int(value)
        tag_counts.update(summary["failure_tags"])

    reports.sort(key=lambda item: (item["losses"], item["metrics"].get("board_pressure_steps", 0)), reverse=True)
    return {
        "aggregate": dict(sorted(aggregate.items())),
        "failure_tag_counts": dict(tag_counts.most_common()),
        "reports": reports,
    }


def write_trace_failure_summary(paths: list[Path], output_path: Path) -> dict[str, Any]:
    summary = summarize_trace_reports(paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
