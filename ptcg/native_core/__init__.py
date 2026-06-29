from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time


DECK_SIZE = 60
HAND_SIZE = 60
DISCARD_SIZE = 120
PRIZE_SIZE = 6
BENCH_SIZE = 5
ATTACHED_SIZE = 60
PRE_EVOLUTION_SIZE = 3
CARD_ATTACK_SIZE = 2
ATTACK_COST_SIZE = 5
AREA_DECK = 1
AREA_HAND = 2
AREA_DISCARD = 3
AREA_ACTIVE = 4
AREA_BENCH = 5
CARD_DUSK_BALL = 1102
CARD_SWITCH = 1123
CARD_PREMIUM_POWER_PRO = 1141
CARD_FIGHTING_GONG = 1142
CARD_POKE_PAD = 1152
CARD_HEROS_CAPE = 1159
CARD_BOSS_ORDERS = 1182
CARD_CARMINE = 1192
CARD_LILLIES_DETERMINATION = 1227
CARD_GRAVITY_MOUNTAIN = 1252
CARD_HARIYAMA = 674
CARD_LUNATONE = 675
CARD_SOLROCK = 676
CARD_MEGA_LUCARIO_EX = 678
ATTACK_WILD_PRESS = 978
ATTACK_COSMIC_BEAM = 980
ATTACK_AURA_JAB = 982
ENERGY_FIGHTING = 6
RESISTANCE_DAMAGE_REDUCTION = 30
SOURCE_PATH = Path(__file__).with_name("ptcg_native_core.c")
HEADER_PATH = Path(__file__).with_name("ptcg_native_core.h")
CARD_CATALOG_PATH = Path(__file__).with_name("ptcg_card_catalog.generated.h")
NATIVE_BUILD_INPUTS = (SOURCE_PATH, HEADER_PATH, CARD_CATALOG_PATH)
DEFAULT_BUILD_DIR = Path("artifacts/native_api")


class NativeCoreError(RuntimeError):
    pass


class _NativeDeckC(ctypes.Structure):
    _fields_ = [
        ("card_count", ctypes.c_int),
        ("cards", ctypes.c_int * DECK_SIZE),
    ]


class _NativeDeckNamedCountC(ctypes.Structure):
    _fields_ = [
        ("card_id", ctypes.c_int),
        ("count", ctypes.c_int),
        ("name", ctypes.c_char * 96),
    ]


class _NativeBattlePlayerC(ctypes.Structure):
    _fields_ = [
        ("deck_count", ctypes.c_int),
        ("deck", ctypes.c_int * DECK_SIZE),
        ("hand_count", ctypes.c_int),
        ("hand", ctypes.c_int * HAND_SIZE),
        ("discard_count", ctypes.c_int),
        ("discard", ctypes.c_int * DISCARD_SIZE),
        ("prize_count", ctypes.c_int),
        ("prize", ctypes.c_int * PRIZE_SIZE),
        ("active_card_id", ctypes.c_int),
        ("active_damage", ctypes.c_int),
        ("active_entered_turn", ctypes.c_int),
        ("active_evolved_turn", ctypes.c_int),
        ("active_pre_evolution_count", ctypes.c_int),
        ("active_pre_evolution", ctypes.c_int * PRE_EVOLUTION_SIZE),
        ("active_energy_count", ctypes.c_int),
        ("active_energy", ctypes.c_int * ATTACHED_SIZE),
        ("active_tool_card_id", ctypes.c_int),
        ("active_disabled_attack_id", ctypes.c_int),
        ("active_disabled_attack_turn", ctypes.c_int),
        ("bench_count", ctypes.c_int),
        ("bench", ctypes.c_int * BENCH_SIZE),
        ("bench_damage", ctypes.c_int * BENCH_SIZE),
        ("bench_entered_turn", ctypes.c_int * BENCH_SIZE),
        ("bench_evolved_turn", ctypes.c_int * BENCH_SIZE),
        ("bench_pre_evolution_count", ctypes.c_int * BENCH_SIZE),
        ("bench_pre_evolution", (ctypes.c_int * PRE_EVOLUTION_SIZE) * BENCH_SIZE),
        ("bench_energy_count", ctypes.c_int * BENCH_SIZE),
        ("bench_energy", (ctypes.c_int * ATTACHED_SIZE) * BENCH_SIZE),
        ("bench_tool", ctypes.c_int * BENCH_SIZE),
    ]


class _NativeBattleSetupC(ctypes.Structure):
    _fields_ = [
        ("turn", ctypes.c_int),
        ("first_player", ctypes.c_int),
        ("current_player", ctypes.c_int),
        ("setup_complete", ctypes.c_int * 2),
        ("setup_mulligans", ctypes.c_int * 2),
        ("setup_mulligan_draw_choices", ctypes.c_int * 2),
        ("energy_attached", ctypes.c_int),
        ("retreated", ctypes.c_int),
        ("supporter_played", ctypes.c_int),
        ("lunar_cycle_used", ctypes.c_int),
        ("stadium_played", ctypes.c_int),
        ("stadium_card_id", ctypes.c_int),
        ("stadium_player_index", ctypes.c_int),
        ("fighting_attack_bonus", ctypes.c_int),
        ("result", ctypes.c_int),
        ("pending_promotion_player", ctypes.c_int),
        ("pending_promotion_next_player", ctypes.c_int),
        ("pending_dusk_ball_player", ctypes.c_int),
        ("pending_dusk_ball_start", ctypes.c_int),
        ("pending_dusk_ball_count", ctypes.c_int),
        ("pending_boss_orders_player", ctypes.c_int),
        ("pending_heave_ho_player", ctypes.c_int),
        ("pending_fighting_gong_player", ctypes.c_int),
        ("pending_poke_pad_player", ctypes.c_int),
        ("pending_switch_player", ctypes.c_int),
        ("pending_retreat_player", ctypes.c_int),
        ("pending_retreat_remaining", ctypes.c_int),
        ("pending_aura_jab_player", ctypes.c_int),
        ("pending_aura_jab_remaining", ctypes.c_int),
        ("players", _NativeBattlePlayerC * 2),
    ]


class _NativeCardMetadataC(ctypes.Structure):
    _fields_ = [
        ("card_id", ctypes.c_int),
        ("card_type", ctypes.c_int),
        ("hp", ctypes.c_int),
        ("basic", ctypes.c_int),
        ("stage1", ctypes.c_int),
        ("stage2", ctypes.c_int),
        ("energy_type", ctypes.c_int),
        ("retreat_cost", ctypes.c_int),
        ("weakness_type", ctypes.c_int),
        ("resistance_type", ctypes.c_int),
        ("ex", ctypes.c_int),
        ("mega_ex", ctypes.c_int),
        ("evolves_from", ctypes.c_char * 96),
        ("attack_count", ctypes.c_int),
        ("attacks", ctypes.c_int * CARD_ATTACK_SIZE),
        ("name", ctypes.c_char * 96),
    ]


class _NativeAttackMetadataC(ctypes.Structure):
    _fields_ = [
        ("attack_id", ctypes.c_int),
        ("damage", ctypes.c_int),
        ("energy_count", ctypes.c_int),
        ("energies", ctypes.c_int * ATTACK_COST_SIZE),
        ("name", ctypes.c_char * 96),
    ]


@dataclass(frozen=True)
class NativeDeck:
    cards: tuple[int, ...]

    @property
    def card_count(self) -> int:
        return len(self.cards)

    @property
    def sha256(self) -> str:
        canonical = ("\n".join(str(card) for card in self.cards) + "\n").encode("ascii")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class NativeDeckLoadResult:
    ok: bool
    error_code: int
    message: str
    deck: NativeDeck | None = None


@dataclass(frozen=True)
class NativeDeckSummary:
    card_count: int
    unique_count: int
    basic_pokemon_count: int
    energy_count: int
    named_counts: tuple[dict[str, int | str], ...]

    def count_card(self, card_id: int) -> int:
        for item in self.named_counts:
            if item["card_id"] == card_id:
                return int(item["count"])
        return 0


@dataclass(frozen=True)
class NativeCardMetadata:
    card_id: int
    card_type: int
    hp: int
    basic: bool
    stage1: bool
    stage2: bool
    energy_type: int
    retreat_cost: int
    weakness_type: int | None
    resistance_type: int | None
    ex: bool
    mega_ex: bool
    evolves_from: str | None
    attack_ids: tuple[int, ...]
    name: str

    @property
    def is_basic_pokemon(self) -> bool:
        return self.card_type == 0 and self.basic

    @property
    def is_pokemon(self) -> bool:
        return self.card_type == 0


@dataclass(frozen=True)
class NativeAttackMetadata:
    attack_id: int
    damage: int
    energy_types: tuple[int, ...]
    name: str


@dataclass(frozen=True)
class NativeBattlePlayer:
    deck_card_ids: tuple[int, ...]
    hand_card_ids: tuple[int, ...]
    prize_card_ids: tuple[int, ...]
    active_card_id: int | None
    bench_card_ids: tuple[int, ...]
    discard_card_ids: tuple[int, ...] = ()
    active_damage: int = 0
    bench_damage: tuple[int, ...] = ()
    active_entered_turn: int = 0
    active_evolved_turn: int = 0
    bench_entered_turns: tuple[int, ...] = ()
    bench_evolved_turns: tuple[int, ...] = ()
    active_pre_evolution_card_ids: tuple[int, ...] = ()
    bench_pre_evolution_card_ids: tuple[tuple[int, ...], ...] = ()
    active_energy_card_ids: tuple[int, ...] = ()
    bench_energy_card_ids: tuple[tuple[int, ...], ...] = ()
    active_energy_card_serials: tuple[int, ...] = ()
    bench_energy_card_serials: tuple[tuple[int, ...], ...] = ()
    active_tool_card_id: int | None = None
    bench_tool_card_ids: tuple[int | None, ...] = ()
    active_disabled_attack_id: int | None = None
    active_disabled_attack_turn: int = 0
    setup_complete: bool = False
    deck_card_serials: tuple[int, ...] = ()
    hand_card_serials: tuple[int, ...] = ()
    prize_card_serials: tuple[int, ...] = ()
    active_card_serial: int | None = None
    bench_card_serials: tuple[int, ...] = ()

    @property
    def deck_count(self) -> int:
        return len(self.deck_card_ids)

    @property
    def hand_count(self) -> int:
        return len(self.hand_card_ids)

    @property
    def prize_count(self) -> int:
        return len(self.prize_card_ids)

    def to_observation_player(
        self,
        *,
        viewer_index: int,
        player_index: int,
        current_turn: int,
        stadium_card_id: int | None = None,
        native_core: NativeCore | None = None,
    ) -> dict:
        hand_visible = viewer_index == player_index
        return {
            "active": [
                _pokemon(
                    self.active_card_id,
                    player_index,
                    serial=self.active_card_serial
                    if self.active_card_serial is not None
                    else 100000 + player_index,
                    damage=self.active_damage,
                    appear_this_turn=_appeared_this_turn(
                        current_turn=current_turn,
                        entered_turn=self.active_entered_turn,
                        evolved_turn=self.active_evolved_turn,
                    ),
                    pre_evolution_card_ids=self.active_pre_evolution_card_ids,
                    energy_card_ids=self.active_energy_card_ids,
                    energy_card_serials=self.active_energy_card_serials,
                    tool_card_ids=(self.active_tool_card_id,) if self.active_tool_card_id is not None else (),
                    energy_serial_base=200000 + player_index * 1000,
                    tool_serial_base=500000 + player_index * 1000,
                    stadium_card_id=stadium_card_id,
                    native_core=native_core,
                )
            ]
            if self.active_card_id is not None
            else [],
            "bench": [
                _pokemon(
                    card_id,
                    player_index,
                    serial=_zone_serial(
                        self.bench_card_serials,
                        index,
                        101000 + player_index * 100 + index,
                    ),
                    damage=self.bench_damage[index] if index < len(self.bench_damage) else 0,
                    appear_this_turn=_appeared_this_turn(
                        current_turn=current_turn,
                        entered_turn=self.bench_entered_turns[index]
                        if index < len(self.bench_entered_turns)
                        else 0,
                        evolved_turn=self.bench_evolved_turns[index]
                        if index < len(self.bench_evolved_turns)
                        else 0,
                    ),
                    pre_evolution_card_ids=self.bench_pre_evolution_card_ids[index]
                    if index < len(self.bench_pre_evolution_card_ids)
                    else (),
                    energy_card_ids=self.bench_energy_card_ids[index]
                    if index < len(self.bench_energy_card_ids)
                    else (),
                    energy_card_serials=self.bench_energy_card_serials[index]
                    if index < len(self.bench_energy_card_serials)
                    else (),
                    tool_card_ids=(
                        (self.bench_tool_card_ids[index],)
                        if index < len(self.bench_tool_card_ids)
                        and self.bench_tool_card_ids[index] is not None
                        else ()
                    ),
                    energy_serial_base=201000 + player_index * 1000 + index * 100,
                    tool_serial_base=501000 + player_index * 1000 + index * 100,
                    stadium_card_id=stadium_card_id,
                    native_core=native_core,
                )
                for index, card_id in enumerate(self.bench_card_ids)
            ],
            "benchMax": BENCH_SIZE,
            "deckCount": self.deck_count,
            "discard": [
                _card(card_id, player_index, serial=300000 + player_index * 1000 + index)
                for index, card_id in enumerate(self.discard_card_ids)
            ],
            "prize": [None for _ in self.prize_card_ids],
            "handCount": self.hand_count,
            "hand": [
                _card(
                    card_id,
                    player_index,
                    serial=_zone_serial(
                        self.hand_card_serials,
                        index,
                        player_index * 1000 + index + 1,
                    ),
                )
                for index, card_id in enumerate(self.hand_card_ids)
            ]
            if hand_visible
            else None,
            "poisoned": False,
            "burned": False,
            "asleep": False,
            "paralyzed": False,
            "confused": False,
        }


@dataclass(frozen=True)
class NativeBattleSetup:
    turn: int
    first_player: int
    current_player: int
    energy_attached: bool
    result: int
    players: tuple[NativeBattlePlayer, NativeBattlePlayer]
    setup_mulligans: tuple[int, int] = (0, 0)
    setup_mulligan_draw_choices: tuple[int | None, int | None] = (None, None)
    retreated: bool = False
    fighting_attack_bonus: int = 0
    lunar_cycle_used: bool = False
    stadium_played: bool = False
    stadium_card_id: int | None = None
    stadium_player_index: int | None = None
    pending_promotion_player: int | None = None
    pending_promotion_next_player: int | None = None
    pending_dusk_ball_player: int | None = None
    pending_dusk_ball_start: int = 0
    pending_dusk_ball_count: int = 0
    pending_boss_orders_player: int | None = None
    pending_heave_ho_player: int | None = None
    pending_fighting_gong_player: int | None = None
    pending_poke_pad_player: int | None = None
    pending_switch_player: int | None = None
    pending_retreat_player: int | None = None
    pending_retreat_remaining: int = 0
    pending_aura_jab_player: int | None = None
    pending_aura_jab_remaining: int = 0
    supporter_played: bool = False
    logs: tuple[dict[str, object], ...] = ()

    @property
    def setup_complete(self) -> bool:
        return self.players[0].setup_complete and self.players[1].setup_complete

    def pending_draw_count_player(self) -> int | None:
        if self.turn != 0:
            return None
        if self.first_player not in {0, 1}:
            return None
        if any(player.active_card_id is None or player.prize_count != PRIZE_SIZE for player in self.players):
            return None
        for player_index in (self.first_player, 1 - self.first_player):
            if self.setup_mulligan_draw_choices[player_index] is not None:
                continue
            opponent_index = 1 - player_index
            if self.setup_mulligans[opponent_index] - self.setup_mulligans[player_index] > 0:
                return player_index
        return None

    def to_observation(
        self,
        *,
        player_index: int,
        native_core: NativeCore | None = None,
        view_player_index: int | None = None,
        suppress_options_when_waiting: bool = False,
    ) -> dict:
        if player_index not in {0, 1}:
            raise ValueError("player_index must be 0 or 1")
        if view_player_index is not None and view_player_index not in {0, 1}:
            raise ValueError("view_player_index must be 0 or 1")
        acting_index = (
            self.pending_promotion_player
            if self.pending_promotion_player is not None
            else self.pending_dusk_ball_player
            if self.pending_dusk_ball_player is not None
            else self.pending_boss_orders_player
            if self.pending_boss_orders_player is not None
            else self.pending_heave_ho_player
            if self.pending_heave_ho_player is not None
            else self.pending_fighting_gong_player
            if self.pending_fighting_gong_player is not None
            else self.pending_poke_pad_player
            if self.pending_poke_pad_player is not None
            else self.pending_switch_player
            if self.pending_switch_player is not None
            else self.pending_retreat_player
            if self.pending_retreat_player is not None
            else self.pending_aura_jab_player
            if self.pending_aura_jab_player is not None
            else self.current_player
            if self.turn > 0 and self.setup_complete
            else player_index
        )
        viewer_index = view_player_index if view_player_index is not None else acting_index
        if (
            suppress_options_when_waiting
            and self.turn > 0
            and self.setup_complete
            and viewer_index != acting_index
        ):
            select = _empty_select_data()
        else:
            select = self._select_data(player_index=acting_index, native_core=native_core)
        return {
            "select": select,
            "logs": [dict(item) for item in self.logs],
            "current": {
                "turn": self.turn,
                "turnActionCount": 0,
                "yourIndex": viewer_index,
                "firstPlayer": self.first_player,
                "supporterPlayed": self.supporter_played,
                "lunarCycleUsed": self.lunar_cycle_used,
                "fightingAttackBonus": self.fighting_attack_bonus,
                "stadiumPlayed": self.stadium_played,
                "energyAttached": self.energy_attached,
                "retreated": self.retreated,
                "result": self.result,
                "stadium": [
                    _card(
                        self.stadium_card_id,
                        self.stadium_player_index if self.stadium_player_index is not None else -1,
                        serial=600000,
                    )
                ]
                if self.stadium_card_id is not None
                else [],
                "looking": (
                    {"effect": "dusk_ball", "playerIndex": self.pending_dusk_ball_player}
                    if self.pending_dusk_ball_player is not None
                    else {"effect": "boss_orders", "playerIndex": self.pending_boss_orders_player}
                    if self.pending_boss_orders_player is not None
                    else {"effect": "heave_ho_catcher", "playerIndex": self.pending_heave_ho_player}
                    if self.pending_heave_ho_player is not None
                    else {"effect": "fighting_gong", "playerIndex": self.pending_fighting_gong_player}
                    if self.pending_fighting_gong_player is not None
                    else {"effect": "poke_pad", "playerIndex": self.pending_poke_pad_player}
                    if self.pending_poke_pad_player is not None
                    else {"effect": "switch", "playerIndex": self.pending_switch_player}
                    if self.pending_switch_player is not None
                    else {"effect": "retreat", "playerIndex": self.pending_retreat_player}
                    if self.pending_retreat_player is not None
                    else {"effect": "aura_jab", "playerIndex": self.pending_aura_jab_player}
                    if self.pending_aura_jab_player is not None
                    else None
                ),
                "players": [
                    player.to_observation_player(
                        viewer_index=viewer_index,
                        player_index=index,
                        current_turn=self.turn,
                        stadium_card_id=self.stadium_card_id,
                        native_core=native_core,
                    )
                    for index, player in enumerate(self.players)
                ],
            },
            "search_begin_input": None,
        }

    def _select_data(self, *, player_index: int, native_core: NativeCore | None) -> dict:
        if self.pending_promotion_player is not None:
            return self._promotion_select_data(player_index=self.pending_promotion_player)
        if self.pending_dusk_ball_player is not None:
            return self._dusk_ball_select_data(
                player_index=self.pending_dusk_ball_player,
                native_core=native_core,
            )
        if self.pending_boss_orders_player is not None:
            return self._boss_orders_select_data(player_index=self.pending_boss_orders_player)
        if self.pending_heave_ho_player is not None:
            return self._heave_ho_catcher_select_data(player_index=self.pending_heave_ho_player)
        if self.pending_fighting_gong_player is not None:
            return self._fighting_gong_select_data(
                player_index=self.pending_fighting_gong_player,
                native_core=native_core,
            )
        if self.pending_poke_pad_player is not None:
            return self._poke_pad_select_data(
                player_index=self.pending_poke_pad_player,
                native_core=native_core,
            )
        if self.pending_switch_player is not None:
            return self._switch_select_data(player_index=self.pending_switch_player)
        if self.pending_retreat_player is not None:
            if self.pending_retreat_remaining > 0:
                return self._retreat_discard_select_data(player_index=self.pending_retreat_player)
            return self._retreat_promote_select_data(player_index=self.pending_retreat_player)
        if self.pending_aura_jab_player is not None:
            return self._aura_jab_select_data(player_index=self.pending_aura_jab_player)
        pending_draw_count_player = self.pending_draw_count_player()
        if pending_draw_count_player is not None:
            return self._draw_count_select_data(player_index=pending_draw_count_player)
        if self.turn > 0 and self.setup_complete:
            player = self.players[self.current_player]
            opponent = self.players[1 - self.current_player]
            options = []
            if native_core is not None and len(player.bench_card_ids) < BENCH_SIZE:
                options.extend(
                    {"type": 7, "index": index, "cardId": card_id}
                    for index, card_id in enumerate(player.hand_card_ids)
                    if native_core.is_basic_pokemon_card(card_id)
                )
            options.extend(
                {"type": 7, "index": index, "cardId": card_id, "effect": "premium_power_pro"}
                for index, card_id in enumerate(player.hand_card_ids)
                if card_id == CARD_PREMIUM_POWER_PRO
            )
            options.extend(
                {"type": 7, "index": index, "cardId": card_id, "effect": "dusk_ball"}
                for index, card_id in enumerate(player.hand_card_ids)
                if card_id == CARD_DUSK_BALL
            )
            options.extend(
                {"type": 7, "index": index, "cardId": card_id, "effect": "poke_pad"}
                for index, card_id in enumerate(player.hand_card_ids)
                if card_id == CARD_POKE_PAD
            )
            if len(player.bench_card_ids) > 0:
                options.extend(
                    {"type": 7, "index": index, "cardId": card_id, "effect": "switch"}
                    for index, card_id in enumerate(player.hand_card_ids)
                    if card_id == CARD_SWITCH
                )
            options.extend(
                {"type": 7, "index": index, "cardId": card_id, "effect": "fighting_gong"}
                for index, card_id in enumerate(player.hand_card_ids)
                if card_id == CARD_FIGHTING_GONG
            )
            if (
                not self.lunar_cycle_used
                and _player_has_card_in_play(player, CARD_LUNATONE)
                and _player_has_card_in_play(player, CARD_SOLROCK)
            ):
                options.extend(
                    {"type": 7, "index": index, "cardId": card_id, "effect": "lunar_cycle"}
                    for index, card_id in enumerate(player.hand_card_ids)
                    if card_id == ENERGY_FIGHTING
                )
            if not self.stadium_played and self.stadium_card_id != CARD_GRAVITY_MOUNTAIN:
                options.extend(
                    {"type": 7, "index": index, "cardId": card_id, "effect": "gravity_mountain"}
                    for index, card_id in enumerate(player.hand_card_ids)
                    if card_id == CARD_GRAVITY_MOUNTAIN
                )
            for index, card_id in enumerate(player.hand_card_ids):
                if card_id != CARD_HEROS_CAPE:
                    continue
                if player.active_card_id is not None and player.active_tool_card_id is None:
                    options.append(
                        {
                            "type": 8,
                            "area": AREA_HAND,
                            "index": index,
                            "cardId": card_id,
                            "effect": "heros_cape",
                            "inPlayArea": AREA_ACTIVE,
                            "inPlayIndex": 0,
                        }
                    )
                options.extend(
                    {
                        "type": 8,
                        "area": AREA_HAND,
                        "index": index,
                        "cardId": card_id,
                        "effect": "heros_cape",
                        "inPlayArea": AREA_BENCH,
                        "inPlayIndex": bench_index,
                    }
                    for bench_index, _bench_card_id in enumerate(player.bench_card_ids)
                    if (
                        bench_index >= len(player.bench_tool_card_ids)
                        or player.bench_tool_card_ids[bench_index] is None
                    )
                )
            if not self.supporter_played:
                non_carmine_supporters_allowed = not (
                    self.turn == 1 and self.current_player == self.first_player
                )
                if non_carmine_supporters_allowed and len(opponent.bench_card_ids) > 0:
                    options.extend(
                        {"type": 7, "index": index, "cardId": card_id, "effect": "boss_orders"}
                        for index, card_id in enumerate(player.hand_card_ids)
                        if card_id == CARD_BOSS_ORDERS
                    )
                options.extend(
                    {"type": 7, "index": index, "cardId": card_id, "effect": "carmine"}
                    for index, card_id in enumerate(player.hand_card_ids)
                    if card_id == CARD_CARMINE
                )
                if non_carmine_supporters_allowed:
                    options.extend(
                        {"type": 7, "index": index, "cardId": card_id, "effect": "lillies_determination"}
                        for index, card_id in enumerate(player.hand_card_ids)
                        if card_id == CARD_LILLIES_DETERMINATION
                    )
            if native_core is not None:
                for index, card_id in enumerate(player.hand_card_ids):
                    if (
                        player.active_card_id is not None
                        and native_core.can_evolve_card(card_id, player.active_card_id)
                        and self._can_evolve_target_this_turn(player, in_play_area=AREA_ACTIVE, in_play_index=0)
                    ):
                        options.append(
                            {
                                "type": 9,
                                "area": AREA_HAND,
                                "index": index,
                                "cardId": card_id,
                                "inPlayArea": AREA_ACTIVE,
                                "inPlayIndex": 0,
                            }
                        )
                    options.extend(
                        {
                            "type": 9,
                            "area": AREA_HAND,
                            "index": index,
                            "cardId": card_id,
                            "inPlayArea": AREA_BENCH,
                            "inPlayIndex": bench_index,
                        }
                        for bench_index, bench_card_id in enumerate(player.bench_card_ids)
                        if native_core.can_evolve_card(card_id, bench_card_id)
                        and self._can_evolve_target_this_turn(
                            player,
                            in_play_area=AREA_BENCH,
                            in_play_index=bench_index,
                        )
                    )
            if native_core is not None and not self.energy_attached:
                for index, card_id in enumerate(player.hand_card_ids):
                    if not native_core.is_energy_card(card_id):
                        continue
                    if player.active_card_id is not None:
                        options.append(
                            {
                                "type": 8,
                                "area": AREA_HAND,
                                "index": index,
                                "cardId": card_id,
                                "inPlayArea": AREA_ACTIVE,
                                "inPlayIndex": 0,
                            }
                        )
                    options.extend(
                        {
                            "type": 8,
                            "area": AREA_HAND,
                            "index": index,
                            "cardId": card_id,
                            "inPlayArea": AREA_BENCH,
                            "inPlayIndex": bench_index,
                        }
                        for bench_index, _bench_card_id in enumerate(player.bench_card_ids)
                    )
            if (
                native_core is not None
                and not self.retreated
                and player.active_card_id is not None
                and len(player.bench_card_ids) > 0
            ):
                active_metadata = native_core.card_metadata(player.active_card_id)
                if len(player.active_energy_card_ids) >= active_metadata.retreat_cost:
                    options.append({"type": 12})
            if native_core is not None and player.active_card_id is not None:
                for attack_id in native_core.card_metadata(player.active_card_id).attack_ids:
                    if native_core.can_use_attack(
                        player.active_card_id,
                        attack_id,
                        player.active_energy_card_ids,
                    ) and not _active_attack_is_disabled(player, attack_id, self.turn):
                        options.append({"type": 13, "attackId": attack_id})
            options.append({"type": 14})
            options = _order_main_options_by_official_hand_order(options)
            return {
                "type": 0,
                "context": 0,
                "minCount": 1,
                "maxCount": 1,
                "remainDamageCounter": 0,
                "remainEnergyCost": 0,
                "option": options,
                "deck": None,
                "contextCard": None,
                "effect": None,
            }

        player = self.players[player_index]
        setup_options = []
        if not player.setup_complete:
            setup_options = [
                (index, card_id)
                for index, card_id in enumerate(player.hand_card_ids)
                if native_core is None or native_core.is_basic_pokemon_card(card_id)
            ]
        active_selected = player.active_card_id is not None
        max_bench_choices = max(0, min(BENCH_SIZE - len(player.bench_card_ids), len(setup_options)))
        return {
            "type": 1,
            "context": 2 if active_selected else 1,
            "minCount": 0 if active_selected else 1,
            "maxCount": max_bench_choices if active_selected else 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": 3,
                    "area": 2,
                    "index": index,
                    "playerIndex": player_index,
                    "cardId": card_id,
                }
                for index, card_id in setup_options
            ],
            "deck": None,
            "contextCard": None,
            "effect": None,
        }

    def _draw_count_select_data(self, *, player_index: int) -> dict:
        max_count = max(0, self.setup_mulligans[1 - player_index] - self.setup_mulligans[player_index])
        return {
            "type": "Count",
            "context": "DrawCount",
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": "Number",
                    "number": number,
                }
                for number in range(max_count + 1)
            ],
            "deck": None,
            "contextCard": None,
            "effect": None,
        }

    def _can_evolve_target_this_turn(
        self,
        player: NativeBattlePlayer,
        *,
        in_play_area: int,
        in_play_index: int,
    ) -> bool:
        if self.turn <= 2:
            return False
        if in_play_area == AREA_ACTIVE:
            return not _appeared_this_turn(
                current_turn=self.turn,
                entered_turn=player.active_entered_turn,
                evolved_turn=player.active_evolved_turn,
            )
        if in_play_area == AREA_BENCH and 0 <= in_play_index < len(player.bench_card_ids):
            entered_turn = (
                player.bench_entered_turns[in_play_index]
                if in_play_index < len(player.bench_entered_turns)
                else 0
            )
            evolved_turn = (
                player.bench_evolved_turns[in_play_index]
                if in_play_index < len(player.bench_evolved_turns)
                else 0
            )
            return not _appeared_this_turn(
                current_turn=self.turn,
                entered_turn=entered_turn,
                evolved_turn=evolved_turn,
            )
        return False

    def _dusk_ball_select_data(
        self,
        *,
        player_index: int,
        native_core: NativeCore | None,
    ) -> dict:
        player = self.players[player_index]
        start = max(0, min(self.pending_dusk_ball_start, len(player.deck_card_ids)))
        end = max(start, min(start + self.pending_dusk_ball_count, len(player.deck_card_ids)))
        options = []
        if native_core is not None:
            for deck_index in range(start, end):
                card_id = player.deck_card_ids[deck_index]
                if native_core.card_metadata(card_id).is_pokemon:
                    options.append(
                        {
                            "type": 3,
                            "area": AREA_DECK,
                            "index": deck_index,
                            "playerIndex": player_index,
                            "cardId": card_id,
                            "effect": "dusk_ball_pick",
                        }
                    )
        options.append({"type": 16, "effect": "dusk_ball_skip"})
        return {
            "type": 1,
            "context": 7,
            "minCount": 0,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options,
            "deck": None,
            "contextCard": {"id": CARD_DUSK_BALL, "playerIndex": player_index},
            "effect": "dusk_ball",
        }

    def _boss_orders_select_data(self, *, player_index: int) -> dict:
        target_player = 1 - player_index
        opponent = self.players[target_player]
        return {
            "type": 1,
            "context": 8,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": 3,
                    "area": AREA_BENCH,
                    "index": index,
                    "playerIndex": target_player,
                    "cardId": card_id,
                    "effect": "boss_orders_target",
                }
                for index, card_id in enumerate(opponent.bench_card_ids)
            ],
            "deck": None,
            "contextCard": {"id": CARD_BOSS_ORDERS, "playerIndex": player_index},
            "effect": "boss_orders",
        }

    def _heave_ho_catcher_select_data(self, *, player_index: int) -> dict:
        target_player = 1 - player_index
        opponent = self.players[target_player]
        options = [
            {
                "type": 3,
                "area": AREA_BENCH,
                "index": index,
                "playerIndex": target_player,
                "cardId": card_id,
                "effect": "heave_ho_catcher_target",
            }
            for index, card_id in enumerate(opponent.bench_card_ids)
        ]
        options.append({"type": 16, "effect": "heave_ho_catcher_skip"})
        return {
            "type": 1,
            "context": 8,
            "minCount": 0,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options,
            "deck": None,
            "contextCard": {"id": CARD_HARIYAMA, "playerIndex": player_index},
            "effect": "heave_ho_catcher",
        }

    def _fighting_gong_select_data(
        self,
        *,
        player_index: int,
        native_core: NativeCore | None,
    ) -> dict:
        player = self.players[player_index]
        options = []
        if native_core is not None:
            for deck_index, card_id in enumerate(player.deck_card_ids):
                if _is_fighting_gong_target(native_core, card_id):
                    options.append(
                        {
                            "type": 3,
                            "area": AREA_DECK,
                            "index": deck_index,
                            "playerIndex": player_index,
                            "cardId": card_id,
                            "effect": "fighting_gong_pick",
                        }
                    )
        options.append({"type": 16, "effect": "fighting_gong_skip"})
        return {
            "type": 1,
            "context": 9,
            "minCount": 0,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options,
            "deck": None,
            "contextCard": {"id": CARD_FIGHTING_GONG, "playerIndex": player_index},
            "effect": "fighting_gong",
        }

    def _poke_pad_select_data(
        self,
        *,
        player_index: int,
        native_core: NativeCore | None,
    ) -> dict:
        player = self.players[player_index]
        options = []
        if native_core is not None:
            for deck_index, card_id in enumerate(player.deck_card_ids):
                if _is_poke_pad_target(native_core, card_id):
                    options.append(
                        {
                            "type": 3,
                            "area": AREA_DECK,
                            "index": deck_index,
                            "playerIndex": player_index,
                            "cardId": card_id,
                            "effect": "poke_pad_pick",
                        }
                    )
        options.append({"type": 16, "effect": "poke_pad_skip"})
        return {
            "type": 1,
            "context": 10,
            "minCount": 0,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options,
            "deck": None,
            "contextCard": {"id": CARD_POKE_PAD, "playerIndex": player_index},
            "effect": "poke_pad",
        }

    def _switch_select_data(self, *, player_index: int) -> dict:
        player = self.players[player_index]
        return {
            "type": 1,
            "context": 11,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": 3,
                    "area": AREA_BENCH,
                    "index": index,
                    "playerIndex": player_index,
                    "cardId": card_id,
                    "effect": "switch_target",
                }
                for index, card_id in enumerate(player.bench_card_ids)
            ],
            "deck": None,
            "contextCard": {"id": CARD_SWITCH, "playerIndex": player_index},
            "effect": "switch",
        }

    def _retreat_discard_select_data(self, *, player_index: int) -> dict:
        player = self.players[player_index]
        return {
            "type": 4,
            "context": 30,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": self.pending_retreat_remaining,
            "option": [
                {
                    "type": 6,
                    "area": AREA_ACTIVE,
                    "index": index,
                    "energyIndex": index,
                    "playerIndex": player_index,
                    "cardId": card_id,
                    "effect": "retreat_discard",
                }
                for index, card_id in enumerate(player.active_energy_card_ids)
            ],
            "deck": None,
            "contextCard": None,
            "effect": "retreat",
        }

    def _retreat_promote_select_data(self, *, player_index: int) -> dict:
        player = self.players[player_index]
        return {
            "type": 1,
            "context": 3,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": 3,
                    "area": AREA_BENCH,
                    "index": index,
                    "playerIndex": player_index,
                    "cardId": card_id,
                    "effect": "retreat_promote",
                }
                for index, card_id in enumerate(player.bench_card_ids)
            ],
            "deck": None,
            "contextCard": None,
            "effect": "retreat",
        }

    def _aura_jab_select_data(self, *, player_index: int) -> dict:
        player = self.players[player_index]
        options = []
        for discard_index, card_id in enumerate(player.discard_card_ids):
            if card_id != ENERGY_FIGHTING:
                continue
            for bench_index, _bench_card_id in enumerate(player.bench_card_ids):
                options.append(
                    {
                        "type": 8,
                        "area": AREA_DISCARD,
                        "index": discard_index,
                        "playerIndex": player_index,
                        "cardId": card_id,
                        "effect": "aura_jab_attach",
                        "inPlayArea": AREA_BENCH,
                        "inPlayIndex": bench_index,
                    }
                )
        options.append({"type": 16, "effect": "aura_jab_skip"})
        return {
            "type": 1,
            "context": 12,
            "minCount": 0,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options,
            "deck": None,
            "contextCard": {"id": CARD_MEGA_LUCARIO_EX, "playerIndex": player_index},
            "effect": "aura_jab",
        }

    def _promotion_select_data(self, *, player_index: int) -> dict:
        player = self.players[player_index]
        return {
            "type": 1,
            "context": 3,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": 15,
                    "area": AREA_BENCH,
                    "index": index,
                    "playerIndex": player_index,
                    "cardId": card_id,
                }
                for index, card_id in enumerate(player.bench_card_ids)
            ],
            "deck": None,
            "contextCard": None,
            "effect": None,
        }


def _order_main_options_by_official_hand_order(options: list[dict]) -> list[dict]:
    hand_backed_types = {7, 8, 9}
    hand_backed_options = [
        option for option in options if option.get("type") in hand_backed_types and "index" in option
    ]
    other_options = [
        option for option in options if option.get("type") not in hand_backed_types or "index" not in option
    ]

    def hand_order(option: dict) -> tuple[int, int]:
        try:
            hand_index = int(option.get("index"))
        except (TypeError, ValueError):
            hand_index = PTCG_DECK_SIZE
        return hand_index, options.index(option)

    return sorted(hand_backed_options, key=hand_order) + other_options


def _empty_select_data() -> dict:
    return {
        "type": 0,
        "context": 0,
        "minCount": 0,
        "maxCount": 0,
        "remainDamageCounter": 0,
        "remainEnergyCost": 0,
        "option": [],
        "deck": None,
        "contextCard": None,
        "effect": None,
    }


def _is_fighting_gong_target(native_core: NativeCore, card_id: int) -> bool:
    metadata = native_core.card_metadata(card_id)
    if metadata.card_type == 5 and metadata.energy_type == ENERGY_FIGHTING:
        return True
    return metadata.is_basic_pokemon and metadata.energy_type == ENERGY_FIGHTING


def _is_poke_pad_target(native_core: NativeCore, card_id: int) -> bool:
    metadata = native_core.card_metadata(card_id)
    return metadata.is_pokemon and not metadata.ex and not metadata.mega_ex


def _active_attack_is_disabled(player: NativeBattlePlayer, attack_id: int, turn: int) -> bool:
    return player.active_disabled_attack_id == attack_id and player.active_disabled_attack_turn == turn


def _player_has_card_in_play(player: NativeBattlePlayer, card_id: int) -> bool:
    return player.active_card_id == card_id or card_id in player.bench_card_ids


def _effective_attack_damage(
    native_core: NativeCore,
    setup: NativeBattleSetup,
    *,
    attack_id: int,
) -> int:
    attack = native_core.attack_metadata(attack_id)
    player = setup.players[setup.current_player]
    defender = setup.players[1 - setup.current_player]
    damage = attack.damage
    if attack_id == ATTACK_COSMIC_BEAM and CARD_LUNATONE not in player.bench_card_ids:
        return 0
    attacking_card_id = player.active_card_id
    defending_card_id = defender.active_card_id
    try:
        attacking_card = (
            native_core.card_metadata(attacking_card_id) if attacking_card_id is not None else None
        )
        defending_card = (
            native_core.card_metadata(defending_card_id) if defending_card_id is not None else None
        )
    except NativeCoreError:
        attacking_card = None
        defending_card = None
    if damage > 0 and attacking_card is not None and attacking_card.energy_type == ENERGY_FIGHTING:
        damage += setup.fighting_attack_bonus
    if (
        damage > 0
        and attacking_card is not None
        and defending_card is not None
        and attack_id != ATTACK_COSMIC_BEAM
    ):
        if defending_card.weakness_type == attacking_card.energy_type:
            damage *= 2
        if defending_card.resistance_type == attacking_card.energy_type:
            damage = max(0, damage - RESISTANCE_DAMAGE_REDUCTION)
    return damage


def _attack_self_damage(attack_id: int) -> int:
    if attack_id == ATTACK_WILD_PRESS:
        return 70
    return 0


@dataclass(frozen=True)
class NativeBattleSetupResult:
    ok: bool
    error_code: int
    message: str
    setup: NativeBattleSetup | None = None


class NativeCore:
    def __init__(self, library_path: Path | str) -> None:
        self.library_path = Path(library_path).resolve()
        if not self.library_path.exists():
            raise NativeCoreError(f"native library does not exist: {self.library_path}")
        self._lib = ctypes.CDLL(str(self.library_path))
        self._lib.ptcg_native_version.restype = ctypes.c_char_p
        self._lib.ptcg_load_deck_csv.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(_NativeDeckC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_load_deck_csv.restype = ctypes.c_int
        self._lib.ptcg_deck_count_card.argtypes = [
            ctypes.POINTER(_NativeDeckC),
            ctypes.c_int,
        ]
        self._lib.ptcg_deck_count_card.restype = ctypes.c_int
        self._lib.ptcg_deck_unique_count.argtypes = [ctypes.POINTER(_NativeDeckC)]
        self._lib.ptcg_deck_unique_count.restype = ctypes.c_int
        self._lib.ptcg_deck_basic_pokemon_count.argtypes = [ctypes.POINTER(_NativeDeckC)]
        self._lib.ptcg_deck_basic_pokemon_count.restype = ctypes.c_int
        self._lib.ptcg_deck_energy_count.argtypes = [ctypes.POINTER(_NativeDeckC)]
        self._lib.ptcg_deck_energy_count.restype = ctypes.c_int
        self._lib.ptcg_deck_named_counts.argtypes = [
            ctypes.POINTER(_NativeDeckC),
            ctypes.POINTER(_NativeDeckNamedCountC),
            ctypes.c_int,
        ]
        self._lib.ptcg_deck_named_counts.restype = ctypes.c_int
        self._lib.ptcg_get_card_metadata.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(_NativeCardMetadataC),
        ]
        self._lib.ptcg_get_card_metadata.restype = ctypes.c_int
        self._lib.ptcg_get_attack_metadata.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(_NativeAttackMetadataC),
        ]
        self._lib.ptcg_get_attack_metadata.restype = ctypes.c_int
        self._lib.ptcg_is_basic_pokemon_card.argtypes = [ctypes.c_int]
        self._lib.ptcg_is_basic_pokemon_card.restype = ctypes.c_int
        self._lib.ptcg_is_energy_card.argtypes = [ctypes.c_int]
        self._lib.ptcg_is_energy_card.restype = ctypes.c_int
        self._lib.ptcg_can_use_attack.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int,
        ]
        self._lib.ptcg_can_use_attack.restype = ctypes.c_int
        self._lib.ptcg_start_battle_setup_from_csv.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_start_battle_setup_from_csv.restype = ctypes.c_int
        self._lib.ptcg_start_battle_pregame_from_csv.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_start_battle_pregame_from_csv.restype = ctypes.c_int
        self._lib.ptcg_select_pregame_first_player.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_select_pregame_first_player.restype = ctypes.c_int
        self._lib.ptcg_select_setup_active.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_select_setup_active.restype = ctypes.c_int
        self._lib.ptcg_deal_setup_prizes.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_deal_setup_prizes.restype = ctypes.c_int
        self._lib.ptcg_select_setup_bench.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_select_setup_bench.restype = ctypes.c_int
        self._lib.ptcg_finish_setup_player.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_finish_setup_player.restype = ctypes.c_int
        self._lib.ptcg_is_setup_complete.argtypes = [ctypes.POINTER(_NativeBattleSetupC)]
        self._lib.ptcg_is_setup_complete.restype = ctypes.c_int
        self._lib.ptcg_begin_first_turn.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_begin_first_turn.restype = ctypes.c_int
        self._lib.ptcg_end_turn.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_end_turn.restype = ctypes.c_int
        self._lib.ptcg_play_basic_to_bench.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_basic_to_bench.restype = ctypes.c_int
        self._lib.ptcg_play_dusk_ball.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_dusk_ball.restype = ctypes.c_int
        self._lib.ptcg_resolve_dusk_ball.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_dusk_ball.restype = ctypes.c_int
        self._lib.ptcg_play_fighting_gong.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_fighting_gong.restype = ctypes.c_int
        self._lib.ptcg_play_premium_power_pro.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_premium_power_pro.restype = ctypes.c_int
        self._lib.ptcg_use_lunar_cycle.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_use_lunar_cycle.restype = ctypes.c_int
        self._lib.ptcg_play_gravity_mountain.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_gravity_mountain.restype = ctypes.c_int
        self._lib.ptcg_resolve_fighting_gong.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_fighting_gong.restype = ctypes.c_int
        self._lib.ptcg_play_poke_pad.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_poke_pad.restype = ctypes.c_int
        self._lib.ptcg_resolve_poke_pad.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_poke_pad.restype = ctypes.c_int
        self._lib.ptcg_play_switch.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_switch.restype = ctypes.c_int
        self._lib.ptcg_resolve_switch.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_switch.restype = ctypes.c_int
        self._lib.ptcg_start_retreat.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_start_retreat.restype = ctypes.c_int
        self._lib.ptcg_resolve_retreat_discard.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_retreat_discard.restype = ctypes.c_int
        self._lib.ptcg_resolve_retreat_promote.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_retreat_promote.restype = ctypes.c_int
        self._lib.ptcg_play_lillies_determination.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_lillies_determination.restype = ctypes.c_int
        self._lib.ptcg_play_boss_orders.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_boss_orders.restype = ctypes.c_int
        self._lib.ptcg_play_carmine.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_play_carmine.restype = ctypes.c_int
        self._lib.ptcg_resolve_boss_orders.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_boss_orders.restype = ctypes.c_int
        self._lib.ptcg_resolve_heave_ho_catcher.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_heave_ho_catcher.restype = ctypes.c_int
        self._lib.ptcg_skip_heave_ho_catcher.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_skip_heave_ho_catcher.restype = ctypes.c_int
        self._lib.ptcg_evolve_from_hand.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_evolve_from_hand.restype = ctypes.c_int
        self._lib.ptcg_attach_energy.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_attach_energy.restype = ctypes.c_int
        self._lib.ptcg_attach_heros_cape.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_attach_heros_cape.restype = ctypes.c_int
        self._lib.ptcg_use_attack.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_use_attack.restype = ctypes.c_int
        self._lib.ptcg_resolve_aura_jab_attach.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_resolve_aura_jab_attach.restype = ctypes.c_int
        self._lib.ptcg_skip_aura_jab.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_skip_aura_jab.restype = ctypes.c_int
        self._lib.ptcg_promote_bench_to_active.argtypes = [
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(_NativeBattleSetupC),
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self._lib.ptcg_promote_bench_to_active.restype = ctypes.c_int

    @property
    def version(self) -> str:
        raw = self._lib.ptcg_native_version()
        return raw.decode("ascii")

    def try_load_deck_csv(self, path: Path | str) -> NativeDeckLoadResult:
        deck_c = _NativeDeckC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_load_deck_csv(
            str(Path(path).resolve()).encode("utf-8"),
            ctypes.byref(deck_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeDeckLoadResult(ok=False, error_code=error_code, message=text)
        cards = tuple(int(deck_c.cards[index]) for index in range(int(deck_c.card_count)))
        return NativeDeckLoadResult(
            ok=True,
            error_code=0,
            message=text,
            deck=NativeDeck(cards=cards),
        )

    def load_deck_csv(self, path: Path | str) -> NativeDeck:
        result = self.try_load_deck_csv(path)
        if not result.ok or result.deck is None:
            raise NativeCoreError(result.message)
        return result.deck

    def deck_summary(self, deck: NativeDeck) -> NativeDeckSummary:
        deck_c = self._deck_to_c(deck)
        named_count_array = (_NativeDeckNamedCountC * DECK_SIZE)()
        unique_count = int(
            self._lib.ptcg_deck_named_counts(
                ctypes.byref(deck_c),
                named_count_array,
                ctypes.c_int(DECK_SIZE),
            )
        )
        count_limit = min(max(unique_count, 0), DECK_SIZE)
        named_counts = tuple(
            {
                "card_id": int(named_count_array[index].card_id),
                "count": int(named_count_array[index].count),
                "name": bytes(named_count_array[index].name)
                .split(b"\0", 1)[0]
                .decode("ascii", errors="replace"),
            }
            for index in range(count_limit)
        )
        return NativeDeckSummary(
            card_count=deck.card_count,
            unique_count=int(self._lib.ptcg_deck_unique_count(ctypes.byref(deck_c))),
            basic_pokemon_count=int(self._lib.ptcg_deck_basic_pokemon_count(ctypes.byref(deck_c))),
            energy_count=int(self._lib.ptcg_deck_energy_count(ctypes.byref(deck_c))),
            named_counts=named_counts,
        )

    def deck_count_card(self, deck: NativeDeck, card_id: int) -> int:
        deck_c = self._deck_to_c(deck)
        return int(self._lib.ptcg_deck_count_card(ctypes.byref(deck_c), ctypes.c_int(card_id)))

    def _deck_to_c(self, deck: NativeDeck) -> _NativeDeckC:
        if deck.card_count > DECK_SIZE:
            raise NativeCoreError(f"native deck has too many cards: {deck.card_count}")
        deck_c = _NativeDeckC()
        deck_c.card_count = deck.card_count
        for index, card_id in enumerate(deck.cards):
            deck_c.cards[index] = int(card_id)
        return deck_c

    def card_metadata(self, card_id: int) -> NativeCardMetadata:
        metadata_c = _NativeCardMetadataC()
        error_code = self._lib.ptcg_get_card_metadata(ctypes.c_int(card_id), ctypes.byref(metadata_c))
        if error_code != 0:
            raise NativeCoreError(f"unknown card id: {card_id}")
        return NativeCardMetadata(
            card_id=int(metadata_c.card_id),
            card_type=int(metadata_c.card_type),
            hp=int(metadata_c.hp),
            basic=bool(metadata_c.basic),
            stage1=bool(metadata_c.stage1),
            stage2=bool(metadata_c.stage2),
            energy_type=int(metadata_c.energy_type),
            retreat_cost=int(metadata_c.retreat_cost),
            weakness_type=(
                int(metadata_c.weakness_type) if int(metadata_c.weakness_type) >= 0 else None
            ),
            resistance_type=(
                int(metadata_c.resistance_type) if int(metadata_c.resistance_type) >= 0 else None
            ),
            ex=bool(metadata_c.ex),
            mega_ex=bool(metadata_c.mega_ex),
            evolves_from=(
                bytes(metadata_c.evolves_from).split(b"\0", 1)[0].decode("ascii", errors="replace")
                or None
            ),
            attack_ids=tuple(
                int(metadata_c.attacks[index])
                for index in range(min(int(metadata_c.attack_count), CARD_ATTACK_SIZE))
                if int(metadata_c.attacks[index]) > 0
            ),
            name=bytes(metadata_c.name).split(b"\0", 1)[0].decode("ascii", errors="replace"),
        )

    def attack_metadata(self, attack_id: int) -> NativeAttackMetadata:
        metadata_c = _NativeAttackMetadataC()
        error_code = self._lib.ptcg_get_attack_metadata(ctypes.c_int(attack_id), ctypes.byref(metadata_c))
        if error_code != 0:
            raise NativeCoreError(f"unknown attack id: {attack_id}")
        return NativeAttackMetadata(
            attack_id=int(metadata_c.attack_id),
            damage=int(metadata_c.damage),
            energy_types=tuple(
                int(metadata_c.energies[index])
                for index in range(min(int(metadata_c.energy_count), ATTACK_COST_SIZE))
            ),
            name=bytes(metadata_c.name).split(b"\0", 1)[0].decode("ascii", errors="replace"),
        )

    def is_basic_pokemon_card(self, card_id: int) -> bool:
        return bool(self._lib.ptcg_is_basic_pokemon_card(ctypes.c_int(card_id)))

    def is_energy_card(self, card_id: int) -> bool:
        return bool(self._lib.ptcg_is_energy_card(ctypes.c_int(card_id)))

    def can_evolve_card(self, evolution_card_id: int, source_card_id: int | None) -> bool:
        if source_card_id is None:
            return False
        try:
            evolution = self.card_metadata(evolution_card_id)
            source = self.card_metadata(source_card_id)
        except NativeCoreError:
            return False
        return (
            evolution.card_type == 0
            and (evolution.stage1 or evolution.stage2)
            and evolution.evolves_from == source.name
        )

    def can_use_attack(self, card_id: int, attack_id: int, energy_card_ids: tuple[int, ...]) -> bool:
        if not energy_card_ids:
            energy_array = (ctypes.c_int * 1)(0)
            energy_count = 0
        else:
            energy_array = (ctypes.c_int * len(energy_card_ids))(*energy_card_ids)
            energy_count = len(energy_card_ids)
        return bool(
            self._lib.ptcg_can_use_attack(
                ctypes.c_int(card_id),
                ctypes.c_int(attack_id),
                energy_array,
                ctypes.c_int(energy_count),
            )
        )

    def try_start_battle_pregame(
        self,
        deck0_path: Path | str,
        deck1_path: Path | str,
    ) -> NativeBattleSetupResult:
        setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_start_battle_pregame_from_csv(
            str(Path(deck0_path).resolve()).encode("utf-8"),
            str(Path(deck1_path).resolve()).encode("utf-8"),
            ctypes.byref(setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=_setup_from_c(setup_c),
        )

    def start_battle_pregame(
        self,
        deck0_path: Path | str,
        deck1_path: Path | str,
    ) -> NativeBattleSetup:
        result = self.try_start_battle_pregame(deck0_path, deck1_path)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_select_pregame_first_player(
        self,
        pregame: NativeBattleSetup,
        *,
        first_player: int,
        seed: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(pregame)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_select_pregame_first_player(
            ctypes.byref(setup_c),
            ctypes.c_int(first_player),
            ctypes.c_uint(seed),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=pregame.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "pregame_first_player",
                "turn": pregame.turn,
                "firstPlayer": first_player,
                "message": f"P{first_player} selected to go first.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def select_pregame_first_player(
        self,
        pregame: NativeBattleSetup,
        *,
        first_player: int,
        seed: int,
    ) -> NativeBattleSetup:
        result = self.try_select_pregame_first_player(
            pregame,
            first_player=first_player,
            seed=seed,
        )
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_start_battle_setup(
        self,
        deck0_path: Path | str,
        deck1_path: Path | str,
        *,
        seed: int,
    ) -> NativeBattleSetupResult:
        setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_start_battle_setup_from_csv(
            str(Path(deck0_path).resolve()).encode("utf-8"),
            str(Path(deck1_path).resolve()).encode("utf-8"),
            ctypes.c_uint(seed),
            ctypes.byref(setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=_setup_from_c(setup_c),
        )

    def start_battle_setup(
        self,
        deck0_path: Path | str,
        deck1_path: Path | str,
        *,
        seed: int,
    ) -> NativeBattleSetup:
        result = self.try_start_battle_setup(deck0_path, deck1_path, seed=seed)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def start_battle_setup_from_ordered_zones(
        self,
        *,
        player0_hand_card_ids: tuple[int, ...] | list[int],
        player0_deck_card_ids: tuple[int, ...] | list[int],
        player1_hand_card_ids: tuple[int, ...] | list[int],
        player1_deck_card_ids: tuple[int, ...] | list[int],
        player0_hand_serials: tuple[int, ...] | list[int] | None = None,
        player0_deck_serials: tuple[int, ...] | list[int] | None = None,
        player1_hand_serials: tuple[int, ...] | list[int] | None = None,
        player1_deck_serials: tuple[int, ...] | list[int] | None = None,
        first_player: int,
    ) -> NativeBattleSetup:
        if first_player not in {0, 1}:
            raise NativeCoreError("first_player must be 0 or 1")

        player0_hand = self._validated_ordered_zone_cards(
            player0_hand_card_ids,
            label="player0 hand",
            max_count=HAND_SIZE,
        )
        player0_deck = self._validated_ordered_zone_cards(
            player0_deck_card_ids,
            label="player0 deck",
            max_count=DECK_SIZE,
        )
        player1_hand = self._validated_ordered_zone_cards(
            player1_hand_card_ids,
            label="player1 hand",
            max_count=HAND_SIZE,
        )
        player1_deck = self._validated_ordered_zone_cards(
            player1_deck_card_ids,
            label="player1 deck",
            max_count=DECK_SIZE,
        )
        player0_hand_serial_ids = _validated_ordered_zone_serials(
            player0_hand_serials,
            expected_count=len(player0_hand),
            label="player0 hand serials",
        )
        player0_deck_serial_ids = _validated_ordered_zone_serials(
            player0_deck_serials,
            expected_count=len(player0_deck),
            label="player0 deck serials",
        )
        player1_hand_serial_ids = _validated_ordered_zone_serials(
            player1_hand_serials,
            expected_count=len(player1_hand),
            label="player1 hand serials",
        )
        player1_deck_serial_ids = _validated_ordered_zone_serials(
            player1_deck_serials,
            expected_count=len(player1_deck),
            label="player1 deck serials",
        )

        if len(player0_hand) + len(player0_deck) != DECK_SIZE:
            raise NativeCoreError("player0 ordered zones must contain exactly 60 cards")
        if len(player1_hand) + len(player1_deck) != DECK_SIZE:
            raise NativeCoreError("player1 ordered zones must contain exactly 60 cards")

        return NativeBattleSetup(
            turn=0,
            first_player=first_player,
            current_player=first_player,
            energy_attached=False,
            result=-1,
            players=(
                NativeBattlePlayer(
                    deck_card_ids=player0_deck,
                    hand_card_ids=player0_hand,
                    prize_card_ids=(),
                    active_card_id=None,
                    bench_card_ids=(),
                    setup_complete=False,
                    deck_card_serials=player0_deck_serial_ids,
                    hand_card_serials=player0_hand_serial_ids,
                ),
                NativeBattlePlayer(
                    deck_card_ids=player1_deck,
                    hand_card_ids=player1_hand,
                    prize_card_ids=(),
                    active_card_id=None,
                    bench_card_ids=(),
                    setup_complete=False,
                    deck_card_serials=player1_deck_serial_ids,
                    hand_card_serials=player1_hand_serial_ids,
                ),
            ),
            setup_mulligans=(0, 0),
            setup_mulligan_draw_choices=(None, None),
        )

    def _validated_ordered_zone_cards(
        self,
        card_ids: tuple[int, ...] | list[int],
        *,
        label: str,
        max_count: int,
    ) -> tuple[int, ...]:
        cards = tuple(int(card_id) for card_id in card_ids)
        if len(cards) > max_count:
            raise NativeCoreError(f"{label} has too many cards")
        for card_id in cards:
            self.card_metadata(card_id)
        return cards

    def try_select_setup_active(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_select_setup_active(
            ctypes.byref(setup_c),
            ctypes.c_int(player_index),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_hand_serial_to_active(
            setup,
            next_setup,
            player_index=player_index,
            hand_index=hand_index,
        )
        card_id = setup.players[player_index].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "setup_active",
                "turn": setup.turn,
                "playerIndex": player_index,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{player_index} set {_card_name(self, card_id)} as Active Pokemon.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def select_setup_active(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
        hand_index: int,
    ) -> NativeBattleSetup:
        result = self.try_select_setup_active(setup, player_index=player_index, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_deal_setup_prizes(self, setup: NativeBattleSetup) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_deal_setup_prizes(
            ctypes.byref(setup_c),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_deck_serials_to_setup_prizes(setup, next_setup)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "setup_prizes",
                "turn": setup.turn,
                "message": "Setup prize cards were placed.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def deal_setup_prizes(self, setup: NativeBattleSetup) -> NativeBattleSetup:
        result = self.try_deal_setup_prizes(setup)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def apply_pregame_draw_count(
        self,
        setup: NativeBattleSetup,
        *,
        count: int,
        player_index: int | None = None,
    ) -> NativeBattleSetup:
        pending_player = setup.pending_draw_count_player()
        if pending_player is None:
            raise NativeCoreError("no mulligan DrawCount prompt is pending")
        if player_index is not None and player_index != pending_player:
            raise NativeCoreError("mulligan DrawCount prompt belongs to another player")
        max_count = max(
            0,
            setup.setup_mulligans[1 - pending_player] - setup.setup_mulligans[pending_player],
        )
        if count < 0 or count > max_count:
            raise NativeCoreError(f"mulligan DrawCount choice must be between 0 and {max_count}")
        player = setup.players[pending_player]
        if count > len(player.deck_card_ids):
            raise NativeCoreError("cannot draw more mulligan cards than remain in deck")
        if player.hand_count + count > HAND_SIZE:
            raise NativeCoreError("hand capacity exceeded")

        drawn_cards = player.deck_card_ids[:count]
        drawn_serials = player.deck_card_serials[:count]
        next_player = replace(
            player,
            deck_card_ids=player.deck_card_ids[count:],
            hand_card_ids=player.hand_card_ids + drawn_cards,
            deck_card_serials=player.deck_card_serials[count:],
            hand_card_serials=player.hand_card_serials + drawn_serials,
        )
        players = list(setup.players)
        players[pending_player] = next_player
        draw_choices = list(setup.setup_mulligan_draw_choices)
        draw_choices[pending_player] = count
        next_setup = replace(
            setup,
            players=(players[0], players[1]),
            setup_mulligan_draw_choices=(draw_choices[0], draw_choices[1]),
        )
        return _append_log(
            next_setup,
            {
                "kind": "setup_mulligan_draw_count",
                "turn": setup.turn,
                "playerIndex": pending_player,
                "drawnCount": count,
                "maxCount": max_count,
                "message": f"P{pending_player} chose to draw {count} mulligan card(s).",
            },
        )

    def try_select_setup_bench(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_select_setup_bench(
            ctypes.byref(setup_c),
            ctypes.c_int(player_index),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_hand_serial_to_bench(
            setup,
            next_setup,
            player_index=player_index,
            hand_index=hand_index,
        )
        card_id = setup.players[player_index].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "setup_bench",
                "turn": setup.turn,
                "playerIndex": player_index,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{player_index} put {_card_name(self, card_id)} on the Bench.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def select_setup_bench(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
        hand_index: int,
    ) -> NativeBattleSetup:
        result = self.try_select_setup_bench(setup, player_index=player_index, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_finish_setup_player(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_finish_setup_player(
            ctypes.byref(setup_c),
            ctypes.c_int(player_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_top_deck_serial_to_hand(
            setup,
            next_setup,
            player_index=next_setup.current_player,
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "setup_finish",
                "turn": setup.turn,
                "playerIndex": player_index,
                "message": f"P{player_index} finished setup.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def finish_setup_player(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
    ) -> NativeBattleSetup:
        result = self.try_finish_setup_player(setup, player_index=player_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def is_setup_complete(self, setup: NativeBattleSetup) -> bool:
        setup_c = _setup_to_c(setup)
        return bool(self._lib.ptcg_is_setup_complete(ctypes.byref(setup_c)))

    def try_begin_first_turn(self, setup: NativeBattleSetup) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_begin_first_turn(
            ctypes.byref(setup_c),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_top_deck_serial_to_hand(
            setup,
            next_setup,
            player_index=next_setup.current_player,
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "begin_first_turn",
                "turn": next_setup.turn,
                "playerIndex": next_setup.current_player,
                "message": f"P{next_setup.current_player} began the first turn.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def begin_first_turn(self, setup: NativeBattleSetup) -> NativeBattleSetup:
        result = self.try_begin_first_turn(setup)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_end_turn(self, setup: NativeBattleSetup) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_end_turn(
            ctypes.byref(setup_c),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_top_deck_serial_to_hand(
            setup,
            next_setup,
            player_index=next_setup.current_player,
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "end_turn",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "nextPlayerIndex": next_setup.current_player,
                "message": f"P{setup.current_player} ended the turn. P{next_setup.current_player} drew a card.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def end_turn(self, setup: NativeBattleSetup) -> NativeBattleSetup:
        result = self.try_end_turn(setup)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_basic_to_bench(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_basic_to_bench(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_basic",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played {_card_name(self, card_id)} to the Bench.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_basic_to_bench(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_basic_to_bench(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_dusk_ball(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_dusk_ball(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_dusk_ball",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played Dusk Ball and looked at the bottom 7 cards.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_dusk_ball(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_dusk_ball(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_dusk_ball(
        self,
        setup: NativeBattleSetup,
        *,
        deck_index: int,
        reveal: bool,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_resolve_dusk_ball(
            ctypes.byref(setup_c),
            ctypes.c_int(deck_index),
            ctypes.c_int(1 if reveal else 0),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = (
            setup.players[setup.pending_dusk_ball_player].deck_card_ids[deck_index]
            if reveal and setup.pending_dusk_ball_player is not None
            else None
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "dusk_ball_pick" if reveal else "dusk_ball_skip",
                "turn": setup.turn,
                "playerIndex": setup.pending_dusk_ball_player,
                "deckIndex": deck_index if reveal else None,
                "cardId": card_id,
                "message": (
                    f"P{setup.pending_dusk_ball_player} revealed {_card_name(self, card_id)} with Dusk Ball."
                    if reveal
                    else f"P{setup.pending_dusk_ball_player} chose no card with Dusk Ball."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def resolve_dusk_ball(
        self,
        setup: NativeBattleSetup,
        *,
        deck_index: int = -1,
        reveal: bool,
    ) -> NativeBattleSetup:
        result = self.try_resolve_dusk_ball(setup, deck_index=deck_index, reveal=reveal)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_fighting_gong(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_fighting_gong(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_fighting_gong",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played Fighting Gong and searched the deck.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_fighting_gong(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_fighting_gong(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_premium_power_pro(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_premium_power_pro(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_premium_power_pro",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "fightingAttackBonus": next_setup.fighting_attack_bonus,
                "message": f"P{setup.current_player} played Premium Power Pro.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_premium_power_pro(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_premium_power_pro(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_use_lunar_cycle(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_use_lunar_cycle(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        drawn_count = min(3, len(setup.players[setup.current_player].deck_card_ids))
        next_setup = _append_log(
            next_setup,
            {
                "kind": "use_lunar_cycle",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "drawnCount": drawn_count,
                "message": f"P{setup.current_player} used Lunar Cycle and drew {drawn_count} cards.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def use_lunar_cycle(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_use_lunar_cycle(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_gravity_mountain(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_gravity_mountain(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_stadium",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played {_card_name(self, card_id)}.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_gravity_mountain(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_gravity_mountain(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_fighting_gong(
        self,
        setup: NativeBattleSetup,
        *,
        deck_index: int,
        reveal: bool,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_resolve_fighting_gong(
            ctypes.byref(setup_c),
            ctypes.c_int(deck_index),
            ctypes.c_int(1 if reveal else 0),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = (
            setup.players[setup.pending_fighting_gong_player].deck_card_ids[deck_index]
            if reveal and setup.pending_fighting_gong_player is not None
            else None
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "fighting_gong_pick" if reveal else "fighting_gong_skip",
                "turn": setup.turn,
                "playerIndex": setup.pending_fighting_gong_player,
                "deckIndex": deck_index if reveal else None,
                "cardId": card_id,
                "message": (
                    f"P{setup.pending_fighting_gong_player} revealed {_card_name(self, card_id)} "
                    "with Fighting Gong."
                    if reveal
                    else f"P{setup.pending_fighting_gong_player} chose no card with Fighting Gong."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def resolve_fighting_gong(
        self,
        setup: NativeBattleSetup,
        *,
        deck_index: int = -1,
        reveal: bool,
    ) -> NativeBattleSetup:
        result = self.try_resolve_fighting_gong(setup, deck_index=deck_index, reveal=reveal)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_poke_pad(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_poke_pad(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_poke_pad",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played Poke Pad and searched the deck.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_poke_pad(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_poke_pad(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_poke_pad(
        self,
        setup: NativeBattleSetup,
        *,
        deck_index: int,
        reveal: bool,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_resolve_poke_pad(
            ctypes.byref(setup_c),
            ctypes.c_int(deck_index),
            ctypes.c_int(1 if reveal else 0),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = (
            setup.players[setup.pending_poke_pad_player].deck_card_ids[deck_index]
            if reveal and setup.pending_poke_pad_player is not None
            else None
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "poke_pad_pick" if reveal else "poke_pad_skip",
                "turn": setup.turn,
                "playerIndex": setup.pending_poke_pad_player,
                "deckIndex": deck_index if reveal else None,
                "cardId": card_id,
                "message": (
                    f"P{setup.pending_poke_pad_player} revealed {_card_name(self, card_id)} with Poke Pad."
                    if reveal
                    else f"P{setup.pending_poke_pad_player} chose no card with Poke Pad."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def resolve_poke_pad(
        self,
        setup: NativeBattleSetup,
        *,
        deck_index: int = -1,
        reveal: bool,
    ) -> NativeBattleSetup:
        result = self.try_resolve_poke_pad(setup, deck_index=deck_index, reveal=reveal)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_switch(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_switch(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_switch",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played Switch.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_switch(self, setup: NativeBattleSetup, *, hand_index: int) -> NativeBattleSetup:
        result = self.try_play_switch(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_switch(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        switch_player = setup.pending_switch_player
        active_card_id = (
            setup.players[switch_player].active_card_id
            if switch_player is not None
            else None
        )
        bench_card_id = (
            setup.players[switch_player].bench_card_ids[bench_index]
            if switch_player is not None and 0 <= bench_index < len(setup.players[switch_player].bench_card_ids)
            else None
        )
        error_code = self._lib.ptcg_resolve_switch(
            ctypes.byref(setup_c),
            ctypes.c_int(bench_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "switch_target",
                "turn": setup.turn,
                "playerIndex": switch_player,
                "benchIndex": bench_index,
                "cardId": active_card_id,
                "targetCardId": bench_card_id,
                "message": (
                    f"P{switch_player} switched {_card_name(self, active_card_id)} "
                    f"with {_card_name(self, bench_card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def resolve_switch(self, setup: NativeBattleSetup, *, bench_index: int) -> NativeBattleSetup:
        result = self.try_resolve_switch(setup, bench_index=bench_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_start_retreat(self, setup: NativeBattleSetup) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_start_retreat(
            ctypes.byref(setup_c),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        active_card_id = setup.players[setup.current_player].active_card_id
        next_setup = _append_log(
            next_setup,
            {
                "kind": "retreat_start",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "cardId": active_card_id,
                "retreatCost": next_setup.pending_retreat_remaining,
                "message": (
                    f"P{setup.current_player} started retreating "
                    f"{_card_name(self, active_card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(ok=True, error_code=0, message=text, setup=next_setup)

    def start_retreat(self, setup: NativeBattleSetup) -> NativeBattleSetup:
        result = self.try_start_retreat(setup)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_retreat_discard(
        self,
        setup: NativeBattleSetup,
        *,
        energy_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        retreat_player = setup.pending_retreat_player
        card_id = (
            setup.players[retreat_player].active_energy_card_ids[energy_index]
            if retreat_player is not None
            and 0 <= energy_index < len(setup.players[retreat_player].active_energy_card_ids)
            else None
        )
        error_code = self._lib.ptcg_resolve_retreat_discard(
            ctypes.byref(setup_c),
            ctypes.c_int(energy_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "retreat_discard",
                "turn": setup.turn,
                "playerIndex": retreat_player,
                "energyIndex": energy_index,
                "cardId": card_id,
                "remaining": next_setup.pending_retreat_remaining,
                "message": (
                    f"P{retreat_player} discarded {_card_name(self, card_id)} "
                    "for Retreat."
                ),
            },
        )
        return NativeBattleSetupResult(ok=True, error_code=0, message=text, setup=next_setup)

    def resolve_retreat_discard(
        self,
        setup: NativeBattleSetup,
        *,
        energy_index: int,
    ) -> NativeBattleSetup:
        result = self.try_resolve_retreat_discard(setup, energy_index=energy_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_retreat_promote(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        retreat_player = setup.pending_retreat_player
        active_card_id = (
            setup.players[retreat_player].active_card_id
            if retreat_player is not None
            else None
        )
        bench_card_id = (
            setup.players[retreat_player].bench_card_ids[bench_index]
            if retreat_player is not None
            and 0 <= bench_index < len(setup.players[retreat_player].bench_card_ids)
            else None
        )
        error_code = self._lib.ptcg_resolve_retreat_promote(
            ctypes.byref(setup_c),
            ctypes.c_int(bench_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "retreat_promote",
                "turn": setup.turn,
                "playerIndex": retreat_player,
                "benchIndex": bench_index,
                "cardId": active_card_id,
                "targetCardId": bench_card_id,
                "message": (
                    f"P{retreat_player} retreated {_card_name(self, active_card_id)} "
                    f"and promoted {_card_name(self, bench_card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(ok=True, error_code=0, message=text, setup=next_setup)

    def resolve_retreat_promote(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetup:
        result = self.try_resolve_retreat_promote(setup, bench_index=bench_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_lillies_determination(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_lillies_determination(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        drawn_count = next_setup.players[setup.current_player].hand_count
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_lillies_determination",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "drawnCount": drawn_count,
                "message": (
                    f"P{setup.current_player} played Lillie's Determination "
                    f"and drew {drawn_count} cards."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_lillies_determination(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetup:
        result = self.try_play_lillies_determination(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_carmine(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_carmine(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        drawn_count = next_setup.players[setup.current_player].hand_count
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_carmine",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "drawnCount": drawn_count,
                "message": f"P{setup.current_player} played Carmine and drew {drawn_count} cards.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_carmine(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetup:
        result = self.try_play_carmine(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_play_boss_orders(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_play_boss_orders(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[setup.current_player].hand_card_ids[hand_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "play_boss_orders",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "message": f"P{setup.current_player} played Boss's Orders.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def play_boss_orders(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
    ) -> NativeBattleSetup:
        result = self.try_play_boss_orders(setup, hand_index=hand_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_boss_orders(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_resolve_boss_orders(
            ctypes.byref(setup_c),
            ctypes.c_int(bench_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        target_player = 1 - setup.pending_boss_orders_player if setup.pending_boss_orders_player is not None else None
        card_id = (
            setup.players[target_player].bench_card_ids[bench_index]
            if target_player is not None
            else None
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "boss_orders_target",
                "turn": setup.turn,
                "playerIndex": setup.pending_boss_orders_player,
                "targetPlayerIndex": target_player,
                "benchIndex": bench_index,
                "cardId": card_id,
                "message": (
                    f"P{setup.pending_boss_orders_player} used Boss's Orders "
                    f"to switch in {_card_name(self, card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def resolve_boss_orders(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetup:
        result = self.try_resolve_boss_orders(setup, bench_index=bench_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_heave_ho_catcher(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_resolve_heave_ho_catcher(
            ctypes.byref(setup_c),
            ctypes.c_int(bench_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        target_player = 1 - setup.pending_heave_ho_player if setup.pending_heave_ho_player is not None else None
        card_id = (
            setup.players[target_player].bench_card_ids[bench_index]
            if target_player is not None
            else None
        )
        next_setup = _append_log(
            next_setup,
            {
                "kind": "heave_ho_catcher_target",
                "turn": setup.turn,
                "playerIndex": setup.pending_heave_ho_player,
                "targetPlayerIndex": target_player,
                "benchIndex": bench_index,
                "cardId": card_id,
                "message": (
                    f"P{setup.pending_heave_ho_player} used Heave-Ho Catcher "
                    f"to switch in {_card_name(self, card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def resolve_heave_ho_catcher(
        self,
        setup: NativeBattleSetup,
        *,
        bench_index: int,
    ) -> NativeBattleSetup:
        result = self.try_resolve_heave_ho_catcher(setup, bench_index=bench_index)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_skip_heave_ho_catcher(self, setup: NativeBattleSetup) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_skip_heave_ho_catcher(
            ctypes.byref(setup_c),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "heave_ho_catcher_skip",
                "turn": setup.turn,
                "playerIndex": setup.pending_heave_ho_player,
                "message": f"P{setup.pending_heave_ho_player} chose not to use Heave-Ho Catcher.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def skip_heave_ho_catcher(self, setup: NativeBattleSetup) -> NativeBattleSetup:
        result = self.try_skip_heave_ho_catcher(setup)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_evolve_from_hand(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
        in_play_area: int,
        in_play_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_evolve_from_hand(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.c_int(in_play_area),
            ctypes.c_int(in_play_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_hand_serial_to_evolution(
            setup,
            next_setup,
            player_index=setup.current_player,
            hand_index=hand_index,
            in_play_area=in_play_area,
            in_play_index=in_play_index,
        )
        player = setup.players[setup.current_player]
        card_id = player.hand_card_ids[hand_index]
        source_card_id = _target_card_id(player, in_play_area=in_play_area, in_play_index=in_play_index)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "evolve",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "sourceCardId": source_card_id,
                "inPlayArea": in_play_area,
                "inPlayIndex": in_play_index,
                "message": (
                    f"P{setup.current_player} evolved {_card_name(self, source_card_id)} "
                    f"into {_card_name(self, card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def evolve_from_hand(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
        in_play_area: int,
        in_play_index: int,
    ) -> NativeBattleSetup:
        result = self.try_evolve_from_hand(
            setup,
            hand_index=hand_index,
            in_play_area=in_play_area,
            in_play_index=in_play_index,
        )
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_attach_energy(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
        in_play_area: int,
        in_play_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_attach_energy(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.c_int(in_play_area),
            ctypes.c_int(in_play_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_hand_serial_to_attached_energy(
            setup,
            next_setup,
            player_index=setup.current_player,
            hand_index=hand_index,
            in_play_area=in_play_area,
            in_play_index=in_play_index,
        )
        player = setup.players[setup.current_player]
        card_id = player.hand_card_ids[hand_index]
        target_card_id = _target_card_id(player, in_play_area=in_play_area, in_play_index=in_play_index)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "attach_energy",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "inPlayArea": in_play_area,
                "inPlayIndex": in_play_index,
                "targetCardId": target_card_id,
                "message": (
                    f"P{setup.current_player} attached {_card_name(self, card_id)} "
                    f"to {_card_name(self, target_card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def attach_energy(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
        in_play_area: int,
        in_play_index: int,
    ) -> NativeBattleSetup:
        result = self.try_attach_energy(
            setup,
            hand_index=hand_index,
            in_play_area=in_play_area,
            in_play_index=in_play_index,
        )
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_attach_heros_cape(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
        in_play_area: int,
        in_play_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_attach_heros_cape(
            ctypes.byref(setup_c),
            ctypes.c_int(hand_index),
            ctypes.c_int(in_play_area),
            ctypes.c_int(in_play_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        player = setup.players[setup.current_player]
        card_id = player.hand_card_ids[hand_index]
        target_card_id = _target_card_id(player, in_play_area=in_play_area, in_play_index=in_play_index)
        tool_name = "Hero's Cape" if card_id == CARD_HEROS_CAPE else _card_name(self, card_id)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "attach_tool",
                "turn": setup.turn,
                "playerIndex": setup.current_player,
                "handIndex": hand_index,
                "cardId": card_id,
                "inPlayArea": in_play_area,
                "inPlayIndex": in_play_index,
                "targetCardId": target_card_id,
                "message": (
                    f"P{setup.current_player} attached {tool_name} "
                    f"to {_card_name(self, target_card_id)}."
                ),
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def attach_heros_cape(
        self,
        setup: NativeBattleSetup,
        *,
        hand_index: int,
        in_play_area: int,
        in_play_index: int,
    ) -> NativeBattleSetup:
        result = self.try_attach_heros_cape(
            setup,
            hand_index=hand_index,
            in_play_area=in_play_area,
            in_play_index=in_play_index,
        )
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_use_attack(
        self,
        setup: NativeBattleSetup,
        *,
        attack_id: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_use_attack(
            ctypes.byref(setup_c),
            ctypes.c_int(attack_id),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _move_top_deck_serial_to_hand(
            setup,
            next_setup,
            player_index=next_setup.current_player,
        )
        attack = self.attack_metadata(attack_id)
        damage = _effective_attack_damage(self, setup, attack_id=attack_id)
        self_damage = _attack_self_damage(attack_id)
        message_text = f"P{setup.current_player} used {attack.name} for {damage} damage."
        log: dict[str, object] = {
            "kind": "attack",
            "turn": setup.turn,
            "playerIndex": setup.current_player,
            "attackId": attack_id,
            "damage": damage,
            "message": message_text,
        }
        if self_damage > 0:
            log["selfDamage"] = self_damage
            log["message"] = (
                f"P{setup.current_player} used {attack.name} for {damage} damage "
                f"and {self_damage} self-damage."
            )
        next_setup = _append_log(
            next_setup,
            log,
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def use_attack(self, setup: NativeBattleSetup, *, attack_id: int) -> NativeBattleSetup:
        result = self.try_use_attack(setup, attack_id=attack_id)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_resolve_aura_jab_attach(
        self,
        setup: NativeBattleSetup,
        *,
        discard_index: int,
        bench_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        player_index = setup.pending_aura_jab_player
        card_id = (
            setup.players[player_index].discard_card_ids[discard_index]
            if player_index is not None
            and 0 <= discard_index < len(setup.players[player_index].discard_card_ids)
            else None
        )
        target_card_id = (
            setup.players[player_index].bench_card_ids[bench_index]
            if player_index is not None
            and 0 <= bench_index < len(setup.players[player_index].bench_card_ids)
            else None
        )
        error_code = self._lib.ptcg_resolve_aura_jab_attach(
            ctypes.byref(setup_c),
            ctypes.c_int(discard_index),
            ctypes.c_int(bench_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "aura_jab_attach",
                "turn": setup.turn,
                "playerIndex": player_index,
                "discardIndex": discard_index,
                "benchIndex": bench_index,
                "cardId": card_id,
                "targetCardId": target_card_id,
                "message": (
                    f"P{player_index} attached {_card_name(self, card_id)} from discard "
                    f"to {_card_name(self, target_card_id)} with Aura Jab."
                ),
            },
        )
        return NativeBattleSetupResult(ok=True, error_code=0, message=text, setup=next_setup)

    def resolve_aura_jab_attach(
        self,
        setup: NativeBattleSetup,
        *,
        discard_index: int,
        bench_index: int,
    ) -> NativeBattleSetup:
        result = self.try_resolve_aura_jab_attach(
            setup,
            discard_index=discard_index,
            bench_index=bench_index,
        )
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_skip_aura_jab(self, setup: NativeBattleSetup) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        player_index = setup.pending_aura_jab_player
        error_code = self._lib.ptcg_skip_aura_jab(
            ctypes.byref(setup_c),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        next_setup = _append_log(
            next_setup,
            {
                "kind": "aura_jab_skip",
                "turn": setup.turn,
                "playerIndex": player_index,
                "message": f"P{player_index} finished Aura Jab attachments.",
            },
        )
        return NativeBattleSetupResult(ok=True, error_code=0, message=text, setup=next_setup)

    def skip_aura_jab(self, setup: NativeBattleSetup) -> NativeBattleSetup:
        result = self.try_skip_aura_jab(setup)
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup

    def try_promote_bench_to_active(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
        bench_index: int,
    ) -> NativeBattleSetupResult:
        setup_c = _setup_to_c(setup)
        out_setup_c = _NativeBattleSetupC()
        message = ctypes.create_string_buffer(512)
        error_code = self._lib.ptcg_promote_bench_to_active(
            ctypes.byref(setup_c),
            ctypes.c_int(player_index),
            ctypes.c_int(bench_index),
            ctypes.byref(out_setup_c),
            message,
            len(message),
        )
        text = message.value.decode("utf-8", errors="replace")
        if error_code != 0:
            return NativeBattleSetupResult(ok=False, error_code=error_code, message=text)
        next_setup = _setup_from_c(out_setup_c, logs=setup.logs)
        card_id = setup.players[player_index].bench_card_ids[bench_index]
        next_setup = _append_log(
            next_setup,
            {
                "kind": "promote_active",
                "turn": setup.turn,
                "playerIndex": player_index,
                "benchIndex": bench_index,
                "cardId": card_id,
                "message": f"P{player_index} promoted {_card_name(self, card_id)} to Active Pokemon.",
            },
        )
        return NativeBattleSetupResult(
            ok=True,
            error_code=0,
            message=text,
            setup=next_setup,
        )

    def promote_bench_to_active(
        self,
        setup: NativeBattleSetup,
        *,
        player_index: int,
        bench_index: int,
    ) -> NativeBattleSetup:
        result = self.try_promote_bench_to_active(
            setup,
            player_index=player_index,
            bench_index=bench_index,
        )
        if not result.ok or result.setup is None:
            raise NativeCoreError(result.message)
        return result.setup


def _setup_from_c(
    setup: _NativeBattleSetupC,
    *,
    logs: tuple[dict[str, object], ...] = (),
) -> NativeBattleSetup:
    players = tuple(
        _player_from_c(setup.players[index], setup_complete=bool(setup.setup_complete[index]))
        for index in range(2)
    )
    return NativeBattleSetup(
        turn=int(setup.turn),
        first_player=int(setup.first_player),
        current_player=int(setup.current_player),
        energy_attached=bool(setup.energy_attached),
        result=int(setup.result),
        players=(players[0], players[1]),
        setup_mulligans=(int(setup.setup_mulligans[0]), int(setup.setup_mulligans[1])),
        setup_mulligan_draw_choices=(
            int(setup.setup_mulligan_draw_choices[0])
            if int(setup.setup_mulligan_draw_choices[0]) >= 0
            else None,
            int(setup.setup_mulligan_draw_choices[1])
            if int(setup.setup_mulligan_draw_choices[1]) >= 0
            else None,
        ),
        retreated=bool(setup.retreated),
        fighting_attack_bonus=int(setup.fighting_attack_bonus),
        lunar_cycle_used=bool(setup.lunar_cycle_used),
        stadium_played=bool(setup.stadium_played),
        stadium_card_id=(int(setup.stadium_card_id) if int(setup.stadium_card_id) > 0 else None),
        stadium_player_index=(
            int(setup.stadium_player_index)
            if int(setup.stadium_player_index) >= 0
            else None
        ),
        pending_promotion_player=(
            int(setup.pending_promotion_player) if int(setup.pending_promotion_player) >= 0 else None
        ),
        pending_promotion_next_player=(
            int(setup.pending_promotion_next_player)
            if int(setup.pending_promotion_next_player) >= 0
            else None
        ),
        pending_dusk_ball_player=(
            int(setup.pending_dusk_ball_player) if int(setup.pending_dusk_ball_player) >= 0 else None
        ),
        pending_dusk_ball_start=int(setup.pending_dusk_ball_start),
        pending_dusk_ball_count=int(setup.pending_dusk_ball_count),
        pending_boss_orders_player=(
            int(setup.pending_boss_orders_player) if int(setup.pending_boss_orders_player) >= 0 else None
        ),
        pending_heave_ho_player=(
            int(setup.pending_heave_ho_player) if int(setup.pending_heave_ho_player) >= 0 else None
        ),
        pending_fighting_gong_player=(
            int(setup.pending_fighting_gong_player) if int(setup.pending_fighting_gong_player) >= 0 else None
        ),
        pending_poke_pad_player=(
            int(setup.pending_poke_pad_player) if int(setup.pending_poke_pad_player) >= 0 else None
        ),
        pending_switch_player=(
            int(setup.pending_switch_player) if int(setup.pending_switch_player) >= 0 else None
        ),
        pending_retreat_player=(
            int(setup.pending_retreat_player) if int(setup.pending_retreat_player) >= 0 else None
        ),
        pending_retreat_remaining=int(setup.pending_retreat_remaining),
        pending_aura_jab_player=(
            int(setup.pending_aura_jab_player) if int(setup.pending_aura_jab_player) >= 0 else None
        ),
        pending_aura_jab_remaining=int(setup.pending_aura_jab_remaining),
        supporter_played=bool(setup.supporter_played),
        logs=logs,
    )


def _setup_to_c(setup: NativeBattleSetup) -> _NativeBattleSetupC:
    setup_c = _NativeBattleSetupC()
    setup_c.turn = setup.turn
    setup_c.first_player = setup.first_player
    setup_c.current_player = setup.current_player
    setup_c.energy_attached = int(setup.energy_attached)
    setup_c.setup_mulligans[0] = int(setup.setup_mulligans[0])
    setup_c.setup_mulligans[1] = int(setup.setup_mulligans[1])
    setup_c.setup_mulligan_draw_choices[0] = (
        -1 if setup.setup_mulligan_draw_choices[0] is None else int(setup.setup_mulligan_draw_choices[0])
    )
    setup_c.setup_mulligan_draw_choices[1] = (
        -1 if setup.setup_mulligan_draw_choices[1] is None else int(setup.setup_mulligan_draw_choices[1])
    )
    setup_c.retreated = int(setup.retreated)
    setup_c.supporter_played = int(setup.supporter_played)
    setup_c.lunar_cycle_used = int(setup.lunar_cycle_used)
    setup_c.stadium_played = int(setup.stadium_played)
    setup_c.stadium_card_id = 0 if setup.stadium_card_id is None else setup.stadium_card_id
    setup_c.stadium_player_index = -1 if setup.stadium_player_index is None else setup.stadium_player_index
    setup_c.fighting_attack_bonus = int(setup.fighting_attack_bonus)
    setup_c.result = setup.result
    setup_c.pending_promotion_player = (
        -1 if setup.pending_promotion_player is None else setup.pending_promotion_player
    )
    setup_c.pending_promotion_next_player = (
        -1 if setup.pending_promotion_next_player is None else setup.pending_promotion_next_player
    )
    setup_c.pending_dusk_ball_player = (
        -1 if setup.pending_dusk_ball_player is None else setup.pending_dusk_ball_player
    )
    setup_c.pending_dusk_ball_start = setup.pending_dusk_ball_start
    setup_c.pending_dusk_ball_count = setup.pending_dusk_ball_count
    setup_c.pending_boss_orders_player = (
        -1 if setup.pending_boss_orders_player is None else setup.pending_boss_orders_player
    )
    setup_c.pending_heave_ho_player = (
        -1 if setup.pending_heave_ho_player is None else setup.pending_heave_ho_player
    )
    setup_c.pending_fighting_gong_player = (
        -1 if setup.pending_fighting_gong_player is None else setup.pending_fighting_gong_player
    )
    setup_c.pending_poke_pad_player = (
        -1 if setup.pending_poke_pad_player is None else setup.pending_poke_pad_player
    )
    setup_c.pending_switch_player = (
        -1 if setup.pending_switch_player is None else setup.pending_switch_player
    )
    setup_c.pending_retreat_player = (
        -1 if setup.pending_retreat_player is None else setup.pending_retreat_player
    )
    setup_c.pending_retreat_remaining = setup.pending_retreat_remaining
    setup_c.pending_aura_jab_player = (
        -1 if setup.pending_aura_jab_player is None else setup.pending_aura_jab_player
    )
    setup_c.pending_aura_jab_remaining = setup.pending_aura_jab_remaining
    for index, player in enumerate(setup.players):
        setup_c.setup_complete[index] = int(player.setup_complete)
        _copy_player_to_c(player, setup_c.players[index])
    return setup_c


def _copy_player_to_c(player: NativeBattlePlayer, out_player: _NativeBattlePlayerC) -> None:
    _copy_cards(player.deck_card_ids, out_player.deck, DECK_SIZE, "deck")
    out_player.deck_count = len(player.deck_card_ids)
    _copy_cards(player.hand_card_ids, out_player.hand, HAND_SIZE, "hand")
    out_player.hand_count = len(player.hand_card_ids)
    _copy_cards(player.discard_card_ids, out_player.discard, DISCARD_SIZE, "discard")
    out_player.discard_count = len(player.discard_card_ids)
    _copy_cards(player.prize_card_ids, out_player.prize, PRIZE_SIZE, "prize")
    out_player.prize_count = len(player.prize_card_ids)
    out_player.active_card_id = player.active_card_id or 0
    out_player.active_damage = player.active_damage
    out_player.active_entered_turn = player.active_entered_turn
    out_player.active_evolved_turn = player.active_evolved_turn
    _copy_cards(
        player.active_pre_evolution_card_ids,
        out_player.active_pre_evolution,
        PRE_EVOLUTION_SIZE,
        "active_pre_evolution",
    )
    out_player.active_pre_evolution_count = len(player.active_pre_evolution_card_ids)
    _copy_cards(player.active_energy_card_ids, out_player.active_energy, ATTACHED_SIZE, "active_energy")
    out_player.active_energy_count = len(player.active_energy_card_ids)
    out_player.active_tool_card_id = 0 if player.active_tool_card_id is None else player.active_tool_card_id
    out_player.active_disabled_attack_id = (
        0 if player.active_disabled_attack_id is None else player.active_disabled_attack_id
    )
    out_player.active_disabled_attack_turn = player.active_disabled_attack_turn
    _copy_cards(player.bench_card_ids, out_player.bench, BENCH_SIZE, "bench")
    out_player.bench_count = len(player.bench_card_ids)
    _copy_cards(player.bench_damage, out_player.bench_damage, BENCH_SIZE, "bench_damage")
    _copy_cards(player.bench_entered_turns, out_player.bench_entered_turn, BENCH_SIZE, "bench_entered_turn")
    _copy_cards(player.bench_evolved_turns, out_player.bench_evolved_turn, BENCH_SIZE, "bench_evolved_turn")
    for bench_index, pre_evolution_cards in enumerate(player.bench_pre_evolution_card_ids):
        if bench_index >= BENCH_SIZE:
            raise ValueError(
                f"bench_pre_evolution has {len(player.bench_pre_evolution_card_ids)} rows, max is {BENCH_SIZE}"
            )
        _copy_cards(
            pre_evolution_cards,
            out_player.bench_pre_evolution[bench_index],
            PRE_EVOLUTION_SIZE,
            "bench_pre_evolution",
        )
        out_player.bench_pre_evolution_count[bench_index] = len(pre_evolution_cards)
    for bench_index, energy_cards in enumerate(player.bench_energy_card_ids):
        if bench_index >= BENCH_SIZE:
            raise ValueError(f"bench_energy has {len(player.bench_energy_card_ids)} rows, max is {BENCH_SIZE}")
        _copy_cards(
            energy_cards,
            out_player.bench_energy[bench_index],
            ATTACHED_SIZE,
            "bench_energy",
        )
        out_player.bench_energy_count[bench_index] = len(energy_cards)
    for bench_index, tool_card_id in enumerate(player.bench_tool_card_ids):
        if bench_index >= BENCH_SIZE:
            raise ValueError(f"bench_tool has {len(player.bench_tool_card_ids)} cards, max is {BENCH_SIZE}")
        out_player.bench_tool[bench_index] = 0 if tool_card_id is None else tool_card_id


def _copy_cards(cards: tuple[int, ...], target: ctypes.Array, limit: int, zone_name: str) -> None:
    if len(cards) > limit:
        raise ValueError(f"{zone_name} has {len(cards)} cards, max is {limit}")
    for index, card_id in enumerate(cards):
        target[index] = card_id


def _validated_ordered_zone_serials(
    serials: tuple[int, ...] | list[int] | None,
    *,
    expected_count: int,
    label: str,
) -> tuple[int, ...]:
    if serials is None:
        return ()
    serial_ids = tuple(int(serial) for serial in serials)
    if len(serial_ids) != expected_count:
        raise NativeCoreError(f"{label} must contain {expected_count} entries")
    if any(serial <= 0 for serial in serial_ids):
        raise NativeCoreError(f"{label} must contain positive serials")
    return serial_ids


def _preserve_serial_metadata(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
) -> NativeBattleSetup:
    players = tuple(
        _preserve_player_serial_metadata(source_player, target_player)
        for source_player, target_player in zip(source_setup.players, target_setup.players)
    )
    return replace(target_setup, players=players)


def _preserve_player_serial_metadata(
    source_player: NativeBattlePlayer,
    target_player: NativeBattlePlayer,
) -> NativeBattlePlayer:
    return replace(
        target_player,
        deck_card_serials=_serials_if_zone_unchanged(
            source_player.deck_card_ids,
            target_player.deck_card_ids,
            source_player.deck_card_serials,
            target_player.deck_card_serials,
        ),
        hand_card_serials=_serials_if_zone_unchanged(
            source_player.hand_card_ids,
            target_player.hand_card_ids,
            source_player.hand_card_serials,
            target_player.hand_card_serials,
        ),
        prize_card_serials=_serials_if_zone_unchanged(
            source_player.prize_card_ids,
            target_player.prize_card_ids,
            source_player.prize_card_serials,
            target_player.prize_card_serials,
        ),
        active_card_serial=source_player.active_card_serial
        if source_player.active_card_id == target_player.active_card_id
        else target_player.active_card_serial,
        bench_card_serials=_serials_if_zone_unchanged(
            source_player.bench_card_ids,
            target_player.bench_card_ids,
            source_player.bench_card_serials,
            target_player.bench_card_serials,
        ),
        active_energy_card_serials=_serials_if_zone_unchanged(
            source_player.active_energy_card_ids,
            target_player.active_energy_card_ids,
            source_player.active_energy_card_serials,
            target_player.active_energy_card_serials,
        ),
        bench_energy_card_serials=_nested_serials_if_zones_unchanged(
            source_player.bench_energy_card_ids,
            target_player.bench_energy_card_ids,
            source_player.bench_energy_card_serials,
            target_player.bench_energy_card_serials,
        ),
    )


def _move_hand_serial_to_active(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
    *,
    player_index: int,
    hand_index: int,
) -> NativeBattleSetup:
    target_setup = _preserve_serial_metadata(source_setup, target_setup)
    source_player = source_setup.players[player_index]
    target_player = target_setup.players[player_index]
    if not _has_zone_serials(source_player.hand_card_ids, source_player.hand_card_serials):
        return target_setup
    if hand_index < 0 or hand_index >= len(source_player.hand_card_serials):
        return target_setup

    selected_serial = source_player.hand_card_serials[hand_index]
    remaining_hand_serials = _remove_tuple_index(source_player.hand_card_serials, hand_index)
    if len(remaining_hand_serials) != len(target_player.hand_card_ids):
        return target_setup

    players = list(target_setup.players)
    players[player_index] = replace(
        target_player,
        hand_card_serials=remaining_hand_serials,
        active_card_serial=selected_serial,
    )
    return replace(target_setup, players=(players[0], players[1]))


def _move_hand_serial_to_bench(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
    *,
    player_index: int,
    hand_index: int,
) -> NativeBattleSetup:
    target_setup = _preserve_serial_metadata(source_setup, target_setup)
    source_player = source_setup.players[player_index]
    target_player = target_setup.players[player_index]
    if not _has_zone_serials(source_player.hand_card_ids, source_player.hand_card_serials):
        return target_setup
    if not _has_zone_serials(source_player.bench_card_ids, source_player.bench_card_serials):
        return target_setup
    if hand_index < 0 or hand_index >= len(source_player.hand_card_serials):
        return target_setup

    selected_serial = source_player.hand_card_serials[hand_index]
    remaining_hand_serials = _remove_tuple_index(source_player.hand_card_serials, hand_index)
    expected_bench_serials = source_player.bench_card_serials + (selected_serial,)
    if len(remaining_hand_serials) != len(target_player.hand_card_ids):
        return target_setup
    if len(expected_bench_serials) != len(target_player.bench_card_ids):
        return target_setup

    players = list(target_setup.players)
    players[player_index] = replace(
        target_player,
        hand_card_serials=remaining_hand_serials,
        bench_card_serials=expected_bench_serials,
    )
    return replace(target_setup, players=(players[0], players[1]))


def _move_hand_serial_to_evolution(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
    *,
    player_index: int,
    hand_index: int,
    in_play_area: int,
    in_play_index: int,
) -> NativeBattleSetup:
    target_setup = _preserve_serial_metadata(source_setup, target_setup)
    source_player = source_setup.players[player_index]
    target_player = target_setup.players[player_index]
    if not _has_zone_serials(source_player.hand_card_ids, source_player.hand_card_serials):
        return target_setup
    if hand_index < 0 or hand_index >= len(source_player.hand_card_serials):
        return target_setup

    selected_serial = source_player.hand_card_serials[hand_index]
    remaining_hand_serials = _remove_tuple_index(source_player.hand_card_serials, hand_index)
    if len(remaining_hand_serials) != len(target_player.hand_card_ids):
        return target_setup

    players = list(target_setup.players)
    if in_play_area == AREA_ACTIVE:
        if target_player.active_card_id == source_player.active_card_id:
            return target_setup
        players[player_index] = replace(
            target_player,
            hand_card_serials=remaining_hand_serials,
            active_card_serial=selected_serial,
        )
        return replace(target_setup, players=(players[0], players[1]))

    if in_play_area == AREA_BENCH:
        if (
            in_play_index < 0
            or in_play_index >= len(source_player.bench_card_ids)
            or in_play_index >= len(target_player.bench_card_ids)
        ):
            return target_setup
        if target_player.bench_card_ids[in_play_index] == source_player.bench_card_ids[in_play_index]:
            return target_setup
        if not _has_zone_serials(source_player.bench_card_ids, source_player.bench_card_serials):
            return target_setup
        bench_serials = list(target_player.bench_card_serials)
        if len(bench_serials) != len(target_player.bench_card_ids):
            return target_setup
        bench_serials[in_play_index] = selected_serial
        players[player_index] = replace(
            target_player,
            hand_card_serials=remaining_hand_serials,
            bench_card_serials=tuple(bench_serials),
        )
        return replace(target_setup, players=(players[0], players[1]))

    return target_setup


def _move_hand_serial_to_attached_energy(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
    *,
    player_index: int,
    hand_index: int,
    in_play_area: int,
    in_play_index: int,
) -> NativeBattleSetup:
    target_setup = _preserve_serial_metadata(source_setup, target_setup)
    source_player = source_setup.players[player_index]
    target_player = target_setup.players[player_index]
    if not _has_zone_serials(source_player.hand_card_ids, source_player.hand_card_serials):
        return target_setup
    if hand_index < 0 or hand_index >= len(source_player.hand_card_serials):
        return target_setup

    selected_serial = source_player.hand_card_serials[hand_index]
    remaining_hand_serials = _remove_tuple_index(source_player.hand_card_serials, hand_index)
    if len(remaining_hand_serials) != len(target_player.hand_card_ids):
        return target_setup

    if in_play_area == AREA_ACTIVE:
        if not _has_zone_serials(source_player.active_energy_card_ids, source_player.active_energy_card_serials):
            return target_setup
        expected_energy_serials = source_player.active_energy_card_serials + (selected_serial,)
        if len(expected_energy_serials) != len(target_player.active_energy_card_ids):
            return target_setup
        players = list(target_setup.players)
        players[player_index] = replace(
            target_player,
            hand_card_serials=remaining_hand_serials,
            active_energy_card_serials=expected_energy_serials,
        )
        return replace(target_setup, players=(players[0], players[1]))

    if in_play_area == AREA_BENCH:
        if in_play_index < 0 or in_play_index >= len(source_player.bench_energy_card_ids):
            return target_setup
        source_bench_serials = _normalized_nested_serials(
            source_player.bench_energy_card_ids,
            source_player.bench_energy_card_serials,
        )
        if in_play_index >= len(source_bench_serials):
            return target_setup
        expected_bench_serials = list(source_bench_serials)
        expected_bench_serials[in_play_index] = expected_bench_serials[in_play_index] + (selected_serial,)
        if tuple(len(serials) for serials in expected_bench_serials) != tuple(
            len(ids) for ids in target_player.bench_energy_card_ids
        ):
            return target_setup
        players = list(target_setup.players)
        players[player_index] = replace(
            target_player,
            hand_card_serials=remaining_hand_serials,
            bench_energy_card_serials=tuple(expected_bench_serials),
        )
        return replace(target_setup, players=(players[0], players[1]))

    return target_setup


def _move_deck_serials_to_setup_prizes(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
) -> NativeBattleSetup:
    target_setup = _preserve_serial_metadata(source_setup, target_setup)
    players: list[NativeBattlePlayer] = []
    for source_player, target_player in zip(source_setup.players, target_setup.players):
        if not _has_zone_serials(source_player.deck_card_ids, source_player.deck_card_serials):
            players.append(target_player)
            continue
        expected_prize_ids = tuple(reversed(source_player.deck_card_ids[-PRIZE_SIZE:]))
        expected_deck_ids = source_player.deck_card_ids[:-PRIZE_SIZE]
        if (
            target_player.prize_card_ids != expected_prize_ids
            or target_player.deck_card_ids != expected_deck_ids
        ):
            players.append(target_player)
            continue
        players.append(
            replace(
                target_player,
                prize_card_serials=tuple(reversed(source_player.deck_card_serials[-PRIZE_SIZE:])),
                deck_card_serials=source_player.deck_card_serials[:-PRIZE_SIZE],
            )
        )
    if len(players) != len(target_setup.players):
        return target_setup
    return replace(target_setup, players=(players[0], players[1]))


def _move_top_deck_serial_to_hand(
    source_setup: NativeBattleSetup,
    target_setup: NativeBattleSetup,
    *,
    player_index: int,
) -> NativeBattleSetup:
    target_setup = _preserve_serial_metadata(source_setup, target_setup)
    if player_index < 0 or player_index >= len(source_setup.players):
        return target_setup

    source_player = source_setup.players[player_index]
    target_player = target_setup.players[player_index]
    if not _has_zone_serials(source_player.deck_card_ids, source_player.deck_card_serials):
        return target_setup
    if not _has_zone_serials(source_player.hand_card_ids, source_player.hand_card_serials):
        return target_setup
    if not source_player.deck_card_ids:
        return target_setup

    expected_deck_ids = source_player.deck_card_ids[:-1]
    expected_hand_ids = source_player.hand_card_ids + (source_player.deck_card_ids[-1],)
    if (
        target_player.deck_card_ids != expected_deck_ids
        or target_player.hand_card_ids != expected_hand_ids
    ):
        return target_setup

    players = list(target_setup.players)
    players[player_index] = replace(
        target_player,
        deck_card_serials=source_player.deck_card_serials[:-1],
        hand_card_serials=source_player.hand_card_serials + (source_player.deck_card_serials[-1],),
    )
    return replace(target_setup, players=(players[0], players[1]))


def _serials_if_zone_unchanged(
    source_card_ids: tuple[int, ...],
    target_card_ids: tuple[int, ...],
    source_serials: tuple[int, ...],
    target_serials: tuple[int, ...],
) -> tuple[int, ...]:
    if source_card_ids == target_card_ids and _has_zone_serials(source_card_ids, source_serials):
        return source_serials
    return target_serials


def _nested_serials_if_zones_unchanged(
    source_card_ids: tuple[tuple[int, ...], ...],
    target_card_ids: tuple[tuple[int, ...], ...],
    source_serials: tuple[tuple[int, ...], ...],
    target_serials: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    if source_card_ids == target_card_ids and len(source_card_ids) == len(source_serials):
        if all(_has_zone_serials(ids, serials) for ids, serials in zip(source_card_ids, source_serials)):
            return source_serials
    return target_serials


def _normalized_nested_serials(
    card_ids: tuple[tuple[int, ...], ...],
    serials: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    if len(card_ids) != len(serials):
        return tuple(() for _ in card_ids)
    if not all(_has_zone_serials(ids, zone_serials) for ids, zone_serials in zip(card_ids, serials)):
        return tuple(() for _ in card_ids)
    return serials


def _has_zone_serials(card_ids: tuple[int, ...], serials: tuple[int, ...]) -> bool:
    return len(card_ids) == len(serials)


def _remove_tuple_index(values: tuple[int, ...], index: int) -> tuple[int, ...]:
    return values[:index] + values[index + 1 :]


def _player_from_c(player: _NativeBattlePlayerC, *, setup_complete: bool = False) -> NativeBattlePlayer:
    active = int(player.active_card_id)
    bench_count = int(player.bench_count)
    return NativeBattlePlayer(
        deck_card_ids=tuple(int(player.deck[index]) for index in range(int(player.deck_count))),
        hand_card_ids=tuple(int(player.hand[index]) for index in range(int(player.hand_count))),
        discard_card_ids=tuple(int(player.discard[index]) for index in range(int(player.discard_count))),
        prize_card_ids=tuple(int(player.prize[index]) for index in range(int(player.prize_count))),
        active_card_id=active if active > 0 else None,
        bench_card_ids=tuple(int(player.bench[index]) for index in range(bench_count)),
        active_damage=int(player.active_damage),
        bench_damage=tuple(int(player.bench_damage[index]) for index in range(bench_count)),
        active_entered_turn=int(player.active_entered_turn),
        active_evolved_turn=int(player.active_evolved_turn),
        bench_entered_turns=tuple(int(player.bench_entered_turn[index]) for index in range(bench_count)),
        bench_evolved_turns=tuple(int(player.bench_evolved_turn[index]) for index in range(bench_count)),
        active_pre_evolution_card_ids=tuple(
            int(player.active_pre_evolution[index])
            for index in range(int(player.active_pre_evolution_count))
        ),
        bench_pre_evolution_card_ids=tuple(
            tuple(
                int(player.bench_pre_evolution[bench_index][pre_evolution_index])
                for pre_evolution_index in range(int(player.bench_pre_evolution_count[bench_index]))
            )
            for bench_index in range(bench_count)
        ),
        active_energy_card_ids=tuple(
            int(player.active_energy[index]) for index in range(int(player.active_energy_count))
        ),
        bench_energy_card_ids=tuple(
            tuple(
                int(player.bench_energy[bench_index][energy_index])
                for energy_index in range(int(player.bench_energy_count[bench_index]))
            )
            for bench_index in range(bench_count)
        ),
        active_tool_card_id=(
            int(player.active_tool_card_id)
            if int(player.active_tool_card_id) > 0
            else None
        ),
        bench_tool_card_ids=tuple(
            int(player.bench_tool[index]) if int(player.bench_tool[index]) > 0 else None
            for index in range(bench_count)
        ),
        active_disabled_attack_id=(
            int(player.active_disabled_attack_id)
            if int(player.active_disabled_attack_id) > 0
            else None
        ),
        active_disabled_attack_turn=int(player.active_disabled_attack_turn),
        setup_complete=setup_complete,
    )


def _append_log(setup: NativeBattleSetup, log: dict[str, object]) -> NativeBattleSetup:
    return replace(setup, logs=setup.logs + (log,))


def _card_name(native_core: NativeCore, card_id: int | None) -> str:
    if card_id is None:
        return "unknown"
    try:
        return native_core.card_metadata(card_id).name
    except NativeCoreError:
        return str(card_id)


def _target_card_id(
    player: NativeBattlePlayer,
    *,
    in_play_area: int,
    in_play_index: int,
) -> int | None:
    if in_play_area == AREA_ACTIVE:
        return player.active_card_id
    if in_play_area == AREA_BENCH and 0 <= in_play_index < len(player.bench_card_ids):
        return player.bench_card_ids[in_play_index]
    return None


def _card(card_id: int, player_index: int, *, serial: int) -> dict:
    return {"id": card_id, "serial": serial, "playerIndex": player_index}


def _zone_serial(serials: tuple[int, ...], index: int, fallback: int) -> int:
    if 0 <= index < len(serials):
        return serials[index]
    return fallback


def _appeared_this_turn(*, current_turn: int, entered_turn: int, evolved_turn: int) -> bool:
    return current_turn > 0 and (entered_turn == current_turn or evolved_turn == current_turn)


def _pokemon(
    card_id: int | None,
    player_index: int,
    *,
    serial: int,
    damage: int = 0,
    appear_this_turn: bool = False,
    pre_evolution_card_ids: tuple[int, ...] = (),
    energy_card_ids: tuple[int, ...] = (),
    energy_card_serials: tuple[int, ...] = (),
    tool_card_ids: tuple[int, ...] = (),
    energy_serial_base: int = 200000,
    tool_serial_base: int = 500000,
    stadium_card_id: int | None = None,
    native_core: NativeCore | None = None,
) -> dict:
    energy_cards = [
        _card(
            energy_card_id,
            player_index,
            serial=_zone_serial(energy_card_serials, index, energy_serial_base + index),
        )
        for index, energy_card_id in enumerate(energy_card_ids)
    ]
    pre_evolution_cards = [
        _card(pre_evolution_card_id, player_index, serial=400000 + player_index * 1000 + index)
        for index, pre_evolution_card_id in enumerate(pre_evolution_card_ids)
    ]
    tool_cards = [
        _card(tool_card_id, player_index, serial=tool_serial_base + index)
        for index, tool_card_id in enumerate(tool_card_ids)
    ]
    energies = [
        native_core.card_metadata(energy_card_id).energy_type
        for energy_card_id in energy_card_ids
        if native_core is not None
    ]
    metadata = native_core.card_metadata(card_id) if native_core is not None and card_id is not None else None
    max_hp = metadata.hp if metadata is not None else 0
    if metadata is not None:
        max_hp += _stadium_hp_modifier(metadata, stadium_card_id)
    max_hp += sum(_tool_hp_bonus(tool_card_id) for tool_card_id in tool_card_ids)
    max_hp = max(0, max_hp)
    hp = max(0, max_hp - max(0, damage)) if max_hp > 0 else 0
    return {
        "id": card_id,
        "serial": serial,
        "playerIndex": player_index,
        "hp": hp,
        "maxHp": max_hp,
        "appearThisTurn": appear_this_turn,
        "energies": energies,
        "energyCards": energy_cards,
        "tools": tool_cards,
        "preEvolution": pre_evolution_cards,
    }


def _tool_hp_bonus(tool_card_id: int) -> int:
    if tool_card_id == CARD_HEROS_CAPE:
        return 100
    return 0


def _stadium_hp_modifier(metadata: NativeCardMetadata, stadium_card_id: int | None) -> int:
    if stadium_card_id == CARD_GRAVITY_MOUNTAIN and metadata.stage2:
        return -30
    return 0


def build_native_core(
    *,
    build_dir: Path | str = DEFAULT_BUILD_DIR,
    force: bool = False,
    compiler: str | None = None,
) -> Path:
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    library_name = "ptcg_native.dll" if os.name == "nt" else "libptcg_native.so"
    output_path = build_dir / library_name
    newest_input_mtime = max(path.stat().st_mtime for path in NATIVE_BUILD_INPUTS)
    if output_path.exists() and not force and output_path.stat().st_mtime >= newest_input_mtime:
        return output_path

    selected_compiler = compiler or shutil.which("gcc")
    if selected_compiler is None:
        raise NativeCoreError("gcc was not found on PATH; cannot build native core")

    completed = _compile_native_core(selected_compiler, output_path)
    if completed.returncode != 0 and _is_locked_windows_output(completed, output_path):
        output_path = build_dir / f"ptcg_native_{os.getpid()}_{time.time_ns()}.dll"
        completed = _compile_native_core(selected_compiler, output_path)
    if completed.returncode != 0:
        details = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        raise NativeCoreError(f"native core build failed with exit code {completed.returncode}\n{details}")
    return output_path


def _compile_native_core(compiler: str, output_path: Path) -> subprocess.CompletedProcess[str]:
    command = [
        compiler,
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-shared",
        "-o",
        str(output_path),
        str(SOURCE_PATH),
    ]
    if os.name != "nt":
        command.insert(5, "-fPIC")

    return subprocess.run(command, capture_output=True, text=True, check=False)


def _is_locked_windows_output(completed: subprocess.CompletedProcess[str], output_path: Path) -> bool:
    if os.name != "nt" or completed.returncode == 0 or not output_path.exists():
        return False
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    return "permission denied" in output and "cannot open output file" in output
