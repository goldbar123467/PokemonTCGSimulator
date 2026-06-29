from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


AGENT_TEMPLATE = r'''from __future__ import annotations

import os
import random

DECK = __DECK__
STRATEGY = "__STRATEGY__"
KEY_CARDS = set(__KEY_CARDS__)
SETUP_CARDS = set(__SETUP_CARDS__)
ATTACKERS = set(__ATTACKERS__)
EVOLVERS = set(__EVOLVERS__)
DISRUPTION = set(__DISRUPTION__)
ENERGY_IDS = set(__ENERGY_IDS__)
GATE_TARGETS = set(__GATE_TARGETS__)
LUCARIO_CHAIN_IDS = {673, 674, 675, 676, 677, 678}
DURALUDON_ID = 169
ARCHALUDON_EX_ID = 190
RELICANTH_ID = 57
CINDERACE_ID = 666
METAL_ENERGY_ID = 8
HERO_CAPE_ID = 1159
HAMMER_IN_ATTACK_ID = 223
RAGING_HAMMER_ATTACK_ID = 224
METAL_DEFENDER_ATTACK_ID = 253
TURBO_FLARE_ATTACK_ID = 965
ARCHALUDON_LINE_IDS = {DURALUDON_ID, ARCHALUDON_EX_ID}
DRAGAPULT_BASIC_ID = 119
DRAGAPULT_STAGE1_ID = 120
DRAGAPULT_EX_ID = 121
DRAGAPULT_LINE_IDS = {DRAGAPULT_BASIC_ID, DRAGAPULT_STAGE1_ID, DRAGAPULT_EX_ID}
DRAGAPULT_REBUILD_TARGET_IDS = {
    119,  # Dreepy
    120,  # Drakloak
    235,  # Budew
    673,  # Makuhita
    675,  # Lunatone
    676,  # Solrock
    677,  # Riolu
    741,  # Abra
    742,  # Kadabra
}
JET_HEADBUTT_ATTACK_ID = 153
PHANTOM_DIVE_ATTACK_ID = 154
RNG_NOISE = __RNG_NOISE__
WEIGHTS = __WEIGHTS__


def _w(name: str, default: float) -> float:
    return float(WEIGHTS.get(name, default))


def _agent_impl(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        return list(DECK)
    select = obs_dict.get("select") or {}
    options = select.get("option") or []
    min_count = int(select.get("minCount") or 0)
    max_count = int(select.get("maxCount") or min_count or 1)
    if not options:
        return []
    posture = _posture(obs_dict)
    rng = random.Random(_seed(obs_dict, len(options)))
    scored = []
    for index, option in enumerate(options):
        scored.append((_score_option(obs_dict, option, posture) + rng.uniform(0, RNG_NOISE), index))
    scored.sort(reverse=True)
    count = max(min_count, min(max_count, len(scored)))
    return [index for _, index in scored[:count]]


def _seed(obs: dict, option_count: int) -> int:
    current = obs.get("current") or {}
    return (
        int(current.get("turn") or 0) * 1009
        + int(current.get("turnActionCount") or 0) * 917
        + int(current.get("yourIndex") or 0) * 271
        + option_count * 37
    )


def _players(obs: dict):
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    your = int(current.get("yourIndex") or 0)
    if len(players) < 2:
        players = [{}, {}]
    return current, your, players[your] or {}, players[1 - your] or {}


def _zone_cards(player: dict, zone: str) -> list[dict]:
    value = player.get(zone)
    return [card for card in value if isinstance(card, dict)] if isinstance(value, list) else []


def _board(player: dict) -> list[dict]:
    return _zone_cards(player, "active") + _zone_cards(player, "bench")


def _active(player: dict) -> dict | None:
    cards = _zone_cards(player, "active")
    return cards[0] if cards else None


def _bench(player: dict) -> list[dict]:
    return _zone_cards(player, "bench")


def _energy_value(value) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _single_card_energy_count(card: dict | None) -> int:
    if not isinstance(card, dict):
        return 0
    energy_cards = _energy_value(card.get("energyCards"))
    if energy_cards:
        return energy_cards
    return _energy_value(card.get("energies"))


def _energy_count(cards: list[dict]) -> int:
    return sum(_single_card_energy_count(card) for card in cards)


def _card_energy_count(card: dict | None) -> int:
    return _single_card_energy_count(card)


def _card_hp(card: dict | None) -> int:
    if not isinstance(card, dict):
        return 0
    return int(card.get("hp") or card.get("remainingHp") or card.get("maxHp") or 0)


def _has_board_id(player: dict, card_id: int) -> bool:
    return any(card.get("id") == card_id for card in _board(player))


def _is_archaludon_candidate() -> bool:
    return (
        ARCHALUDON_EX_ID in ATTACKERS
        or DURALUDON_ID in ATTACKERS
        or "archaludon" in STRATEGY.lower()
    )


def _count_board_id(player: dict, card_id: int) -> int:
    return sum(1 for card in _board(player) if card.get("id") == card_id)


def _count_board_ids(player: dict, card_ids: set[int]) -> int:
    return sum(1 for card in _board(player) if card.get("id") in card_ids)


def _card_max_hp(card: dict | None) -> int:
    if not isinstance(card, dict):
        return 0
    return int(card.get("maxHp") or card.get("maximumHp") or card.get("hp") or card.get("remainingHp") or 0)


def _card_is_damaged(card: dict | None) -> bool:
    hp = _card_hp(card)
    max_hp = _card_max_hp(card)
    return bool(hp and max_hp and hp < max_hp)


def _archaludon_ready_attackers(player: dict) -> int:
    ready = 0
    for card in _board(player):
        card_id = card.get("id")
        energy = _card_energy_count(card)
        if card_id in (ARCHALUDON_EX_ID, DURALUDON_ID) and energy >= 3:
            ready += 1
        elif card_id == CINDERACE_ID and energy >= 1:
            ready += 1
    return ready


def _archaludon_has_ready_line(player: dict) -> bool:
    return any(
        card.get("id") in ARCHALUDON_LINE_IDS and _card_energy_count(card) >= 3
        for card in _board(player)
    )


def _archaludon_needs_duraludon(player: dict) -> bool:
    return _count_board_ids(player, ARCHALUDON_LINE_IDS) < 2 or not _has_board_id(player, DURALUDON_ID)


def _archaludon_needs_archaludon(player: dict) -> bool:
    return _has_board_id(player, DURALUDON_ID) and not _has_board_id(player, ARCHALUDON_EX_ID)


def _dragapult_chain_need_card_id(player: dict) -> int | None:
    if _has_board_id(player, DRAGAPULT_STAGE1_ID):
        return DRAGAPULT_EX_ID
    if _has_board_id(player, DRAGAPULT_BASIC_ID):
        return DRAGAPULT_STAGE1_ID
    if not _has_board_id(player, DRAGAPULT_EX_ID):
        return DRAGAPULT_BASIC_ID
    return None


def _is_own_dragapult_line_ready(player: dict) -> bool:
    active = _active(player)
    if not isinstance(active, dict) or active.get("id") != DRAGAPULT_EX_ID:
        return False
    return _card_energy_count(active) >= 2


def _opponent_has_counter_targets(player: dict) -> bool:
    return bool(_bench(player))


def _target_from_option(obs: dict, option: dict) -> dict | None:
    current, your, us, them = _players(obs)
    area = option.get("inPlayArea")
    index = option.get("inPlayIndex")
    if area is None:
        area = option.get("area")
        index = option.get("index")
    player_index = option.get("playerIndex", your)
    zones = {
        4: "active",
        5: "bench",
    }
    zone = zones.get(area)
    if zone is None:
        return None
    player = us if int(player_index or your) == your else them
    cards = _zone_cards(player, zone)
    if isinstance(index, int) and 0 <= index < len(cards):
        return cards[index]
    return None


def _target_score(obs: dict, option: dict, posture: set[str]) -> float:
    current, your, us, them = _players(obs)
    target = _target_from_option(obs, option)
    if not isinstance(target, dict):
        return 0.0
    target_id = target.get("id")
    target_owner = int(option.get("playerIndex", your) or your)
    score = 0.0
    if target_owner == your:
        if target_id in ATTACKERS:
            score += _w("own_attacker_target", 95)
        if target_id in EVOLVERS:
            score += _w("own_evolver_target", 65)
        if option.get("inPlayArea") == 5 or option.get("area") == 5:
            score += _w("own_bench_target", 55)
        if _card_energy_count(target) == 0 and ("setup" in posture or "behind" in posture):
            score += _w("unpowered_next_attacker", 70)
    else:
        if target_id in GATE_TARGETS:
            score += _w("enemy_gate_target", 210)
        if target_id in LUCARIO_CHAIN_IDS and "lucario_pressure" in posture:
            score += _w("lucario_chain_target", 165)
            if option.get("area") == 5:
                score += _w("lucario_bench_chain_target", 145)
            if target_id in (676, 677) and _card_energy_count(target) == 0:
                score += _w("lucario_evolving_basic_target", 120)
        if _card_energy_count(target) > 0:
            score += _w("enemy_powered_target", 160)
            if target_id in LUCARIO_CHAIN_IDS and "lucario_pressure" in posture:
                score += _w("lucario_powered_chain_target", 190)
            if "single_powered_threat" in posture:
                score += _w("single_powered_target", 180)
        if option.get("area") == 5:
            score += _w("enemy_bench_target", 90)
        if "behind" in posture or "gate_pressure" in posture:
            score += _w("enemy_pressure_target", 75)
    return score


def _dragapult_shape_score(obs: dict, option: dict, posture: set[str], card_id: int | None) -> float:
    current, your, us, them = _players(obs)
    opt_type = option.get("type")
    context = ((obs.get("select") or {}).get("context"))
    target = _target_from_option(obs, option)
    target_owner = int(option.get("playerIndex", your) or your)
    score = 0.0

    needed_chain_piece = _dragapult_chain_need_card_id(us)
    if isinstance(card_id, int) and card_id in DRAGAPULT_LINE_IDS and needed_chain_piece is not None:
        if card_id == needed_chain_piece:
            score += _w("dragapult_chain_needed_piece", 210)
        else:
            score -= _w("dragapult_wrong_chain_piece_penalty", 80)

    if opt_type == 9 and isinstance(target, dict) and isinstance(card_id, int):
        target_id = target.get("id")
        if target_owner == your and target_id == DRAGAPULT_BASIC_ID and card_id == DRAGAPULT_STAGE1_ID:
            score += _w("dragapult_evolve_bridge", 220)
        elif target_owner == your and target_id == DRAGAPULT_STAGE1_ID and card_id == DRAGAPULT_EX_ID:
            score += _w("dragapult_evolve_finish", 260)
        elif target_owner == your and target_id == DRAGAPULT_BASIC_ID and card_id == DRAGAPULT_EX_ID:
            score -= _w("dragapult_wrong_chain_piece_penalty", 80)

    if opt_type == 13:
        attack_id = option.get("attackId")
        if attack_id == PHANTOM_DIVE_ATTACK_ID and _is_own_dragapult_line_ready(us) and _opponent_has_counter_targets(them):
            score += _w("dragapult_phantom_dive_attack", 190)
        elif attack_id == JET_HEADBUTT_ATTACK_ID and _is_own_dragapult_line_ready(us) and _opponent_has_counter_targets(them):
            score -= _w("dragapult_jet_headbutt_when_phantom_live_penalty", 70)

    if opt_type == 3 and context in (13, 14, 39) and isinstance(target, dict) and target_owner != your:
        target_area = option.get("area")
        if target_area is None:
            target_area = option.get("inPlayArea")
        target_id = target.get("id")
        if target_area == 5:
            hp = _card_hp(target)
            if 0 < hp <= 60:
                score += _w("dragapult_counter_finish_target", 260)
            if target_id in DRAGAPULT_REBUILD_TARGET_IDS:
                score += _w("dragapult_counter_bench_rebuild_target", 150)
            if _card_energy_count(target) > 0:
                score += _w("dragapult_counter_powered_bench_target", 100)
        else:
            score -= _w("dragapult_counter_active_penalty", 80)

    if (
        opt_type in (13, 14)
        and DRAGAPULT_EX_ID not in {card.get("id") for card in _board(us)}
        and _dragapult_chain_need_card_id(us) is not None
    ):
        score -= _w("dragapult_attack_before_chain_penalty", 110)
    return score


def _archaludon_shape_score(obs: dict, option: dict, posture: set[str], card_id: int | None) -> float:
    if not _is_archaludon_candidate():
        return 0.0
    current, your, us, them = _players(obs)
    opt_type = option.get("type")
    context = ((obs.get("select") or {}).get("context"))
    target = _target_from_option(obs, option)
    target_owner = int(option.get("playerIndex", your) or your)
    active = _active(us)
    active_id = active.get("id") if isinstance(active, dict) else None
    active_energy = _card_energy_count(active)
    line_count = _count_board_ids(us, ARCHALUDON_LINE_IDS)
    ready_line_count = _archaludon_ready_attackers(us)
    needs_duraludon = _archaludon_needs_duraludon(us)
    needs_archaludon = _archaludon_needs_archaludon(us)
    score = 0.0

    if opt_type == 3 and context == 1 and isinstance(card_id, int):
        if card_id == DURALUDON_ID:
            score += _w("archaludon_setup_active_duraludon", 260)
        elif card_id == CINDERACE_ID:
            score -= _w("archaludon_setup_active_cinderace_penalty", 130)
        elif card_id == RELICANTH_ID:
            score -= _w("archaludon_setup_active_relicanth_penalty", 170)
        elif card_id == ARCHALUDON_EX_ID:
            score -= _w("archaludon_setup_active_archaludon_penalty", 120)

    if opt_type == 3 and context in (2, 5, 6, 7, 18, 19, 21, 22) and isinstance(card_id, int):
        if card_id == DURALUDON_ID and needs_duraludon:
            score += _w("archaludon_need_duraludon_card", 230)
        elif card_id == ARCHALUDON_EX_ID and needs_archaludon:
            score += _w("archaludon_need_archaludon_card", 260)
        elif card_id == METAL_ENERGY_ID and not _archaludon_has_ready_line(us):
            score += _w("archaludon_need_metal_energy_card", 135)
        elif card_id == CINDERACE_ID and ready_line_count == 0:
            score += _w("archaludon_setup_bench_cinderace", 95)

    if opt_type == 7 and isinstance(card_id, int):
        if card_id == DURALUDON_ID and needs_duraludon:
            score += _w("archaludon_setup_bench_duraludon", 230)
        elif card_id == CINDERACE_ID and line_count >= 1:
            score += _w("archaludon_setup_bench_cinderace", 110)

    if opt_type == 8 and isinstance(target, dict) and target_owner == your:
        target_id = target.get("id")
        target_energy = _card_energy_count(target)
        if target_id in ARCHALUDON_LINE_IDS:
            score += _w("archaludon_attach_line", 170)
            if option.get("inPlayArea") == 5:
                score += _w("archaludon_attach_bench_line", 165)
            if target_id == ARCHALUDON_EX_ID and target_energy < 3:
                score += _w("archaludon_attach_finish_archaludon", 160)
            if option.get("inPlayArea") == 4 and target_energy >= 3 and "no_next_attacker" in posture:
                score -= _w("archaludon_overfeed_active_penalty", 180)
        elif target_id == CINDERACE_ID and ready_line_count == 0:
            score += _w("archaludon_attach_cinderace_bridge", 105)
        elif target_id == RELICANTH_ID:
            score -= _w("archaludon_attach_relicanth_penalty", 170)

    if opt_type == 9 and isinstance(target, dict) and target_owner == your:
        target_id = target.get("id")
        if target_id == DURALUDON_ID and card_id == ARCHALUDON_EX_ID:
            score += _w("archaludon_evolve_finish", 300)
        elif target_id in ARCHALUDON_LINE_IDS:
            score += _w("archaludon_evolve_line", 120)

    if opt_type == 13:
        attack_id = option.get("attackId")
        active_damaged = _card_is_damaged(active)
        if attack_id == METAL_DEFENDER_ATTACK_ID and active_id == ARCHALUDON_EX_ID and active_energy >= 3:
            score += _w("archaludon_metal_defender_ready", 260)
        elif attack_id == RAGING_HAMMER_ATTACK_ID and active_id in ARCHALUDON_LINE_IDS and active_energy >= 3:
            score += _w("archaludon_raging_hammer_damaged", 210) if active_damaged else _w("archaludon_raging_hammer_ready", 70)
        elif attack_id == HAMMER_IN_ATTACK_ID and active_id == DURALUDON_ID and active_energy >= 3:
            score -= _w("archaludon_hammer_in_when_raging_live_penalty", 120)
        elif attack_id == TURBO_FLARE_ATTACK_ID and active_id == CINDERACE_ID:
            if not _archaludon_has_ready_line(us) or "no_next_attacker" in posture:
                score += _w("archaludon_turbo_flare_setup", 190)
            if _archaludon_has_ready_line(us) and line_count >= 2:
                score -= _w("archaludon_turbo_flare_when_line_ready_penalty", 60)

    if opt_type == 3 and context == 22 and isinstance(target, dict) and target_owner == your:
        target_id = target.get("id")
        if target_id == ARCHALUDON_EX_ID:
            score += _w("archaludon_hero_cape_target", 260)
        elif target_id == DURALUDON_ID:
            score += _w("archaludon_hero_cape_duraludon_target", 130)
        elif target_id == CINDERACE_ID:
            score -= _w("archaludon_hero_cape_cinderace_penalty", 80)

    if opt_type == 3 and context in (3, 13, 14, 15, 20, 25) and isinstance(target, dict) and target_owner != your:
        target_id = target.get("id")
        if target_id in GATE_TARGETS:
            score += _w("archaludon_boss_pressure", 120)
        if _card_energy_count(target) > 0:
            score += _w("archaludon_powered_target_pressure", 75)
    return score


def _posture(obs: dict) -> set[str]:
    current, your, us, them = _players(obs)
    our_board = _board(us)
    their_board = _board(them)
    our_active = _active(us)
    our_bench = _bench(us)
    our_prizes_left = len(us.get("prize") or [])
    their_prizes_left = len(them.get("prize") or [])
    our_attackers = sum(1 for card in our_board if card.get("id") in ATTACKERS or _energy_count([card]) > 0)
    bench_attackers = sum(1 for card in our_bench if card.get("id") in ATTACKERS or _energy_count([card]) > 0)
    their_attackers = sum(1 for card in their_board if _energy_count([card]) > 0)
    their_max_energy = max((_card_energy_count(card) for card in their_board), default=0)
    their_lucario_chain = [card for card in their_board if card.get("id") in LUCARIO_CHAIN_IDS]
    their_powered_lucario_chain = [card for card in their_lucario_chain if _card_energy_count(card) > 0]
    tags = set()
    if our_attackers == 0 or len(our_board) < 2:
        tags.add("setup")
    if len(our_bench) == 0:
        tags.add("empty_bench")
        tags.add("bench_development")
    elif len(our_bench) == 1 and bench_attackers == 0:
        tags.add("bench_development")
    if len(our_bench) < 2 or bench_attackers == 0:
        tags.add("bench_floor")
    if _card_energy_count(our_active) > 0 and bench_attackers == 0:
        tags.add("no_next_attacker")
        tags.add("setup")
    if isinstance(our_active, dict):
        active_hp = int(our_active.get("hp") or our_active.get("remainingHp") or our_active.get("maxHp") or 0)
        active_max_hp = int(our_active.get("maxHp") or active_hp or 0)
        if their_max_energy >= 2 and active_max_hp and active_hp <= max(90, active_max_hp * 0.45):
            tags.add("active_danger")
            tags.add("setup")
    if their_prizes_left < our_prizes_left or their_attackers > our_attackers:
        tags.add("behind")
    if their_attackers == 1:
        tags.add("single_powered_threat")
    if their_prizes_left > our_prizes_left and our_attackers >= 1:
        tags.add("ahead")
    if int(us.get("deckCount") or 99) <= 8:
        tags.add("low_deck")
    if any(card.get("id") in GATE_TARGETS for card in their_board):
        tags.add("gate_pressure")
    if their_lucario_chain:
        tags.add("lucario_pressure")
        tags.add("gate_pressure")
    if len(their_lucario_chain) >= 2 or any(card in _bench(them) for card in their_powered_lucario_chain):
        tags.add("lucario_rebuild_pressure")
        tags.add("behind")
    if _is_archaludon_candidate():
        line_count = _count_board_ids(us, ARCHALUDON_LINE_IDS)
        ready_line_count = _archaludon_ready_attackers(us)
        if line_count == 0 or ready_line_count == 0:
            tags.add("setup")
            tags.add("bench_floor")
        if line_count < 2:
            tags.add("bench_development")
        if isinstance(our_active, dict) and our_active.get("id") in ARCHALUDON_LINE_IDS:
            if _card_energy_count(our_active) > 0 and ready_line_count <= 1 and line_count < 2:
                tags.add("no_next_attacker")
    return tags


def _card_from_option(obs: dict, option: dict) -> dict | None:
    current, your, us, them = _players(obs)
    area = option.get("area")
    player_index = option.get("playerIndex", your)
    index = option.get("index")
    if index is None:
        index = option.get("inPlayIndex")
    zones = {
        2: "hand",
        3: "discard",
        4: "active",
        5: "bench",
        6: "prize",
    }
    player = us if int(player_index or your) == your else them
    zone = zones.get(area)
    if zone is None:
        return None
    cards = _zone_cards(player, zone)
    if isinstance(index, int) and 0 <= index < len(cards):
        return cards[index]
    return None


def _score_card_id(card_id: int, posture: set[str]) -> float:
    score = 0.0
    if card_id in KEY_CARDS:
        score += _w("key_card", 200)
    if card_id in ATTACKERS:
        score += _w("attacker", 140)
    if card_id in EVOLVERS:
        score += _w("evolver", 110)
    if card_id in SETUP_CARDS:
        score += _w("setup_card_setup", 90) if "setup" in posture else _w("setup_card_other", 35)
    if card_id in DISRUPTION:
        score += _w("disruption_pressure", 120) if ("behind" in posture or "gate_pressure" in posture) else _w("disruption_other", 30)
    if card_id in ENERGY_IDS:
        score += _w("energy_setup", 85) if "setup" in posture else _w("energy_other", 20)
        if "low_deck" in posture:
            score += _w("energy_low_deck", 20)
    if card_id in GATE_TARGETS:
        score += _w("gate_target", 160)
    return score


def _turn_shape_score(obs: dict, option: dict, posture: set[str], card_id: int | None) -> float:
    current, your, us, them = _players(obs)
    turn = int(current.get("turn") or 0)
    opt_type = option.get("type")
    context = ((obs.get("select") or {}).get("context"))
    us_board = _board(us)
    them_board = _board(them)
    us_bench = _bench(us)
    us_powered = sum(1 for card in us_board if _card_energy_count(card) > 0)
    them_powered = sum(1 for card in them_board if _card_energy_count(card) > 0)
    us_prizes_left = len(us.get("prize") or [])
    them_prizes_left = len(them.get("prize") or [])
    score = 0.0

    if turn <= 4 and ("setup" in posture or "bench_floor" in posture):
        if opt_type in (7, 8, 9) and (card_id in SETUP_CARDS or card_id in ATTACKERS or card_id in ENERGY_IDS):
            score += _w("early_shape_setup_action", 120)
        if opt_type == 3 and context in (1, 2, 5, 6, 7, 18, 19, 21, 22) and (
            card_id in SETUP_CARDS or card_id in ATTACKERS or card_id in ENERGY_IDS
        ):
            score += _w("early_shape_constructive_select", 115)

    if "bench_floor" in posture or "no_next_attacker" in posture:
        if opt_type == 13 and (them_powered >= 2 or them_prizes_left < us_prizes_left):
            score -= _w("bad_shape_attack_without_backup", 170)
        if opt_type == 14 and len(us_bench) < 2:
            score -= _w("bad_shape_end_without_backup", 150)

    if "behind" in posture:
        target = _target_from_option(obs, option)
        if isinstance(target, dict):
            target_owner = int(option.get("playerIndex", your) or your)
            if target_owner != your and (_card_energy_count(target) > 0 or target.get("id") in GATE_TARGETS):
                score += _w("behind_shape_target_live_threat", 130)
        if opt_type in (7, 9) and (card_id in SETUP_CARDS or card_id in DISRUPTION):
            score += _w("behind_shape_play_out", 80)

    if "ahead" in posture:
        if opt_type == 14 and us_powered >= 2:
            score += _w("ahead_shape_end_when_stable", 55)
        if context in (8, 26, 27, 29, 30) and isinstance(card_id, int) and card_id in DISRUPTION:
            score -= _w("ahead_shape_discard_disruption", 80)

    return score


def _projected_board_score(obs: dict, option: dict, posture: set[str], card_id: int | None) -> float:
    current, your, us, them = _players(obs)
    opt_type = option.get("type")
    context = ((obs.get("select") or {}).get("context"))
    us_board = _board(us)
    them_board = _board(them)
    us_bench = _bench(us)
    target = _target_from_option(obs, option)
    us_powered = sum(1 for card in us_board if _card_energy_count(card) > 0)
    them_powered = sum(1 for card in them_board if _card_energy_count(card) > 0)
    bench_attackers = sum(1 for card in us_bench if card.get("id") in ATTACKERS or _card_energy_count(card) > 0)
    projected_bench = len(us_bench)
    projected_powered = us_powered
    projected_bench_attackers = bench_attackers
    score = 0.0

    if opt_type == 7 and isinstance(card_id, int) and card_id in ATTACKERS | SETUP_CARDS and projected_bench < 5:
        projected_bench += 1
        if card_id in ATTACKERS:
            projected_bench_attackers += 1
    elif opt_type == 8 and isinstance(target, dict):
        target_energy = _card_energy_count(target)
        target_is_powered_after = target_energy == 0
        if option.get("inPlayArea") == 5:
            if target.get("id") in ATTACKERS or target_is_powered_after:
                projected_bench_attackers += 1 if target_energy == 0 else 0
            if target_is_powered_after:
                projected_powered += 1
        elif option.get("inPlayArea") == 4 and target_is_powered_after:
            projected_powered += 1
    elif opt_type == 9 and isinstance(target, dict) and target.get("id") in ATTACKERS | EVOLVERS:
        projected_bench_attackers += 1 if option.get("inPlayArea") == 5 and _card_energy_count(target) == 0 else 0
    elif opt_type == 3 and context in (1, 2, 5, 6, 7, 18, 19, 21, 22) and isinstance(card_id, int):
        if card_id in ATTACKERS or card_id in SETUP_CARDS:
            projected_bench += 1 if projected_bench < 5 else 0
            projected_bench_attackers += 1 if card_id in ATTACKERS else 0

    has_second_attacker = projected_bench_attackers > 0 or projected_powered >= 2
    is_setup_or_attacker = isinstance(card_id, int) and (card_id in ATTACKERS or card_id in SETUP_CARDS)
    if projected_bench >= 1 and is_setup_or_attacker:
        score += _w("projected_second_attacker_bonus", 120)
    if has_second_attacker and ("bench_floor" in posture or "no_next_attacker" in posture):
        score += _w("projected_powered_backup_bonus", 150)
    if "lucario_pressure" in posture and projected_powered >= max(1, them_powered - 1) and has_second_attacker:
        score += _w("projected_lucario_parity_bonus", 130)
    if opt_type == 13 and not has_second_attacker and them_powered >= 2:
        score -= _w("projected_attack_race_penalty", 175)
    if opt_type == 14 and not has_second_attacker and them_powered >= 1:
        score -= _w("projected_end_race_penalty", 155)
    if context in (8, 26, 27, 29, 30) and isinstance(card_id, int) and card_id in ATTACKERS | ENERGY_IDS:
        score -= _w("projected_discard_backup_penalty", 145)
    return score


def _score_option(obs: dict, option: dict, posture: set[str]) -> float:
    opt_type = option.get("type")
    context = ((obs.get("select") or {}).get("context"))
    score = 0.0
    card_id = option.get("cardId")
    if not isinstance(card_id, int):
        card = _card_from_option(obs, option)
        card_id = card.get("id") if isinstance(card, dict) else None
    if isinstance(card_id, int):
        score += _score_card_id(card_id, posture)
        if "bench_development" in posture and (card_id in ATTACKERS or card_id in SETUP_CARDS):
            score += _w("bench_development_card", 130)
        if "bench_floor" in posture and (card_id in ATTACKERS or card_id in SETUP_CARDS):
            score += _w("bench_floor_card", 115)
    score += _target_score(obs, option, posture)
    score += _dragapult_shape_score(obs, option, posture, card_id)
    score += _archaludon_shape_score(obs, option, posture, card_id)
    score += _turn_shape_score(obs, option, posture, card_id)
    score += _projected_board_score(obs, option, posture, card_id)

    if opt_type == 7:  # PLAY
        score += _w("play", 80)
        if "setup" in posture:
            score += _w("play_setup", 80)
        if "bench_development" in posture and isinstance(card_id, int) and (card_id in ATTACKERS or card_id in SETUP_CARDS):
            score += _w("bench_development_play", 150)
        if "bench_floor" in posture and isinstance(card_id, int) and (card_id in ATTACKERS or card_id in SETUP_CARDS):
            score += _w("bench_floor_play", 135)
    elif opt_type == 8:  # ATTACH
        score += _w("attach", 100)
        if "setup" in posture:
            score += _w("attach_setup", 75)
        target = _target_from_option(obs, option)
        if isinstance(target, dict):
            current, your, us, them = _players(obs)
            if option.get("inPlayArea") == 4 and _card_energy_count(target) > 0 and "no_next_attacker" in posture:
                score -= _w("overattach_active_penalty", 140)
            if option.get("inPlayArea") == 4 and "active_danger" in posture:
                score -= _w("active_danger_attach_penalty", 120)
            if option.get("inPlayArea") == 5 and "no_next_attacker" in posture:
                score += _w("build_next_attacker_bonus", 120)
            if option.get("inPlayArea") == 5 and ("bench_floor" in posture or "active_danger" in posture):
                score += _w("bench_floor_attach", 105)
            if "lucario_pressure" in posture and target.get("id") in ATTACKERS:
                target_energy = _card_energy_count(target)
                if option.get("inPlayArea") == 5 and target_energy <= 1:
                    score += _w("lucario_build_bench_attacker_attach", 150)
                if option.get("inPlayArea") == 4 and target_energy >= 2 and ("bench_floor" in posture or "no_next_attacker" in posture):
                    score -= _w("lucario_overfeed_active_penalty", 150)
        if option.get("inPlayArea") == 5:
            score += _w("bench_attach", 80)
    elif opt_type == 9:  # EVOLVE
        score += _w("evolve_option", 135)
    elif opt_type == 13:  # ATTACK
        score += _w("attack_option", 180)
        if "single_powered_threat" in posture:
            score += _w("attack_single_powered_bonus", 80)
        if "setup" in posture:
            score -= _w("attack_setup_penalty", 35)
        if "empty_bench" in posture:
            score -= _w("attack_empty_bench_penalty", 85)
        if "active_danger" in posture and "bench_floor" in posture:
            score -= _w("attack_active_danger_penalty", 95)
        if "lucario_rebuild_pressure" in posture and ("bench_floor" in posture or "no_next_attacker" in posture):
            score -= _w("attack_lucario_rebuild_penalty", 130)
        if "ahead" in posture:
            score += _w("attack_ahead", 60)
    elif opt_type == 12:  # RETREAT
        score += _w("retreat_pressure", 70) if ("behind" in posture or "gate_pressure" in posture) else _w("retreat_other", 5)
    elif opt_type == 14:  # END
        score -= _w("end_penalty", 80)
        if "low_deck" in posture:
            score += _w("end_low_deck", 50)
    elif opt_type in (1, 2):  # YES/NO
        score += 15 if opt_type == 1 else 5
    elif opt_type == 3:  # CARD selection
        score += _w("card_select", 30)
        if "setup" in posture:
            score += _w("card_select_setup", 40)
        if "bench_development" in posture and isinstance(card_id, int) and (card_id in ATTACKERS or card_id in SETUP_CARDS):
            score += _w("bench_development_select", 120)
        if "bench_floor" in posture and isinstance(card_id, int) and (card_id in ATTACKERS or card_id in SETUP_CARDS):
            score += _w("bench_floor_select", 125)
        if context in (1, 2, 5, 6, 7, 18, 19, 21, 22):
            score += _w("constructive_context", 70)
        if context in (8, 26, 27, 29, 30) and isinstance(card_id, int):
            if card_id in KEY_CARDS or card_id in ATTACKERS or card_id in ENERGY_IDS:
                score -= _w("discard_core_penalty", 180)
            elif card_id in SETUP_CARDS and "setup" in posture:
                score -= _w("discard_setup_penalty", 120)
        if context in (13, 14, 15, 20, 25) and "gate_pressure" in posture:
            score += _w("targeting_context_gate_bonus", 85)

    if "behind" in posture:
        if card_id in DISRUPTION or opt_type in (7, 9, 13):
            score += _w("behind_bonus", 55)
    if "gate_pressure" in posture:
        if card_id in GATE_TARGETS or card_id in DISRUPTION:
            score += _w("gate_pressure_bonus", 45)
    if "lucario_pressure" in posture:
        if card_id in DISRUPTION:
            score += _w("lucario_disruption_bonus", 115)
        if opt_type in (9, 12):
            score += _w("lucario_tempo_option_bonus", 60)
    if "low_deck" in posture and card_id in SETUP_CARDS:
        score -= _w("low_deck_setup_penalty", 45)
    return score


def agent(obs_dict: dict, config=None) -> list[int]:
    return _agent_impl(obs_dict)
'''


def _pick_deck(scout: dict, family: str) -> list[int]:
    rows = scout.get(family) or []
    if not rows:
        raise ValueError(f"no scout deck for {family}")
    counts = Counter(tuple(row["deck"]) for row in rows)
    return list(counts.most_common(1)[0][0])


def _write_candidate(root: Path, name: str, deck: list[int], config: dict) -> dict:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    main = AGENT_TEMPLATE
    replacements = {
        "__DECK__": repr(deck),
        "__STRATEGY__": config["strategy"],
        "__KEY_CARDS__": repr(config["key_cards"]),
        "__SETUP_CARDS__": repr(config["setup_cards"]),
        "__ATTACKERS__": repr(config["attackers"]),
        "__EVOLVERS__": repr(config["evolvers"]),
        "__DISRUPTION__": repr(config["disruption"]),
        "__ENERGY_IDS__": repr(config["energy_ids"]),
        "__GATE_TARGETS__": repr(config["gate_targets"]),
        "__RNG_NOISE__": repr(config["rng_noise"]),
        "__WEIGHTS__": repr(config.get("weights", {})),
    }
    for key, value in replacements.items():
        main = main.replace(key, value)
    (path / "main.py").write_text(main, encoding="utf-8")
    (path / "deck.csv").write_text("\n".join(map(str, deck)) + "\n", encoding="utf-8")
    return {
        "name": name,
        "strategy": config["strategy"],
        "path": str(path),
        "main_path": str(path / "main.py"),
        "deck_path": str(path / "deck.csv"),
        "deck_size": len(deck),
        "top_cards": Counter(deck).most_common(12),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scout-guided heuristic RNG PTCG candidates.")
    parser.add_argument("--scout-decks", type=Path, default=Path("artifacts/candidates/scout_decks.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/candidates/generated"))
    args = parser.parse_args()

    scout = json.loads(args.scout_decks.read_text(encoding="utf-8"))
    configs = {
        "candidate_dragapult_spread": {
            "family": "dragapult_120_119",
            "strategy": "spread-aware stabilizer: setup first, bench pressure, conserve when ahead",
            "key_cards": [119, 120, 121, 1086, 1152, 1121, 1227],
            "setup_cards": [119, 120, 121, 1086, 1121, 1152, 1227, 305, 140, 235],
            "attackers": [119, 120, 121, 305, 112],
            "evolvers": [120, 121],
            "disruption": [1182, 1198],
            "energy_ids": [2, 5],
            "gate_targets": [119, 120, 121, 673, 674, 675, 676, 677, 678, 741, 742, 743],
            "rng_noise": 24.0,
        },
        "candidate_dragapult_cracked": {
            "family": "dragapult_120_119",
            "strategy": "dragapult ex anti-Lucario spread controller: finish the chain, Phantom Dive live benches, rebuild before racing",
            "key_cards": [119, 120, 121, 1086, 1121, 1152, 1182, 1198, 1227],
            "setup_cards": [119, 120, 121, 1086, 1121, 1152, 1227, 305, 140, 235],
            "attackers": [119, 120, 121, 305, 112],
            "evolvers": [120, 121],
            "disruption": [1120, 1182, 1197, 1198],
            "energy_ids": [2, 5, 7],
            "gate_targets": [119, 120, 121, 673, 674, 675, 676, 677, 678, 741, 742, 743],
            "rng_noise": 10.0,
            "weights": {
                "dragapult_chain_needed_piece": 290,
                "dragapult_wrong_chain_piece_penalty": 170,
                "dragapult_evolve_bridge": 270,
                "dragapult_evolve_finish": 330,
                "dragapult_phantom_dive_attack": 260,
                "dragapult_jet_headbutt_when_phantom_live_penalty": 120,
                "dragapult_counter_finish_target": 360,
                "dragapult_counter_bench_rebuild_target": 240,
                "dragapult_counter_powered_bench_target": 160,
                "dragapult_counter_active_penalty": 100,
                "dragapult_attack_before_chain_penalty": 150,
                "lucario_bench_chain_target": 230,
                "lucario_evolving_basic_target": 210,
                "attack_lucario_rebuild_penalty": 170,
                "bad_shape_attack_without_backup": 210,
                "projected_powered_backup_bonus": 190,
                "discard_core_penalty": 220,
                "build_next_attacker_bonus": 170,
            },
        },
        "candidate_alakazam_stabilizer": {
            "family": "alakazam_741_742",
            "strategy": "stabilizer: build Abra line and second attacker before disruption",
            "key_cards": [741, 742, 743, 1086, 1152, 1231],
            "setup_cards": [741, 742, 1086, 1152, 1225, 1231, 305, 66],
            "attackers": [741, 742, 743, 305, 66],
            "evolvers": [742, 743],
            "disruption": [1079, 1156, 1231],
            "energy_ids": [5, 19],
            "gate_targets": [119, 120, 121, 673, 677, 678],
            "rng_noise": 18.0,
        },
        "candidate_666_disruptor": {
            "family": "shell_666",
            "strategy": "disruptor: exact-out search, energy tempo, higher variance when behind",
            "key_cards": [666, 1030, 1031, 1086, 1122, 1145],
            "setup_cards": [666, 1030, 1031, 1086, 1120, 1122, 1227],
            "attackers": [666, 1030, 1031],
            "evolvers": [1031],
            "disruption": [1122, 1145, 1189, 1229],
            "energy_ids": [3, 17],
            "gate_targets": [119, 120, 121, 673, 677, 678, 741, 742, 743],
            "rng_noise": 36.0,
        },
        "candidate_lucario_race": {
            "family": "lucario",
            "strategy": "lucario mirror/race: fast setup, second attacker, deny opposing Lucario rebuild",
            "key_cards": [676, 677, 678, 1102, 1141, 1142, 1152, 1192, 1227],
            "setup_cards": [676, 677, 678, 1102, 1141, 1142, 1152, 1192, 1227, 1123],
            "attackers": [676, 677, 678],
            "evolvers": [677, 678],
            "disruption": [1123, 1182, 1252],
            "energy_ids": [6],
            "gate_targets": [119, 120, 121, 673, 674, 675, 676, 677, 678, 741, 742, 743],
            "rng_noise": 20.0,
        },
    }
    manifest = []
    for name, config in configs.items():
        deck = _pick_deck(scout, config["family"])
        manifest.append(_write_candidate(args.output_dir, name, deck, config))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "candidates_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for item in manifest:
        print(json.dumps(item))


if __name__ == "__main__":
    main()
