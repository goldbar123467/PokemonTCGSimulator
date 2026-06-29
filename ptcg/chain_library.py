from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
import json


ACTION_TYPE_NAMES = {
    0: "number",
    1: "yes",
    2: "no",
    3: "card",
    4: "tool_card",
    5: "energy_card",
    6: "energy",
    7: "play",
    8: "attach",
    9: "evolve",
    10: "ability",
    11: "discard",
    12: "retreat",
    13: "attack",
    14: "end",
    15: "skill",
    16: "special_condition",
}

AREA_NAMES = {
    1: "deck",
    2: "hand",
    3: "discard",
    4: "active",
    5: "bench",
    6: "prize",
    7: "stadium",
    12: "looking",
    "deck": "deck",
    "hand": "hand",
    "discard": "discard",
    "active": "active",
    "bench": "bench",
    "prize": "prize",
    "stadium": "stadium",
    "looking": "looking",
}

MATCHUP_STRATEGY_LABELS = {
    "lucario": "anti_lucario_gate",
    "dragapult_spread": "anti_dragapult_spread_gate",
    "alakazam": "anti_alakazam_setup_gate",
    "mega_starmie": "anti_mega_starmie_spread_gate",
    "hop_trevenant": "anti_hop_trevenant_control_gate",
}

PIPELINE_STRATEGY_LABELS = {
    "setup": "engine_setup",
    "bench_develop": "engine_setup",
    "energy_attach_bench_next_attacker": "next_attacker_energy",
    "attack_prize_race": "attack_closure",
    "risk_behind_high_variance": "high_variance_recovery",
    "stall_or_denial": "disruption_or_gust",
    "gust_target": "disruption_or_gust",
    "disruption": "disruption_or_gust",
}

FLAW_STRATEGY_LABELS = {
    "missed_setup": "setup_gap_patch",
    "bench_develop": "setup_gap_patch",
    "attack_without_backup": "next_attacker_gap_patch",
    "teacher_preferred_alternative": "teacher_rewrite_candidate",
    "dead_or_random_move": "avoid_random_end",
    "unclear_or_forced": "avoid_random_end",
    "active_overattach": "energy_conservation_patch",
    "energy_attach_active": "energy_conservation_patch",
    "preserve_resources": "resource_preservation_patch",
    "unconverted_decision": "unconverted_decision_review",
}


def _unique_ordered(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _zone_cards(player: dict[str, Any], zone: str) -> list[dict[str, Any]]:
    value = player.get(zone)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _energy_count(card: dict[str, Any] | None) -> int:
    if not isinstance(card, dict):
        return 0
    energy_cards = card.get("energyCards")
    if isinstance(energy_cards, list) and energy_cards:
        return len(energy_cards)
    energies = card.get("energies")
    if isinstance(energies, list):
        return len(energies)
    if isinstance(energies, (int, float)):
        return int(energies)
    return 0


def _card_summary(card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(card, dict):
        return None
    return {
        "id": card.get("id"),
        "hp": card.get("hp"),
        "max_hp": card.get("maxHp"),
        "energy_count": _energy_count(card),
        "tool_count": len(card.get("tools") or []) if isinstance(card.get("tools"), list) else 0,
        "serial": card.get("serial"),
    }


def _deck_count(player: dict[str, Any]) -> int | None:
    for key in ("deckCount", "deck_count"):
        value = player.get(key)
        if isinstance(value, int):
            return value
    deck = player.get("deck")
    return len(deck) if isinstance(deck, list) else None


def _hand_count(player: dict[str, Any]) -> int | None:
    value = player.get("handCount")
    if isinstance(value, int):
        return value
    hand = player.get("hand")
    return len(hand) if isinstance(hand, list) else None


def _prize_count(player: dict[str, Any]) -> int | None:
    for key in ("prizeCount", "prize_count"):
        value = player.get(key)
        if isinstance(value, int) and 0 <= value <= 6:
            return value
    prize = player.get("prize")
    return len(prize) if isinstance(prize, list) else None


def _player_snapshot(player: dict[str, Any]) -> dict[str, Any]:
    active = _zone_cards(player, "active")
    bench = _zone_cards(player, "bench")
    active_summary = _card_summary(active[0]) if active else None
    bench_summary = [_card_summary(card) for card in bench]
    return {
        "active": active_summary,
        "bench": bench_summary,
        "active_id": active_summary.get("id") if active_summary else None,
        "bench_ids": [card.get("id") for card in bench_summary if isinstance(card, dict)],
        "active_energy_count": active_summary.get("energy_count") if active_summary else 0,
        "bench_energy_total": sum(int(card.get("energy_count") or 0) for card in bench_summary if isinstance(card, dict)),
        "bench_count": len(bench),
        "deck_count": _deck_count(player),
        "hand_count": _hand_count(player),
        "prize_count": _prize_count(player),
    }


def _board_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    raw_players = current.get("players") if isinstance(current.get("players"), list) else []
    players = [player if isinstance(player, dict) else {} for player in raw_players]
    while len(players) < 2:
        players.append({})
    actor_index = _safe_int(row.get("actor_index", current.get("yourIndex")), _safe_int(current.get("yourIndex"), 0))
    opponent_index = _safe_int(row.get("opponent_index"), 1 - actor_index if actor_index in {0, 1} else 1)
    if actor_index not in {0, 1}:
        actor_index = _safe_int(current.get("yourIndex"), 0)
    if opponent_index not in {0, 1}:
        opponent_index = 1 - actor_index if actor_index in {0, 1} else 1
    return {
        "turn": current.get("turn"),
        "turn_action_count": current.get("turnActionCount"),
        "energy_attached": current.get("energyAttached"),
        "supporter_played": current.get("supporterPlayed"),
        "stadium_played": current.get("stadiumPlayed"),
        "result": current.get("result"),
        "actor": _player_snapshot(players[actor_index]),
        "opponent": _player_snapshot(players[opponent_index]),
    }


def _card_from_area(row: dict[str, Any], option: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(option.get("cardId"), int):
        return {"id": int(option["cardId"])}
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    area = AREA_NAMES.get(option.get("area"))
    if area is None and option.get("type") == 7:
        area = "hand"
    if area in {"deck", "prize"}:
        return None
    player_index = _safe_int(option.get("playerIndex", row.get("actor_index", current.get("yourIndex"))), 0)
    index = _safe_int(option.get("index"), -1)
    if not (0 <= player_index < len(players)) or not isinstance(players[player_index], dict):
        return None
    cards = _zone_cards(players[player_index], area) if area else []
    return cards[index] if 0 <= index < len(cards) else None


def _target_from_option(row: dict[str, Any], option: dict[str, Any]) -> dict[str, Any] | None:
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    area = AREA_NAMES.get(option.get("inPlayArea"))
    player_index = _safe_int(option.get("inPlayPlayerIndex", option.get("playerIndex", row.get("actor_index"))), 0)
    index = _safe_int(option.get("inPlayIndex"), -1)
    if area is None or not (0 <= player_index < len(players)) or not isinstance(players[player_index], dict):
        return None
    cards = _zone_cards(players[player_index], area)
    return cards[index] if 0 <= index < len(cards) else None


def _selected_options(row: dict[str, Any], action_key: str) -> list[dict[str, Any]]:
    options = row.get("legal_actions") if isinstance(row.get("legal_actions"), list) else []
    selected = row.get(action_key) if isinstance(row.get(action_key), list) else []
    output: list[dict[str, Any]] = []
    for raw_index in selected:
        index = _safe_int(raw_index, -1)
        resolved = 0 <= index < len(options) and isinstance(options[index], dict)
        option = options[index] if resolved else {}
        option_type = option.get("type")
        source = _card_from_area(row, option)
        target = _target_from_option(row, option)
        output.append(
            {
                "resolved": resolved,
                "raw_selection": raw_index,
                "option_index": index,
                "option_type": option_type,
                "action_type": ACTION_TYPE_NAMES.get(option_type, "unresolved_selection"),
                "card_id": option.get("cardId") if option.get("cardId") is not None else (source or {}).get("id"),
                "attack_id": option.get("attackId"),
                "area": option.get("area"),
                "area_index": option.get("index"),
                "player_index": option.get("playerIndex"),
                "in_play_area": option.get("inPlayArea"),
                "in_play_index": option.get("inPlayIndex"),
                "source_card": _card_summary(source),
                "target_card": _card_summary(target),
            }
        )
    return output


def _turn_key(row: dict[str, Any]) -> tuple[Any, int, Any]:
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    return (row.get("replay_id") or row.get("episode_id"), _safe_int(row.get("actor_index"), 0), current.get("turn"))


def _is_startup_deck_payload(row: dict[str, Any]) -> bool:
    chosen_action = row.get("chosen_action")
    if not isinstance(chosen_action, list) or len(chosen_action) != 60:
        return False
    if not all(isinstance(value, int) for value in chosen_action):
        return False
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    return _safe_int(current.get("turn"), 0) == 0 or _safe_int(row.get("step_index"), 0) <= 3


def _posture_tags(rows: list[dict[str, Any]], start_snapshot: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    matchup = str(rows[0].get("matchup_tag", "unknown"))
    pipeline = set(str(label) for row in rows for label in row.get("pipeline_labels", []))
    flaws = set(str(tag) for row in rows for tag in row.get("flaw_tags", []))
    action_types = {
        detail["action_type"]
        for row in rows
        for detail in _selected_options(row, "chosen_action")
        if isinstance(detail.get("action_type"), str)
    }

    if matchup in {"lucario", "dragapult_spread", "alakazam", "mega_starmie"}:
        tags.append("gate_pressure")
    if "setup" in pipeline or "bench_develop" in pipeline or "missed_setup" in flaws:
        tags.append("setup")
    actor = start_snapshot.get("actor") if isinstance(start_snapshot.get("actor"), dict) else {}
    opponent = start_snapshot.get("opponent") if isinstance(start_snapshot.get("opponent"), dict) else {}
    if int(actor.get("bench_energy_total") or 0) == 0:
        tags.append("next_attacker_gap")
    actor_prizes = actor.get("prize_count")
    opponent_prizes = opponent.get("prize_count")
    if isinstance(actor_prizes, int) and isinstance(opponent_prizes, int):
        if actor_prizes < opponent_prizes:
            tags.append("ahead")
        elif actor_prizes > opponent_prizes:
            tags.append("behind")
    deck_count = actor.get("deck_count")
    if isinstance(deck_count, int) and deck_count <= 12:
        tags.append("low_deck")
    if "attack_prize_race" in pipeline or "attack" in action_types:
        tags.append("prize_race")
    if flaws:
        tags.append("correction_pressure")
    if any(row.get("outcome") == "loss" for row in rows):
        tags.append("failed_game_context")
    return _unique_ordered(tags)


def _strategy_labels(rows: list[dict[str, Any]], action_counts: Counter[str], quality: str) -> list[str]:
    labels: list[str] = []
    matchup = str(rows[0].get("matchup_tag", "unknown"))
    if matchup in MATCHUP_STRATEGY_LABELS:
        labels.append(MATCHUP_STRATEGY_LABELS[matchup])
    for row in rows:
        labels.extend(PIPELINE_STRATEGY_LABELS.get(str(label), str(label)) for label in row.get("pipeline_labels", []))
        labels.extend(FLAW_STRATEGY_LABELS.get(str(tag), str(tag)) for tag in row.get("flaw_tags", []))
    if action_counts.get("play") or action_counts.get("evolve") or action_counts.get("attach"):
        labels.append("board_development")
    if action_counts.get("attack"):
        labels.append("attack_sequence")
    if action_counts.get("retreat"):
        labels.append("mobility_or_trap_escape")
    if quality == "successful_strategy":
        labels.append("successful_strategy_to_imitate")
    elif quality == "loss_correction":
        labels.append("loss_correction_patch")
    elif quality == "successful_strategy_with_teacher_alternative":
        labels.append("successful_but_review_teacher_alternative")
    return _unique_ordered(labels)


def _chain_quality(rows: list[dict[str, Any]], teacher_disagreements: int, flaw_tags: list[str]) -> str:
    outcomes = {str(row.get("outcome", "draw")) for row in rows}
    if outcomes == {"win"} and not flaw_tags and teacher_disagreements == 0:
        return "successful_strategy"
    if outcomes == {"win"} and not flaw_tags:
        return "successful_strategy_with_teacher_alternative"
    if "loss" in outcomes and (flaw_tags or teacher_disagreements > 0):
        return "loss_correction"
    if "loss" in outcomes:
        return "loss_observation"
    return "mixed_or_forced"


def build_chain_rows(decision_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decision_rows = [row for row in decision_rows if not _is_startup_deck_payload(row)]
    ordered_rows = sorted(
        decision_rows,
        key=lambda row: (
            str(row.get("replay_id") or row.get("episode_id")),
            _safe_int(row.get("actor_index"), 0),
            _safe_int((row.get("observation") or {}).get("current", {}).get("turn"), -1)
            if isinstance(row.get("observation"), dict)
            else -1,
            _safe_int(row.get("step_index"), 0),
        ),
    )
    grouped: dict[tuple[Any, int, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in ordered_rows:
        grouped[_turn_key(row)].append(row)

    chains: list[dict[str, Any]] = []
    for (replay_key, actor_index, turn), rows in sorted(
        grouped.items(), key=lambda item: (str(item[0][0]), item[0][1], _safe_int(item[0][2], -1))
    ):
        rows = sorted(rows, key=lambda row: _safe_int(row.get("step_index"), 0))
        step_indices = [_safe_int(row.get("step_index"), 0) for row in rows]
        chosen_details = [detail for row in rows for detail in _selected_options(row, "chosen_action")]
        teacher_details = [detail for row in rows for detail in _selected_options(row, "teacher_action")]
        action_counts: Counter[str] = Counter(str(detail["action_type"]) for detail in chosen_details)
        teacher_counts: Counter[str] = Counter(str(detail["action_type"]) for detail in teacher_details)
        flaw_tags = _unique_ordered(tag for row in rows for tag in row.get("flaw_tags", []))
        pipeline_labels = _unique_ordered(label for row in rows for label in row.get("pipeline_labels", []))
        teacher_disagreements = sum(1 for row in rows if not bool(row.get("teacher_agrees")))
        quality = _chain_quality(rows, teacher_disagreements, flaw_tags)
        start_snapshot = _board_snapshot(rows[0])
        end_snapshot = _board_snapshot(rows[-1])
        selected_card_ids = _unique_ordered(
            str(detail["card_id"]) for detail in chosen_details if detail.get("card_id") is not None
        )
        selected_attack_ids = _unique_ordered(
            str(detail["attack_id"]) for detail in chosen_details if detail.get("attack_id") is not None
        )
        chain_id = f"{replay_key}:{actor_index}:{turn}:{step_indices[0]}-{step_indices[-1]}"
        chain = {
            "chain_id": chain_id,
            "data_source": rows[0].get("data_source"),
            "submission_id": rows[0].get("submission_id"),
            "episode_id": rows[0].get("episode_id"),
            "replay_id": rows[0].get("replay_id"),
            "agent_family": rows[0].get("agent_family"),
            "team_name": rows[0].get("team_name"),
            "actor_owner": rows[0].get("actor_owner"),
            "actor_index": actor_index,
            "opponent_index": rows[0].get("opponent_index"),
            "opponent_team_name": rows[0].get("opponent_team_name"),
            "actor_archetype": rows[0].get("actor_archetype"),
            "opponent_archetype": rows[0].get("opponent_archetype"),
            "matchup_tag": rows[0].get("matchup_tag"),
            "outcome": rows[0].get("outcome"),
            "winner_side": rows[0].get("winner_side"),
            "reward": rows[0].get("reward"),
            "leaderboard_score": rows[0].get("leaderboard_score"),
            "turn": turn,
            "turn_key": f"{replay_key}:{actor_index}:{turn}",
            "step_indices": step_indices,
            "chain_length": len(rows),
            "chosen_actions": [row.get("chosen_action", []) for row in rows],
            "teacher_actions": [row.get("teacher_action", []) for row in rows],
            "selected_options": chosen_details,
            "teacher_options": teacher_details,
            "action_type_counts": dict(action_counts),
            "teacher_action_type_counts": dict(teacher_counts),
            "selected_card_ids": [int(value) for value in selected_card_ids if value.isdigit()],
            "selected_attack_ids": [int(value) for value in selected_attack_ids if value.isdigit()],
            "pipeline_labels": pipeline_labels,
            "flaw_tags": flaw_tags,
            "teacher_disagreements": teacher_disagreements,
            "teacher_agreements": len(rows) - teacher_disagreements,
            "teacher_agreement_rate": (len(rows) - teacher_disagreements) / len(rows) if rows else 0.0,
            "sample_weight_sum": sum(float(row.get("sample_weight", 1.0) or 1.0) for row in rows),
            "chain_quality": quality,
            "posture_tags": _posture_tags(rows, start_snapshot),
            "strategy_labels": _strategy_labels(rows, action_counts, quality),
            "start_snapshot": start_snapshot,
            "end_snapshot": end_snapshot,
            "legal_scope": rows[0].get("legal_scope"),
        }
        chains.append(chain)
    return chains


def _counter_dict(values: Iterable[Any]) -> dict[str, int]:
    return dict(Counter(str(value) for value in values if value is not None))


def _top_counter(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in counter.most_common(limit)]


def build_chain_report(
    chains: list[dict[str, Any]],
    *,
    decision_rows: list[dict[str, Any]],
    command: str,
    decision_labels_path: Path,
    output_dir: Path,
    source_run_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality_counter = Counter(str(chain.get("chain_quality")) for chain in chains)
    usable_decisions = sum(int(chain.get("chain_length") or 0) for chain in chains)
    matchup_counter = Counter(str(chain.get("matchup_tag", "unknown")) for chain in chains)
    outcome_counter = Counter(str(chain.get("outcome", "draw")) for chain in chains)
    strategy_counter = Counter(
        str(label) for chain in chains for label in chain.get("strategy_labels", []) if label
    )
    flaw_counter = Counter(str(tag) for chain in chains for tag in chain.get("flaw_tags", []) if tag)
    action_counter = Counter()
    unresolved_selection_count = 0
    for chain in chains:
        action_counter.update(chain.get("action_type_counts", {}))
        unresolved_selection_count += int(chain.get("action_type_counts", {}).get("unresolved_selection", 0))

    return {
        "command": command,
        "decision_labels_path": str(decision_labels_path),
        "output_dir": str(output_dir),
        "total_decisions": len(decision_rows),
        "usable_decisions": usable_decisions,
        "filtered_startup_deck_rows": max(0, len(decision_rows) - usable_decisions),
        "total_chains": len(chains),
        "episode_count": len({row.get("episode_id") for row in decision_rows}),
        "matchup_counts": dict(matchup_counter),
        "outcome_counts": dict(outcome_counter),
        "chain_quality_counts": dict(quality_counter),
        "strategy_label_counts": dict(strategy_counter),
        "flaw_tag_counts": dict(flaw_counter),
        "action_type_counts": dict(action_counter),
        "unresolved_selection_count": unresolved_selection_count,
        "top_loss_correction_flaws": _top_counter(flaw_counter),
        "top_strategy_labels": _top_counter(strategy_counter),
        "chains_by_episode": _counter_dict(chain.get("episode_id") for chain in chains),
        "chains_by_matchup_quality": {
            f"{matchup}:{quality}": count
            for (matchup, quality), count in Counter(
                (str(item.get("matchup_tag")), str(item.get("chain_quality"))) for item in chains
            ).items()
        },
        "research_role": "replay_chain_library_for_heuristic_patch_and_engine_audit",
        "promotion_warning": (
            "Use as heuristic patch and engine-audit evidence only. This artifact is not a learned-policy "
            "dataset and is not a champion-promotion gate by itself."
        ),
        "source_run_report_summary": _source_summary(source_run_report or {}),
        "paths": {
            "chain_library_jsonl": str(output_dir / "chain_library.jsonl"),
            "chain_library_report_json": str(output_dir / "chain_library_report.json"),
            "chain_library_report_md": str(output_dir / "chain_library_report.md"),
        },
        "kaggle_submission_made": False,
    }


def _source_summary(source_run_report: dict[str, Any]) -> dict[str, Any]:
    dataset_report = source_run_report.get("dataset_report") if isinstance(source_run_report.get("dataset_report"), dict) else {}
    meta = dataset_report.get("meta_snapshot") if isinstance(dataset_report.get("meta_snapshot"), dict) else {}
    source = meta.get("source") if isinstance(meta.get("source"), dict) else {}
    return {
        "command": source_run_report.get("command"),
        "data_manifest": source_run_report.get("data_manifest"),
        "artifact_manifest": source_run_report.get("artifact_manifest"),
        "source_decision_rows": dataset_report.get("decision_rows"),
        "source_actor_records": dataset_report.get("actor_records"),
        "meta_date": meta.get("date"),
        "meta_latest_date": meta.get("latestDate"),
        "meta_total_decks": meta.get("totalDecks"),
        "meta_dataset_url": source.get("datasetUrl"),
        "kaggle_submission_made": bool(source_run_report.get("kaggle_submission_made", False)),
    }


def _markdown_report(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Kaggle Chain Library",
            "",
            f"- Command: `{report['command']}`",
            f"- Decision rows: {report['total_decisions']}",
            f"- Usable gameplay decisions: {report['usable_decisions']}",
            f"- Filtered startup deck rows: {report['filtered_startup_deck_rows']}",
            f"- Chains: {report['total_chains']}",
            f"- Episodes: {report['episode_count']}",
            f"- Research role: `{report['research_role']}`",
            f"- Unresolved selected values: {report['unresolved_selection_count']}",
            f"- Chain qualities: `{json.dumps(report['chain_quality_counts'], sort_keys=True)}`",
            f"- Matchups: `{json.dumps(report['matchup_counts'], sort_keys=True)}`",
            "",
            report["promotion_warning"],
            "",
            "Kaggle submission made: no",
            "",
        ]
    )


def write_chain_library(
    *,
    decision_labels_path: Path,
    output_dir: Path,
    command: str,
    source_run_report_path: Path | None = None,
) -> dict[str, Any]:
    decision_rows = _read_jsonl(decision_labels_path)
    chains = build_chain_rows(decision_rows)
    source_run_report: dict[str, Any] | None = None
    if source_run_report_path is not None and source_run_report_path.exists():
        source_run_report = json.loads(source_run_report_path.read_text(encoding="utf-8"))

    report = build_chain_report(
        chains,
        decision_rows=decision_rows,
        command=command,
        decision_labels_path=decision_labels_path,
        output_dir=output_dir,
        source_run_report=source_run_report,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    chain_path = output_dir / "chain_library.jsonl"
    json_report_path = output_dir / "chain_library_report.json"
    markdown_report_path = output_dir / "chain_library_report.md"
    _write_jsonl(chain_path, chains)
    json_report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_report_path.write_text(_markdown_report(report), encoding="utf-8")
    return report
