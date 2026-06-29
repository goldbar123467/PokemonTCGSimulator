from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Sequence

from ptcg.options import choose_legal_action
from ptcg.replays import ReplayDecision
from ptcg.replays import iter_replay_decisions


OPTION_PLAY = 7
OPTION_ATTACH = 8
OPTION_EVOLVE = 9
OPTION_ATTACK = 13
OPTION_END = 14

AREA_HAND = 2
AREA_ACTIVE = 4
AREA_BENCH = 5

ATTACK_PSYCHIC = 1072
ATTACK_VERDANT_STORM = 323
ATTACK_CORNER = 1267
ATTACK_ICY_WIND = 1488
ATTACK_ABSOLUTE_SNOW = 1240
ATTACK_PHANTOM_DIVE = 153
ATTACK_HORRIFYING_REVENGE = 1266

SETUP_ATTACKER_IDS = {
    65,
    66,
    112,
    119,
    120,
    121,
    235,
    305,
    344,
    345,
    666,
    673,
    674,
    675,
    676,
    677,
    678,
    741,
    742,
    743,
    860,
    861,
    878,
    879,
    941,
    942,
    943,
    1030,
    1031,
}

LABEL_WEIGHTS = {
    "setup_next_attacker": 5.0,
    "punish_overpowered_active": 6.0,
    "trap_active": 5.0,
    "sleep_tempo": 5.0,
    "spread_pressure": 4.0,
    "tempo_reversal": 3.5,
    "behind_on_prizes_recovery": 2.5,
    "direct_aggression_with_backup": 2.0,
}

PENALTY_WEIGHTS = {
    "end_with_constructive_setup": -7.0,
    "dead_or_random_move": -3.0,
    "attack_without_backup": -2.5,
    "active_overattach": -2.0,
}

LABEL_ORDER = (
    "setup_next_attacker",
    "punish_overpowered_active",
    "trap_active",
    "sleep_tempo",
    "spread_pressure",
    "tempo_reversal",
    "behind_on_prizes_recovery",
    "direct_aggression_with_backup",
)

PENALTY_ORDER = (
    "end_with_constructive_setup",
    "dead_or_random_move",
    "attack_without_backup",
    "active_overattach",
)

DEFAULT_SEED_GAME_LABELS = {
    "81140971": "lucario_direct_aggression_gate",
    "81307708": "anti_lucario_hand_damage",
    "81343903": "anti_lucario_control_trap",
    "81489022": "anti_dragapult_alakazam_gate",
    "81327484": "sleep_tempo_comeback_control",
}


@dataclass(frozen=True)
class TeacherOptionScore:
    option_index: int
    score: float
    labels: tuple[str, ...]
    penalties: tuple[str, ...]


@dataclass(frozen=True)
class TeacherPatchSet:
    decisions: list[ReplayDecision]
    sample_count: int
    source_decision_count: int
    rewritten_count: int
    label_counts: dict[str, int]
    decision_window_counts: dict[str, int]


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _cards(player: dict, zone: str) -> list[dict]:
    value = player.get(zone)
    return [card for card in value if isinstance(card, dict)] if isinstance(value, list) else []


def _active(player: dict) -> dict | None:
    cards = _cards(player, "active")
    return cards[0] if cards else None


def _energy_count(card: dict | None) -> int:
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


def _players(obs: dict) -> tuple[int, dict, dict, list[dict]]:
    current = obs.get("current") if isinstance(obs.get("current"), dict) else {}
    raw_players = current.get("players") if isinstance(current.get("players"), list) else []
    players = [player if isinstance(player, dict) else {} for player in raw_players[:2]]
    while len(players) < 2:
        players.append({})
    your = _int(current.get("yourIndex"), 0)
    if your not in {0, 1}:
        your = 0
    return your, players[your], players[1 - your], players


def _zone_name(area: object) -> str | None:
    return {
        2: "hand",
        3: "discard",
        4: "active",
        5: "bench",
        7: "stadium",
        12: "looking",
        "hand": "hand",
        "discard": "discard",
        "active": "active",
        "bench": "bench",
        "stadium": "stadium",
        "looking": "looking",
    }.get(area)


def _card_from_area(obs: dict, option: dict, players: list[dict], your: int) -> dict | None:
    if isinstance(option.get("cardId"), int):
        return {"id": int(option["cardId"])}
    zone = _zone_name(option.get("area"))
    if zone is None:
        return None
    player_index = _int(option.get("playerIndex", your), your)
    index = _int(option.get("index"), -1)
    if not (0 <= player_index < len(players)):
        return None
    if zone in {"deck", "prize"}:
        return None
    cards = _cards(players[player_index], zone)
    if not (0 <= index < len(cards)):
        return None
    return cards[index]


def _target_from_option(option: dict, players: list[dict], your: int) -> dict | None:
    player_index = _int(option.get("playerIndex", your), your)
    zone = _zone_name(option.get("inPlayArea"))
    index = _int(option.get("inPlayIndex"), -1)
    if zone is None or not (0 <= player_index < len(players)):
        return None
    cards = _cards(players[player_index], zone)
    if not (0 <= index < len(cards)):
        return None
    return cards[index]


def _card_id(card: dict | None) -> int | None:
    if not isinstance(card, dict):
        return None
    value = card.get("id")
    return int(value) if isinstance(value, int) else None


def _bench_powered(player: dict) -> int:
    return sum(1 for card in _cards(player, "bench") if _energy_count(card) > 0)


def _bench_count(player: dict) -> int:
    return len(_cards(player, "bench"))


def _board_energy(player: dict) -> int:
    return sum(_energy_count(card) for card in _cards(player, "active") + _cards(player, "bench"))


def _active_is_dangerous(player: dict) -> bool:
    active = _active(player)
    if active is None:
        return False
    hp = _int(active.get("hp"), _int(active.get("maxHp")))
    max_hp = _int(active.get("maxHp"), hp)
    return max_hp > 0 and hp <= max(90, int(max_hp * 0.45))


def _prizes_taken(player: dict) -> int:
    prize = player.get("prize")
    return max(0, 6 - len(prize)) if isinstance(prize, list) else 0


def _ordered(values: Iterable[str], order: Sequence[str]) -> tuple[str, ...]:
    found = set(values)
    return tuple(label for label in order if label in found)


def _under_setup_pressure(us: dict, them: dict) -> bool:
    if _bench_powered(us) == 0:
        return True
    if _active_is_dangerous(us) and _bench_powered(us) < 2:
        return True
    if _prizes_taken(us) < _prizes_taken(them):
        return True
    return False


def _is_setup_attacker(card_id: int | None) -> bool:
    return card_id in SETUP_ATTACKER_IDS


def _is_constructive_setup_option(obs: dict, option: dict) -> bool:
    your, us, them, players = _players(obs)
    source = _card_from_area(obs, option, players, your)
    source_id = _card_id(source)
    target = _target_from_option(option, players, your)
    target_id = _card_id(target)
    option_type = option.get("type")

    if option_type == OPTION_PLAY and _is_setup_attacker(source_id):
        return True
    if option_type == OPTION_EVOLVE:
        return True
    if option_type == OPTION_ATTACH and option.get("inPlayArea") == AREA_BENCH and _is_setup_attacker(target_id):
        return True
    if option_type == OPTION_ATTACH and _under_setup_pressure(us, them) and _is_setup_attacker(target_id):
        return True
    return False


def _labels_for_option(obs: dict, option: dict) -> set[str]:
    your, us, them, players = _players(obs)
    option_type = option.get("type")
    attack_id = _int(option.get("attackId"), -1)
    labels: set[str] = set()

    if _is_constructive_setup_option(obs, option):
        labels.add("setup_next_attacker")

    if option_type == OPTION_ATTACK and attack_id in {ATTACK_PSYCHIC, ATTACK_VERDANT_STORM}:
        them_active = _active(them)
        if _energy_count(them_active) >= 2 or _board_energy(them) >= 3:
            labels.add("punish_overpowered_active")

    if option_type == OPTION_ATTACK and attack_id == ATTACK_CORNER:
        labels.add("trap_active")

    if option_type == OPTION_ATTACK and attack_id in {ATTACK_ICY_WIND, ATTACK_ABSOLUTE_SNOW}:
        labels.add("sleep_tempo")

    if option_type == OPTION_ATTACK and attack_id == ATTACK_PHANTOM_DIVE:
        labels.add("spread_pressure")

    if option_type == OPTION_ATTACK and attack_id == ATTACK_HORRIFYING_REVENGE:
        labels.add("tempo_reversal")

    if option_type == OPTION_ATTACK and _bench_powered(us) > 0 and _bench_count(us) >= 2:
        labels.add("direct_aggression_with_backup")

    recovery_labels = {"setup_next_attacker", "trap_active", "sleep_tempo", "tempo_reversal"}
    if _prizes_taken(us) < _prizes_taken(them) and labels.intersection(recovery_labels):
        labels.add("behind_on_prizes_recovery")

    return labels


def _penalties_for_option(obs: dict, option: dict) -> set[str]:
    _your, us, them, players = _players(obs)
    select = obs.get("select") if isinstance(obs.get("select"), dict) else {}
    options = [item for item in select.get("option") or [] if isinstance(item, dict)]
    option_type = option.get("type")
    penalties: set[str] = set()

    if option_type == OPTION_END and any(_is_constructive_setup_option(obs, item) for item in options):
        penalties.add("end_with_constructive_setup")

    if option_type == OPTION_END and any(item.get("type") != OPTION_END for item in options):
        penalties.add("dead_or_random_move")

    if option_type == OPTION_ATTACK and _under_setup_pressure(us, them) and _bench_powered(us) == 0:
        labels = _labels_for_option(obs, option)
        if not labels.intersection({"punish_overpowered_active", "trap_active", "sleep_tempo", "spread_pressure"}):
            penalties.add("attack_without_backup")

    if option_type == OPTION_ATTACH and option.get("inPlayArea") == AREA_ACTIVE:
        target = _target_from_option(option, players, _int((obs.get("current") or {}).get("yourIndex"), 0))
        if _energy_count(target) > 0 and _bench_powered(us) == 0:
            penalties.add("active_overattach")

    return penalties


def score_option(obs: dict, option: dict, *, option_index: int = 0) -> TeacherOptionScore:
    labels = _ordered(_labels_for_option(obs, option), LABEL_ORDER)
    penalties = _ordered(_penalties_for_option(obs, option), PENALTY_ORDER)
    score = sum(LABEL_WEIGHTS[label] for label in labels) + sum(PENALTY_WEIGHTS[penalty] for penalty in penalties)
    return TeacherOptionScore(option_index=option_index, score=score, labels=labels, penalties=penalties)


def score_options(obs: dict) -> list[TeacherOptionScore]:
    select = obs.get("select") if isinstance(obs.get("select"), dict) else {}
    options = [option for option in select.get("option") or [] if isinstance(option, dict)]
    return [score_option(obs, option, option_index=index) for index, option in enumerate(options)]


def choose_teacher_action(obs: dict) -> list[int]:
    select = obs.get("select") if isinstance(obs.get("select"), dict) else {}
    options = [option for option in select.get("option") or [] if isinstance(option, dict)]
    if not options:
        return []
    scores = score_options(obs)
    min_count = _int(select.get("minCount", select.get("min_count")), 1)
    max_count = _int(select.get("maxCount", select.get("max_count")), 1)
    if min_count == 0 and max(score.score for score in scores) < 0:
        return []
    return choose_legal_action(options, min_count=min_count, max_count=max_count, scores=[score.score for score in scores])


def label_selected_decision(
    replay_id: str,
    *,
    step_index: int,
    agent_index: int,
    observation: dict,
    action_indices: Sequence[int],
    game_label: str = "",
) -> dict:
    scores = score_options(observation)
    score_by_index = {score.option_index: score for score in scores}
    selected = [score_by_index[index] for index in action_indices if index in score_by_index]
    selected_labels = _ordered((label for score in selected for label in score.labels), LABEL_ORDER)
    selected_penalties = _ordered((penalty for score in selected for penalty in score.penalties), PENALTY_ORDER)
    teacher_action = choose_teacher_action(observation)
    teacher_selected = [score_by_index[index] for index in teacher_action if index in score_by_index]
    teacher_labels = _ordered((label for score in teacher_selected for label in score.labels), LABEL_ORDER)
    teacher_penalties = _ordered((penalty for score in teacher_selected for penalty in score.penalties), PENALTY_ORDER)
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    decision_window = decision_window_from_labels(selected_labels, selected_penalties)
    teacher_decision_window = decision_window_from_labels(teacher_labels, teacher_penalties)
    return {
        "replay_id": replay_id,
        "step_index": int(step_index),
        "agent_index": int(agent_index),
        "turn": _int(current.get("turn")),
        "game_label": game_label,
        "decision_window": decision_window,
        "teacher_decision_window": teacher_decision_window,
        "action_indices": [int(index) for index in action_indices],
        "teacher_action": teacher_action,
        "selected_labels": list(selected_labels),
        "selected_penalties": list(selected_penalties),
        "teacher_labels": list(teacher_labels),
        "teacher_penalties": list(teacher_penalties),
        "selected_score": sum(score.score for score in selected),
        "teacher_score": sum(score.score for score in teacher_selected),
        "option_count": len(scores),
        "teacher_agrees": list(action_indices) == teacher_action,
    }


def decision_window_from_labels(labels: Sequence[str], penalties: Sequence[str] = ()) -> str:
    label_set = set(labels)
    penalty_set = set(penalties)
    if label_set.intersection({"trap_active", "sleep_tempo"}):
        return "trap_status_turn"
    if "tempo_reversal" in label_set:
        return "ko_response"
    if "setup_next_attacker" in label_set:
        return "setup_turn"
    if label_set.intersection({"punish_overpowered_active", "spread_pressure", "direct_aggression_with_backup"}):
        return "attack_choice"
    if "behind_on_prizes_recovery" in label_set:
        return "behind_on_prizes_recovery"
    if penalty_set:
        return "dead_random_move"
    return "unlabeled"


def write_labeled_decision_windows(
    replay_paths: Sequence[Path],
    output_path: Path,
    *,
    game_labels: dict[str, str] | None = None,
) -> dict:
    labels_by_replay = dict(DEFAULT_SEED_GAME_LABELS)
    if game_labels:
        labels_by_replay.update({str(key): str(value) for key, value in game_labels.items()})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    replay_count = 0
    decision_count = 0
    written_rows = 0
    label_counts: dict[str, int] = {}
    window_counts: dict[str, int] = {}

    with output_path.open("w", encoding="utf-8") as handle:
        for replay_path in replay_paths:
            replay_count += 1
            for decision in iter_replay_decisions(Path(replay_path), include_optional_pass=True):
                decision_count += 1
                game_label = labels_by_replay.get(decision.replay_id, labels_by_replay.get(Path(replay_path).stem, ""))
                row = label_selected_decision(
                    decision.replay_id,
                    step_index=decision.step_index,
                    agent_index=decision.agent_index,
                    observation=decision.observation,
                    action_indices=decision.action_indices,
                    game_label=game_label,
                )
                if not row["selected_labels"] and not row["selected_penalties"]:
                    continue
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                written_rows += 1
                window_counts[row["decision_window"]] = window_counts.get(row["decision_window"], 0) + 1
                for label in row["selected_labels"]:
                    label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "replay_count": replay_count,
        "decision_count": decision_count,
        "written_rows": written_rows,
        "output_path": str(output_path),
        "label_counts": dict(sorted(label_counts.items())),
        "decision_window_counts": dict(sorted(window_counts.items())),
    }


def teacher_patch_decisions(
    replay_paths: Sequence[Path],
    *,
    game_labels: dict[str, str] | None = None,
    include_penalty_rewrites: bool = True,
) -> TeacherPatchSet:
    labels_by_replay = dict(DEFAULT_SEED_GAME_LABELS)
    if game_labels:
        labels_by_replay.update({str(key): str(value) for key, value in game_labels.items()})

    decisions: list[ReplayDecision] = []
    source_decision_count = 0
    rewritten_count = 0
    label_counts: dict[str, int] = {}
    window_counts: dict[str, int] = {}

    for replay_path in replay_paths:
        for decision in iter_replay_decisions(Path(replay_path), include_optional_pass=True):
            source_decision_count += 1
            game_label = labels_by_replay.get(decision.replay_id, labels_by_replay.get(Path(replay_path).stem, ""))
            row = label_selected_decision(
                decision.replay_id,
                step_index=decision.step_index,
                agent_index=decision.agent_index,
                observation=decision.observation,
                action_indices=decision.action_indices,
                game_label=game_label,
            )
            teacher_action = tuple(int(index) for index in row["teacher_action"])
            if not teacher_action:
                continue
            if not row["teacher_labels"] and not (include_penalty_rewrites and row["selected_penalties"]):
                continue
            if tuple(decision.action_indices) != teacher_action:
                rewritten_count += 1
            decisions.append(
                ReplayDecision(
                    replay_id=decision.replay_id,
                    step_index=decision.step_index,
                    agent_index=decision.agent_index,
                    observation=decision.observation,
                    action_indices=teacher_action,
                    option_count=decision.option_count,
                )
            )
            window_counts[row["teacher_decision_window"]] = window_counts.get(row["teacher_decision_window"], 0) + 1
            for label in row["teacher_labels"]:
                label_counts[label] = label_counts.get(label, 0) + 1

    return TeacherPatchSet(
        decisions=decisions,
        sample_count=len(decisions),
        source_decision_count=source_decision_count,
        rewritten_count=rewritten_count,
        label_counts=dict(sorted(label_counts.items())),
        decision_window_counts=dict(sorted(window_counts.items())),
    )
