from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.official import game
from ptcg.native_core import NativeCore, build_native_core
from scripts.official_shuffle_probe import OFFICIAL_LIB_PATH, official_startup_order, official_symbol_surface, order_key
from scripts.official_setup_branch_probe import probe_setup_branches


def read_deck(path: Path) -> list[int]:
    cards = [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cards) != 60:
        raise ValueError(f"deck must contain 60 cards: {path} has {len(cards)}")
    return cards


def deck_summary(path: Path, cards: list[int]) -> dict[str, Any]:
    canonical = "".join(f"{card_id}\n" for card_id in cards).encode("ascii")
    return {
        "path": str(path.resolve()),
        "count": len(cards),
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def comparison(
    *,
    comparison_id: str,
    label: str,
    status: str,
    official: Any,
    native: Any,
    note: str,
) -> dict[str, Any]:
    return {
        "id": comparison_id,
        "label": label,
        "status": status,
        "official": official,
        "native": native,
        "note": note,
    }


def count_statuses(comparisons: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass_count": sum(1 for item in comparisons if item["status"] == "pass"),
        "gap_count": sum(1 for item in comparisons if item["status"] == "gap"),
        "fail_count": sum(1 for item in comparisons if item["status"] == "fail"),
    }


def native_player_counts(player, *, include_setup_details: bool = False) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "deck_count": player.deck_count,
        "hand_count": player.hand_count,
        "prize_count": player.prize_count,
    }
    if include_setup_details:
        counts["active_card_id"] = player.active_card_id
        counts["bench_count"] = len(player.bench_card_ids)
        counts["setup_complete"] = player.setup_complete
    return counts


def native_setup_summary(setup, *, seed: int, include_setup_details: bool = False) -> dict[str, Any]:
    return {
        "seed": seed,
        "turn": setup.turn,
        "first_player": setup.first_player if setup.first_player >= 0 else None,
        "current_player": setup.current_player,
        "mulligans": list(setup.setup_mulligans),
        "mulligan_draw_choices": list(setup.setup_mulligan_draw_choices),
        "players": [
            native_player_counts(player, include_setup_details=include_setup_details)
            for player in setup.players
        ],
    }


def native_pregame_frame(setup) -> dict[str, Any]:
    return {
        "select": {
            "context": "IsFirst",
            "type": "YesNo",
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": "Yes"}, {"type": "No"}],
        },
        "current": {
            "turn": 0,
            "turnActionCount": 1,
            "yourIndex": 0,
            "firstPlayer": None,
            "supporterPlayed": False,
            "lunarCycleUsed": False,
            "fightingAttackBonus": 0,
            "stadiumPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "result": -1,
            "stadium": [],
            "looking": None,
            "players": [
                {
                    "active": [],
                    "bench": [],
                    "benchMax": 5,
                    "deckCount": setup.players[0].deck_count,
                    "discard": [],
                    "prize": [],
                    "handCount": setup.players[0].hand_count,
                    "hand": [],
                },
                {
                    "active": [],
                    "bench": [],
                    "benchMax": 5,
                    "deckCount": setup.players[1].deck_count,
                    "discard": [],
                    "prize": [],
                    "handCount": setup.players[1].hand_count,
                    "hand": [],
                },
            ],
        },
    }


def native_visible_player(setup, native_core: NativeCore, player_index: int) -> dict[str, Any]:
    player = setup.players[player_index]
    visible_player = player.to_observation_player(
        viewer_index=player_index,
        player_index=player_index,
        current_turn=setup.turn,
        stadium_card_id=setup.stadium_card_id,
        native_core=native_core,
    )
    visible_player["deck"] = [
        {
            "id": card_id,
            "playerIndex": player_index,
            "serial": (
                player.deck_card_serials[index]
                if index < len(player.deck_card_serials)
                else 700000 + player_index * 1000 + index
            ),
        }
        for index, card_id in enumerate(player.deck_card_ids)
    ]
    visible_player["prize"] = [
        {
            "id": card_id,
            "playerIndex": player_index,
            "serial": (
                player.prize_card_serials[index]
                if index < len(player.prize_card_serials)
                else 800000 + player_index * 1000 + index
            ),
        }
        for index, card_id in enumerate(player.prize_card_ids)
    ]
    return visible_player


def native_setup_active_frame(
    setup,
    native_core: NativeCore,
    *,
    acting_player: int,
    turn_action_count: int,
) -> dict[str, Any]:
    observation = setup.to_observation(player_index=acting_player, native_core=native_core)
    current = dict(observation["current"])
    current["turnActionCount"] = turn_action_count
    current["players"] = [
        native_visible_player(setup, native_core, 0),
        native_visible_player(setup, native_core, 1),
    ]
    select = dict(observation["select"])
    raw_context = select.get("context")
    select["context"] = {
        0: "Main",
        1: "SetupActivePokemon",
        2: "SetupBenchPokemon",
    }.get(raw_context, raw_context)
    select["type"] = "Card" if raw_context in {1, 2} else {0: "Action", 1: "Card"}.get(
        select.get("type"),
        select.get("type"),
    )
    if raw_context in {1, 2}:
        select["option"] = [
            {
                **option,
                "type": "Card",
            }
            for option in observation["select"]["option"]
        ]
    else:
        select["option"] = [dict(option) for option in observation["select"]["option"]]
    return {
        "select": select,
        "logs": [dict(item) for item in setup.logs],
        "current": current,
        "search_begin_input": None,
    }


def native_setup_active_option(setup, native_core: NativeCore, *, player_index: int, option_index: int) -> dict[str, Any]:
    observation = setup.to_observation(player_index=player_index, native_core=native_core)
    options = observation["select"]["option"]
    if option_index < 0 or option_index >= len(options):
        raise ValueError(
            f"setup active option index {option_index} is outside available options for player {player_index}: "
            f"{len(options)}"
        )
    return options[option_index]


def apply_native_setup_bench_option_indexes(
    setup,
    native_core: NativeCore,
    *,
    player_index: int,
    option_indexes: list[int],
) -> tuple[Any, list[dict[str, Any]]]:
    observation = setup.to_observation(player_index=player_index, native_core=native_core)
    options = observation["select"]["option"]
    removed_original_hand_indexes: list[int] = []
    selections: list[dict[str, Any]] = []
    if len(set(option_indexes)) != len(option_indexes):
        raise ValueError("setup bench option indexes must not contain duplicates")
    for option_index in option_indexes:
        if option_index < 0 or option_index >= len(options):
            raise ValueError(
                f"setup bench option index {option_index} is outside available options: {len(options)}"
            )
        option = options[option_index]
        original_hand_index = int(option["index"])
        applied_hand_index = original_hand_index - sum(
            1 for removed in removed_original_hand_indexes if removed < original_hand_index
        )
        setup = native_core.select_setup_bench(
            setup,
            player_index=player_index,
            hand_index=applied_hand_index,
        )
        removed_original_hand_indexes.append(original_hand_index)
        selections.append(
            {
                "player_index": player_index,
                "option_index": option_index,
                "original_hand_index": original_hand_index,
                "applied_hand_index": applied_hand_index,
                "card_id": int(option["cardId"]) if "cardId" in option else None,
            }
        )
    setup = native_core.finish_setup_player(setup, player_index=player_index)
    return setup, selections


def frame_player_counts(frame: dict[str, Any]) -> list[dict[str, int]]:
    return [
        {
            "deck_count": int(player.get("deckCount", -1)),
            "hand_count": int(player.get("handCount", -1)),
            "prize_count": len(player.get("prize") or []),
        }
        for player in frame.get("current", {}).get("players", [])
    ]


def frame_summary(frame: dict[str, Any]) -> dict[str, Any]:
    current = frame.get("current", {})
    players = current.get("players") or []
    return {
        "context": frame.get("select", {}).get("context"),
        "type": frame.get("select", {}).get("type"),
        "minCount": frame.get("select", {}).get("minCount"),
        "maxCount": frame.get("select", {}).get("maxCount"),
        "option_count": len(frame.get("select", {}).get("option") or []),
        "turn": current.get("turn"),
        "turnActionCount": current.get("turnActionCount"),
        "yourIndex": current.get("yourIndex"),
        "players": [
            {
                "deckCount": player.get("deckCount"),
                "handCount": player.get("handCount"),
                "prizeCount": len(player.get("prize") or []),
                "activeCount": len(player.get("active") or []),
                "benchCount": len(player.get("bench") or []),
            }
            for player in players
        ],
    }


STARTUP_PREFIX_MATCHED_FIELDS = [
    "select.context",
    "select.normalized_type",
    "select.minCount",
    "current.turn",
    "current.turnActionCount",
    "current.yourIndex",
    "current.players.deckCount",
    "current.players.handCount",
    "current.players.prizeCount",
]
STARTUP_PREFIX_EXCLUDED_FIELDS = [
    "select.maxCount",
    "select.option_count",
    "select.option.card_ids",
    "select.option.card_order",
]
SETUP_BENCH_BRANCH_DEPENDENT_FIELDS = [
    "maxCount",
    "option_count",
    "option.card_ids",
    "option.card_order",
]
STARTUP_OPTION_BRANCH_DEPENDENT_FIELDS = [
    "option_count",
    "option.card_ids",
    "option.card_order",
]
MAIN_HAND_BACKED_OPTION_TYPES = [
    "Attach",
    "Evolve",
    "Play",
]
MAIN_OPTION_BRANCH_DEPENDENT_FIELDS = [
    "option_count",
    "option.card_ids",
    "option.card_order",
    "option.type_counts",
]


OPTION_TYPE_NAMES = {
    0: "Number",
    1: "Yes",
    2: "No",
    3: "Card",
    4: "ToolCard",
    5: "EnergyCard",
    6: "Energy",
    7: "Play",
    8: "Attach",
    9: "Evolve",
    10: "Ability",
    11: "Discard",
    12: "Retreat",
    13: "Attack",
    14: "End",
    15: "Skill",
    16: "SpecialCondition",
}
MAIN_SELECTOR_REQUIRED_COMMON_OPTIONS = ["End", "Play"]
MAIN_SELECTOR_BRANCH_DEPENDENT_OPTIONS = ["Attach"]


def normalize_option_type(raw_type: Any) -> str:
    if isinstance(raw_type, str):
        return raw_type
    if isinstance(raw_type, int):
        return OPTION_TYPE_NAMES.get(raw_type, str(raw_type))
    return str(raw_type)


def normalize_selector_type(raw_type: Any, context: Any) -> str:
    if context == "Main" and raw_type == "Main":
        return "Action"
    return normalize_option_type(raw_type)


def selector_summary(frame: dict[str, Any]) -> dict[str, Any]:
    select = frame.get("select", {})
    context = select.get("context")
    raw_type = select.get("type")
    normalized_option_types = [
        normalize_option_type(option.get("type")) for option in select.get("option") or []
    ]
    option_type_counts = {
        option_type: normalized_option_types.count(option_type)
        for option_type in sorted(set(normalized_option_types))
    }
    return {
        "context": context,
        "type": raw_type,
        "normalized_type": normalize_selector_type(raw_type, context),
        "minCount": select.get("minCount"),
        "maxCount": select.get("maxCount"),
        "option_count": len(normalized_option_types),
        "normalized_option_types": sorted(set(normalized_option_types)),
        "option_type_counts": option_type_counts,
    }


def visible_hand_card_id(frame: dict[str, Any], *, player_index: int, hand_index: int) -> int | None:
    players = frame.get("current", {}).get("players") or []
    if player_index < 0 or player_index >= len(players):
        return None
    hand = players[player_index].get("hand") or []
    if hand_index < 0 or hand_index >= len(hand):
        return None
    card = hand[hand_index]
    if not isinstance(card, dict):
        return None
    raw_card_id = card.get("id", card.get("cardId"))
    try:
        return int(raw_card_id)
    except (TypeError, ValueError):
        return None


def visible_hand_card_serial(frame: dict[str, Any], *, player_index: int, hand_index: int) -> int | None:
    players = frame.get("current", {}).get("players") or []
    if player_index < 0 or player_index >= len(players):
        return None
    hand = players[player_index].get("hand") or []
    if hand_index < 0 or hand_index >= len(hand):
        return None
    card = hand[hand_index]
    if not isinstance(card, dict):
        return None
    try:
        return int(card.get("serial"))
    except (TypeError, ValueError):
        return None


def zone_card_ids(player: dict[str, Any], zone: str) -> list[int]:
    card_ids: list[int] = []
    for card in player.get(zone) or []:
        if not isinstance(card, dict):
            continue
        raw_card_id = card.get("id", card.get("cardId"))
        try:
            card_ids.append(int(raw_card_id))
        except (TypeError, ValueError):
            continue
    return card_ids


def zone_card_serials(player: dict[str, Any], zone: str) -> list[int]:
    serials: list[int] = []
    for card in player.get(zone) or []:
        if not isinstance(card, dict):
            continue
        try:
            serials.append(int(card.get("serial")))
        except (TypeError, ValueError):
            continue
    return serials


def first_zone_card_id(player: dict[str, Any], zone: str) -> int | None:
    card_ids = zone_card_ids(player, zone)
    return card_ids[0] if card_ids else None


def first_zone_card_serial(player: dict[str, Any], zone: str) -> int | None:
    serials = zone_card_serials(player, zone)
    return serials[0] if serials else None


def zone_card_field_ints(player: dict[str, Any], zone: str, field: str) -> list[int | None]:
    values: list[int | None] = []
    for card in player.get(zone) or []:
        if not isinstance(card, dict):
            continue
        raw_value = card.get(field)
        try:
            values.append(int(raw_value))
        except (TypeError, ValueError):
            values.append(None)
    return values


def first_zone_card_field_int(player: dict[str, Any], zone: str, field: str) -> int | None:
    values = zone_card_field_ints(player, zone, field)
    return values[0] if values else None


def first_pokemon_attached_card_ids(player: dict[str, Any], zone: str, attached_zone: str) -> list[int]:
    cards = player.get(zone) or []
    if not cards or not isinstance(cards[0], dict):
        return []
    attached_cards = cards[0].get(attached_zone) or []
    ids: list[int] = []
    for card in attached_cards:
        if not isinstance(card, dict):
            continue
        raw_card_id = card.get("id", card.get("cardId"))
        try:
            ids.append(int(raw_card_id))
        except (TypeError, ValueError):
            continue
    return ids


def first_pokemon_attached_card_serials(player: dict[str, Any], zone: str, attached_zone: str) -> list[int]:
    cards = player.get(zone) or []
    if not cards or not isinstance(cards[0], dict):
        return []
    attached_cards = cards[0].get(attached_zone) or []
    serials: list[int] = []
    for card in attached_cards:
        if not isinstance(card, dict):
            continue
        try:
            serials.append(int(card.get("serial")))
        except (TypeError, ValueError):
            continue
    return serials


def resolve_option_card_serial(frame: dict[str, Any], option: dict[str, Any]) -> int | None:
    area = option.get("area")
    index = option.get("index")
    raw_player_index = option.get("playerIndex", frame.get("current", {}).get("yourIndex"))
    try:
        player_index = int(raw_player_index)
        hand_index = int(index)
    except (TypeError, ValueError):
        return None
    if area not in (2, "Hand"):
        return None
    return visible_hand_card_serial(frame, player_index=player_index, hand_index=hand_index)


def ordered_zone_sync_summary(frame: dict[str, Any], *, source: str) -> dict[str, Any]:
    players = frame.get("current", {}).get("players") or []
    selector = selector_option_identity_frame(frame)
    hand_backed_selector = selector_visible_hand_option_identity_frame(
        frame,
        hand_backed_option_types=MAIN_HAND_BACKED_OPTION_TYPES,
    )
    option_indexes: list[int] = []
    option_serials: list[int] = []
    for option in frame.get("select", {}).get("option") or []:
        if normalize_option_type(option.get("type")) != "Card":
            continue
        try:
            option_indexes.append(int(option.get("index")))
        except (TypeError, ValueError):
            continue
        serial = resolve_option_card_serial(frame, option)
        if serial is not None:
            option_serials.append(serial)
    return {
        "source": source,
        "context": frame.get("select", {}).get("context"),
        "yourIndex": frame.get("current", {}).get("yourIndex"),
        "energyAttached": frame.get("current", {}).get("energyAttached"),
        "players": [
            {
                "hand_card_ids": zone_card_ids(player, "hand"),
                "deck_card_ids": zone_card_ids(player, "deck"),
                "prize_card_ids": zone_card_ids(player, "prize"),
                "active_card_id": first_zone_card_id(player, "active"),
                "active_hp": first_zone_card_field_int(player, "active", "hp"),
                "active_max_hp": first_zone_card_field_int(player, "active", "maxHp"),
                "bench_card_ids": zone_card_ids(player, "bench"),
                "bench_hps": zone_card_field_ints(player, "bench", "hp"),
                "bench_max_hps": zone_card_field_ints(player, "bench", "maxHp"),
                "hand_serials": zone_card_serials(player, "hand"),
                "deck_serials": zone_card_serials(player, "deck"),
                "prize_serials": zone_card_serials(player, "prize"),
                "active_serial": first_zone_card_serial(player, "active"),
                "active_energy_card_ids": first_pokemon_attached_card_ids(player, "active", "energyCards"),
                "active_energy_serials": first_pokemon_attached_card_serials(player, "active", "energyCards"),
                "bench_serials": zone_card_serials(player, "bench"),
                "hand_count": player.get("handCount"),
                "deck_count": player.get("deckCount"),
                "prize_count": len(player.get("prize") or []),
                "bench_count": len(player.get("bench") or []),
            }
            for player in players
        ],
        "selector_option_card_ids": selector["option_card_ids"],
        "selector_option_indexes": option_indexes,
        "selector_option_serials": option_serials,
        "selector_hand_backed_option_card_ids": hand_backed_selector["option_card_ids"],
        "selector_hand_backed_option_indexes": hand_backed_selector["option_indexes"],
        "selector_hand_backed_option_serials": hand_backed_selector["option_serials"],
        "selector_hand_backed_option_type_counts": hand_backed_selector["resolved_option_type_counts"],
        "selector_hand_backed_ignored_option_type_counts": hand_backed_selector["ignored_option_type_counts"],
        "selector_hand_backed_unresolved_option_count": hand_backed_selector["unresolved_option_count"],
        "unresolved_option_count": selector["unresolved_option_count"],
    }


def resolve_option_card_id(frame: dict[str, Any], option: dict[str, Any]) -> int | None:
    if "cardId" in option:
        try:
            return int(option["cardId"])
        except (TypeError, ValueError):
            return None
    area = option.get("area")
    index = option.get("index")
    raw_player_index = option.get("playerIndex", frame.get("current", {}).get("yourIndex"))
    try:
        player_index = int(raw_player_index)
        hand_index = int(index)
    except (TypeError, ValueError):
        return None
    if area not in (2, "Hand"):
        return None
    return visible_hand_card_id(frame, player_index=player_index, hand_index=hand_index)


def resolve_visible_hand_option_card_id(
    frame: dict[str, Any],
    option: dict[str, Any],
    *,
    allowed_option_types: list[str],
) -> int | None:
    if "cardId" in option:
        try:
            return int(option["cardId"])
        except (TypeError, ValueError):
            return None
    option_type = normalize_option_type(option.get("type"))
    if option_type not in allowed_option_types:
        return None
    area = option.get("area")
    if area not in (None, 2, "Hand"):
        return None
    raw_player_index = option.get("playerIndex", frame.get("current", {}).get("yourIndex"))
    index = option.get("index")
    try:
        player_index = int(raw_player_index)
        hand_index = int(index)
    except (TypeError, ValueError):
        return None
    return visible_hand_card_id(frame, player_index=player_index, hand_index=hand_index)


def resolve_visible_hand_option_card_serial(
    frame: dict[str, Any],
    option: dict[str, Any],
    *,
    allowed_option_types: list[str],
) -> int | None:
    option_type = normalize_option_type(option.get("type"))
    if option_type not in allowed_option_types:
        return None
    area = option.get("area")
    if area not in (None, 2, "Hand"):
        return None
    raw_player_index = option.get("playerIndex", frame.get("current", {}).get("yourIndex"))
    index = option.get("index")
    try:
        player_index = int(raw_player_index)
        hand_index = int(index)
    except (TypeError, ValueError):
        return None
    return visible_hand_card_serial(frame, player_index=player_index, hand_index=hand_index)


def selector_option_identity_frame(frame: dict[str, Any]) -> dict[str, Any]:
    select = frame.get("select", {})
    options = select.get("option") or []
    card_option_ids: list[int] = []
    unresolved_options: list[dict[str, Any]] = []
    non_card_option_count = 0
    for option_index, option in enumerate(options):
        option_type = normalize_option_type(option.get("type"))
        if option_type != "Card":
            non_card_option_count += 1
            continue
        card_id = resolve_option_card_id(frame, option)
        if card_id is None:
            unresolved_options.append(
                {
                    "option_index": option_index,
                    "area": option.get("area"),
                    "index": option.get("index"),
                    "playerIndex": option.get("playerIndex"),
                }
            )
            continue
        card_option_ids.append(card_id)
    context = select.get("context")
    return {
        "context": context,
        "normalized_type": normalize_selector_type(select.get("type"), context),
        "option_count": len(options),
        "card_option_count": len(card_option_ids) + len(unresolved_options),
        "non_card_option_count": non_card_option_count,
        "option_card_ids": card_option_ids,
        "unresolved_option_count": len(unresolved_options),
        "unresolved_options": unresolved_options,
    }


def selector_visible_hand_option_identity_frame(
    frame: dict[str, Any],
    *,
    hand_backed_option_types: list[str],
) -> dict[str, Any]:
    select = frame.get("select", {})
    options = select.get("option") or []
    option_card_ids: list[int] = []
    option_indexes: list[int] = []
    option_serials: list[int] = []
    unresolved_options: list[dict[str, Any]] = []
    resolved_option_type_counts: dict[str, int] = {}
    ignored_option_type_counts: dict[str, int] = {}
    for option_index, option in enumerate(options):
        option_type = normalize_option_type(option.get("type"))
        if option_type not in hand_backed_option_types:
            ignored_option_type_counts[option_type] = ignored_option_type_counts.get(option_type, 0) + 1
            continue
        card_id = resolve_visible_hand_option_card_id(
            frame,
            option,
            allowed_option_types=hand_backed_option_types,
        )
        if card_id is None:
            unresolved_options.append(
                {
                    "option_index": option_index,
                    "type": option_type,
                    "area": option.get("area"),
                    "index": option.get("index"),
                    "playerIndex": option.get("playerIndex"),
                }
            )
            continue
        option_card_ids.append(card_id)
        try:
            option_indexes.append(int(option.get("index")))
        except (TypeError, ValueError):
            pass
        option_serial = resolve_visible_hand_option_card_serial(
            frame,
            option,
            allowed_option_types=hand_backed_option_types,
        )
        if option_serial is not None:
            option_serials.append(option_serial)
        resolved_option_type_counts[option_type] = resolved_option_type_counts.get(option_type, 0) + 1
    context = select.get("context")
    resolved_option_types = sorted(resolved_option_type_counts)
    return {
        "context": context,
        "normalized_type": normalize_selector_type(select.get("type"), context),
        "option_count": len(options),
        "hand_backed_option_types": hand_backed_option_types,
        "resolved_option_count": len(option_card_ids),
        "resolved_option_types": resolved_option_types,
        "resolved_option_type_counts": resolved_option_type_counts,
        "ignored_option_type_counts": ignored_option_type_counts,
        "option_card_ids": option_card_ids,
        "option_indexes": option_indexes,
        "option_serials": option_serials,
        "unresolved_option_count": len(unresolved_options),
        "unresolved_options": unresolved_options,
    }


def selector_visible_hand_option_identity_comparison(
    frames: list[dict[str, Any]],
    *,
    hand_backed_option_types: list[str],
    branch_dependent_fields: list[str],
) -> dict[str, Any]:
    frame_summaries = [
        selector_visible_hand_option_identity_frame(
            frame,
            hand_backed_option_types=hand_backed_option_types,
        )
        for frame in frames
    ]
    return {
        "frame_count": len(frame_summaries),
        "hand_backed_option_types": hand_backed_option_types,
        "branch_dependent_fields": branch_dependent_fields,
        "resolved_option_count": sum(frame["resolved_option_count"] for frame in frame_summaries),
        "unresolved_option_count": sum(frame["unresolved_option_count"] for frame in frame_summaries),
        "frames": frame_summaries,
    }


def selector_option_identity_comparison(frames: list[dict[str, Any]]) -> dict[str, Any]:
    frame_summaries = [selector_option_identity_frame(frame) for frame in frames]
    return {
        "frame_count": len(frame_summaries),
        "branch_dependent_fields": STARTUP_OPTION_BRANCH_DEPENDENT_FIELDS,
        "unresolved_option_count": sum(frame["unresolved_option_count"] for frame in frame_summaries),
        "card_option_count": sum(frame["card_option_count"] for frame in frame_summaries),
        "frames": frame_summaries,
    }


def selector_core_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    option_types = set(summary.get("normalized_option_types") or [])
    return {
        **summary,
        "required_common_option_types": MAIN_SELECTOR_REQUIRED_COMMON_OPTIONS,
        "required_common_present": all(
            option_type in option_types for option_type in MAIN_SELECTOR_REQUIRED_COMMON_OPTIONS
        ),
        "branch_dependent_option_types": MAIN_SELECTOR_BRANCH_DEPENDENT_OPTIONS,
        "branch_dependent_present": {
            option_type: option_type in option_types for option_type in MAIN_SELECTOR_BRANCH_DEPENDENT_OPTIONS
        },
    }


def frame_prefix_core(frame: dict[str, Any]) -> dict[str, Any]:
    current = frame.get("current", {})
    players = current.get("players") or []
    select = frame.get("select", {})
    context = select.get("context")
    return {
        "context": context,
        "normalized_type": normalize_selector_type(select.get("type"), context),
        "minCount": select.get("minCount"),
        "turn": current.get("turn"),
        "turnActionCount": current.get("turnActionCount"),
        "yourIndex": current.get("yourIndex"),
        "players": [
            {
                "deckCount": player.get("deckCount"),
                "handCount": player.get("handCount"),
                "prizeCount": len(player.get("prize") or []),
            }
            for player in players
        ],
    }


def frame_prefix_core_comparison(frames: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "frame_count": len(frames),
        "matched_fields": STARTUP_PREFIX_MATCHED_FIELDS,
        "excluded_fields": STARTUP_PREFIX_EXCLUDED_FIELDS,
        "frames": [frame_prefix_core(frame) for frame in frames],
    }


def setup_bench_selector_bounds_summary(frame: dict[str, Any]) -> dict[str, Any]:
    select = frame.get("select", {})
    options = select.get("option") or []
    option_count = len(options)
    return {
        "context": select.get("context"),
        "type": select.get("type"),
        "minCount": select.get("minCount"),
        "maxCount": select.get("maxCount"),
        "option_count": option_count,
        "max_equals_option_count": select.get("maxCount") == option_count,
        "branch_dependent_fields": SETUP_BENCH_BRANCH_DEPENDENT_FIELDS,
        "option_types": sorted({normalize_option_type(option.get("type")) for option in options}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare clean-room native startup with official cg.VisualizeData.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-frames", type=int, default=2)
    parser.add_argument("--build-dir", type=Path, default=Path("artifacts/native_api"))
    parser.add_argument("--shuffle-probe-attempts", type=int, default=6)
    args = parser.parse_args(argv)

    opponent_deck_path = args.opponent_deck or args.deck
    deck0 = read_deck(args.deck)
    deck1 = read_deck(opponent_deck_path)
    player_deck = deck_summary(args.deck, deck0)
    opponent_deck = deck_summary(opponent_deck_path, deck1)
    first_player_choice = int(args.seed % 2)
    setup_branch_probe = probe_setup_branches(
        deck0,
        deck1,
        attempts=80,
        first_player=1,
        active_choice=0,
        next_active_choice=0,
        draw_count_choice=0,
        max_frames=max(6, args.max_frames),
    )
    official_shuffle_probe_attempts = max(2, args.shuffle_probe_attempts)
    official_shuffle_orders = [
        official_startup_order(deck0, deck1, first_player=first_player_choice)
        for _attempt in range(official_shuffle_probe_attempts)
    ]
    official_shuffle_unique_order_count = len({order_key(order) for order in official_shuffle_orders})
    official_seed_surface = official_symbol_surface(OFFICIAL_LIB_PATH)
    official_shuffle_probe = {
        "attempt_count": official_shuffle_probe_attempts,
        "unique_order_count": official_shuffle_unique_order_count,
        "deterministic_replay_available": bool(official_seed_surface["exported_seed_symbols"]),
        "first_player": first_player_choice,
        "seed_surface": official_seed_surface,
        "sample_orders": official_shuffle_orders[: min(3, len(official_shuffle_orders))],
    }

    start_data = None
    official_observation: dict[str, Any] | None = None
    official_frames_after_isfirst: list[dict[str, Any]] = []
    official_frames_after_first_active: list[dict[str, Any]] = []
    official_frames: list[dict[str, Any]] = []
    official_active_option: dict[str, Any] | None = None
    official_next_active_option: dict[str, Any] | None = None
    official_setup_bench_empty_select_probe: dict[str, Any] | None = None
    official_frames_after_setup_bench_skip: list[dict[str, Any]] = []
    official_setup_complete_main_probe: dict[str, Any] | None = None
    official_frames_after_setup_complete_main: list[dict[str, Any]] = []
    official_first_main_end_probe: dict[str, Any] | None = None
    official_frames_after_first_main_end: list[dict[str, Any]] = []
    official_first_main_end_option_index: int | None = None
    official_next_main_attach_probe: dict[str, Any] | None = None
    official_frames_after_next_main_attach: list[dict[str, Any]] = []
    official_next_main_attach_option: dict[str, Any] | None = None
    official_next_main_attack_probe: dict[str, Any] | None = None
    official_frames_after_next_main_attack: list[dict[str, Any]] = []
    official_next_main_attack_option: dict[str, Any] | None = None
    official_after_attack_attach_probe: dict[str, Any] | None = None
    official_frames_after_attack_attach: list[dict[str, Any]] = []
    official_after_attack_attach_option: dict[str, Any] | None = None
    official_after_attack_attach_attack_probe: dict[str, Any] | None = None
    official_frames_after_attack_attach_attack: list[dict[str, Any]] = []
    official_after_attack_attach_attack_option: dict[str, Any] | None = None
    official_attempt_limit = 200
    official_attempts = 0
    for attempt in range(1, official_attempt_limit + 1):
        official_started = False
        try:
            official_observation, start_data = game.battle_start(deck0, deck1)
            official_started = True
            official_observation = game.battle_select([first_player_choice])
            frames_after_isfirst = json.loads(game.visualize_data())
            if not isinstance(frames_after_isfirst, list):
                raise TypeError("official VisualizeData did not return a JSON list")
            second_candidate = frames_after_isfirst[1] if len(frames_after_isfirst) > 1 else {}
            if second_candidate.get("current", {}).get("yourIndex") != first_player_choice:
                continue
            legal_active_options = second_candidate.get("select", {}).get("option") or []
            if not legal_active_options:
                continue
            official_active_option = legal_active_options[0]
            official_observation = game.battle_select([0])
            frames_after_first_active = json.loads(game.visualize_data())
            if not isinstance(frames_after_first_active, list):
                raise TypeError("official VisualizeData did not return a JSON list")
            third_candidate = frames_after_first_active[2] if len(frames_after_first_active) > 2 else {}
            if third_candidate.get("current", {}).get("yourIndex") != 1 - first_player_choice:
                continue
            next_active_options = third_candidate.get("select", {}).get("option") or []
            if not next_active_options:
                continue
            official_next_active_option = next_active_options[0]
            official_observation = game.battle_select([0])
            official_frames = json.loads(game.visualize_data())
            if not isinstance(official_frames, list):
                raise TypeError("official VisualizeData did not return a JSON list")
            fourth_candidate = official_frames[3] if len(official_frames) > 3 else {}
            if (
                fourth_candidate.get("select", {}).get("context") != "SetupBenchPokemon"
                or fourth_candidate.get("current", {}).get("yourIndex") != first_player_choice
            ):
                continue
            official_setup_bench_empty_select_probe = {
                "select": [],
                "before": frame_summary(fourth_candidate),
            }
            try:
                game.battle_select([])
                after_empty_select_frames = json.loads(game.visualize_data())
                if not isinstance(after_empty_select_frames, list):
                    raise TypeError("official VisualizeData did not return a JSON list after empty setup Bench select")
                official_frames_after_setup_bench_skip = after_empty_select_frames
                official_setup_bench_empty_select_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_empty_select_frames),
                        "after_last_frame": frame_summary(after_empty_select_frames[-1])
                        if after_empty_select_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_setup_bench_empty_select_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            after_empty_select_summary = official_setup_bench_empty_select_probe.get("after_last_frame")
            if (
                official_setup_bench_empty_select_probe.get("accepted") is not True
                or not isinstance(after_empty_select_summary, dict)
                or after_empty_select_summary.get("context") != "SetupBenchPokemon"
                or after_empty_select_summary.get("yourIndex") != 1 - first_player_choice
            ):
                continue
            official_setup_complete_main_probe = {
                "selection_sequence": [[], []],
                "before": after_empty_select_summary,
            }
            try:
                game.battle_select([])
                after_setup_complete_frames = json.loads(game.visualize_data())
                if not isinstance(after_setup_complete_frames, list):
                    raise TypeError("official VisualizeData did not return a JSON list after both setup Bench skips")
                official_frames_after_setup_complete_main = after_setup_complete_frames
                official_setup_complete_main_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_setup_complete_frames),
                        "after_last_frame": frame_summary(after_setup_complete_frames[-1])
                        if after_setup_complete_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_setup_complete_main_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            setup_complete_main_summary = official_setup_complete_main_probe.get("after_last_frame")
            if (
                official_setup_complete_main_probe.get("accepted") is not True
                or not isinstance(setup_complete_main_summary, dict)
                or setup_complete_main_summary.get("context") != "Main"
                or setup_complete_main_summary.get("yourIndex") != first_player_choice
                or setup_complete_main_summary.get("turn") != 1
            ):
                continue
            setup_complete_main_frame = after_setup_complete_frames[-1]
            main_options = setup_complete_main_frame.get("select", {}).get("option") or []
            first_main_end_option_index = next(
                (index for index, option in enumerate(main_options) if option.get("type") == "End"),
                None,
            )
            if first_main_end_option_index is None:
                continue
            official_first_main_end_probe = {
                "selection": [first_main_end_option_index],
                "before": frame_summary(setup_complete_main_frame),
            }
            try:
                game.battle_select([first_main_end_option_index])
                after_first_main_end_frames = json.loads(game.visualize_data())
                if not isinstance(after_first_main_end_frames, list):
                    raise TypeError("official VisualizeData did not return a JSON list after first Main End")
                official_frames_after_first_main_end = after_first_main_end_frames
                official_first_main_end_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_first_main_end_frames),
                        "after_last_frame": frame_summary(after_first_main_end_frames[-1])
                        if after_first_main_end_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_first_main_end_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            first_main_end_summary = official_first_main_end_probe.get("after_last_frame")
            if (
                official_first_main_end_probe.get("accepted") is not True
                or not isinstance(first_main_end_summary, dict)
                or first_main_end_summary.get("context") != "Main"
                or first_main_end_summary.get("yourIndex") != 1 - first_player_choice
                or first_main_end_summary.get("turn") != 2
            ):
                continue
            first_main_end_frame = after_first_main_end_frames[-1]
            next_main_options = first_main_end_frame.get("select", {}).get("option") or []
            next_main_attach_option_index = next(
                (
                    index
                    for index, option in enumerate(next_main_options)
                    if option.get("type") == "Attach"
                    and option.get("inPlayArea") == 4
                    and option.get("inPlayIndex") == 0
                ),
                None,
            )
            if next_main_attach_option_index is None:
                continue
            official_next_main_attach_option = next_main_options[next_main_attach_option_index]
            official_next_main_attach_probe = {
                "selection": [next_main_attach_option_index],
                "option": official_next_main_attach_option,
                "before": frame_summary(first_main_end_frame),
            }
            try:
                game.battle_select([next_main_attach_option_index])
                after_next_main_attach_frames = json.loads(game.visualize_data())
                if not isinstance(after_next_main_attach_frames, list):
                    raise TypeError("official VisualizeData did not return a JSON list after next Main Attach")
                official_frames_after_next_main_attach = after_next_main_attach_frames
                official_next_main_attach_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_next_main_attach_frames),
                        "after_last_frame": frame_summary(after_next_main_attach_frames[-1])
                        if after_next_main_attach_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_next_main_attach_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            next_main_attach_summary = official_next_main_attach_probe.get("after_last_frame")
            if (
                official_next_main_attach_probe.get("accepted") is not True
                or not isinstance(next_main_attach_summary, dict)
                or next_main_attach_summary.get("context") != "Main"
                or next_main_attach_summary.get("yourIndex") != 1 - first_player_choice
                or next_main_attach_summary.get("turn") != 2
            ):
                continue
            next_main_attach_frame = after_next_main_attach_frames[-1]
            next_main_attack_options = next_main_attach_frame.get("select", {}).get("option") or []
            next_main_attack_option_index = next(
                (
                    index
                    for index, option in enumerate(next_main_attack_options)
                    if normalize_option_type(option.get("type")) == "Attack"
                ),
                None,
            )
            if next_main_attack_option_index is None:
                continue
            official_next_main_attack_option = next_main_attack_options[next_main_attack_option_index]
            official_next_main_attack_probe = {
                "selection": [next_main_attack_option_index],
                "option": official_next_main_attack_option,
                "before": frame_summary(next_main_attach_frame),
            }
            try:
                game.battle_select([next_main_attack_option_index])
                after_next_main_attack_frames = json.loads(game.visualize_data())
                if not isinstance(after_next_main_attack_frames, list):
                    raise TypeError("official VisualizeData did not return a JSON list after next Main Attack")
                official_frames_after_next_main_attack = after_next_main_attack_frames
                official_next_main_attack_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_next_main_attack_frames),
                        "after_last_frame": frame_summary(after_next_main_attack_frames[-1])
                        if after_next_main_attack_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_next_main_attack_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            next_main_attack_summary = official_next_main_attack_probe.get("after_last_frame")
            if (
                official_next_main_attack_probe.get("accepted") is not True
                or not isinstance(next_main_attack_summary, dict)
                or next_main_attack_summary.get("context") != "Main"
                or next_main_attack_summary.get("yourIndex") != first_player_choice
                or next_main_attack_summary.get("turn") != 3
            ):
                continue
            after_attack_frame = after_next_main_attack_frames[-1]
            after_attack_options = after_attack_frame.get("select", {}).get("option") or []
            after_attack_attach_option_index = next(
                (
                    index
                    for index, option in enumerate(after_attack_options)
                    if normalize_option_type(option.get("type")) == "Attach"
                    and option.get("inPlayArea") == 4
                    and option.get("inPlayIndex") == 0
                ),
                None,
            )
            if after_attack_attach_option_index is None:
                continue
            official_after_attack_attach_option = after_attack_options[after_attack_attach_option_index]
            official_after_attack_attach_probe = {
                "selection": [after_attack_attach_option_index],
                "option": official_after_attack_attach_option,
                "before": frame_summary(after_attack_frame),
            }
            try:
                game.battle_select([after_attack_attach_option_index])
                after_attack_attach_frames = json.loads(game.visualize_data())
                if not isinstance(after_attack_attach_frames, list):
                    raise TypeError("official VisualizeData did not return a JSON list after post-attack Attach")
                official_frames_after_attack_attach = after_attack_attach_frames
                official_after_attack_attach_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_attack_attach_frames),
                        "after_last_frame": frame_summary(after_attack_attach_frames[-1])
                        if after_attack_attach_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_after_attack_attach_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            after_attack_attach_summary = official_after_attack_attach_probe.get("after_last_frame")
            if (
                official_after_attack_attach_probe.get("accepted") is not True
                or not isinstance(after_attack_attach_summary, dict)
                or after_attack_attach_summary.get("context") != "Main"
                or after_attack_attach_summary.get("yourIndex") != first_player_choice
                or after_attack_attach_summary.get("turn") != 3
            ):
                continue
            after_attack_attach_frame = after_attack_attach_frames[-1]
            after_attack_attach_options = after_attack_attach_frame.get("select", {}).get("option") or []
            after_attack_attach_attack_option_index = next(
                (
                    index
                    for index, option in enumerate(after_attack_attach_options)
                    if normalize_option_type(option.get("type")) == "Attack"
                ),
                None,
            )
            if after_attack_attach_attack_option_index is None:
                continue
            official_after_attack_attach_attack_option = after_attack_attach_options[
                after_attack_attach_attack_option_index
            ]
            official_after_attack_attach_attack_probe = {
                "selection": [after_attack_attach_attack_option_index],
                "option": official_after_attack_attach_attack_option,
                "before": frame_summary(after_attack_attach_frame),
            }
            try:
                game.battle_select([after_attack_attach_attack_option_index])
                after_attack_attach_attack_frames = json.loads(game.visualize_data())
                if not isinstance(after_attack_attach_attack_frames, list):
                    raise TypeError(
                        "official VisualizeData did not return a JSON list after post-attach Attack"
                    )
                official_frames_after_attack_attach_attack = after_attack_attach_attack_frames
                official_after_attack_attach_attack_probe.update(
                    {
                        "accepted": True,
                        "after_frame_count": len(after_attack_attach_attack_frames),
                        "after_last_frame": frame_summary(after_attack_attach_attack_frames[-1])
                        if after_attack_attach_attack_frames
                        else None,
                    }
                )
            except Exception as exc:  # pragma: no cover - retained as live official-wrapper evidence.
                official_after_attack_attach_attack_probe.update(
                    {
                        "accepted": False,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            after_attack_attach_attack_summary = official_after_attack_attach_attack_probe.get("after_last_frame")
            if (
                official_after_attack_attach_attack_probe.get("accepted") is not True
                or not isinstance(after_attack_attach_attack_summary, dict)
                or after_attack_attach_attack_summary.get("context") != "Main"
                or after_attack_attach_attack_summary.get("yourIndex") != 1 - first_player_choice
                or after_attack_attach_attack_summary.get("turn") != 4
            ):
                continue
            official_first_main_end_option_index = first_main_end_option_index
            official_frames_after_isfirst = frames_after_isfirst
            official_frames_after_first_active = frames_after_first_active
            official_attempts = attempt
            break
        finally:
            if official_started:
                game.battle_finish()
    if (
        start_data is None
        or official_observation is None
        or not official_frames
        or official_active_option is None
        or official_next_active_option is None
        or official_first_main_end_option_index is None
        or official_next_main_attach_option is None
        or official_next_main_attack_option is None
        or official_after_attack_attach_option is None
        or official_after_attack_attach_attack_option is None
        or not official_frames_after_next_main_attach
        or not official_frames_after_next_main_attack
        or not official_frames_after_attack_attach
        or not official_frames_after_attack_attach_attack
        or not official_frames_after_first_main_end
    ):
        raise RuntimeError(
            "official engine did not produce a comparable ordered parity chain "
            f"within {official_attempt_limit} attempts"
        )

    first_frame = official_frames[0] if official_frames else {}
    second_frame = official_frames[1] if len(official_frames) > 1 else {}
    third_frame = official_frames[2] if len(official_frames) > 2 else {}
    fourth_frame = official_frames[3] if len(official_frames) > 3 else {}

    library_path = build_native_core(build_dir=args.build_dir)
    native_core = NativeCore(library_path)
    native_deck = native_core.load_deck_csv(args.deck)
    native_pregame = native_core.start_battle_pregame(args.deck, opponent_deck_path)
    native_first_frame = native_pregame_frame(native_pregame)
    native_post_isfirst = native_core.select_pregame_first_player(
        native_pregame,
        first_player=first_player_choice,
        seed=args.seed,
    )
    native_post_isfirst_repeat = native_core.select_pregame_first_player(
        native_pregame,
        first_player=first_player_choice,
        seed=args.seed,
    )
    native_post_isfirst_next_seed = native_core.select_pregame_first_player(
        native_pregame,
        first_player=first_player_choice,
        seed=args.seed + 1,
    )
    native_startup_order_probe = {
        "same_seed_deterministic": native_post_isfirst == native_post_isfirst_repeat,
        "different_seed_changes_order": native_post_isfirst != native_post_isfirst_next_seed,
        "seed": args.seed,
    }
    native_second_frame = native_setup_active_frame(
        native_post_isfirst,
        native_core,
        acting_player=first_player_choice,
        turn_action_count=2,
    )
    official_post_isfirst_ordered_zone_sync = ordered_zone_sync_summary(
        second_frame,
        source="official VisualizeData observed ordered hand/deck zones",
    )
    official_sync_players = official_post_isfirst_ordered_zone_sync["players"]
    native_post_isfirst_ordered_setup = native_core.start_battle_setup_from_ordered_zones(
        player0_hand_card_ids=official_sync_players[0]["hand_card_ids"],
        player0_deck_card_ids=official_sync_players[0]["deck_card_ids"],
        player0_hand_serials=official_sync_players[0]["hand_serials"],
        player0_deck_serials=official_sync_players[0]["deck_serials"],
        player1_hand_card_ids=official_sync_players[1]["hand_card_ids"],
        player1_deck_card_ids=official_sync_players[1]["deck_card_ids"],
        player1_hand_serials=official_sync_players[1]["hand_serials"],
        player1_deck_serials=official_sync_players[1]["deck_serials"],
        first_player=first_player_choice,
    )
    native_post_isfirst_ordered_frame = native_setup_active_frame(
        native_post_isfirst_ordered_setup,
        native_core,
        acting_player=first_player_choice,
        turn_action_count=2,
    )
    native_post_isfirst_ordered_zone_sync = ordered_zone_sync_summary(
        native_post_isfirst_ordered_frame,
        source="official observed ordered hand/deck zones",
    )
    next_setup_player = 1 - first_player_choice
    native_ordered_active_option = native_setup_active_option(
        native_post_isfirst_ordered_setup,
        native_core,
        player_index=first_player_choice,
        option_index=0,
    )
    native_post_ordered_first_active = native_core.select_setup_active(
        native_post_isfirst_ordered_setup,
        player_index=first_player_choice,
        hand_index=int(native_ordered_active_option["index"]),
    )
    native_post_ordered_first_active_frame = native_setup_active_frame(
        native_post_ordered_first_active,
        native_core,
        acting_player=next_setup_player,
        turn_action_count=3,
    )
    official_post_ordered_first_active_zone_sync = ordered_zone_sync_summary(
        third_frame,
        source="official VisualizeData after first setup Active selection",
    )
    native_post_ordered_first_active_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_first_active_frame,
        source="official observed ordered hand/deck zones after native first setup Active selection",
    )
    native_ordered_next_active_option = native_setup_active_option(
        native_post_ordered_first_active,
        native_core,
        player_index=next_setup_player,
        option_index=0,
    )
    native_post_ordered_both_actives = native_core.select_setup_active(
        native_post_ordered_first_active,
        player_index=next_setup_player,
        hand_index=int(native_ordered_next_active_option["index"]),
    )
    native_post_ordered_both_actives = native_core.deal_setup_prizes(native_post_ordered_both_actives)
    native_post_ordered_both_actives_frame = native_setup_active_frame(
        native_post_ordered_both_actives,
        native_core,
        acting_player=first_player_choice,
        turn_action_count=4,
    )
    official_post_ordered_both_actives_setup_bench_zone_sync = ordered_zone_sync_summary(
        fourth_frame,
        source="official VisualizeData after both setup Active selections and setup prize deal",
    )
    native_post_ordered_both_actives_setup_bench_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_both_actives_frame,
        source=(
            "official observed ordered hand/deck zones after native both setup Active "
            "selections and setup prize deal"
        ),
    )
    native_post_ordered_first_setup_bench_skip = native_core.finish_setup_player(
        native_post_ordered_both_actives,
        player_index=first_player_choice,
    )
    native_post_ordered_first_setup_bench_skip_frame = native_setup_active_frame(
        native_post_ordered_first_setup_bench_skip,
        native_core,
        acting_player=next_setup_player,
        turn_action_count=5,
    )
    official_post_ordered_first_setup_bench_skip_zone_sync = ordered_zone_sync_summary(
        official_frames_after_setup_bench_skip[-1],
        source="official VisualizeData after first setup Bench skip",
    )
    native_post_ordered_first_setup_bench_skip_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_first_setup_bench_skip_frame,
        source="official observed ordered zones after native first setup Bench skip",
    )
    native_post_ordered_setup_complete = native_core.finish_setup_player(
        native_post_ordered_first_setup_bench_skip,
        player_index=next_setup_player,
    )
    native_post_ordered_setup_complete_main = native_core.begin_first_turn(native_post_ordered_setup_complete)
    native_post_ordered_setup_complete_main_frame = native_setup_active_frame(
        native_post_ordered_setup_complete_main,
        native_core,
        acting_player=native_post_ordered_setup_complete_main.current_player,
        turn_action_count=1,
    )
    official_post_ordered_both_setup_bench_skips_main_zone_sync = ordered_zone_sync_summary(
        official_frames_after_setup_complete_main[-1],
        source="official VisualizeData after both setup Bench skips into first Main",
    )
    native_post_ordered_both_setup_bench_skips_main_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_setup_complete_main_frame,
        source="official observed ordered zones after native both setup Bench skips into first Main",
    )
    native_post_ordered_first_main_end = native_core.end_turn(native_post_ordered_setup_complete_main)
    native_post_ordered_first_main_end_frame = native_setup_active_frame(
        native_post_ordered_first_main_end,
        native_core,
        acting_player=native_post_ordered_first_main_end.current_player,
        turn_action_count=1,
    )
    official_post_ordered_first_main_end_next_main_zone_sync = ordered_zone_sync_summary(
        official_frames_after_first_main_end[-1],
        source="official VisualizeData after first Main End into next Main",
    )
    native_post_ordered_first_main_end_next_main_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_first_main_end_frame,
        source="official observed ordered zones after native first Main End into next Main",
    )
    native_post_ordered_next_main_attach = native_core.attach_energy(
        native_post_ordered_first_main_end,
        hand_index=int(official_next_main_attach_option["index"]),
        in_play_area=int(official_next_main_attach_option["inPlayArea"]),
        in_play_index=int(official_next_main_attach_option["inPlayIndex"]),
    )
    native_post_ordered_next_main_attach_frame = native_setup_active_frame(
        native_post_ordered_next_main_attach,
        native_core,
        acting_player=native_post_ordered_next_main_attach.current_player,
        turn_action_count=2,
    )
    official_post_ordered_next_main_attach_active_zone_sync = ordered_zone_sync_summary(
        official_frames_after_next_main_attach[-1],
        source="official VisualizeData after next Main Attach to active",
    )
    native_post_ordered_next_main_attach_active_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_next_main_attach_frame,
        source="official observed ordered zones after native next Main Attach to active",
    )
    native_post_ordered_next_main_attack = native_core.use_attack(
        native_post_ordered_next_main_attach,
        attack_id=int(official_next_main_attack_option["attackId"]),
    )
    native_post_ordered_next_main_attack_frame = native_setup_active_frame(
        native_post_ordered_next_main_attack,
        native_core,
        acting_player=native_post_ordered_next_main_attack.current_player,
        turn_action_count=1,
    )
    official_post_ordered_next_main_attack_zone_sync = ordered_zone_sync_summary(
        official_frames_after_next_main_attack[-1],
        source="official VisualizeData after next Main Attack",
    )
    native_post_ordered_next_main_attack_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_next_main_attack_frame,
        source="official observed ordered zones after native next Main Attack",
    )
    native_post_ordered_after_attack_attach = native_core.attach_energy(
        native_post_ordered_next_main_attack,
        hand_index=int(official_after_attack_attach_option["index"]),
        in_play_area=int(official_after_attack_attach_option["inPlayArea"]),
        in_play_index=int(official_after_attack_attach_option["inPlayIndex"]),
    )
    native_post_ordered_after_attack_attach_frame = native_setup_active_frame(
        native_post_ordered_after_attack_attach,
        native_core,
        acting_player=native_post_ordered_after_attack_attach.current_player,
        turn_action_count=2,
    )
    official_post_ordered_after_attack_attach_active_zone_sync = ordered_zone_sync_summary(
        official_frames_after_attack_attach[-1],
        source="official VisualizeData after post-attack Attach to active",
    )
    native_post_ordered_after_attack_attach_active_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_after_attack_attach_frame,
        source="official observed ordered zones after native post-attack Attach to active",
    )
    native_post_ordered_after_attack_attach_attack = native_core.use_attack(
        native_post_ordered_after_attack_attach,
        attack_id=int(official_after_attack_attach_attack_option["attackId"]),
    )
    native_post_ordered_after_attack_attach_attack_frame = native_setup_active_frame(
        native_post_ordered_after_attack_attach_attack,
        native_core,
        acting_player=native_post_ordered_after_attack_attach_attack.current_player,
        turn_action_count=1,
    )
    official_post_ordered_after_attack_attach_attack_zone_sync = ordered_zone_sync_summary(
        official_frames_after_attack_attach_attack[-1],
        source="official VisualizeData after post-attach return Attack",
    )
    native_post_ordered_after_attack_attach_attack_zone_sync = ordered_zone_sync_summary(
        native_post_ordered_after_attack_attach_attack_frame,
        source="official observed ordered zones after native post-attach return Attack",
    )
    native_active_option = native_setup_active_option(
        native_post_isfirst,
        native_core,
        player_index=first_player_choice,
        option_index=0,
    )
    native_post_setup_active = native_core.select_setup_active(
        native_post_isfirst,
        player_index=first_player_choice,
        hand_index=int(native_active_option["index"]),
    )
    native_third_frame = native_setup_active_frame(
        native_post_setup_active,
        native_core,
        acting_player=next_setup_player,
        turn_action_count=3,
    )
    native_next_active_option = native_setup_active_option(
        native_post_setup_active,
        native_core,
        player_index=next_setup_player,
        option_index=0,
    )
    native_post_both_actives = native_core.select_setup_active(
        native_post_setup_active,
        player_index=next_setup_player,
        hand_index=int(native_next_active_option["index"]),
    )
    native_post_both_actives = native_core.deal_setup_prizes(native_post_both_actives)
    native_fourth_frame = native_setup_active_frame(
        native_post_both_actives,
        native_core,
        acting_player=first_player_choice,
        turn_action_count=4,
    )
    native_post_setup_bench_skip = native_core.finish_setup_player(
        native_post_both_actives,
        player_index=first_player_choice,
    )
    native_post_setup_bench_skip_frame = native_setup_active_frame(
        native_post_setup_bench_skip,
        native_core,
        acting_player=next_setup_player,
        turn_action_count=5,
    )
    native_post_setup_complete = native_core.finish_setup_player(
        native_post_setup_bench_skip,
        player_index=next_setup_player,
    )
    native_post_setup_complete_main = native_core.begin_first_turn(native_post_setup_complete)
    native_post_setup_complete_main_frame = native_setup_active_frame(
        native_post_setup_complete_main,
        native_core,
        acting_player=native_post_setup_complete_main.current_player,
        turn_action_count=1,
    )
    native_post_first_main_end = native_core.end_turn(native_post_setup_complete_main)
    native_post_first_main_end_frame = native_setup_active_frame(
        native_post_first_main_end,
        native_core,
        acting_player=native_post_first_main_end.current_player,
        turn_action_count=1,
    )
    native_optional_pregame = native_core.start_battle_pregame(args.deck, opponent_deck_path)
    native_optional_setup = native_core.select_pregame_first_player(
        native_optional_pregame,
        first_player=1,
        seed=3,
    )
    native_optional_first_active = native_setup_active_option(
        native_optional_setup,
        native_core,
        player_index=1,
        option_index=0,
    )
    native_optional_setup = native_core.select_setup_active(
        native_optional_setup,
        player_index=1,
        hand_index=int(native_optional_first_active["index"]),
    )
    native_optional_next_active = native_setup_active_option(
        native_optional_setup,
        native_core,
        player_index=0,
        option_index=0,
    )
    native_optional_setup = native_core.select_setup_active(
        native_optional_setup,
        player_index=0,
        hand_index=int(native_optional_next_active["index"]),
    )
    native_optional_setup = native_core.deal_setup_prizes(native_optional_setup)
    native_optional_prompt = native_setup_active_frame(
        native_optional_setup,
        native_core,
        acting_player=1,
        turn_action_count=4,
    )
    native_optional_skip_setup = native_core.finish_setup_player(
        native_optional_setup,
        player_index=1,
    )
    native_optional_skip_frame = native_setup_active_frame(
        native_optional_skip_setup,
        native_core,
        acting_player=0,
        turn_action_count=5,
    )
    native_optional_multi_setup, native_optional_multi_selections = apply_native_setup_bench_option_indexes(
        native_optional_setup,
        native_core,
        player_index=1,
        option_indexes=[0, 1],
    )
    native_optional_multi_frame = native_setup_active_frame(
        native_optional_multi_setup,
        native_core,
        acting_player=0,
        turn_action_count=5,
    )
    native_setup_bench_optional_replay = {
        "prompt": {
            "context": native_optional_prompt.get("select", {}).get("context"),
            "minCount": native_optional_prompt.get("select", {}).get("minCount"),
            "maxCount": native_optional_prompt.get("select", {}).get("maxCount"),
            "option_count": len(native_optional_prompt.get("select", {}).get("option") or []),
        },
        "skip": {
            "setup": native_setup_summary(
                native_optional_skip_setup,
                seed=3,
                include_setup_details=True,
            ),
            "first_frame": native_optional_skip_frame,
        },
        "multi": {
            "setup": native_setup_summary(
                native_optional_multi_setup,
                seed=3,
                include_setup_details=True,
            ),
            "selections": native_optional_multi_selections,
            "first_frame": native_optional_multi_frame,
        },
    }
    draw_count_probe_deck_path = Path(args.build_dir) / "native_draw_count_probe_sparse_deck.csv"
    draw_count_probe_deck_path.parent.mkdir(parents=True, exist_ok=True)
    draw_count_probe_deck_path.write_text("675\n" + ("1227\n" * 59), encoding="utf-8")
    native_draw_count_pregame = native_core.start_battle_pregame(draw_count_probe_deck_path, opponent_deck_path)
    native_draw_count_setup = native_core.select_pregame_first_player(
        native_draw_count_pregame,
        first_player=1,
        seed=1,
    )
    native_draw_first_active_option = native_setup_active_option(
        native_draw_count_setup,
        native_core,
        player_index=1,
        option_index=0,
    )
    native_draw_count_setup = native_core.select_setup_active(
        native_draw_count_setup,
        player_index=1,
        hand_index=int(native_draw_first_active_option["index"]),
    )
    native_draw_next_active_option = native_setup_active_option(
        native_draw_count_setup,
        native_core,
        player_index=0,
        option_index=0,
    )
    native_draw_count_setup = native_core.select_setup_active(
        native_draw_count_setup,
        player_index=0,
        hand_index=int(native_draw_next_active_option["index"]),
    )
    native_draw_count_setup = native_core.deal_setup_prizes(native_draw_count_setup)
    native_draw_pending_player = native_draw_count_setup.pending_draw_count_player()
    native_draw_max_count = (
        max(
            0,
            native_draw_count_setup.setup_mulligans[1 - native_draw_pending_player]
            - native_draw_count_setup.setup_mulligans[native_draw_pending_player],
        )
        if native_draw_pending_player is not None
        else 0
    )
    native_draw_choice = min(2, native_draw_max_count)
    if native_draw_pending_player is not None:
        native_draw_count_setup = native_core.apply_pregame_draw_count(
            native_draw_count_setup,
            player_index=native_draw_pending_player,
            count=native_draw_choice,
        )
    native_draw_count_frame = native_setup_active_frame(
        native_draw_count_setup,
        native_core,
        acting_player=native_draw_pending_player if native_draw_pending_player is not None else 1,
        turn_action_count=5,
    )
    native_draw_count_replay = {
        "phase": "post_mulligan_draw_count_selected"
        if native_draw_pending_player is not None
        else "no_native_draw_count_prompt",
        "deck": str(draw_count_probe_deck_path),
        "setup": native_setup_summary(
            native_draw_count_setup,
            seed=1,
            include_setup_details=True,
        ),
        "draw_count_selection": (
            {
                "player_index": native_draw_pending_player,
                "count": native_draw_choice,
                "max_count": native_draw_max_count,
            }
            if native_draw_pending_player is not None
            else None
        ),
        "first_frame": native_draw_count_frame,
    }
    native_setup_bench_option: dict[str, Any] | None = None
    native_post_setup_bench = None
    native_fifth_frame = None
    native_fourth_options = native_fourth_frame.get("select", {}).get("option") or []
    if native_fourth_options:
        native_setup_bench_option = native_fourth_options[0]
        native_post_setup_bench = native_core.select_setup_bench(
            native_post_both_actives,
            player_index=first_player_choice,
            hand_index=int(native_setup_bench_option["index"]),
        )
        native_post_setup_bench = native_core.finish_setup_player(
            native_post_setup_bench,
            player_index=first_player_choice,
        )
        native_fifth_frame = native_setup_active_frame(
            native_post_setup_bench,
            native_core,
            acting_player=next_setup_player,
            turn_action_count=5,
        )
    native_pregame_players = [native_player_counts(player) for player in native_pregame.players]
    native_post_isfirst_players = [native_player_counts(player) for player in native_post_isfirst.players]
    native_post_setup_active_players = [native_player_counts(player) for player in native_post_setup_active.players]
    native_post_both_actives_players = [native_player_counts(player) for player in native_post_both_actives.players]

    official_first_player = first_frame.get("current", {}).get("players", [{}])[0]
    official_first_context = first_frame.get("select", {}).get("context")
    official_first_type = first_frame.get("select", {}).get("type")
    official_first_turn_action_count = first_frame.get("current", {}).get("turnActionCount")
    official_deck_count = official_first_player.get("deckCount")
    official_second_context = second_frame.get("select", {}).get("context")
    official_second_type = second_frame.get("select", {}).get("type")
    official_second_players = frame_player_counts(second_frame)
    official_third_context = third_frame.get("select", {}).get("context")
    official_third_type = third_frame.get("select", {}).get("type")
    official_third_players = frame_player_counts(third_frame)
    official_third_your_index = third_frame.get("current", {}).get("yourIndex")
    official_fourth_context = fourth_frame.get("select", {}).get("context")
    official_fourth_type = fourth_frame.get("select", {}).get("type")
    official_fourth_players = frame_player_counts(fourth_frame)
    official_fourth_your_index = fourth_frame.get("current", {}).get("yourIndex")
    official_setup_bench_skip_frame = (
        official_frames_after_setup_bench_skip[-1] if official_frames_after_setup_bench_skip else {}
    )
    official_setup_bench_skip_summary = (
        frame_summary(official_setup_bench_skip_frame) if official_setup_bench_skip_frame else None
    )
    official_setup_complete_main_frame = (
        official_frames_after_setup_complete_main[-1] if official_frames_after_setup_complete_main else {}
    )
    official_setup_complete_main_summary = (
        frame_summary(official_setup_complete_main_frame) if official_setup_complete_main_frame else None
    )
    official_setup_complete_main_selector = (
        selector_summary(official_setup_complete_main_frame) if official_setup_complete_main_frame else None
    )
    official_setup_complete_main_selector_core = selector_core_summary(official_setup_complete_main_selector)
    official_first_main_end_frame = (
        official_frames_after_first_main_end[-1] if official_frames_after_first_main_end else {}
    )
    official_first_main_end_summary = (
        frame_summary(official_first_main_end_frame) if official_first_main_end_frame else None
    )
    official_first_main_end_selector = (
        selector_summary(official_first_main_end_frame) if official_first_main_end_frame else None
    )
    official_first_main_end_selector_core = selector_core_summary(official_first_main_end_selector)
    official_setup_player_index = second_frame.get("current", {}).get("yourIndex")
    official_next_setup_player = 1 - official_setup_player_index if official_setup_player_index in (0, 1) else None
    native_first_context = native_first_frame.get("select", {}).get("context")
    native_first_type = native_first_frame.get("select", {}).get("type")
    native_first_turn_action_count = native_first_frame.get("current", {}).get("turnActionCount")
    native_second_context = native_second_frame.get("select", {}).get("context")
    native_second_type = native_second_frame.get("select", {}).get("type")
    native_third_context = native_third_frame.get("select", {}).get("context")
    native_third_type = native_third_frame.get("select", {}).get("type")
    native_third_your_index = native_third_frame.get("current", {}).get("yourIndex")
    native_fourth_context = native_fourth_frame.get("select", {}).get("context")
    native_fourth_type = native_fourth_frame.get("select", {}).get("type")
    native_fourth_your_index = native_fourth_frame.get("current", {}).get("yourIndex")
    native_setup_bench_skip_context = native_post_setup_bench_skip_frame.get("select", {}).get("context")
    native_setup_bench_skip_type = native_post_setup_bench_skip_frame.get("select", {}).get("type")
    native_setup_bench_skip_your_index = native_post_setup_bench_skip_frame.get("current", {}).get("yourIndex")
    native_setup_complete_main_context = native_post_setup_complete_main_frame.get("select", {}).get("context")
    native_setup_complete_main_type = native_post_setup_complete_main_frame.get("select", {}).get("type")
    native_setup_complete_main_your_index = native_post_setup_complete_main_frame.get("current", {}).get("yourIndex")
    native_setup_complete_main_turn = native_post_setup_complete_main_frame.get("current", {}).get("turn")
    native_first_main_end_context = native_post_first_main_end_frame.get("select", {}).get("context")
    native_first_main_end_type = native_post_first_main_end_frame.get("select", {}).get("type")
    native_first_main_end_your_index = native_post_first_main_end_frame.get("current", {}).get("yourIndex")
    native_first_main_end_turn = native_post_first_main_end_frame.get("current", {}).get("turn")
    native_setup_complete_main_selector = selector_summary(native_post_setup_complete_main_frame)
    native_setup_complete_main_selector_core = selector_core_summary(native_setup_complete_main_selector)
    native_first_main_end_selector = selector_summary(native_post_first_main_end_frame)
    native_first_main_end_selector_core = selector_core_summary(native_first_main_end_selector)
    official_post_setup_complete_main_option_card_ids = selector_visible_hand_option_identity_comparison(
        [official_setup_complete_main_frame],
        hand_backed_option_types=MAIN_HAND_BACKED_OPTION_TYPES,
        branch_dependent_fields=MAIN_OPTION_BRANCH_DEPENDENT_FIELDS,
    )
    native_post_setup_complete_main_option_card_ids = selector_visible_hand_option_identity_comparison(
        [native_post_setup_complete_main_frame],
        hand_backed_option_types=MAIN_HAND_BACKED_OPTION_TYPES,
        branch_dependent_fields=MAIN_OPTION_BRANCH_DEPENDENT_FIELDS,
    )
    official_post_first_main_end_option_card_ids = selector_visible_hand_option_identity_comparison(
        [official_first_main_end_frame],
        hand_backed_option_types=MAIN_HAND_BACKED_OPTION_TYPES,
        branch_dependent_fields=MAIN_OPTION_BRANCH_DEPENDENT_FIELDS,
    )
    native_post_first_main_end_option_card_ids = selector_visible_hand_option_identity_comparison(
        [native_post_first_main_end_frame],
        hand_backed_option_types=MAIN_HAND_BACKED_OPTION_TYPES,
        branch_dependent_fields=MAIN_OPTION_BRANCH_DEPENDENT_FIELDS,
    )
    official_startup_frame_prefix_core = frame_prefix_core_comparison(
        [first_frame, second_frame, third_frame, fourth_frame]
    )
    native_startup_frame_prefix_core = frame_prefix_core_comparison(
        [native_first_frame, native_second_frame, native_third_frame, native_fourth_frame]
    )
    official_startup_selector_option_card_ids = selector_option_identity_comparison(
        [first_frame, second_frame, third_frame, fourth_frame]
    )
    native_startup_selector_option_card_ids = selector_option_identity_comparison(
        [native_first_frame, native_second_frame, native_third_frame, native_fourth_frame]
    )
    official_post_setup_progression_frame_prefix_core = frame_prefix_core_comparison(
        [official_setup_bench_skip_frame, official_setup_complete_main_frame]
    )
    native_post_setup_progression_frame_prefix_core = frame_prefix_core_comparison(
        [native_post_setup_bench_skip_frame, native_post_setup_complete_main_frame]
    )
    official_post_first_main_end_frame_prefix_core = frame_prefix_core_comparison(
        [official_first_main_end_frame]
    )
    native_post_first_main_end_frame_prefix_core = frame_prefix_core_comparison(
        [native_post_first_main_end_frame]
    )
    official_setup_bench_bounds = setup_bench_selector_bounds_summary(fourth_frame)
    native_setup_bench_bounds = setup_bench_selector_bounds_summary(native_fourth_frame)
    native_pregame_counts_ok = all(
        player == {"deck_count": 60, "hand_count": 0, "prize_count": 0}
        for player in native_pregame_players
    )
    native_post_isfirst_counts_ok = all(
        player == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
        for player in native_post_isfirst_players
    )
    official_post_isfirst_counts_ok = all(
        player == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
        for player in official_second_players
    )
    native_post_setup_active_counts_ok = (
        native_post_setup_active_players[first_player_choice]
        == {"deck_count": 53, "hand_count": 6, "prize_count": 0}
        and native_post_setup_active_players[next_setup_player]
        == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
    )
    official_post_setup_active_counts_ok = (
        len(official_third_players) == 2
        and official_setup_player_index in (0, 1)
        and official_next_setup_player in (0, 1)
        and official_third_players[official_setup_player_index]["hand_count"] == 6
        and official_third_players[official_next_setup_player]["hand_count"] == 7
    )
    official_post_setup_active_prize_timing = (
        official_third_players[official_setup_player_index]
        if len(official_third_players) == 2 and official_setup_player_index in (0, 1)
        else None
    )
    native_post_setup_active_selected_counts = native_post_setup_active_players[first_player_choice]
    native_post_setup_active_next_counts = native_post_setup_active_players[next_setup_player]
    official_post_setup_active_prize_timing_ok = (
        len(official_third_players) == 2
        and official_setup_player_index in (0, 1)
        and official_next_setup_player in (0, 1)
        and official_setup_player_index == first_player_choice
        and official_next_setup_player == next_setup_player
        and official_third_players[official_setup_player_index]
        == {"deck_count": 53, "hand_count": 6, "prize_count": 0}
        and official_third_players[official_next_setup_player]
        == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
        and native_post_setup_active_selected_counts
        == {"deck_count": 53, "hand_count": 6, "prize_count": 0}
        and native_post_setup_active_next_counts
        == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
    )
    native_post_both_actives_counts_ok = all(
        player == {"deck_count": 47, "hand_count": 6, "prize_count": 6}
        for player in native_post_both_actives_players
    )
    official_post_both_actives_counts_ok = all(
        player == {"deck_count": 47, "hand_count": 6, "prize_count": 6}
        for player in official_fourth_players
    )

    comparisons = [
        comparison(
            comparison_id="deck_csv_count",
            label="deck.csv card count",
            status="pass" if player_deck["count"] == opponent_deck["count"] == native_deck.card_count == 60 else "fail",
            official={"player": player_deck["count"], "opponent": opponent_deck["count"]},
            native=native_deck.card_count,
            note="Both wrappers use the same 60-card deck.csv input.",
        ),
        comparison(
            comparison_id="deck_csv_sha256",
            label="deck.csv SHA256",
            status="pass" if player_deck["sha256"] == native_deck.sha256 else "fail",
            official=player_deck["sha256"],
            native=native_deck.sha256,
            note="Hash is computed from canonical one-card-id-per-line deck.csv.",
        ),
        comparison(
            comparison_id="official_initial_context",
            label="official initial selector",
            status="pass" if official_first_context == "IsFirst" and official_first_type == "YesNo" else "fail",
            official={"context": official_first_context, "type": official_first_type},
            native=None,
            note="Official cg.dll starts at first-player choice before setup cards are placed.",
        ),
        comparison(
            comparison_id="native_initial_context",
            label="native initial selector",
            status="pass"
            if (
                native_first_context == "IsFirst"
                and native_first_type == "YesNo"
                and native_pregame.first_player == -1
                and native_pregame_counts_ok
            )
            else "fail",
            official={"context": official_first_context, "type": official_first_type},
            native={
                "context": native_first_context,
                "type": native_first_type,
                "players": native_pregame_players,
            },
            note="Native clean-room core now exposes the same pre-setup first-player prompt shape.",
        ),
        comparison(
            comparison_id="initial_turn_action_count",
            label="initial turnActionCount",
            status="pass"
            if official_first_turn_action_count == 1 and native_first_turn_action_count == 1
            else "fail",
            official=official_first_turn_action_count,
            native=native_first_turn_action_count,
            note="Official VisualizeData starts the pre-setup IsFirst prompt at turnActionCount=1; the native official-shaped frame mirrors that counter.",
        ),
        comparison(
            comparison_id="post_isfirst_opening_hand_counts",
            label="post-IsFirst opening hand counts",
            status="pass"
            if official_post_isfirst_counts_ok and native_post_isfirst_counts_ok
            else "fail",
            official=official_second_players,
            native=native_post_isfirst_players,
            note="Official and native both draw opening hands after IsFirst, leaving prize zones empty and 53 cards in deck.",
        ),
        comparison(
            comparison_id="post_isfirst_setup_active_frame",
            label="post-IsFirst setup active frame",
            status="pass"
            if (
                official_second_context == "SetupActivePokemon"
                and official_second_type == "Card"
                and native_second_context == "SetupActivePokemon"
                and native_second_type == "Card"
                and len(native_second_frame.get("select", {}).get("option") or []) > 0
            )
            else "fail",
            official={"context": official_second_context, "type": official_second_type},
            native={
                "context": native_second_context,
                "type": native_second_type,
                "option_count": len(native_second_frame.get("select", {}).get("option") or []),
            },
            note="Native now emits the same second-frame selector family as official VisualizeData.",
        ),
        comparison(
            comparison_id="post_setup_active_visible_counts",
            label="post setup-active visible counts",
            status="pass"
            if official_post_setup_active_counts_ok and native_post_setup_active_counts_ok
            else "fail",
            official={
                "selected_player": official_setup_player_index,
                "next_player": official_next_setup_player,
                "players": official_third_players,
            },
            native=native_post_setup_active_players,
            note="After the first active choice, both engines show the selected player's hand reduced to six and the next player still at seven.",
        ),
        comparison(
            comparison_id="post_setup_active_prize_timing",
            label="post setup-active prize timing",
            status="pass" if official_post_setup_active_prize_timing_ok else "fail",
            official={
                "selected_player": official_setup_player_index,
                "next_player": official_next_setup_player,
                "selected_player_counts": official_post_setup_active_prize_timing,
                "next_player_counts": (
                    official_third_players[official_next_setup_player]
                    if len(official_third_players) == 2 and official_next_setup_player in (0, 1)
                    else None
                ),
            },
            native={
                "selected_player": first_player_choice,
                "next_player": next_setup_player,
                "selected_player_counts": native_post_setup_active_selected_counts,
                "next_player_counts": native_post_setup_active_next_counts,
            },
            note="After the first Active selection, both engines still show zero prizes and 53-card decks; prize placement is verified separately after both Actives.",
        ),
        comparison(
            comparison_id="official_draw_count_branch_semantics",
            label="official DrawCount setup branch semantics",
            status="pass"
            if (
                setup_branch_probe["branch_counts"].get("DrawCount", 0) > 0
                and native_draw_count_replay["phase"] == "post_mulligan_draw_count_selected"
                and native_draw_count_replay["first_frame"].get("select", {}).get("context")
                == "SetupBenchPokemon"
            )
            else "fail",
            official={
                "branch_counts": setup_branch_probe["branch_counts"],
                "draw_count_example": setup_branch_probe["examples"].get("DrawCount"),
            },
            native={
                "modeled": native_draw_count_replay["phase"] == "post_mulligan_draw_count_selected",
                "draw_count_replay": native_draw_count_replay,
            },
            note="Official cg.dll can branch to DrawCount before setup Bench or Main; native now has a replayed DrawCount branch, while exact RNG/frame equivalence remains covered by frame-by-frame parity.",
        ),
        comparison(
            comparison_id="post_setup_active_next_prompt",
            label="post setup-active next prompt",
            status="pass"
            if (
                official_third_context == "SetupActivePokemon"
                and official_third_type == "Card"
                and official_third_your_index == official_next_setup_player
                and native_third_context == "SetupActivePokemon"
                and native_third_type == "Card"
                and native_third_your_index == next_setup_player
            )
            else "fail",
            official={
                "context": official_third_context,
                "type": official_third_type,
                "yourIndex": official_third_your_index,
            },
            native={
                "context": native_third_context,
                "type": native_third_type,
                "yourIndex": native_third_your_index,
                "option_count": len(native_third_frame.get("select", {}).get("option") or []),
            },
            note="After one active is selected, the next setup-active prompt moves to the other player.",
        ),
        comparison(
            comparison_id="post_both_actives_setup_bench_frame",
            label="post both Active setup bench frame",
            status="pass"
            if (
                official_fourth_context == "SetupBenchPokemon"
                and official_fourth_type == "Card"
                and official_fourth_your_index == first_player_choice
                and native_fourth_context == "SetupBenchPokemon"
                and native_fourth_type == "Card"
                and native_fourth_your_index == first_player_choice
            )
            else "fail",
            official={
                "context": official_fourth_context,
                "type": official_fourth_type,
                "yourIndex": official_fourth_your_index,
            },
            native={
                "context": native_fourth_context,
                "type": native_fourth_type,
                "yourIndex": native_fourth_your_index,
                "option_count": len(native_fourth_frame.get("select", {}).get("option") or []),
            },
            note="When official cg.dll exposes the fourth setup-bench prompt, native now emits the same prompt family for the first setup player.",
        ),
        comparison(
            comparison_id="post_both_actives_prize_counts",
            label="post both Active prize counts",
            status="pass" if official_post_both_actives_counts_ok and native_post_both_actives_counts_ok else "fail",
            official=official_fourth_players,
            native=native_post_both_actives_players,
            note="After both Active Pokemon are selected, both engines show six-card prizes and 47-card decks for both players.",
        ),
        comparison(
            comparison_id="startup_frame_prefix_core",
            label="startup frame prefix core",
            status="pass"
            if (
                official_startup_frame_prefix_core["frame_count"] == 4
                and native_startup_frame_prefix_core["frame_count"] == 4
                and official_startup_frame_prefix_core["frames"] == native_startup_frame_prefix_core["frames"]
            )
            else "fail",
            official=official_startup_frame_prefix_core,
            native=native_startup_frame_prefix_core,
            note="First four startup frames now match on context, normalized selector type, minCount, turn counters, acting player, and public player deck/hand/prize counts. maxCount, option count, card ids, and option order remain excluded until branch/RNG/card-order parity is solved.",
        ),
        comparison(
            comparison_id="setup_bench_selector_bounds_semantics",
            label="setup Bench selector bounds semantics",
            status="pass"
            if (
                official_setup_bench_bounds["context"] == "SetupBenchPokemon"
                and official_setup_bench_bounds["type"] == "Card"
                and official_setup_bench_bounds["minCount"] == 0
                and official_setup_bench_bounds["max_equals_option_count"] is True
                and native_setup_bench_bounds["context"] == "SetupBenchPokemon"
                and native_setup_bench_bounds["type"] == "Card"
                and native_setup_bench_bounds["minCount"] == 0
                and native_setup_bench_bounds["max_equals_option_count"] is True
            )
            else "fail",
            official=official_setup_bench_bounds,
            native=native_setup_bench_bounds,
            note="Setup Bench frames expose the same optional-selection bound semantics: minCount=0 and maxCount equals the currently legal option count. The exact maxCount value, option count, card ids, and ordering remain branch-dependent until shuffle/card-order parity is solved.",
        ),
        comparison(
            comparison_id="startup_selector_option_card_ids",
            label="startup selector option card ID resolution",
            status="pass"
            if (
                official_startup_selector_option_card_ids["frame_count"] == 4
                and native_startup_selector_option_card_ids["frame_count"] == 4
                and official_startup_selector_option_card_ids["unresolved_option_count"] == 0
                and native_startup_selector_option_card_ids["unresolved_option_count"] == 0
                and official_startup_selector_option_card_ids["card_option_count"] > 0
                and native_startup_selector_option_card_ids["card_option_count"] > 0
            )
            else "fail",
            official=official_startup_selector_option_card_ids,
            native=native_startup_selector_option_card_ids,
            note="Official card options identify visible hand cards through area/index/playerIndex; native options carry cardId directly. Exact option counts, card IDs, and order remain branch-dependent until shuffle/card-order parity is solved.",
        ),
        comparison(
            comparison_id="post_isfirst_ordered_zone_sync",
            label="post-IsFirst ordered-zone sync",
            status="pass"
            if (
                official_post_isfirst_ordered_zone_sync["context"] == "SetupActivePokemon"
                and native_post_isfirst_ordered_zone_sync["context"] == "SetupActivePokemon"
                and official_post_isfirst_ordered_zone_sync["yourIndex"] == first_player_choice
                and native_post_isfirst_ordered_zone_sync["yourIndex"] == first_player_choice
                and official_post_isfirst_ordered_zone_sync["players"]
                == native_post_isfirst_ordered_zone_sync["players"]
                and official_post_isfirst_ordered_zone_sync["selector_option_card_ids"]
                == native_post_isfirst_ordered_zone_sync["selector_option_card_ids"]
                and official_post_isfirst_ordered_zone_sync["selector_option_indexes"]
                == native_post_isfirst_ordered_zone_sync["selector_option_indexes"]
                and official_post_isfirst_ordered_zone_sync["selector_option_serials"]
                == native_post_isfirst_ordered_zone_sync["selector_option_serials"]
                and official_post_isfirst_ordered_zone_sync["unresolved_option_count"] == 0
                and native_post_isfirst_ordered_zone_sync["unresolved_option_count"] == 0
            )
            else "fail",
            official=official_post_isfirst_ordered_zone_sync,
            native=native_post_isfirst_ordered_zone_sync,
            note="When native is initialized from official VisualizeData's observed ordered hand/deck zones, the post-IsFirst setup-active selector matches official on visible zone card IDs and legal active option card IDs/order. This isolates the remaining 1:1 blocker to reproducing official shuffle/RNG from deck.csv without observed-state injection.",
        ),
        comparison(
            comparison_id="post_ordered_first_active_zone_sync",
            label="ordered branch first setup Active replay sync",
            status="pass"
            if (
                official_post_ordered_first_active_zone_sync["context"] == "SetupActivePokemon"
                and native_post_ordered_first_active_zone_sync["context"] == "SetupActivePokemon"
                and official_post_ordered_first_active_zone_sync["yourIndex"] == next_setup_player
                and native_post_ordered_first_active_zone_sync["yourIndex"] == next_setup_player
                and official_post_ordered_first_active_zone_sync["players"]
                == native_post_ordered_first_active_zone_sync["players"]
                and official_post_ordered_first_active_zone_sync["selector_option_card_ids"]
                == native_post_ordered_first_active_zone_sync["selector_option_card_ids"]
                and official_post_ordered_first_active_zone_sync["selector_option_indexes"]
                == native_post_ordered_first_active_zone_sync["selector_option_indexes"]
                and official_post_ordered_first_active_zone_sync["selector_option_serials"]
                == native_post_ordered_first_active_zone_sync["selector_option_serials"]
                and official_post_ordered_first_active_zone_sync["unresolved_option_count"] == 0
                and native_post_ordered_first_active_zone_sync["unresolved_option_count"] == 0
            )
            else "fail",
            official=official_post_ordered_first_active_zone_sync,
            native=native_post_ordered_first_active_zone_sync,
            note="Starting from official observed ordered zones, native now preserves card occurrence serials through the first setup Active selection and matches the official third setup-active frame for the next player. This is still observed-state replay, not proof of standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_both_actives_setup_bench_zone_sync",
            label="ordered branch both setup Actives and prize deal sync",
            status="pass"
            if (
                official_post_ordered_both_actives_setup_bench_zone_sync["context"] == "SetupBenchPokemon"
                and native_post_ordered_both_actives_setup_bench_zone_sync["context"] == "SetupBenchPokemon"
                and official_post_ordered_both_actives_setup_bench_zone_sync["yourIndex"] == first_player_choice
                and native_post_ordered_both_actives_setup_bench_zone_sync["yourIndex"] == first_player_choice
                and official_post_ordered_both_actives_setup_bench_zone_sync["players"]
                == native_post_ordered_both_actives_setup_bench_zone_sync["players"]
                and official_post_ordered_both_actives_setup_bench_zone_sync["selector_option_card_ids"]
                == native_post_ordered_both_actives_setup_bench_zone_sync["selector_option_card_ids"]
                and official_post_ordered_both_actives_setup_bench_zone_sync["selector_option_indexes"]
                == native_post_ordered_both_actives_setup_bench_zone_sync["selector_option_indexes"]
                and official_post_ordered_both_actives_setup_bench_zone_sync["selector_option_serials"]
                == native_post_ordered_both_actives_setup_bench_zone_sync["selector_option_serials"]
                and official_post_ordered_both_actives_setup_bench_zone_sync["unresolved_option_count"] == 0
                and native_post_ordered_both_actives_setup_bench_zone_sync["unresolved_option_count"] == 0
            )
            else "fail",
            official=official_post_ordered_both_actives_setup_bench_zone_sync,
            native=native_post_ordered_both_actives_setup_bench_zone_sync,
            note="Starting from official observed ordered zones, native now preserves card occurrence serials through both setup Active selections and setup prize dealing, matching the official setup Bench frame including visible hand/deck/prize zones and setup Bench legal options. This is still observed-state replay, not proof of standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_first_setup_bench_skip_zone_sync",
            label="ordered branch first setup Bench skip sync",
            status="pass"
            if (
                official_post_ordered_first_setup_bench_skip_zone_sync["context"] == "SetupBenchPokemon"
                and native_post_ordered_first_setup_bench_skip_zone_sync["context"] == "SetupBenchPokemon"
                and official_post_ordered_first_setup_bench_skip_zone_sync["yourIndex"] == next_setup_player
                and native_post_ordered_first_setup_bench_skip_zone_sync["yourIndex"] == next_setup_player
                and official_post_ordered_first_setup_bench_skip_zone_sync["players"]
                == native_post_ordered_first_setup_bench_skip_zone_sync["players"]
                and official_post_ordered_first_setup_bench_skip_zone_sync["selector_option_card_ids"]
                == native_post_ordered_first_setup_bench_skip_zone_sync["selector_option_card_ids"]
                and official_post_ordered_first_setup_bench_skip_zone_sync["selector_option_indexes"]
                == native_post_ordered_first_setup_bench_skip_zone_sync["selector_option_indexes"]
                and official_post_ordered_first_setup_bench_skip_zone_sync["selector_option_serials"]
                == native_post_ordered_first_setup_bench_skip_zone_sync["selector_option_serials"]
                and official_post_ordered_first_setup_bench_skip_zone_sync["unresolved_option_count"] == 0
                and native_post_ordered_first_setup_bench_skip_zone_sync["unresolved_option_count"] == 0
            )
            else "fail",
            official=official_post_ordered_first_setup_bench_skip_zone_sync,
            native=native_post_ordered_first_setup_bench_skip_zone_sync,
            note="Starting from official observed ordered zones, native now matches the official frame after the first player chooses zero setup Bench Pokemon, including the next player's setup Bench legal options and all visible zone card occurrence serials. This remains observed-state replay, not standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_both_setup_bench_skips_main_zone_sync",
            label="ordered branch both setup Bench skips into Main sync",
            status="pass"
            if (
                official_post_ordered_both_setup_bench_skips_main_zone_sync["context"] == "Main"
                and native_post_ordered_both_setup_bench_skips_main_zone_sync["context"] == "Main"
                and official_post_ordered_both_setup_bench_skips_main_zone_sync["yourIndex"] == first_player_choice
                and native_post_ordered_both_setup_bench_skips_main_zone_sync["yourIndex"] == first_player_choice
                and official_post_ordered_both_setup_bench_skips_main_zone_sync["players"]
                == native_post_ordered_both_setup_bench_skips_main_zone_sync["players"]
                and official_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                == native_post_ordered_both_setup_bench_skips_main_zone_sync["selector_hand_backed_option_card_ids"]
                and official_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                == native_post_ordered_both_setup_bench_skips_main_zone_sync["selector_hand_backed_option_indexes"]
                and official_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                == native_post_ordered_both_setup_bench_skips_main_zone_sync["selector_hand_backed_option_serials"]
                and official_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                == native_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                and official_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                == native_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                and official_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
                and native_post_ordered_both_setup_bench_skips_main_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
            )
            else "fail",
            official=official_post_ordered_both_setup_bench_skips_main_zone_sync,
            native=native_post_ordered_both_setup_bench_skips_main_zone_sync,
            note="Starting from official observed ordered zones, native now matches the official first Main frame after both players choose zero setup Bench Pokemon, including visible zones and exact hand-backed Main action identities by card id, hand index, occurrence serial, and option type. This still does not prove standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_first_main_end_next_main_zone_sync",
            label="ordered branch first Main End into next Main sync",
            status="pass"
            if (
                official_post_ordered_first_main_end_next_main_zone_sync["context"] == "Main"
                and native_post_ordered_first_main_end_next_main_zone_sync["context"] == "Main"
                and official_post_ordered_first_main_end_next_main_zone_sync["yourIndex"] == next_setup_player
                and native_post_ordered_first_main_end_next_main_zone_sync["yourIndex"] == next_setup_player
                and official_post_ordered_first_main_end_next_main_zone_sync["players"]
                == native_post_ordered_first_main_end_next_main_zone_sync["players"]
                and official_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                == native_post_ordered_first_main_end_next_main_zone_sync["selector_hand_backed_option_card_ids"]
                and official_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                == native_post_ordered_first_main_end_next_main_zone_sync["selector_hand_backed_option_indexes"]
                and official_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                == native_post_ordered_first_main_end_next_main_zone_sync["selector_hand_backed_option_serials"]
                and official_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                == native_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                and official_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                == native_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                and official_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
                and native_post_ordered_first_main_end_next_main_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
            )
            else "fail",
            official=official_post_ordered_first_main_end_next_main_zone_sync,
            native=native_post_ordered_first_main_end_next_main_zone_sync,
            note="Starting from official observed ordered zones, native now matches the official next Main frame after the first player chooses End, including the next player's draw, visible zones, and exact hand-backed Main action identities. This still does not prove standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_next_main_attach_active_zone_sync",
            label="ordered branch next Main Attach-to-active sync",
            status="pass"
            if (
                official_post_ordered_next_main_attach_active_zone_sync["context"] == "Main"
                and native_post_ordered_next_main_attach_active_zone_sync["context"] == "Main"
                and official_post_ordered_next_main_attach_active_zone_sync["yourIndex"] == next_setup_player
                and native_post_ordered_next_main_attach_active_zone_sync["yourIndex"] == next_setup_player
                and official_post_ordered_next_main_attach_active_zone_sync["energyAttached"] is True
                and native_post_ordered_next_main_attach_active_zone_sync["energyAttached"] is True
                and official_post_ordered_next_main_attach_active_zone_sync["players"]
                == native_post_ordered_next_main_attach_active_zone_sync["players"]
                and official_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                == native_post_ordered_next_main_attach_active_zone_sync["selector_hand_backed_option_card_ids"]
                and official_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                == native_post_ordered_next_main_attach_active_zone_sync["selector_hand_backed_option_indexes"]
                and official_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                == native_post_ordered_next_main_attach_active_zone_sync["selector_hand_backed_option_serials"]
                and official_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                == native_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                and official_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                == native_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                and official_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
                and native_post_ordered_next_main_attach_active_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
            )
            else "fail",
            official=official_post_ordered_next_main_attach_active_zone_sync,
            native=native_post_ordered_next_main_attach_active_zone_sync,
            note="Starting from official observed ordered zones after the first End, native now matches an actual Main Attach action to the active Pokemon, including hand removal, attached Energy occurrence serial, energyAttached flag, and remaining Main action identities. This still does not prove standalone official RNG/shuffle parity or all action types.",
        ),
        comparison(
            comparison_id="post_ordered_next_main_attack_zone_sync",
            label="ordered branch next Main Attack sync",
            status="pass"
            if (
                official_post_ordered_next_main_attack_zone_sync["context"] == "Main"
                and native_post_ordered_next_main_attack_zone_sync["context"] == "Main"
                and official_post_ordered_next_main_attack_zone_sync["yourIndex"] == first_player_choice
                and native_post_ordered_next_main_attack_zone_sync["yourIndex"] == first_player_choice
                and official_post_ordered_next_main_attack_zone_sync["energyAttached"] is False
                and native_post_ordered_next_main_attack_zone_sync["energyAttached"] is False
                and official_post_ordered_next_main_attack_zone_sync["players"]
                == native_post_ordered_next_main_attack_zone_sync["players"]
                and official_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_card_ids"]
                == native_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_card_ids"]
                and official_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_indexes"]
                == native_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_indexes"]
                and official_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_serials"]
                == native_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_serials"]
                and official_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_type_counts"]
                == native_post_ordered_next_main_attack_zone_sync["selector_hand_backed_option_type_counts"]
                and official_post_ordered_next_main_attack_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                == native_post_ordered_next_main_attack_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                and official_post_ordered_next_main_attack_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
                and native_post_ordered_next_main_attack_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
            )
            else "fail",
            official=official_post_ordered_next_main_attack_zone_sync,
            native=native_post_ordered_next_main_attack_zone_sync,
            note="Starting from official observed ordered zones after Attach, native must match the following Attack, including damage/HP, turn handoff, energyAttached reset, card occurrence serials, and next player's Main action identities. This still does not prove all attacks, knockouts, prize flow, or standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_after_attack_attach_active_zone_sync",
            label="ordered branch post-attack Attach-to-active sync",
            status="pass"
            if (
                official_post_ordered_after_attack_attach_active_zone_sync["context"] == "Main"
                and native_post_ordered_after_attack_attach_active_zone_sync["context"] == "Main"
                and official_post_ordered_after_attack_attach_active_zone_sync["yourIndex"] == first_player_choice
                and native_post_ordered_after_attack_attach_active_zone_sync["yourIndex"] == first_player_choice
                and official_post_ordered_after_attack_attach_active_zone_sync["energyAttached"] is True
                and native_post_ordered_after_attack_attach_active_zone_sync["energyAttached"] is True
                and official_post_ordered_after_attack_attach_active_zone_sync["players"]
                == native_post_ordered_after_attack_attach_active_zone_sync["players"]
                and official_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                == native_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                and official_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                == native_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                and official_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                == native_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                and official_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                == native_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                and official_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                == native_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                and official_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
                and native_post_ordered_after_attack_attach_active_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
            )
            else "fail",
            official=official_post_ordered_after_attack_attach_active_zone_sync,
            native=native_post_ordered_after_attack_attach_active_zone_sync,
            note="Starting from official observed ordered zones after the first attack and next-player draw, native now matches the next player's Attach to active, including the drawn hand identity, attached Energy occurrence serial, energyAttached flag, damage-preserved active HP, and remaining Main action identities. This still does not prove all action branches or standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_ordered_after_attack_attach_attack_zone_sync",
            label="ordered branch post-attach return Attack sync",
            status="pass"
            if (
                official_post_ordered_after_attack_attach_attack_zone_sync["context"] == "Main"
                and native_post_ordered_after_attack_attach_attack_zone_sync["context"] == "Main"
                and official_post_ordered_after_attack_attach_attack_zone_sync["yourIndex"]
                == 1 - first_player_choice
                and native_post_ordered_after_attack_attach_attack_zone_sync["yourIndex"]
                == 1 - first_player_choice
                and official_post_ordered_after_attack_attach_attack_zone_sync["energyAttached"] is False
                and native_post_ordered_after_attack_attach_attack_zone_sync["energyAttached"] is False
                and official_post_ordered_after_attack_attach_attack_zone_sync["players"]
                == native_post_ordered_after_attack_attach_attack_zone_sync["players"]
                and official_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                == native_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_card_ids"
                ]
                and official_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                == native_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_indexes"
                ]
                and official_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                == native_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_serials"
                ]
                and official_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                == native_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_option_type_counts"
                ]
                and official_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                == native_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_ignored_option_type_counts"
                ]
                and official_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
                and native_post_ordered_after_attack_attach_attack_zone_sync[
                    "selector_hand_backed_unresolved_option_count"
                ]
                == 0
            )
            else "fail",
            official=official_post_ordered_after_attack_attach_attack_zone_sync,
            native=native_post_ordered_after_attack_attach_attack_zone_sync,
            note="Starting from official observed ordered zones after the next player's Attach, native now matches the return Attack and handoff back to the other player, including damage/HP, next-turn draw identity, energyAttached reset, and remaining Main action identities. This still does not prove knockouts, prize flow, promotion, or standalone official RNG/shuffle parity.",
        ),
        comparison(
            comparison_id="post_setup_progression_frame_prefix_core",
            label="post setup progression frame prefix core",
            status="pass"
            if (
                official_post_setup_progression_frame_prefix_core["frame_count"] == 2
                and native_post_setup_progression_frame_prefix_core["frame_count"] == 2
                and official_post_setup_progression_frame_prefix_core["frames"]
                == native_post_setup_progression_frame_prefix_core["frames"]
            )
            else "fail",
            official=official_post_setup_progression_frame_prefix_core,
            native=native_post_setup_progression_frame_prefix_core,
            note="After the first setup Bench skip and after both setup Bench skips into Main, official and native now match on normalized context/type, minCount, turn counters, acting player, and public deck/hand/prize counts. maxCount, option count, card ids, and option order remain excluded until branch/RNG/card-order parity is solved.",
        ),
        comparison(
            comparison_id="post_setup_bench_optional_selection_semantics",
            label="post setup-bench optional selection semantics",
            official={
                "context": official_fourth_context,
                "minCount": fourth_frame.get("select", {}).get("minCount"),
                "maxCount": fourth_frame.get("select", {}).get("maxCount"),
                "option_count": len(fourth_frame.get("select", {}).get("option") or []),
                "empty_select_probe": official_setup_bench_empty_select_probe,
                "note": "cg.dll advertises minCount=0 for setup Bench, but the Python Select wrapper must prove how a zero-card skip is encoded.",
            },
            native={
                "skip_modeled": native_setup_bench_optional_replay["skip"]["setup"]["players"][1]["setup_complete"]
                and native_setup_bench_optional_replay["skip"]["setup"]["players"][1]["bench_count"] == 0,
                "multi_modeled": native_setup_bench_optional_replay["multi"]["setup"]["players"][1]["bench_count"]
                >= 2,
                "optional_replay": native_setup_bench_optional_replay,
                "post_setup_bench_available": native_post_setup_bench is not None,
                "selected_option": native_setup_bench_option,
                "next_context": native_fifth_frame.get("select", {}).get("context") if native_fifth_frame else None,
                "next_yourIndex": native_fifth_frame.get("current", {}).get("yourIndex") if native_fifth_frame else None,
            },
            status="pass"
            if (
                fourth_frame.get("select", {}).get("minCount") == 0
                and official_setup_bench_empty_select_probe
                and official_setup_bench_empty_select_probe.get("accepted") is True
                and native_setup_bench_optional_replay["skip"]["setup"]["players"][1]["setup_complete"]
                and native_setup_bench_optional_replay["skip"]["setup"]["players"][1]["bench_count"] == 0
                and native_setup_bench_optional_replay["multi"]["setup"]["players"][1]["bench_count"] >= 2
            )
            else "gap",
            note="Native models zero-card finish and multi-card setup Bench choices, but exact official Select-list skip encoding remains a gap until the empty-select probe is accepted or the real skip encoding is found.",
        ),
        comparison(
            comparison_id="post_setup_bench_skip_next_prompt",
            label="post setup-bench skip advances to next setup player",
            status="pass"
            if (
                official_setup_bench_empty_select_probe
                and official_setup_bench_empty_select_probe.get("accepted") is True
                and official_setup_bench_skip_summary is not None
                and official_setup_bench_skip_summary.get("context") == "SetupBenchPokemon"
                and official_setup_bench_skip_summary.get("type") == "Card"
                and official_setup_bench_skip_summary.get("yourIndex") == next_setup_player
                and len(official_setup_bench_skip_summary.get("players", [])) > first_player_choice
                and official_setup_bench_skip_summary.get("players", [])[first_player_choice]["benchCount"] == 0
                and native_setup_bench_skip_context == "SetupBenchPokemon"
                and native_setup_bench_skip_type == "Card"
                and native_setup_bench_skip_your_index == next_setup_player
                and native_post_setup_bench_skip.players[first_player_choice].setup_complete
                and len(native_post_setup_bench_skip.players[first_player_choice].bench_card_ids) == 0
            )
            else "fail",
            official={
                "selection": [],
                "next_context": official_setup_bench_skip_summary.get("context")
                if official_setup_bench_skip_summary
                else None,
                "next_type": official_setup_bench_skip_summary.get("type")
                if official_setup_bench_skip_summary
                else None,
                "next_yourIndex": official_setup_bench_skip_summary.get("yourIndex")
                if official_setup_bench_skip_summary
                else None,
                "first_skipped_player": first_player_choice,
                "first_skipped_player_bench_count": (
                    official_setup_bench_skip_summary.get("players", [])[first_player_choice]["benchCount"]
                    if official_setup_bench_skip_summary
                    and len(official_setup_bench_skip_summary.get("players", [])) > first_player_choice
                    else None
                ),
                "first_frame_summary": official_setup_bench_skip_summary,
            },
            native={
                "selection": [],
                "next_context": native_setup_bench_skip_context,
                "next_type": native_setup_bench_skip_type,
                "next_yourIndex": native_setup_bench_skip_your_index,
                "first_skipped_player": first_player_choice,
                "first_skipped_player_bench_count": len(
                    native_post_setup_bench_skip.players[first_player_choice].bench_card_ids
                ),
            },
            note="After choosing zero setup Bench Pokemon for the first setup player, both engines advance to the other player's setup Bench prompt without adding Bench Pokemon.",
        ),
        comparison(
            comparison_id="post_both_setup_bench_skips_main_frame",
            label="post both setup-bench skips main frame",
            status="pass"
            if (
                official_setup_complete_main_probe
                and official_setup_complete_main_probe.get("accepted") is True
                and official_setup_complete_main_summary is not None
                and official_setup_complete_main_summary.get("context") == "Main"
                and official_setup_complete_main_summary.get("turn") == 1
                and official_setup_complete_main_summary.get("yourIndex") == first_player_choice
                and native_setup_complete_main_context == "Main"
                and native_setup_complete_main_type == "Action"
                and native_setup_complete_main_turn == 1
                and native_setup_complete_main_your_index == first_player_choice
                and native_post_setup_complete_main.setup_complete
            )
            else "fail",
            official={
                "selection_sequence": [[], []],
                "main_context": official_setup_complete_main_summary.get("context")
                if official_setup_complete_main_summary
                else None,
                "main_turn": official_setup_complete_main_summary.get("turn")
                if official_setup_complete_main_summary
                else None,
                "main_yourIndex": official_setup_complete_main_summary.get("yourIndex")
                if official_setup_complete_main_summary
                else None,
                "first_frame_summary": official_setup_complete_main_summary,
            },
            native={
                "selection_sequence": [[], []],
                "main_context": native_setup_complete_main_context,
                "main_type": native_setup_complete_main_type,
                "main_turn": native_setup_complete_main_turn,
                "main_yourIndex": native_setup_complete_main_your_index,
                "setup_complete": native_post_setup_complete_main.setup_complete,
            },
            note="After both players choose zero setup Bench Pokemon, both engines expose the first turn Main selector for the first player.",
        ),
        comparison(
            comparison_id="post_setup_complete_main_selector_core",
            label="post setup-complete Main selector core",
            status="pass"
            if (
                official_setup_complete_main_selector_core is not None
                and official_setup_complete_main_selector_core.get("context") == "Main"
                and official_setup_complete_main_selector_core.get("normalized_type") == "Action"
                and official_setup_complete_main_selector_core.get("minCount") == 1
                and official_setup_complete_main_selector_core.get("maxCount") == 1
                and official_setup_complete_main_selector_core.get("required_common_present") is True
                and native_setup_complete_main_selector_core is not None
                and native_setup_complete_main_selector_core.get("context") == "Main"
                and native_setup_complete_main_selector_core.get("normalized_type") == "Action"
                and native_setup_complete_main_selector_core.get("minCount") == 1
                and native_setup_complete_main_selector_core.get("maxCount") == 1
                and native_setup_complete_main_selector_core.get("required_common_present") is True
            )
            else "fail",
            official=official_setup_complete_main_selector_core,
            native=native_setup_complete_main_selector_core,
            note="The first Main selector common core is normalized across official string option names and native numeric option ids. Attach is branch-dependent until official shuffle and native deck-order parity are synchronized; exact option count and card identity order remain under frame-by-frame parity.",
        ),
        comparison(
            comparison_id="post_setup_complete_main_option_card_ids",
            label="post setup-complete Main option card ID resolution",
            status="pass"
            if (
                official_post_setup_complete_main_option_card_ids["frame_count"] == 1
                and native_post_setup_complete_main_option_card_ids["frame_count"] == 1
                and official_post_setup_complete_main_option_card_ids["unresolved_option_count"] == 0
                and native_post_setup_complete_main_option_card_ids["unresolved_option_count"] == 0
                and official_post_setup_complete_main_option_card_ids["resolved_option_count"] > 0
                and native_post_setup_complete_main_option_card_ids["resolved_option_count"] > 0
            )
            else "fail",
            official=official_post_setup_complete_main_option_card_ids,
            native=native_post_setup_complete_main_option_card_ids,
            note="The first Main selector's hand-backed options now resolve to visible hand card IDs on both wrappers: official Play/Attach/Evolve-style options resolve by hand index, while native options carry cardId directly. Exact option count, ids, and order remain branch-dependent until shuffle/card-order parity is solved.",
        ),
        comparison(
            comparison_id="post_first_main_end_frame_prefix_core",
            label="post first Main End frame prefix core",
            status="pass"
            if (
                official_first_main_end_probe
                and official_first_main_end_probe.get("accepted") is True
                and official_post_first_main_end_frame_prefix_core["frame_count"] == 1
                and native_post_first_main_end_frame_prefix_core["frame_count"] == 1
                and official_post_first_main_end_frame_prefix_core["frames"]
                == native_post_first_main_end_frame_prefix_core["frames"]
                and native_first_main_end_context == "Main"
                and native_first_main_end_type == "Action"
                and native_first_main_end_turn == 2
                and native_first_main_end_your_index == 1 - first_player_choice
            )
            else "fail",
            official=official_post_first_main_end_frame_prefix_core,
            native=native_post_first_main_end_frame_prefix_core,
            note="After selecting End on the first Main turn, official and native now match on normalized context/type, minCount, turn counters, acting player, and public deck/hand/prize counts. Exact option count, card ids, and option order on the new Main frame remain under frame-by-frame parity.",
        ),
        comparison(
            comparison_id="post_first_main_end_selector_core",
            label="post first Main End selector core",
            status="pass"
            if (
                official_first_main_end_selector_core is not None
                and official_first_main_end_selector_core.get("context") == "Main"
                and official_first_main_end_selector_core.get("normalized_type") == "Action"
                and official_first_main_end_selector_core.get("minCount") == 1
                and official_first_main_end_selector_core.get("maxCount") == 1
                and official_first_main_end_selector_core.get("required_common_present") is True
                and native_first_main_end_selector_core is not None
                and native_first_main_end_selector_core.get("context") == "Main"
                and native_first_main_end_selector_core.get("normalized_type") == "Action"
                and native_first_main_end_selector_core.get("minCount") == 1
                and native_first_main_end_selector_core.get("maxCount") == 1
                and native_first_main_end_selector_core.get("required_common_present") is True
            )
            else "fail",
            official=official_first_main_end_selector_core,
            native=native_first_main_end_selector_core,
            note="The turn-2 Main selector common core is normalized across official string option names and native numeric option ids. Attach and exact option identity/order remain branch-dependent until shuffle/card-order parity is solved.",
        ),
        comparison(
            comparison_id="post_first_main_end_option_card_ids",
            label="post first Main End option card ID resolution",
            status="pass"
            if (
                official_post_first_main_end_option_card_ids["frame_count"] == 1
                and native_post_first_main_end_option_card_ids["frame_count"] == 1
                and official_post_first_main_end_option_card_ids["unresolved_option_count"] == 0
                and native_post_first_main_end_option_card_ids["unresolved_option_count"] == 0
                and official_post_first_main_end_option_card_ids["resolved_option_count"] > 0
                and native_post_first_main_end_option_card_ids["resolved_option_count"] > 0
            )
            else "fail",
            official=official_post_first_main_end_option_card_ids,
            native=native_post_first_main_end_option_card_ids,
            note="The turn-2 Main selector's hand-backed options now resolve to visible hand card IDs on both wrappers: official Play/Attach/Evolve-style options resolve by hand index, while native options carry cardId directly. Exact option count, ids, and order remain branch-dependent until shuffle/card-order parity is solved.",
        ),
        comparison(
            comparison_id="phase_alignment",
            label="startup phase alignment",
            status="pass"
            if (
                official_first_context == "IsFirst"
                and official_first_type == "YesNo"
                and native_first_context == "IsFirst"
                and native_first_type == "YesNo"
                and official_deck_count == 60
                and native_pregame_counts_ok
            )
            else "gap",
            official={"phase": "pre-setup IsFirst prompt", "deck_count": official_deck_count},
            native={"phase": "pre-setup IsFirst prompt", "players": native_pregame_players},
            note="Both official and native now expose the startup first-player prompt before setup cards are dealt.",
        ),
        comparison(
            comparison_id="official_seed_surface",
            label="official startup shuffle seed surface",
            status="pass"
            if (
                official_shuffle_probe["seed_surface"]["exported_seed_symbols"] == []
                and official_shuffle_probe["seed_surface"]["has_random_device_symbol"] is True
                and official_shuffle_probe["seed_surface"]["has_mt19937_symbol"] is True
                and official_shuffle_probe["unique_order_count"] >= 2
                and native_startup_order_probe["same_seed_deterministic"] is True
                and native_startup_order_probe["different_seed_changes_order"] is True
            )
            else "gap",
            official={
                "exported_seed_symbols": official_shuffle_probe["seed_surface"]["exported_seed_symbols"],
                "has_random_device_symbol": official_shuffle_probe["seed_surface"]["has_random_device_symbol"],
                "has_mt19937_symbol": official_shuffle_probe["seed_surface"]["has_mt19937_symbol"],
                "attempt_count": official_shuffle_probe["attempt_count"],
                "unique_order_count": official_shuffle_probe["unique_order_count"],
                "deterministic_replay_available": official_shuffle_probe[
                    "deterministic_replay_available"
                ],
            },
            native=native_startup_order_probe,
            note="The public official wrapper exposes no seed setter and repeated BattleStart calls produce different ordered startup zones, while native remains explicitly deterministic by seed. Exact standalone card-order parity therefore requires discovering or exposing the official seed/order source, or replaying official observed ordered zones.",
        ),
        comparison(
            comparison_id="frame_by_frame_engine_parity",
            label="frame-by-frame engine parity",
            status="gap",
            official={
                "frames_available": len(official_frames),
                "first_context": official_first_context,
                "second_context": official_second_context,
                "third_context": official_third_context,
                "fourth_context": official_fourth_context,
            },
            native={
                "frames_available": 4,
                "first_context": native_first_context,
                "second_context": native_second_context,
                "third_context": native_third_context,
                "fourth_context": native_fourth_context,
                "reason": "native emits the first four startup frames, but hand RNG/card identity order and later setup Bench choices/main-loop frames are not fully proven 1:1 yet",
            },
            note="This is the main remaining 1:1 blocker: continue frame stepping through setup Bench choices and prove card-order/RNG parity.",
        ),
    ]
    summary = count_statuses(comparisons)
    payload = {
        "source": "native-official parity audit",
        "status": "partial_not_1_to_1" if summary["gap_count"] or summary["fail_count"] else "one_to_one_startup_parity",
        "decks": {
            "player": player_deck,
            "opponent": opponent_deck,
        },
        "official": {
            "source": "official cg.VisualizeData",
            "setup_branch_probe": setup_branch_probe,
            "shuffle_probe": official_shuffle_probe,
            "start_data": {
                "battle_ptr_present": bool(getattr(start_data, "battlePtr", None)),
                "error_player": int(start_data.errorPlayer),
                "error_type": int(start_data.errorType),
            },
            "observation_select_context": official_observation.get("select", {}).get("context")
            if isinstance(official_observation, dict)
            else None,
            "first_frame_context": official_first_context,
            "first_frame_type": official_first_type,
            "first_frame_player0_deck_count": official_deck_count,
            "frame_count": len(official_frames),
            "frames": official_frames[: max(1, args.max_frames)],
            "truncated": len(official_frames) > max(1, args.max_frames),
            "attempts": official_attempts,
            "post_isfirst": {
                "first_frame": official_frames_after_isfirst[1] if len(official_frames_after_isfirst) > 1 else {},
            },
            "post_setup_active": {
                "first_frame": third_frame,
                "active_selection": {
                    "player_index": official_setup_player_index,
                    "option_index": 0,
                    "option_hand_index": int(official_active_option["index"])
                    if "index" in official_active_option
                    else None,
                },
            },
            "post_both_actives": {
                "first_frame": fourth_frame,
                "active_selections": [
                    {
                        "player_index": first_player_choice,
                        "option_index": 0,
                        "option_hand_index": int(official_active_option["index"])
                        if "index" in official_active_option
                        else None,
                    },
                    {
                        "player_index": next_setup_player,
                        "option_index": 0,
                        "option_hand_index": int(official_next_active_option["index"])
                        if "index" in official_next_active_option
                        else None,
                    },
                ],
            },
            "post_setup_bench_skip": {
                "selection": [],
                "first_frame_summary": official_setup_bench_skip_summary,
                "frame_count": len(official_frames_after_setup_bench_skip),
                "frames": official_frames_after_setup_bench_skip[: max(1, args.max_frames)],
                "truncated": len(official_frames_after_setup_bench_skip) > max(1, args.max_frames),
            },
            "post_setup_complete_main": {
                "selection_sequence": [[], []],
                "first_frame_summary": official_setup_complete_main_summary,
                "selector_summary": official_setup_complete_main_selector,
                "frame_count": len(official_frames_after_setup_complete_main),
                "frames": official_frames_after_setup_complete_main[: max(1, args.max_frames)],
                "truncated": len(official_frames_after_setup_complete_main) > max(1, args.max_frames),
            },
            "post_first_main_end": {
                "selection": [official_first_main_end_option_index],
                "first_frame_summary": official_first_main_end_summary,
                "selector_summary": official_first_main_end_selector,
                "frame_count": len(official_frames_after_first_main_end),
                "frames": official_frames_after_first_main_end[: max(1, args.max_frames)],
                "truncated": len(official_frames_after_first_main_end) > max(1, args.max_frames),
            },
        },
        "native": {
            "wrapper": "clean-room C native core",
            "library": str(library_path),
            "version": native_core.version,
            "pregame": {
                "setup": native_setup_summary(native_pregame, seed=args.seed),
                "first_frame": native_first_frame,
            },
            "post_isfirst": {
                "setup": native_setup_summary(native_post_isfirst, seed=args.seed),
                "first_frame": native_second_frame,
            },
            "post_setup_active": {
                "setup": native_setup_summary(native_post_setup_active, seed=args.seed),
                "first_frame": native_third_frame,
                "active_selection": {
                    "player_index": first_player_choice,
                    "option_index": 0,
                    "hand_index": int(native_active_option["index"]),
                    "card_id": int(native_active_option["cardId"]) if "cardId" in native_active_option else None,
                },
            },
            "post_both_actives": {
                "setup": native_setup_summary(native_post_both_actives, seed=args.seed),
                "first_frame": native_fourth_frame,
                "active_selections": [
                    {
                        "player_index": first_player_choice,
                        "option_index": 0,
                        "hand_index": int(native_active_option["index"]),
                        "card_id": int(native_active_option["cardId"]) if "cardId" in native_active_option else None,
                    },
                    {
                        "player_index": next_setup_player,
                        "option_index": 0,
                        "hand_index": int(native_next_active_option["index"]),
                        "card_id": int(native_next_active_option["cardId"])
                        if "cardId" in native_next_active_option
                        else None,
                    },
                ],
            },
            "draw_count_replay": native_draw_count_replay,
            "setup_bench_optional_replay": native_setup_bench_optional_replay,
            "post_setup_bench_skip": {
                "setup": native_setup_summary(
                    native_post_setup_bench_skip,
                    seed=args.seed,
                    include_setup_details=True,
                ),
                "selection": [],
                "first_frame": native_post_setup_bench_skip_frame,
            },
            "post_setup_complete_main": {
                "setup": native_setup_summary(
                    native_post_setup_complete_main,
                    seed=args.seed,
                    include_setup_details=True,
                ),
                "selection_sequence": [[], []],
                "first_frame": native_post_setup_complete_main_frame,
                "selector_summary": native_setup_complete_main_selector,
            },
            "post_first_main_end": {
                "setup": native_setup_summary(
                    native_post_first_main_end,
                    seed=args.seed,
                    include_setup_details=True,
                ),
                "selection": ["end"],
                "first_frame": native_post_first_main_end_frame,
                "selector_summary": native_first_main_end_selector,
            },
            "post_setup_bench": (
                {
                    "setup": native_setup_summary(
                        native_post_setup_bench,
                        seed=args.seed,
                        include_setup_details=True,
                    ),
                    "first_frame": native_fifth_frame,
                    "bench_selection": {
                        "player_index": first_player_choice,
                        "option_index": 0,
                        "hand_index": int(native_setup_bench_option["index"]),
                        "card_id": int(native_setup_bench_option["cardId"])
                        if "cardId" in native_setup_bench_option
                        else None,
                    },
                }
                if native_post_setup_bench is not None and native_setup_bench_option is not None
                else None
            ),
        },
        "comparisons": comparisons,
        "summary": summary,
        "kaggle_submission_made": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
