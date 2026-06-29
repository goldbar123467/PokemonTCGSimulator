from __future__ import annotations

from collections.abc import Sequence


FIGHTING_ENERGY_ID = 6
MEGA_LUCARIO_EX_ID = 678
RIOLU_ID = 677
MAKUHITA_ID = 673
HARIYAMA_ID = 674
LUNATONE_ID = 675
SOLROCK_ID = 676
DRAGAPULT_EX_ID = 121
DRAKLOAK_ID = 120
DREEPY_ID = 119

LUCARIO_CORE_CARD_TAGS = {
    1142: "fighting_gong",
    1152: "poke_pad",
    1182: "boss_orders",
    1227: "lillies_determination",
}
LUCARIO_DAMAGE_AMP_CARD_TAGS = {
    1141: "premium_power_pro",
    1252: "gravity_mountain",
    1159: "heros_cape",
}
LUCARIO_POKEMON_CARD_TAGS = {
    MEGA_LUCARIO_EX_ID: "mega_lucario_ex",
    RIOLU_ID: "riolu",
    MAKUHITA_ID: "makuhita",
    HARIYAMA_ID: "hariyama",
    LUNATONE_ID: "lunatone",
    SOLROCK_ID: "solrock",
}
LUCARIO_ATTACK_TAGS = {
    982: "aura_jab",
    983: "mega_brave",
}
DRAGAPULT_CARD_TAGS = {
    DRAGAPULT_EX_ID: "dragapult_ex",
    DRAKLOAK_ID: "drakloak",
    DREEPY_ID: "dreepy",
}


def _cards(player: dict, zone: str) -> list[dict]:
    value = player.get(zone)
    return [card for card in value if isinstance(card, dict)] if isinstance(value, list) else []


def _energy_value(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _energy_count(card: dict) -> int:
    energy_cards = _energy_value(card.get("energyCards"))
    if energy_cards:
        return energy_cards
    return _energy_value(card.get("energies"))


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _add_card_id(card_ids: list[int], value: object) -> None:
    card_id = _int_or_none(value)
    if card_id is None:
        return
    if card_id > 0:
        card_ids.append(card_id)


def _visible_zone_cards(player: dict, zone: str) -> list[dict]:
    if zone in {"deck", "prize"}:
        return []
    return _cards(player, zone)


def _zone_name(area: object) -> str | None:
    area_map = {
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
    }
    return area_map.get(area)


def _option_area_card(players: list[dict], option: dict, your_index: int) -> dict | None:
    zone = _zone_name(option.get("area"))
    if zone is None:
        return None
    try:
        player_index = int(option.get("playerIndex", your_index))
        index = int(option.get("index"))
    except (TypeError, ValueError):
        return None
    if not (0 <= player_index < len(players)):
        return None
    cards = _visible_zone_cards(players[player_index] or {}, zone)
    if not (0 <= index < len(cards)):
        return None
    return cards[index]


def _option_target_card(players: list[dict], option: dict, your_index: int) -> dict | None:
    zone = _zone_name(option.get("inPlayArea"))
    if zone is None:
        zone = _zone_name(option.get("targetArea"))
    if zone is None:
        return None
    player_value = option.get("targetPlayerIndex", option.get("inPlayPlayerIndex", option.get("playerIndex", your_index)))
    index_value = option.get("targetIndex", option.get("inPlayIndex"))
    try:
        player_index = int(player_value)
        index = int(index_value)
    except (TypeError, ValueError):
        return None
    if not (0 <= player_index < len(players)):
        return None
    cards = _visible_zone_cards(players[player_index] or {}, zone)
    if not (0 <= index < len(cards)):
        return None
    return cards[index]


def _card_ids(player: dict, zones: Sequence[str]) -> set[int]:
    ids: set[int] = set()
    for zone in zones:
        for card in _visible_zone_cards(player, zone):
            card_id = _int_or_none(card.get("id"))
            if card_id is not None:
                ids.add(card_id)
    return ids


def _has_card_id(player: dict, zones: Sequence[str], card_id: int) -> bool:
    return card_id in _card_ids(player, zones)


def _has_fighting_energy_in_discard(player: dict) -> bool:
    return any(_int_or_none(card.get("id")) == FIGHTING_ENERGY_ID for card in _cards(player, "discard"))


def _hp_bucket(card: dict) -> str:
    hp = _int_or_none(card.get("hp"))
    max_hp = _int_or_none(card.get("maxHp"))
    if hp is None or max_hp is None or max_hp <= 0:
        return "unknown"
    ratio = hp / max_hp
    if ratio <= 0.25:
        return "critical"
    if ratio <= 0.5:
        return "damaged"
    return "healthy"


def _powered_board_count(player: dict) -> int:
    return sum(1 for card in _cards(player, "active") + _cards(player, "bench") if _energy_count(card) > 0)


def _ready_attacker_present(player: dict) -> bool:
    return any(_energy_count(card) >= 2 for card in _cards(player, "active") + _cards(player, "bench"))


def _add_visible_line_tokens(tokens: list[str], prefix: str, player: dict) -> None:
    ids = _card_ids(player, ("active", "bench"))
    if MEGA_LUCARIO_EX_ID in ids or RIOLU_ID in ids:
        tokens.append(f"{prefix}_lucario_line")
    if DRAGAPULT_EX_ID in ids or DRAKLOAK_ID in ids or DREEPY_ID in ids:
        tokens.append(f"{prefix}_dragapult_line")
    active = _cards(player, "active")
    if active:
        active_id = _int_or_none(active[0].get("id"))
        if active_id in DRAGAPULT_CARD_TAGS:
            tokens.append(f"{prefix}_active_dragapult_line")
        if active_id in LUCARIO_POKEMON_CARD_TAGS:
            tokens.append(f"{prefix}_active_lucario_line")


def _add_lucario_source_card_tokens(tokens: list[str], source_card_id: int | None) -> None:
    if source_card_id is None:
        return
    tokens.append(f"option_source_card:{source_card_id}")
    if source_card_id in LUCARIO_CORE_CARD_TAGS:
        tokens.append(f"lucario_core_card:{LUCARIO_CORE_CARD_TAGS[source_card_id]}")
    if source_card_id in LUCARIO_DAMAGE_AMP_CARD_TAGS:
        tokens.append(f"lucario_damage_amp:{LUCARIO_DAMAGE_AMP_CARD_TAGS[source_card_id]}")
    if source_card_id in LUCARIO_POKEMON_CARD_TAGS:
        tokens.append(f"lucario_pokemon:{LUCARIO_POKEMON_CARD_TAGS[source_card_id]}")


def _add_option_target_tokens(tokens: list[str], target_card: dict | None) -> None:
    if target_card is None:
        return
    target_id = _int_or_none(target_card.get("id"))
    if target_id is None:
        return
    tokens.append(f"option_target_card:{target_id}")
    tokens.append(f"option_target_energy:{_energy_count(target_card)}")
    tokens.append(f"option_target_hp_bucket:{_hp_bucket(target_card)}")
    if target_id in LUCARIO_POKEMON_CARD_TAGS:
        tokens.append(f"option_target_lucario_pokemon:{LUCARIO_POKEMON_CARD_TAGS[target_id]}")
    if target_id in DRAGAPULT_CARD_TAGS:
        tokens.append(f"option_target_dragapult_pokemon:{DRAGAPULT_CARD_TAGS[target_id]}")


def _add_posture_tokens(tokens: list[str], us: dict, them: dict) -> None:
    us_prizes = len(us.get("prize") or [])
    them_prizes = len(them.get("prize") or [])
    if us_prizes > them_prizes:
        tokens.append("posture:behind_on_prizes")
    elif us_prizes < them_prizes:
        tokens.append("posture:ahead_on_prizes")
    else:
        tokens.append("posture:even_prizes")
    if _ready_attacker_present(us):
        tokens.append("posture:has_ready_attacker")
    else:
        tokens.append("posture:setup_need_attacker")
    if _powered_board_count(them) > _powered_board_count(us):
        tokens.append("posture:behind_powered_board")


def _add_lucario_board_tokens(tokens: list[str], us: dict, them: dict) -> None:
    active = _cards(us, "active")
    active_id = _int_or_none(active[0].get("id")) if active else None
    active_energy = _energy_count(active[0]) if active else 0
    us_board_ids = _card_ids(us, ("active", "bench"))
    them_board_ids = _card_ids(them, ("active", "bench"))

    if active_id == MEGA_LUCARIO_EX_ID:
        tokens.append("lucario_board:mega_lucario_active")
        if active_energy >= 2:
            tokens.append("lucario_board:mega_lucario_ready")
    if MEGA_LUCARIO_EX_ID in us_board_ids or RIOLU_ID in us_board_ids:
        tokens.append("lucario_board:lucario_line_present")
    if HARIYAMA_ID in us_board_ids or MEGA_LUCARIO_EX_ID in _card_ids(us, ("bench",)) or RIOLU_ID in _card_ids(us, ("bench",)):
        tokens.append("lucario_board:next_attacker_available")
    if _has_card_id(us, ("active", "bench"), SOLROCK_ID) and _has_card_id(us, ("active", "bench"), LUNATONE_ID):
        tokens.append("lucario_board:solrock_lunatone_online")
    if _has_fighting_energy_in_discard(us):
        tokens.append("lucario_board:fighting_energy_in_discard")
        if active_id == MEGA_LUCARIO_EX_ID:
            tokens.append("lucario_plan:aura_jab_acceleration")
    if MEGA_LUCARIO_EX_ID in them_board_ids or RIOLU_ID in them_board_ids:
        tokens.append("lucario_matchup:opposing_lucario_line")
    if MEGA_LUCARIO_EX_ID in them_board_ids and active_id == MEGA_LUCARIO_EX_ID:
        tokens.append("lucario_matchup:mirror_pressure")


def option_card_ids(obs: dict, option: dict) -> list[int]:
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    if len(players) < 2:
        players = [{}, {}]
    your = int(current.get("yourIndex") or 0)
    card_ids: list[int] = []
    _add_card_id(card_ids, option.get("cardId"))

    source_card = _option_area_card(players, option, your)
    if source_card is not None:
        _add_card_id(card_ids, source_card.get("id"))

    for player in players[:2]:
        if not isinstance(player, dict):
            continue
        for zone in ("active", "bench", "discard", "stadium", "looking"):
            for card in _visible_zone_cards(player, zone):
                _add_card_id(card_ids, card.get("id"))
                for attached in card.get("energyCards") or []:
                    if isinstance(attached, dict):
                        _add_card_id(card_ids, attached.get("id"))
                for tool in card.get("tools") or []:
                    if isinstance(tool, dict):
                        _add_card_id(card_ids, tool.get("id"))

    return card_ids


def option_feature_tokens(obs: dict, option: dict, *, option_index: int) -> list[str]:
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    if len(players) < 2:
        players = [{}, {}]
    your = int(current.get("yourIndex") or 0)
    us = players[your] or {}
    them = players[1 - your] or {}
    select = obs.get("select") or {}
    source_card = _option_area_card(players, option, your)
    target_card = _option_target_card(players, option, your)
    source_card_id = _int_or_none(source_card.get("id")) if source_card is not None else _int_or_none(option.get("cardId"))
    attack_id = _int_or_none(option.get("attackId"))
    tokens = [
        f"turn:{current.get('turn')}",
        f"turn_action:{current.get('turnActionCount')}",
        f"your:{your}",
        f"context:{select.get('context')}",
        f"select_type:{select.get('type')}",
        f"option_index:{option_index}",
        f"option_type:{option.get('type')}",
        f"option_card:{option.get('cardId')}",
        f"option_attack:{option.get('attackId')}",
        f"option_area:{option.get('area')}",
        f"option_player:{option.get('playerIndex')}",
    ]
    _add_lucario_source_card_tokens(tokens, source_card_id)
    if attack_id in LUCARIO_ATTACK_TAGS:
        tokens.append(f"lucario_attack:{LUCARIO_ATTACK_TAGS[attack_id]}")
    _add_option_target_tokens(tokens, target_card)
    _add_lucario_board_tokens(tokens, us, them)
    _add_posture_tokens(tokens, us, them)
    for prefix, player in (("us", us), ("them", them)):
        _add_visible_line_tokens(tokens, prefix, player)
        active = _cards(player, "active")
        if active:
            card = active[0]
            tokens.extend([f"{prefix}_active:{card.get('id')}", f"{prefix}_active_energy:{_energy_count(card)}"])
        for card in _cards(player, "bench"):
            tokens.extend([f"{prefix}_bench_id:{card.get('id')}", f"{prefix}_bench_energy:{_energy_count(card)}"])
        tokens.extend(
            [
                f"{prefix}_hand:{player.get('handCount')}",
                f"{prefix}_deck:{player.get('deckCount')}",
                f"{prefix}_prizes:{len(player.get('prize') or [])}",
                f"{prefix}_bench_count:{len(_cards(player, 'bench'))}",
                f"{prefix}_powered_board:{_powered_board_count(player)}",
            ]
        )
    return tokens


def choose_legal_action(options: Sequence[dict], *, min_count: int, max_count: int, scores: Sequence[float]) -> list[int]:
    if not options:
        return []
    count = max(min_count, min(max_count, len(options)))
    ranked = sorted(range(len(options)), key=lambda index: (-float(scores[index]), index))
    return ranked[:count]
