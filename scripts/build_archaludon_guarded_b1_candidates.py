from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


BASE_DECK_COUNTS = {
    8: 11,
    57: 1,
    169: 4,
    190: 4,
    666: 4,
    1097: 3,
    1121: 4,
    1122: 4,
    1147: 4,
    1152: 4,
    1159: 1,
    1182: 4,
    1185: 4,
    1227: 4,
    1244: 4,
}


JUDGE_DECK_COUNTS = {
    **BASE_DECK_COUNTS,
    1213: 1,
    1244: BASE_DECK_COUNTS[1244] - 1,
}


NO_RELIC_JUDGE_METAL_DECK_COUNTS = {
    **JUDGE_DECK_COUNTS,
    57: 0,
    8: JUDGE_DECK_COUNTS[8] + 1,
}


NO_RELIC_BASE_METAL_DECK_COUNTS = {
    **BASE_DECK_COUNTS,
    57: 0,
    8: BASE_DECK_COUNTS[8] + 1,
}


NO_RELIC_JUDGE_LAB_DECK_COUNTS = {
    **JUDGE_DECK_COUNTS,
    57: 0,
    1244: JUDGE_DECK_COUNTS[1244] + 1,
}

PUBLIC_DISRUPTOR_DECK_COUNTS = {
    8: 11,
    57: 1,
    169: 4,
    190: 4,
    1087: 1,
    1097: 3,
    1121: 4,
    1122: 4,
    1123: 2,
    1152: 4,
    1159: 1,
    1182: 4,
    1192: 4,
    1197: 1,
    1213: 4,
    1227: 4,
    1244: 4,
}


DEFAULT_PARAMS = {
    "order_weight": 18,
    "optional_threshold": 55,
    "return_full_ranking": False,
    "skip_optional_setup_bench": False,
    "duraludon_setup_active_bonus": 1000,
    "cinderace_setup_active_bonus": 160,
    "attack_bonus": 180,
    "attack_without_backup_penalty": 40,
    "unsafe_retreat_penalty": 5000,
    "end_attack_penalty": 900,
    "setup_bonus": 180,
    "bench_line_bonus": 220,
    "attach_line_bonus": 220,
    "bench_attach_bonus": 180,
    "active_overfeed_penalty": 520,
    "evolve_bonus": 650,
    "target_bonus": 160,
    "starmie_target_bonus": 320,
    "low_hp_target_bonus": 170,
    "discard_core_penalty": 420,
    "b1_patch_mode": "",
}


VARIANTS = {
    "archaludon_guarded_b1_v2": {
        "strategy": "guarded B1: preserve SDK order, hard-veto unsafe retreat/end, and patch Archaludon setup",
        "params": {},
    },
    "archaludon_starmie_bridge_breaker_v1": {
        "strategy": "guarded B1 anti-Starmie: target Staryu/Mega Starmie bridges and take live attacks",
        "params": {
            "attack_bonus": 230,
            "starmie_target_bonus": 520,
            "target_bonus": 210,
            "end_attack_penalty": 1100,
            "optional_threshold": 70,
        },
    },
    "archaludon_backup_first_guard_v1": {
        "strategy": "guarded B1 backup-first: build second Duraludon/Archaludon before extra active feeding",
        "params": {
            "setup_bonus": 240,
            "bench_line_bonus": 320,
            "attach_line_bonus": 240,
            "bench_attach_bonus": 300,
            "active_overfeed_penalty": 700,
            "attack_bonus": 150,
            "optional_threshold": 60,
        },
    },
    "archaludon_fumi_ranked_b1_v1": {
        "strategy": "Fumi-style ranked B1: Cinderace active, skip optional setup bench, preserve order, return full ranked options",
        "params": {
            "order_weight": 48,
            "return_full_ranking": True,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 260,
            "cinderace_setup_active_bonus": 900,
            "optional_threshold": 9999,
            "attack_bonus": 120,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 120,
            "setup_bonus": 40,
            "bench_line_bonus": 30,
            "attach_line_bonus": 40,
            "bench_attach_bonus": 10,
            "active_overfeed_penalty": 80,
            "evolve_bonus": 80,
            "starmie_target_bonus": 220,
            "target_bonus": 80,
        },
    },
    "archaludon_fumi_attack_rank_v1": {
        "strategy": "Fumi-style ranked attacker: same ranked-B1 shell with stronger live Metal Defender conversion",
        "params": {
            "order_weight": 42,
            "return_full_ranking": True,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 260,
            "cinderace_setup_active_bonus": 900,
            "optional_threshold": 9999,
            "attack_bonus": 420,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 240,
            "setup_bonus": 40,
            "bench_line_bonus": 30,
            "attach_line_bonus": 35,
            "bench_attach_bonus": 10,
            "active_overfeed_penalty": 80,
            "evolve_bonus": 70,
            "starmie_target_bonus": 260,
            "target_bonus": 90,
        },
    },
    "archaludon_fumi_retreat_rank_v1": {
        "strategy": "Fumi-style ranked mobility: Cinderace start, full ranking, and no hard retreat veto",
        "params": {
            "order_weight": 38,
            "return_full_ranking": True,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 220,
            "cinderace_setup_active_bonus": 940,
            "optional_threshold": 9999,
            "attack_bonus": 260,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 180,
            "setup_bonus": 25,
            "bench_line_bonus": 20,
            "attach_line_bonus": 30,
            "bench_attach_bonus": 0,
            "active_overfeed_penalty": 40,
            "evolve_bonus": 60,
            "starmie_target_bonus": 220,
            "target_bonus": 80,
        },
    },
    "archaludon_fumi_single_b1_v1": {
        "strategy": "Fumi-prior single-index B1: Cinderace active, skip optional setup bench, soft retreat, low evolve override",
        "params": {
            "order_weight": 48,
            "return_full_ranking": False,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 260,
            "cinderace_setup_active_bonus": 900,
            "optional_threshold": 120,
            "attack_bonus": 160,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 120,
            "setup_bonus": 35,
            "bench_line_bonus": 25,
            "attach_line_bonus": 35,
            "bench_attach_bonus": 10,
            "active_overfeed_penalty": 60,
            "evolve_bonus": 55,
            "starmie_target_bonus": 220,
            "target_bonus": 80,
        },
    },
    "archaludon_fumi_single_attack_v1": {
        "strategy": "Fumi-prior single-index attacker: preserve order but take Metal Defender over extra setup churn",
        "params": {
            "order_weight": 42,
            "return_full_ranking": False,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 240,
            "cinderace_setup_active_bonus": 920,
            "optional_threshold": 140,
            "attack_bonus": 420,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 260,
            "setup_bonus": 30,
            "bench_line_bonus": 20,
            "attach_line_bonus": 30,
            "bench_attach_bonus": 5,
            "active_overfeed_penalty": 60,
            "evolve_bonus": 45,
            "starmie_target_bonus": 260,
            "target_bonus": 90,
        },
    },
    "archaludon_fumi_single_mobility_v1": {
        "strategy": "Fumi-prior single-index mobility: preserve retreat lines and avoid overbuilding active",
        "params": {
            "order_weight": 38,
            "return_full_ranking": False,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 220,
            "cinderace_setup_active_bonus": 940,
            "optional_threshold": 140,
            "attack_bonus": 260,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 180,
            "setup_bonus": 25,
            "bench_line_bonus": 15,
            "attach_line_bonus": 25,
            "bench_attach_bonus": 0,
            "active_overfeed_penalty": 30,
            "evolve_bonus": 40,
            "starmie_target_bonus": 220,
            "target_bonus": 80,
        },
    },
    "archaludon_fumi_single_second_b1_v1": {
        "strategy": "Fumi-prior single-index B1 plus choosing second for Cinderace/Metal tempo",
        "params": {
            "order_weight": 48,
            "return_full_ranking": False,
            "skip_optional_setup_bench": True,
            "prefer_second": True,
            "duraludon_setup_active_bonus": 260,
            "cinderace_setup_active_bonus": 900,
            "optional_threshold": 120,
            "attack_bonus": 160,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 120,
            "setup_bonus": 35,
            "bench_line_bonus": 25,
            "attach_line_bonus": 35,
            "bench_attach_bonus": 10,
            "active_overfeed_penalty": 60,
            "evolve_bonus": 55,
            "starmie_target_bonus": 220,
            "target_bonus": 80,
        },
    },
    "archaludon_fumi_single_second_attack_v1": {
        "strategy": "Fumi-prior single-index attacker plus choosing second for Cinderace/Metal tempo",
        "params": {
            "order_weight": 42,
            "return_full_ranking": False,
            "skip_optional_setup_bench": True,
            "prefer_second": True,
            "duraludon_setup_active_bonus": 240,
            "cinderace_setup_active_bonus": 920,
            "optional_threshold": 140,
            "attack_bonus": 420,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 260,
            "setup_bonus": 30,
            "bench_line_bonus": 20,
            "attach_line_bonus": 30,
            "bench_attach_bonus": 5,
            "active_overfeed_penalty": 60,
            "evolve_bonus": 45,
            "starmie_target_bonus": 260,
            "target_bonus": 90,
        },
    },
    "archaludon_fumi_single_second_mobility_v1": {
        "strategy": "Fumi-prior single-index mobility plus choosing second for Cinderace/Metal tempo",
        "params": {
            "order_weight": 38,
            "return_full_ranking": False,
            "skip_optional_setup_bench": True,
            "prefer_second": True,
            "duraludon_setup_active_bonus": 220,
            "cinderace_setup_active_bonus": 940,
            "optional_threshold": 140,
            "attack_bonus": 260,
            "unsafe_retreat_penalty": 0,
            "end_attack_penalty": 180,
            "setup_bonus": 25,
            "bench_line_bonus": 15,
            "attach_line_bonus": 25,
            "bench_attach_bonus": 0,
            "active_overfeed_penalty": 30,
            "evolve_bonus": 40,
            "starmie_target_bonus": 220,
            "target_bonus": 80,
        },
    },
    "archaludon_b1_retreat_patch_v1": {
        "strategy": "B1 patch: exact first-option floor with only unsafe-retreat veto",
        "params": {"b1_patch_mode": "retreat"},
    },
    "archaludon_b1_attack_patch_v1": {
        "strategy": "B1 patch: unsafe-retreat veto plus live Metal Defender over end/search churn",
        "params": {"b1_patch_mode": "attack"},
    },
    "archaludon_b1_backup_patch_v1": {
        "strategy": "B1 patch: unsafe-retreat, live attack, and bench attach over active overfeed",
        "params": {"b1_patch_mode": "backup"},
    },
    "archaludon_cinderace_turbo_b1_v1": {
        "strategy": "Cinderace bridge: start Cinderace, bench Duraludon, Turbo Flare Metal to bench, then Assemble Alloy into Archaludon",
        "params": {"b1_patch_mode": "cinderace_turbo"},
    },
    "archaludon_cinderace_memory_dive_v1": {
        "strategy": "Cinderace public shell with Relicanth Memory Dive: keep Relicanth, build Archaludon, and prefer damaged Raging Hammer lines when available",
        "params": {"b1_patch_mode": "cinderace_memory_dive"},
    },
    "archaludon_cinderace_turbo_judge_v1": {
        "strategy": "Cinderace bridge plus public variant list: -1 Full Metal Lab, +1 Judge for disruption into Starmie/Lucario",
        "deck_counts": JUDGE_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo"},
    },
    "archaludon_cinderace_turbo_second_judge_v1": {
        "strategy": "Cinderace bridge plus Judge list, choosing second for attack/energy tempo when the SDK asks who goes first",
        "deck_counts": JUDGE_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo", "prefer_second": True},
    },
    "archaludon_cinderace_no_relic_second_judge_metal_v1": {
        "strategy": "Cinderace/Judge choose-second deck pivot: remove Relicanth sink for one extra Metal so setup attachments stay on the Archaludon line",
        "deck_counts": NO_RELIC_JUDGE_METAL_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo", "prefer_second": True},
    },
    "archaludon_cinderace_no_relic_judge_metal_v1": {
        "strategy": "Cinderace/Judge no-Relic Metal deck pivot without forcing second, testing whether first-player tempo beats extra attack access",
        "deck_counts": NO_RELIC_JUDGE_METAL_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo"},
    },
    "archaludon_cinderace_no_relic_backup_lock_metal_v1": {
        "strategy": "Cinderace/Judge no-Relic backup lock: same best shell, but bench/attach a second Archaludon line before end or low-backup attacks",
        "deck_counts": NO_RELIC_JUDGE_METAL_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_backup_lock"},
    },
    "archaludon_public_disruptor_guarded_v1": {
        "strategy": "Public Archaludon disruption shell: keep Relicanth and core Metal line, replace the Cinderace package with Carmine/Judge/Switch/Xerosic pressure",
        "deck_counts": PUBLIC_DISRUPTOR_DECK_COUNTS,
        "params": {"b1_patch_mode": "backup"},
    },
    "archaludon_public_disruptor_attack_v1": {
        "strategy": "Public Archaludon disruption shell with live-attack guard: same Carmine/Judge/Switch/Xerosic deck, but attack over end/search churn once Metal Defender is live",
        "deck_counts": PUBLIC_DISRUPTOR_DECK_COUNTS,
        "params": {"b1_patch_mode": "attack"},
    },
    "archaludon_cinderace_no_relic_base_metal_v1": {
        "strategy": "Cinderace no-Relic Metal base list: remove Relicanth for Metal but keep the fourth Full Metal Lab instead of Judge",
        "deck_counts": NO_RELIC_BASE_METAL_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo"},
    },
    "archaludon_cinderace_no_relic_line_guard_metal_v1": {
        "strategy": "No-Relic Metal line guard: choose second, bench the second Duraludon line, and convert live Archaludon-line attacks before trainer churn",
        "deck_counts": NO_RELIC_JUDGE_METAL_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_line_guard", "prefer_second": True},
    },
    "archaludon_cinderace_no_relic_second_judge_lab_v1": {
        "strategy": "Cinderace/Judge choose-second deck pivot: remove Relicanth sink and restore the fourth Full Metal Lab for a cleaner metal-board floor",
        "deck_counts": NO_RELIC_JUDGE_LAB_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo", "prefer_second": True},
    },
    "archaludon_cinderace_tempo_guard_second_judge_v1": {
        "strategy": "Cinderace/Judge tempo guard: choose second, attach/evolve before churn, cap active overfeed, and build a second Duraludon line",
        "deck_counts": JUDGE_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_tempo_guard", "prefer_second": True},
    },
    "archaludon_cinderace_turbo_discard_v1": {
        "strategy": "Cinderace bridge with more discard fuel: discard Metal before core Pokemon and use max Metal selections after Turbo Flare/Assemble Alloy",
        "params": {"b1_patch_mode": "cinderace_turbo_discard"},
    },
    "archaludon_cinderace_spread_b1_v1": {
        "strategy": "Cinderace bridge with backup-first energy spread and safer post-KO promotion",
        "params": {"b1_patch_mode": "cinderace_turbo_spread"},
    },
    "archaludon_cinderace_spread_judge_v1": {
        "strategy": "Cinderace bridge with backup-first energy spread plus the public -1 Lab/+1 Judge disruption list",
        "deck_counts": JUDGE_DECK_COUNTS,
        "params": {"b1_patch_mode": "cinderace_turbo_spread"},
    },
    "archaludon_cinderace_spread_discard_v1": {
        "strategy": "Cinderace bridge with backup-first energy spread and Metal discard fuel for Assemble Alloy",
        "params": {"b1_patch_mode": "cinderace_turbo_spread_discard"},
    },
}


POLICY_TEMPLATE = r'''from __future__ import annotations

DECK = __DECK__
VARIANT = "__VARIANT__"
PARAMS = __PARAMS__

DURALUDON = 169
ARCHALUDON_EX = 190
RELICANTH = 57
CINDERACE = 666
METAL_ENERGY = 8
JUMBO_ICE_CREAM = 1147
HERO_CAPE = 1159
FULL_METAL_LAB = 1244
BOSS_ORDERS = 1182
JUDGE = 1213
CARMINE = 1192
SWITCH = 1123
XEROSIC = 1197
HAND_TRIMMER = 1087
EXPLORERS_GUIDANCE = 1185
LILLIES_DETERMINATION = 1227
ULTRA_BALL = 1121
POKEGEAR = 1122
POKE_PAD = 1152
HAMMER_IN = 223
RAGING_HAMMER = 224
METAL_DEFENDER = 253
TURBO_FLARE = 965
ARCH_LINE = {DURALUDON, ARCHALUDON_EX}
STARMIE_LINE = {360, 361, 1030, 1031}
DRAGAPULT_LINE = {119, 120, 121}
LUCARIO_LINE = {673, 674, 675, 676, 677, 678}
ALAKAZAM_LINE = {741, 742, 743}
HOP_TREVENANT_LINE = {878, 879}
GATE_TARGETS = STARMIE_LINE | DRAGAPULT_LINE | LUCARIO_LINE | ALAKAZAM_LINE | HOP_TREVENANT_LINE | {169, 190, 1030, 1031, 1219, 1220}
SEARCH_DRAW = {1097, ULTRA_BALL, POKEGEAR, POKE_PAD, EXPLORERS_GUIDANCE, LILLIES_DETERMINATION, JUDGE, CARMINE}
CORE_CARDS = ARCH_LINE | {METAL_ENERGY, CINDERACE, BOSS_ORDERS, JUMBO_ICE_CREAM, HERO_CAPE}
DISCARDABLE_TRAINERS = {POKEGEAR, POKE_PAD, FULL_METAL_LAB, JUMBO_ICE_CREAM, JUDGE, CARMINE, SWITCH, XEROSIC, HAND_TRIMMER}
DISCARD_CONTEXTS = {8, 26, 27, 29, 30}
CONSTRUCTIVE_CONTEXTS = {1, 2, 5, 6, 7, 18, 19, 21, 22}
TARGET_CONTEXTS = {3, 13, 14, 15, 20, 25}
TYPE_MAP = {
    "Yes": 1,
    "No": 2,
    "Select": 3,
    "Play": 7,
    "Attach": 8,
    "Evolve": 9,
    "Retreat": 12,
    "Attack": 13,
    "End": 14,
}


def _p(name: str) -> float:
    return float(PARAMS[name])


def _type_id(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return TYPE_MAP.get(value, -1)
    return -1


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _players(obs: dict):
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    if len(players) < 2:
        players = [{}, {}]
    your = _int(current.get("yourIndex"), 0)
    if your not in (0, 1):
        your = 0
    return current, your, players[your] or {}, players[1 - your] or {}


def _zone_cards(player: dict, zone: str) -> list[dict]:
    value = player.get(zone)
    return [card for card in value if isinstance(card, dict)] if isinstance(value, list) else []


def _active(player: dict) -> dict | None:
    cards = _zone_cards(player, "active")
    return cards[0] if cards else None


def _bench(player: dict) -> list[dict]:
    return _zone_cards(player, "bench")


def _board(player: dict) -> list[dict]:
    return _zone_cards(player, "active") + _zone_cards(player, "bench")


def _energy_value(value) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _energy_count(card: dict | None) -> int:
    if not isinstance(card, dict):
        return 0
    energy_cards = _energy_value(card.get("energyCards"))
    if energy_cards:
        return energy_cards
    return _energy_value(card.get("energies"))


def _hp(card: dict | None) -> int:
    if not isinstance(card, dict):
        return 0
    return _int(card.get("hp") or card.get("remainingHp") or card.get("maxHp"), 0)


def _max_hp(card: dict | None) -> int:
    if not isinstance(card, dict):
        return 0
    return _int(card.get("maxHp") or card.get("maximumHp") or card.get("hp"), 0)


def _damaged(card: dict | None) -> bool:
    return bool(_hp(card) and _max_hp(card) and _hp(card) < _max_hp(card))


def _card_id(card: dict | None) -> int | None:
    return card.get("id") if isinstance(card, dict) and isinstance(card.get("id"), int) else None


def _source_card(obs: dict, option: dict) -> dict | None:
    if isinstance(option.get("cardId"), int):
        return {"id": option["cardId"]}
    current, your, us, them = _players(obs)
    area = option.get("area")
    if area is None and _type_id(option.get("type")) in {7, 8, 9}:
        area = 2
    index = option.get("index")
    if not isinstance(index, int):
        return None
    player_index = _int(option.get("playerIndex"), your)
    player = us if player_index == your else them
    zone = {2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    cards = _zone_cards(player, zone) if zone else []
    if 0 <= index < len(cards):
        return cards[index]
    return None


def _target_card(obs: dict, option: dict) -> dict | None:
    current, your, us, them = _players(obs)
    area = option.get("inPlayArea")
    index = option.get("inPlayIndex")
    if area is None:
        area = option.get("area")
        index = option.get("index")
    if not isinstance(index, int):
        return None
    owner = option.get("targetPlayerIndex")
    if owner is None:
        owner = option.get("inPlayPlayerIndex")
    if owner is None:
        owner = option.get("playerIndex", your)
    player = us if _int(owner, your) == your else them
    zone = {4: "active", 5: "bench"}.get(area)
    cards = _zone_cards(player, zone) if zone else []
    if 0 <= index < len(cards):
        return cards[index]
    return None


def _target_owner(obs: dict, option: dict) -> int:
    current, your, us, them = _players(obs)
    owner = option.get("targetPlayerIndex")
    if owner is None:
        owner = option.get("inPlayPlayerIndex")
    if owner is None:
        owner = option.get("playerIndex", your)
    return _int(owner, your)


def _ready_arch_count(player: dict) -> int:
    return sum(1 for card in _board(player) if _card_id(card) in ARCH_LINE and _energy_count(card) >= 3)


def _arch_line_count(player: dict) -> int:
    return sum(1 for card in _board(player) if _card_id(card) in ARCH_LINE)


def _has_arch_backup(player: dict) -> bool:
    for card in _bench(player):
        cid = _card_id(card)
        energy = _energy_count(card)
        if cid in ARCH_LINE and energy >= 2:
            return True
        if cid == CINDERACE and energy >= 1:
            return True
    return False


def _opponent_powered(player: dict) -> int:
    return sum(1 for card in _board(player) if _energy_count(card) > 0)


def _safe_retreat(us: dict, them: dict) -> bool:
    active = _active(us)
    active_id = _card_id(active)
    active_energy = _energy_count(active)
    bench = _bench(us)
    ready_bench = any(
        (_card_id(card) in ARCH_LINE and _energy_count(card) >= 3) or (_card_id(card) == CINDERACE and _energy_count(card) >= 1)
        for card in bench
    )
    if not ready_bench:
        return False
    if active_id in ARCH_LINE and active_energy >= 2:
        return bool(_hp(active) <= 60 and _opponent_powered(them) > 0)
    return True


def _constructive_option_exists(obs: dict, options: list[dict]) -> bool:
    for option in options:
        typ = _type_id(option.get("type"))
        card = _source_card(obs, option)
        target = _target_card(obs, option)
        cid = _card_id(card)
        tid = _card_id(target)
        if typ in {7, 8, 9} and (cid in CORE_CARDS or tid in ARCH_LINE or tid == CINDERACE):
            return True
    return False


def _find_option(options: list[dict], typ: int, predicate=None) -> int | None:
    for index, option in enumerate(options):
        if _type_id(option.get("type")) != typ:
            continue
        if predicate is None or predicate(index, option):
            return index
    return None


def _selection_bounds(obs_dict: dict, options: list[dict]) -> tuple[int, int]:
    select = obs_dict.get("select") or {}
    min_count = max(0, _int(select.get("minCount"), 0))
    max_count = max(min_count, _int(select.get("maxCount"), min_count or 1))
    max_count = min(max_count, len(options))
    min_count = min(min_count, max_count)
    return min_count, max_count


def _first_legal_selection(obs_dict: dict, options: list[dict], preferred: int | None = None) -> list[int]:
    min_count, max_count = _selection_bounds(obs_dict, options)
    if max_count <= 0:
        return []
    target_count = 1 if min_count == 0 else min_count
    target_count = min(target_count, max_count)
    chosen: list[int] = []
    if preferred is not None and 0 <= preferred < len(options):
        chosen.append(preferred)
    for index in range(len(options)):
        if len(chosen) >= target_count:
            break
        if index not in chosen:
            chosen.append(index)
    return chosen


def _matching_selection(obs_dict: dict, options: list[dict], predicate, *, prefer_max: bool = False) -> list[int] | None:
    min_count, max_count = _selection_bounds(obs_dict, options)
    if max_count <= 0:
        return []
    matches = [index for index, option in enumerate(options) if predicate(index, option)]
    if not matches:
        return None
    target_count = max_count if prefer_max else (1 if min_count == 0 else min_count)
    target_count = max(0, min(target_count, max_count))
    chosen = matches[:target_count]
    for index in range(len(options)):
        if len(chosen) >= max(min_count, target_count):
            break
        if index not in chosen:
            chosen.append(index)
    if len(chosen) < min_count:
        return _first_legal_selection(obs_dict, options, matches[0])
    return chosen


def _card_id_from_option(obs_dict: dict, option: dict) -> int | None:
    source = _source_card(obs_dict, option)
    target = _target_card(obs_dict, option)
    return _card_id(source) if _card_id(source) is not None else _card_id(target)


def _discard_metal_count(player: dict) -> int:
    return sum(1 for card in _zone_cards(player, "discard") if _card_id(card) == METAL_ENERGY)


def _option_area(option: dict) -> int | None:
    area = option.get("inPlayArea")
    if area is None:
        area = option.get("area")
    return area if isinstance(area, int) else None


def _best_arch_target_index(obs_dict: dict, options: list[dict]) -> int | None:
    best: tuple[tuple[int, int, int, int], int] | None = None
    for index, option in enumerate(options):
        card = _target_card(obs_dict, option) or _source_card(obs_dict, option)
        cid = _card_id(card)
        if cid not in ARCH_LINE:
            continue
        energy = _energy_count(card)
        area = _option_area(option)
        key = (
            1 if energy < 3 else 0,
            1 if area == 5 else 0,
            1 if cid == ARCHALUDON_EX else 0,
            -energy,
        )
        if best is None or key > best[0]:
            best = (key, index)
    return best[1] if best is not None else None


def _best_promote_index(obs_dict: dict, options: list[dict]) -> int | None:
    best: tuple[tuple[int, int, int, int], int] | None = None
    for index, option in enumerate(options):
        card = _source_card(obs_dict, option)
        cid = _card_id(card)
        energy = _energy_count(card)
        if cid == ARCHALUDON_EX:
            key = (5 if energy >= 3 else 3, energy, _hp(card), -index)
        elif cid == DURALUDON:
            key = (4 if energy >= 3 else 2, energy, _hp(card), -index)
        elif cid == CINDERACE:
            key = (3 if energy >= 1 else 1, energy, _hp(card), -index)
        elif cid == RELICANTH:
            key = (0, energy, _hp(card), -index)
        else:
            key = (1 if energy > 0 else 0, energy, _hp(card), -index)
        if best is None or key > best[0]:
            best = (key, index)
    return best[1] if best is not None else None


def _bench_arch_attach_index(obs_dict: dict, options: list[dict], *, max_energy: int = 3) -> int | None:
    best: tuple[tuple[int, int, int], int] | None = None
    for index, option in enumerate(options):
        if _type_id(option.get("type")) != 8:
            continue
        if _card_id(_source_card(obs_dict, option)) != METAL_ENERGY:
            continue
        if _option_area(option) != 5:
            continue
        target = _target_card(obs_dict, option)
        cid = _card_id(target)
        if cid not in ARCH_LINE:
            continue
        energy = _energy_count(target)
        if energy >= max_energy:
            continue
        key = (1 if cid == ARCHALUDON_EX else 0, -energy, -index)
        if best is None or key > best[0]:
            best = (key, index)
    return best[1] if best is not None else None


def _backup_development_index(obs_dict: dict, options: list[dict]) -> int | None:
    current, your, us, them = _players(obs_dict)
    duraludon_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
    if duraludon_play is not None and _arch_line_count(us) < 2:
        return duraludon_play

    bench_attach = _bench_arch_attach_index(obs_dict, options, max_energy=2)
    if bench_attach is not None:
        return bench_attach

    bench_evolve = _find_option(
        options,
        9,
        lambda _, option: option.get("inPlayArea") == 5
        and _card_id(_source_card(obs_dict, option)) == ARCHALUDON_EX
        and _card_id(_target_card(obs_dict, option)) == DURALUDON,
    )
    if bench_evolve is not None:
        return bench_evolve

    return None


def _active_arch_attach_index(obs_dict: dict, options: list[dict], *, max_energy: int) -> int | None:
    for index, option in enumerate(options):
        if _type_id(option.get("type")) != 8:
            continue
        if _card_id(_source_card(obs_dict, option)) != METAL_ENERGY:
            continue
        if option.get("inPlayArea") != 4:
            continue
        target = _target_card(obs_dict, option)
        if _card_id(target) in ARCH_LINE and _energy_count(target) < max_energy:
            return index
    return None


def _active_arch_evolve_index(obs_dict: dict, options: list[dict]) -> int | None:
    return _find_option(
        options,
        9,
        lambda _, option: option.get("inPlayArea") == 4
        and _card_id(_source_card(obs_dict, option)) == ARCHALUDON_EX
        and _card_id(_target_card(obs_dict, option)) == DURALUDON,
    )


def _tool_redirect_index(obs_dict: dict, options: list[dict]) -> int | None:
    best: tuple[tuple[int, int, int], int] | None = None
    for index, option in enumerate(options):
        source_id = _card_id(_source_card(obs_dict, option))
        target = _target_card(obs_dict, option)
        target_id = _card_id(target)
        if source_id != HERO_CAPE or target_id not in (ARCHALUDON_EX, DURALUDON, CINDERACE):
            continue
        energy = _energy_count(target)
        key = (2 if target_id == ARCHALUDON_EX else 1, energy, -index)
        if best is None or key > best[0]:
            best = (key, index)
    return best[1] if best is not None else None


def _has_board_card(player: dict, card_id: int) -> bool:
    return any(_card_id(card) == card_id for card in _board(player))


def _best_gate_target_index(obs_dict: dict, options: list[dict]) -> int | None:
    current, your, us, them = _players(obs_dict)
    best: tuple[tuple[int, int, int, int], int] | None = None
    for index, option in enumerate(options):
        if _target_owner(obs_dict, option) == your:
            continue
        card = _target_card(obs_dict, option) or _source_card(obs_dict, option)
        cid = _card_id(card)
        if cid not in GATE_TARGETS:
            continue
        key = (
            4 if cid in {678, 1031} else 3 if cid in {677, 1030, 676, 675} else 2,
            _energy_count(card),
            1 if 0 < _hp(card) <= 220 else 0,
            -index,
        )
        if best is None or key > best[0]:
            best = (key, index)
    return best[1] if best is not None else None


def _cinderace_turbo_action(
    obs_dict: dict,
    options: list[dict],
    *,
    discard_first: bool,
    spread_energy: bool = False,
    tempo_guard: bool = False,
    line_guard: bool = False,
    backup_lock: bool = False,
    memory_dive: bool = False,
) -> list[int] | None:
    current, your, us, them = _players(obs_dict)
    select = obs_dict.get("select") or {}
    context = select.get("context")
    active = _active(us)
    active_id = _card_id(active)
    active_energy = _energy_count(active)
    bench_has_arch = any(_card_id(card) in ARCH_LINE for card in _bench(us))
    first = options[0] if options else {}
    first_type = _type_id(first.get("type"))

    if context == 4:
        promote_index = _best_promote_index(obs_dict, options)
        if promote_index is not None:
            return _first_legal_selection(obs_dict, options, promote_index)

    if context == 1:
        cinderace_index = _find_option(options, 3, lambda _, option: _card_id(_source_card(obs_dict, option)) == CINDERACE)
        if cinderace_index is not None:
            return _first_legal_selection(obs_dict, options, cinderace_index)
        duraludon_index = _find_option(options, 3, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_index is not None:
            return _first_legal_selection(obs_dict, options, duraludon_index)

    if context == 2:
        duraludon_index = _find_option(options, 3, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_index is not None:
            return _first_legal_selection(obs_dict, options, duraludon_index)
        relicanth_index = _find_option(options, 3, lambda _, option: _card_id(_source_card(obs_dict, option)) == RELICANTH)
        if relicanth_index is not None and _arch_line_count(us) > 0:
            return _first_legal_selection(obs_dict, options, relicanth_index)
        return []

    if context in DISCARD_CONTEXTS:
        if discard_first:
            energy_discard = _matching_selection(
                obs_dict,
                options,
                lambda _, option: _card_id_from_option(obs_dict, option) == METAL_ENERGY,
                prefer_max=False,
            )
            if energy_discard is not None:
                return energy_discard
        trainer_discard = _matching_selection(
            obs_dict,
            options,
            lambda _, option: _card_id_from_option(obs_dict, option) in DISCARDABLE_TRAINERS,
            prefer_max=False,
        )
        if trainer_discard is not None:
            return trainer_discard

    if context in {7, 22}:
        metal_selection = _matching_selection(
            obs_dict,
            options,
            lambda _, option: _card_id_from_option(obs_dict, option) == METAL_ENERGY,
            prefer_max=True,
        )
        if metal_selection is not None:
            return metal_selection

    if context == 21:
        arch_target = _best_arch_target_index(obs_dict, options)
        if arch_target is not None:
            return _first_legal_selection(obs_dict, options, arch_target)

    if context == 22:
        tool_target = _tool_redirect_index(obs_dict, options)
        if tool_target is not None:
            return _first_legal_selection(obs_dict, options, tool_target)

    if context in TARGET_CONTEXTS:
        gate_target = _best_gate_target_index(obs_dict, options)
        if gate_target is not None:
            return _first_legal_selection(obs_dict, options, gate_target)

    if line_guard and context == 0 and active_id in ARCH_LINE:
        duraludon_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_play is not None and _arch_line_count(us) < 2:
            return _first_legal_selection(obs_dict, options, duraludon_play)

        if active_id == DURALUDON:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=2)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)

            evolve_active = _active_arch_evolve_index(obs_dict, options)
            if evolve_active is not None and active_energy >= 2:
                return _first_legal_selection(obs_dict, options, evolve_active)

            bench_attach = _bench_arch_attach_index(obs_dict, options, max_energy=2)
            if bench_attach is not None and active_energy >= 2:
                return _first_legal_selection(obs_dict, options, bench_attach)

            hammer_index = _find_option(options, 13, lambda _, option: option.get("attackId") == HAMMER_IN)
            if hammer_index is not None and active_energy >= 2 and first_type in {7, 8, 14}:
                return _first_legal_selection(obs_dict, options, hammer_index)

        if active_id == ARCHALUDON_EX:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=3)
            if active_attach is not None and active_energy < 3:
                return _first_legal_selection(obs_dict, options, active_attach)

            bench_attach = _bench_arch_attach_index(obs_dict, options, max_energy=3)
            if bench_attach is not None and active_energy >= 3:
                return _first_legal_selection(obs_dict, options, bench_attach)

            metal_defender_index = _find_option(options, 13, lambda _, option: option.get("attackId") == METAL_DEFENDER)
            if metal_defender_index is not None and active_energy >= 3 and first_type in {7, 8, 14}:
                return _first_legal_selection(obs_dict, options, metal_defender_index)

    if tempo_guard and context == 0 and active_id in ARCH_LINE:
        duraludon_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_play is not None and _arch_line_count(us) < 2:
            return _first_legal_selection(obs_dict, options, duraludon_play)

        if active_id == DURALUDON:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=2)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)

            evolve_active = _active_arch_evolve_index(obs_dict, options)
            if evolve_active is not None and (_hp(active) <= 90 or _opponent_powered(them) > 0):
                return _first_legal_selection(obs_dict, options, evolve_active)

            bench_attach = _bench_arch_attach_index(obs_dict, options, max_energy=2)
            if bench_attach is not None and active_energy >= 2:
                return _first_legal_selection(obs_dict, options, bench_attach)

            hammer_index = _find_option(options, 13)
            if hammer_index is not None and active_energy >= 2 and (first_type in {7, 14} or _int(current.get("turnActionCount"), 0) >= 4):
                return _first_legal_selection(obs_dict, options, hammer_index)

        if active_id == ARCHALUDON_EX:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=4)
            if active_attach is not None and active_energy < 4:
                return _first_legal_selection(obs_dict, options, active_attach)

            bench_attach = _bench_arch_attach_index(obs_dict, options, max_energy=4)
            if bench_attach is not None and active_energy >= 4:
                return _first_legal_selection(obs_dict, options, bench_attach)

            metal_defender_index = _find_option(options, 13, lambda _, option: option.get("attackId") == METAL_DEFENDER)
            if active_energy >= 4 and metal_defender_index is not None and first_type in {7, 8, 14}:
                return _first_legal_selection(obs_dict, options, metal_defender_index)

    if context == 0 and active_id == CINDERACE:
        if not bench_has_arch:
            duraludon_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
            if duraludon_play is not None:
                return _first_legal_selection(obs_dict, options, duraludon_play)
        if active_energy <= 0:
            attach_to_cinderace = _find_option(
                options,
                8,
                lambda _, option: _card_id(_source_card(obs_dict, option)) == METAL_ENERGY
                and _card_id(_target_card(obs_dict, option)) == CINDERACE
                and option.get("inPlayArea") == 4,
            )
            if attach_to_cinderace is not None:
                return _first_legal_selection(obs_dict, options, attach_to_cinderace)
        if bench_has_arch:
            turbo_attack = _find_option(options, 13, lambda _, option: option.get("attackId") == TURBO_FLARE)
            if turbo_attack is not None:
                return _first_legal_selection(obs_dict, options, turbo_attack)

    if memory_dive and context == 0 and active_id in ARCH_LINE:
        duraludon_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_play is not None and _arch_line_count(us) < 2:
            return _first_legal_selection(obs_dict, options, duraludon_play)

        relicanth_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == RELICANTH)
        if relicanth_play is not None and not _has_board_card(us, RELICANTH) and _arch_line_count(us) >= 1:
            return _first_legal_selection(obs_dict, options, relicanth_play)

        if active_id == DURALUDON and active_energy < (3 if _damaged(active) else 2):
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=2)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)
            if _damaged(active):
                active_attach = _active_arch_attach_index(obs_dict, options, max_energy=3)
                if active_attach is not None:
                    return _first_legal_selection(obs_dict, options, active_attach)

        if active_id == ARCHALUDON_EX and active_energy < 2:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=2)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)

        raging_hammer_index = _find_option(options, 13, lambda _, option: option.get("attackId") == RAGING_HAMMER)
        if raging_hammer_index is not None and _damaged(active):
            return _first_legal_selection(obs_dict, options, raging_hammer_index)

        if active_id == ARCHALUDON_EX and active_energy < 3:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=3)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)

        metal_defender_index = _find_option(options, 13, lambda _, option: option.get("attackId") == METAL_DEFENDER)
        if metal_defender_index is not None and active_id == ARCHALUDON_EX and active_energy >= 3 and first_type in {7, 8, 14}:
            return _first_legal_selection(obs_dict, options, metal_defender_index)

    if backup_lock and context == 0 and active_id in ARCH_LINE:
        if active_id == DURALUDON and active_energy < 2:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=2)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)

        if active_id == ARCHALUDON_EX and active_energy < 3:
            active_attach = _active_arch_attach_index(obs_dict, options, max_energy=3)
            if active_attach is not None:
                return _first_legal_selection(obs_dict, options, active_attach)

        has_backup = _has_arch_backup(us)
        development_index = _backup_development_index(obs_dict, options)
        if not has_backup and development_index is not None:
            return _first_legal_selection(obs_dict, options, development_index)

        first_target = _target_card(obs_dict, first)
        if (
            first_type == 8
            and _option_area(first) == 4
            and _card_id(first_target) in ARCH_LINE
            and _energy_count(first_target) >= (3 if _card_id(first_target) == ARCHALUDON_EX else 2)
            and development_index is not None
        ):
            return _first_legal_selection(obs_dict, options, development_index)

        live_arch_attack = _find_option(
            options,
            13,
            lambda _, option: option.get("attackId") in {HAMMER_IN, RAGING_HAMMER, METAL_DEFENDER},
        )
        if live_arch_attack is not None:
            if first_type == 14:
                return _first_legal_selection(obs_dict, options, live_arch_attack)
            if has_backup and first_type in {7, 8}:
                return _first_legal_selection(obs_dict, options, live_arch_attack)
            if development_index is None and first_type in {7, 8, 14}:
                return _first_legal_selection(obs_dict, options, live_arch_attack)

    if spread_energy and context == 0:
        duraludon_play = _find_option(options, 7, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_play is not None and _arch_line_count(us) < 2:
            return _first_legal_selection(obs_dict, options, duraludon_play)

        cape_target = _target_card(obs_dict, first)
        if (
            _card_id(_source_card(obs_dict, first)) == HERO_CAPE
            and _card_id(cape_target) == RELICANTH
        ):
            redirect = _tool_redirect_index(obs_dict, options)
            if redirect is not None:
                return _first_legal_selection(obs_dict, options, redirect)

        if active_id in ARCH_LINE:
            if active_energy < 3:
                active_attach = _find_option(
                    options,
                    8,
                    lambda _, option: _card_id(_source_card(obs_dict, option)) == METAL_ENERGY
                    and option.get("inPlayArea") == 4
                    and _card_id(_target_card(obs_dict, option)) in ARCH_LINE,
                )
                if active_attach is not None:
                    return _first_legal_selection(obs_dict, options, active_attach)

            bench_attach = _bench_arch_attach_index(obs_dict, options, max_energy=3)
            if bench_attach is not None and active_energy >= 3:
                return _first_legal_selection(obs_dict, options, bench_attach)

            metal_defender_index = _find_option(options, 13, lambda _, option: option.get("attackId") == METAL_DEFENDER)
            if active_id == ARCHALUDON_EX and active_energy >= 3 and metal_defender_index is not None:
                if first_type in {7, 14}:
                    return _first_legal_selection(obs_dict, options, metal_defender_index)
                if first_type == 8 and _card_id(_target_card(obs_dict, first)) in ARCH_LINE and _energy_count(_target_card(obs_dict, first)) >= 3:
                    return _first_legal_selection(obs_dict, options, metal_defender_index)

    return None


def _b1_patch_action(obs_dict: dict, options: list[dict]) -> list[int]:
    mode = str(PARAMS.get("b1_patch_mode") or "")
    if not mode:
        return []
    select = obs_dict.get("select") or {}
    context = select.get("context")
    if PARAMS.get("prefer_second") and context == 41:
        no_index = _find_option(options, 2)
        if no_index is not None:
            return _first_legal_selection(obs_dict, options, no_index)
    if mode in {"cinderace_turbo", "cinderace_memory_dive", "cinderace_turbo_discard", "cinderace_turbo_spread", "cinderace_turbo_spread_discard", "cinderace_tempo_guard", "cinderace_line_guard", "cinderace_backup_lock"}:
        turbo_action = _cinderace_turbo_action(
            obs_dict,
            options,
            discard_first=mode in {"cinderace_turbo_discard", "cinderace_turbo_spread_discard"},
            spread_energy=mode in {"cinderace_turbo_spread", "cinderace_turbo_spread_discard"},
            tempo_guard=mode == "cinderace_tempo_guard",
            line_guard=mode == "cinderace_line_guard",
            backup_lock=mode == "cinderace_backup_lock",
            memory_dive=mode == "cinderace_memory_dive",
        )
        if turbo_action is not None:
            return turbo_action
    current, your, us, them = _players(obs_dict)
    first = options[0]
    first_type = _type_id(first.get("type"))

    if context == 1:
        duraludon_index = _find_option(options, 3, lambda _, option: _card_id(_source_card(obs_dict, option)) == DURALUDON)
        if duraludon_index is not None:
            return _first_legal_selection(obs_dict, options, duraludon_index)

    if first_type == 12 and not _safe_retreat(us, them):
        attack_index = _find_option(options, 13)
        if attack_index is not None:
            return _first_legal_selection(obs_dict, options, attack_index)
        end_index = _find_option(options, 14)
        if end_index is not None:
            return _first_legal_selection(obs_dict, options, end_index)
        for index, option in enumerate(options[1:], start=1):
            if _type_id(option.get("type")) != 12:
                return _first_legal_selection(obs_dict, options, index)

    if mode in {"attack", "backup"}:
        active = _active(us)
        active_id = _card_id(active)
        active_energy = _energy_count(active)
        if active_id == ARCHALUDON_EX and active_energy >= 3:
            metal_defender_index = _find_option(options, 13, lambda _, option: option.get("attackId") == METAL_DEFENDER)
            if metal_defender_index is not None:
                if first_type == 14:
                    return _first_legal_selection(obs_dict, options, metal_defender_index)
                if first_type == 7 and _card_id(_source_card(obs_dict, first)) in SEARCH_DRAW | {JUMBO_ICE_CREAM, BOSS_ORDERS}:
                    return _first_legal_selection(obs_dict, options, metal_defender_index)

    if mode == "backup" and first_type == 8:
        target = _target_card(obs_dict, first)
        if _card_id(target) in ARCH_LINE and first.get("inPlayArea") == 4 and _energy_count(target) >= 2:
            bench_attach = _find_option(
                options,
                8,
                lambda _, option: option.get("inPlayArea") == 5
                and _card_id(_target_card(obs_dict, option)) in ARCH_LINE
                and _energy_count(_target_card(obs_dict, option)) < 3,
            )
            if bench_attach is not None:
                return _first_legal_selection(obs_dict, options, bench_attach)

    return _first_legal_selection(obs_dict, options, 0)


def _score_option(obs: dict, option: dict, option_index: int, options: list[dict]) -> float:
    current, your, us, them = _players(obs)
    select = obs.get("select") or {}
    context = select.get("context")
    typ = _type_id(option.get("type"))
    source = _source_card(obs, option)
    target = _target_card(obs, option)
    source_id = _card_id(source)
    target_id = _card_id(target)
    target_owner = _target_owner(obs, option)
    active = _active(us)
    active_id = _card_id(active)
    active_energy = _energy_count(active)
    arch_lines = _arch_line_count(us)
    has_backup = _has_arch_backup(us)
    attack_live = any(_type_id(item.get("type")) == 13 for item in options)
    score = -float(option_index) * _p("order_weight")

    if typ == 3 and context == 1:
        if source_id == DURALUDON:
            score += _p("duraludon_setup_active_bonus")
        elif source_id == CINDERACE:
            score += _p("cinderace_setup_active_bonus")
        elif source_id == RELICANTH:
            score += 20
        elif source_id == ARCHALUDON_EX:
            score -= 500

    if typ == 3 and context in CONSTRUCTIVE_CONTEXTS:
        if source_id == DURALUDON and arch_lines < 2:
            score += _p("setup_bonus") + _p("bench_line_bonus")
        elif source_id == ARCHALUDON_EX and any(_card_id(card) == DURALUDON for card in _board(us)):
            score += _p("setup_bonus") + 120
        elif source_id == METAL_ENERGY and _ready_arch_count(us) == 0:
            score += 90
        elif source_id in SEARCH_DRAW and arch_lines < 2:
            score += 80

    if typ == 7:
        if source_id == DURALUDON and arch_lines < 2:
            score += _p("setup_bonus") + _p("bench_line_bonus")
        elif source_id == CINDERACE:
            score += 80 if arch_lines >= 1 else -70
        elif source_id == FULL_METAL_LAB:
            score += 70
        elif source_id in SEARCH_DRAW and arch_lines < 2:
            score += 75

    if typ == 8:
        if target_id in ARCH_LINE:
            score += _p("attach_line_bonus")
            if option.get("inPlayArea") == 5:
                score += _p("bench_attach_bonus")
            if target_id == ARCHALUDON_EX and _energy_count(target) < 3:
                score += 180
            if option.get("inPlayArea") == 4 and _energy_count(target) >= 3:
                score -= _p("active_overfeed_penalty")
            if option.get("inPlayArea") == 4 and active_energy >= 2 and not has_backup:
                score -= 220
        elif target_id == CINDERACE and _ready_arch_count(us) == 0:
            score += 70
        elif target_id == RELICANTH:
            score -= 280

    if typ == 9:
        if target_id == DURALUDON and source_id == ARCHALUDON_EX:
            score += _p("evolve_bonus")
        elif target_id in ARCH_LINE:
            score += 180

    if typ == 13:
        score += _p("attack_bonus")
        attack_id = option.get("attackId")
        if attack_id == METAL_DEFENDER and active_id == ARCHALUDON_EX and active_energy >= 3:
            score += 360
        elif attack_id == RAGING_HAMMER and active_id in ARCH_LINE and active_energy >= 3:
            score += 260 if _damaged(active) else 70
        elif attack_id == HAMMER_IN and active_id == DURALUDON and active_energy >= 3:
            score -= 70
        elif attack_id == TURBO_FLARE and active_id == CINDERACE and _ready_arch_count(us) == 0:
            score += 260
        if not has_backup and _opponent_powered(them) >= 2:
            score -= _p("attack_without_backup_penalty")

    if typ == 12:
        score += 120 if _safe_retreat(us, them) else -_p("unsafe_retreat_penalty")

    if typ == 14:
        if attack_live and active_energy > 0:
            score -= _p("end_attack_penalty")
        elif _constructive_option_exists(obs, options):
            score -= 180
        else:
            score += 5

    if typ == 3 and context in TARGET_CONTEXTS and target_owner != your and isinstance(target, dict):
        if target_id in STARMIE_LINE:
            score += _p("starmie_target_bonus")
        if target_id in GATE_TARGETS:
            score += _p("target_bonus")
        if _energy_count(target) > 0:
            score += 170
        if option.get("area") == 5 or option.get("inPlayArea") == 5:
            score += 90
        if 0 < _hp(target) <= 220:
            score += _p("low_hp_target_bonus")

    if typ == 3 and context in DISCARD_CONTEXTS:
        if source_id in CORE_CARDS or source_id == METAL_ENERGY:
            score -= _p("discard_core_penalty")
        elif source_id in SEARCH_DRAW and arch_lines < 2:
            score -= 140

    if _int(us.get("deckCount"), 99) <= 8 and source_id in SEARCH_DRAW:
        score -= 140
    return score


def _ranked_action(obs_dict: dict) -> list[int]:
    select = obs_dict.get("select") or {}
    options = [option for option in (select.get("option") or []) if isinstance(option, dict)]
    if not options:
        return []
    if PARAMS.get("b1_patch_mode"):
        return _b1_patch_action(obs_dict, options)
    min_count = _int(select.get("minCount"), 0)
    max_count = _int(select.get("maxCount"), min_count or 1)
    context = select.get("context")
    if PARAMS.get("prefer_second") and context == 41:
        no_index = _find_option(options, 2)
        if no_index is not None:
            return _first_legal_selection(obs_dict, options, no_index)
    if min_count == 0 and PARAMS.get("skip_optional_setup_bench") and context == 2:
        return []
    scored = [(_score_option(obs_dict, option, index, options), index) for index, option in enumerate(options)]
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    if min_count == 0:
        chosen = [index for score, index in scored if score >= _p("optional_threshold")]
        return chosen[: max(0, min(max_count, len(chosen)))]
    if PARAMS.get("return_full_ranking"):
        return [index for _, index in scored]
    count = max(min_count, min(max_count, len(scored)))
    return [index for _, index in scored[:count]]


def agent(obs_dict: dict, config=None) -> list[int]:
    if obs_dict.get("select") is None:
        return list(DECK)
    return _ranked_action(obs_dict)
'''


def _render_main(deck: list[int], variant: str, params: dict[str, Any] | None = None) -> str:
    merged = {**DEFAULT_PARAMS, **(params or {})}
    return (
        POLICY_TEMPLATE.replace("__DECK__", repr(deck))
        .replace("__VARIANT__", variant)
        .replace("__PARAMS__", repr(merged))
    )


def _deck_from_counts(counts: dict[int, int]) -> list[int]:
    deck: list[int] = []
    for card_id, count in counts.items():
        deck.extend([card_id] * count)
    if len(deck) != 60:
        raise ValueError(f"deck has {len(deck)} cards, expected 60")
    return deck


def _safe_remove_tree(path: Path) -> None:
    resolved = path.resolve()
    artifact_root = (ROOT / "artifacts").resolve()
    if artifact_root != resolved and artifact_root not in resolved.parents:
        raise ValueError(f"refusing to remove outside artifacts: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def _copy_cg_bundle(candidate_dir: Path) -> None:
    source = ROOT / "data" / "official" / "cg"
    if not source.exists():
        source = ROOT / "artifacts" / "archaludon_metal_stabilizer_v1" / "cg"
    if not source.exists():
        raise FileNotFoundError("could not find cg runtime bundle")
    destination = candidate_dir / "cg"
    if destination.exists():
        _safe_remove_tree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_archive(candidate_dir: Path, archive_path: Path) -> str:
    if archive_path.exists():
        archive_path.unlink()
    members = [candidate_dir / "main.py", candidate_dir / "deck.csv"]
    members.extend(path for path in sorted((candidate_dir / "cg").rglob("*")) if path.is_file() and "__pycache__" not in path.parts)
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in members:
            tar.add(path, arcname=path.relative_to(candidate_dir).as_posix())
    return _sha256(archive_path)


def _git_status_short() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return [result.stderr.strip() or "git status failed"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def _meta_summary(meta_path: Path) -> dict[str, Any]:
    data = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    source = data.get("source") or {}
    return {
        "date": data.get("date"),
        "latestDate": data.get("latestDate"),
        "redirected": data.get("redirected"),
        "totalDecks": data.get("totalDecks"),
        "source": source,
        "datasetUrl": source.get("datasetUrl"),
    }


def build(output_root: Path, meta_path: Path, variant_names: list[str] | None = None) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    selected = set(variant_names or [])
    unknown = selected.difference(VARIANTS)
    if unknown:
        raise ValueError(f"unknown variants: {', '.join(sorted(unknown))}")
    meta = _meta_summary(meta_path)
    manifest: list[dict[str, Any]] = []
    for name, spec in VARIANTS.items():
        if selected and name not in selected:
            continue
        deck_counts = spec.get("deck_counts", BASE_DECK_COUNTS)
        deck = _deck_from_counts(deck_counts)
        candidate_dir = output_root / name
        _safe_remove_tree(candidate_dir)
        candidate_dir.mkdir(parents=True, exist_ok=True)
        params = {**DEFAULT_PARAMS, **spec.get("params", {})}
        (candidate_dir / "main.py").write_text(_render_main(deck, name, params), encoding="utf-8")
        (candidate_dir / "deck.csv").write_text("\n".join(str(card) for card in deck) + "\n", encoding="utf-8")
        _copy_cg_bundle(candidate_dir)
        shutil.copy2(meta_path, candidate_dir / "meta_snapshot.json")
        strategy = [
            f"# {name}",
            "",
            spec["strategy"],
            "",
            "Policy notes:",
            "- Default to the official option order unless a known bad state is present.",
            "- Veto unsafe retreats from powered Duraludon/Archaludon unless a ready bench attacker exists.",
            "- Attack instead of ending when a powered Archaludon line has a live attack.",
            "- Prioritize Duraludon setup, Archaludon evolution, bench/back-up energy, and Staryu/Mega Starmie target selection.",
            "",
            "Kaggle submission made: false",
            "",
        ]
        (candidate_dir / "strategy.md").write_text("\n".join(strategy), encoding="utf-8")
        archive_path = output_root / f"submission_{name}.tar.gz"
        sha256 = _write_archive(candidate_dir, archive_path)
        row = {
            "name": name,
            "strategy": spec["strategy"],
            "artifact_dir": str(candidate_dir),
            "archive": str(archive_path),
            "archive_sha256": sha256,
            "deck_size": len(deck),
            "deck_counts": dict(sorted(Counter(deck).items())),
            "params": params,
            "meta": meta,
            "kaggle_submission_made": False,
        }
        (candidate_dir / "build_report.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest.append(row)
    report = {
        "command": [sys.executable, *sys.argv],
        "git_status_short": _git_status_short(),
        "candidate_count": len(manifest),
        "candidates": manifest,
        "meta": meta,
        "kaggle_submission_made": False,
    }
    (output_root / "archaludon_guarded_b1_build_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build guarded-B1 Archaludon heuristic candidates.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--meta-json", type=Path, required=True)
    parser.add_argument("--variant", action="append", choices=sorted(VARIANTS))
    args = parser.parse_args(argv)
    report = build(args.output_root, args.meta_json, variant_names=args.variant)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
