from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class CardLocation:
    card_id: int | None
    serial: int
    player_index: int
    zone: str
    attached_to_serial: int | None = None


@dataclass(frozen=True)
class PokemonPublicState:
    card_id: int | None
    serial: int | None
    player_index: int
    zone: str
    hp: int | None
    max_hp: int | None
    appear_this_turn: bool
    energy_card_ids: tuple[int, ...]
    energy_serials: tuple[int, ...]
    tool_card_ids: tuple[int, ...]
    tool_serials: tuple[int, ...]
    pre_evolution_card_ids: tuple[int, ...]
    pre_evolution_serials: tuple[int, ...]


@dataclass(frozen=True)
class PlayerPublicState:
    player_index: int
    active: tuple[PokemonPublicState, ...]
    bench: tuple[PokemonPublicState, ...]
    bench_max: int
    deck_count: int
    hand_count: int
    hand_visible: bool
    visible_hand_card_ids: tuple[int, ...]
    visible_hand_serials: tuple[int, ...]
    discard_card_ids: tuple[int, ...]
    discard_serials: tuple[int, ...]
    prize_count: int
    poisoned: bool
    burned: bool
    asleep: bool
    paralyzed: bool
    confused: bool


@dataclass(frozen=True)
class ReplayLogEvent:
    type: int | None
    player_index: int | None
    card_id: int | None
    serial: int | None
    from_area: int | None
    to_area: int | None
    card_id_target: int | None
    serial_target: int | None
    value: int | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class ReplayEngineSnapshot:
    replay_id: str
    step_index: int
    agent_index: int | None
    turn: int | None
    turn_action_count: int | None
    your_index: int | None
    first_player: int | None
    result: int | None
    supporter_played: bool
    stadium_played: bool
    energy_attached: bool
    retreated: bool
    players: tuple[PlayerPublicState, ...]
    stadium_card_ids: tuple[int, ...]
    stadium_serials: tuple[int, ...]
    legal_action_count: int
    select_type: int | None
    select_context: int | None
    log_events: tuple[ReplayLogEvent, ...]

    @property
    def log_types(self) -> tuple[int, ...]:
        return tuple(event.type for event in self.log_events if event.type is not None)

    def iter_card_locations(self) -> Iterable[CardLocation]:
        for player in self.players:
            yield from _hand_locations(player)
            yield from _discard_locations(player)
            for pokemon in player.active:
                yield from _pokemon_locations(pokemon, "active")
            for pokemon in player.bench:
                yield from _pokemon_locations(pokemon, "bench")
        for card_id, serial in zip(self.stadium_card_ids, self.stadium_serials):
            yield CardLocation(card_id=card_id, serial=serial, player_index=-1, zone="stadium")


@dataclass(frozen=True)
class ZoneCountDelta:
    player_index: int
    zone: str
    card_id: int
    delta: int


@dataclass(frozen=True)
class CardMovement:
    card_id: int | None
    serial: int
    player_index: int
    from_zone: str
    to_zone: str
    from_attached_to_serial: int | None
    to_attached_to_serial: int | None
    log_type_hint: int | None


@dataclass(frozen=True)
class ReplayStateDelta:
    before_step_index: int
    after_step_index: int
    count_deltas: tuple[ZoneCountDelta, ...]
    movements: tuple[CardMovement, ...]
    log_events: tuple[ReplayLogEvent, ...]

    def count_delta(self, *, player_index: int, zone: str, card_id: int) -> int:
        for delta in self.count_deltas:
            if delta.player_index == player_index and delta.zone == zone and delta.card_id == card_id:
                return delta.delta
        return 0

    def movement_for_serial(self, serial: int) -> CardMovement | None:
        for movement in self.movements:
            if movement.serial == serial:
                return movement
        return None


def snapshot_from_observation(
    observation: dict[str, Any],
    *,
    replay_id: str = "",
    step_index: int = -1,
    agent_index: int | None = None,
) -> ReplayEngineSnapshot:
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    select = observation.get("select") if isinstance(observation.get("select"), dict) else {}
    options = select.get("option") if isinstance(select.get("option"), list) else []
    players = tuple(
        _parse_player(player_index, player)
        for player_index, player in enumerate(current.get("players") or [])
        if isinstance(player, dict)
    )
    stadium_cards = _card_refs(current.get("stadium"))
    log_events = tuple(_parse_log_event(item) for item in observation.get("logs") or [] if isinstance(item, dict))
    return ReplayEngineSnapshot(
        replay_id=replay_id,
        step_index=step_index,
        agent_index=agent_index,
        turn=_int_or_none(current.get("turn")),
        turn_action_count=_int_or_none(current.get("turnActionCount")),
        your_index=_int_or_none(current.get("yourIndex")),
        first_player=_int_or_none(current.get("firstPlayer")),
        result=_int_or_none(current.get("result")),
        supporter_played=bool(current.get("supporterPlayed")),
        stadium_played=bool(current.get("stadiumPlayed")),
        energy_attached=bool(current.get("energyAttached")),
        retreated=bool(current.get("retreated")),
        players=players,
        stadium_card_ids=tuple(card_id for card_id, _serial in stadium_cards),
        stadium_serials=tuple(serial for _card_id, serial in stadium_cards),
        legal_action_count=len(options),
        select_type=_int_or_none(select.get("type")),
        select_context=_int_or_none(select.get("context")),
        log_events=log_events,
    )


def diff_snapshots(before: ReplayEngineSnapshot, after: ReplayEngineSnapshot) -> ReplayStateDelta:
    before_locations = {location.serial: location for location in before.iter_card_locations()}
    after_locations = {location.serial: location for location in after.iter_card_locations()}
    count_deltas = _count_deltas(before_locations.values(), after_locations.values())
    log_hints = _log_type_hints(after.log_events)
    movements: list[CardMovement] = []
    for serial in sorted(set(before_locations).intersection(after_locations)):
        previous = before_locations[serial]
        current = after_locations[serial]
        if (
            previous.zone == current.zone
            and previous.attached_to_serial == current.attached_to_serial
            and previous.player_index == current.player_index
        ):
            continue
        movements.append(
            CardMovement(
                card_id=current.card_id if current.card_id is not None else previous.card_id,
                serial=serial,
                player_index=current.player_index,
                from_zone=previous.zone,
                to_zone=current.zone,
                from_attached_to_serial=previous.attached_to_serial,
                to_attached_to_serial=current.attached_to_serial,
                log_type_hint=log_hints.get(serial),
            )
        )
    return ReplayStateDelta(
        before_step_index=before.step_index,
        after_step_index=after.step_index,
        count_deltas=tuple(count_deltas),
        movements=tuple(movements),
        log_events=after.log_events,
    )


def _parse_player(player_index: int, player: dict[str, Any]) -> PlayerPublicState:
    hand = player.get("hand")
    hand_refs = _card_refs(hand) if isinstance(hand, list) else []
    discard_refs = _card_refs(player.get("discard"))
    prize = player.get("prize")
    prize_count = _int_or_none(player.get("prize_count"))
    if prize_count is None and isinstance(prize, list):
        prize_count = len(prize)
    return PlayerPublicState(
        player_index=player_index,
        active=tuple(
            state
            for state in (_parse_pokemon(item, zone="active") for item in player.get("active") or [])
            if state is not None
        ),
        bench=tuple(
            state
            for state in (_parse_pokemon(item, zone="bench") for item in player.get("bench") or [])
            if state is not None
        ),
        bench_max=int(player.get("benchMax") or 0),
        deck_count=int(player.get("deckCount") or player.get("deck_count") or 0),
        hand_count=int(player.get("handCount") or 0),
        hand_visible=isinstance(hand, list),
        visible_hand_card_ids=tuple(card_id for card_id, _serial in hand_refs),
        visible_hand_serials=tuple(serial for _card_id, serial in hand_refs),
        discard_card_ids=tuple(card_id for card_id, _serial in discard_refs),
        discard_serials=tuple(serial for _card_id, serial in discard_refs),
        prize_count=int(prize_count or 0),
        poisoned=bool(player.get("poisoned")),
        burned=bool(player.get("burned")),
        asleep=bool(player.get("asleep")),
        paralyzed=bool(player.get("paralyzed")),
        confused=bool(player.get("confused")),
    )


def _parse_pokemon(value: Any, *, zone: str) -> PokemonPublicState | None:
    if not isinstance(value, dict):
        return None
    energies = _card_refs(value.get("energyCards"))
    if not energies:
        energies = [(card_id, -1) for card_id in _int_tuple(value.get("energies"))]
    tools = _card_refs(value.get("tools"))
    pre_evolution = _card_refs(value.get("preEvolution"))
    return PokemonPublicState(
        card_id=_int_or_none(value.get("id")),
        serial=_int_or_none(value.get("serial")),
        player_index=int(value.get("playerIndex") or 0),
        zone=zone,
        hp=_int_or_none(value.get("hp")),
        max_hp=_int_or_none(value.get("maxHp")),
        appear_this_turn=bool(value.get("appearThisTurn")),
        energy_card_ids=tuple(card_id for card_id, _serial in energies),
        energy_serials=tuple(serial for _card_id, serial in energies if serial >= 0),
        tool_card_ids=tuple(card_id for card_id, _serial in tools),
        tool_serials=tuple(serial for _card_id, serial in tools),
        pre_evolution_card_ids=tuple(card_id for card_id, _serial in pre_evolution),
        pre_evolution_serials=tuple(serial for _card_id, serial in pre_evolution),
    )


def _parse_log_event(value: dict[str, Any]) -> ReplayLogEvent:
    return ReplayLogEvent(
        type=_int_or_none(value.get("type")),
        player_index=_int_or_none(value.get("playerIndex")),
        card_id=_int_or_none(value.get("cardId")),
        serial=_int_or_none(value.get("serial")),
        from_area=_int_or_none(value.get("fromArea")),
        to_area=_int_or_none(value.get("toArea")),
        card_id_target=_int_or_none(value.get("cardIdTarget")),
        serial_target=_int_or_none(value.get("serialTarget")),
        value=_int_or_none(value.get("value")),
        raw=dict(value),
    )


def _hand_locations(player: PlayerPublicState) -> Iterable[CardLocation]:
    for card_id, serial in zip(player.visible_hand_card_ids, player.visible_hand_serials):
        yield CardLocation(card_id=card_id, serial=serial, player_index=player.player_index, zone="hand")


def _discard_locations(player: PlayerPublicState) -> Iterable[CardLocation]:
    for card_id, serial in zip(player.discard_card_ids, player.discard_serials):
        yield CardLocation(card_id=card_id, serial=serial, player_index=player.player_index, zone="discard")


def _pokemon_locations(pokemon: PokemonPublicState, base_zone: str) -> Iterable[CardLocation]:
    if pokemon.serial is not None:
        yield CardLocation(
            card_id=pokemon.card_id,
            serial=pokemon.serial,
            player_index=pokemon.player_index,
            zone=base_zone,
        )
    for card_id, serial in zip(pokemon.energy_card_ids, pokemon.energy_serials):
        yield CardLocation(
            card_id=card_id,
            serial=serial,
            player_index=pokemon.player_index,
            zone=f"{base_zone}_energy",
            attached_to_serial=pokemon.serial,
        )
    for card_id, serial in zip(pokemon.tool_card_ids, pokemon.tool_serials):
        yield CardLocation(
            card_id=card_id,
            serial=serial,
            player_index=pokemon.player_index,
            zone=f"{base_zone}_tool",
            attached_to_serial=pokemon.serial,
        )
    for card_id, serial in zip(pokemon.pre_evolution_card_ids, pokemon.pre_evolution_serials):
        yield CardLocation(
            card_id=card_id,
            serial=serial,
            player_index=pokemon.player_index,
            zone=f"{base_zone}_pre_evolution",
            attached_to_serial=pokemon.serial,
        )


def _count_deltas(before: Iterable[CardLocation], after: Iterable[CardLocation]) -> list[ZoneCountDelta]:
    before_counts = Counter(
        (location.player_index, location.zone, location.card_id)
        for location in before
        if location.card_id is not None
    )
    after_counts = Counter(
        (location.player_index, location.zone, location.card_id)
        for location in after
        if location.card_id is not None
    )
    output: list[ZoneCountDelta] = []
    for key in sorted(set(before_counts).union(after_counts)):
        delta = after_counts[key] - before_counts[key]
        if delta == 0:
            continue
        player_index, zone, card_id = key
        output.append(
            ZoneCountDelta(
                player_index=player_index,
                zone=zone,
                card_id=card_id,
                delta=delta,
            )
        )
    return output


def _log_type_hints(events: Iterable[ReplayLogEvent]) -> dict[int, int]:
    hints: dict[int, int] = {}
    for event in events:
        if event.serial is not None and event.type is not None:
            hints[event.serial] = event.type
    return hints


def _card_refs(value: Any) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        return []
    refs: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        card_id = _int_or_none(item.get("id"))
        serial = _int_or_none(item.get("serial"))
        if card_id is None or serial is None:
            continue
        refs.append((card_id, serial))
    return refs


def _int_tuple(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    output: list[int] = []
    for item in value:
        parsed = _int_or_none(item)
        if parsed is not None:
            output.append(parsed)
    return tuple(output)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
