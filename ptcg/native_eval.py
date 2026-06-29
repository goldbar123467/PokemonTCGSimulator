from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import importlib.util
import os
from pathlib import Path
import random
import sys
import types


@dataclass(frozen=True)
class NativeAgentSmokeResult:
    games: int
    finished: int
    wins: int
    losses: int
    draws: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class NativeAgentTraceResult(NativeAgentSmokeResult):
    traces: tuple[dict, ...]


@contextmanager
def _pushd(path: Path):
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def _load_agent(main_path: Path, module_prefix: str):
    module_name = f"{module_prefix}_{abs(hash(main_path))}"
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {main_path}")
    module = importlib.util.module_from_spec(spec)
    with _pushd(main_path.parent):
        spec.loader.exec_module(module)
    _install_deterministic_time(module)
    if not hasattr(module, "agent"):
        raise AttributeError(f"{main_path} does not define agent(obs_dict)")
    return module.agent


class _DeterministicClock:
    def __init__(self, step: float) -> None:
        self.current = 0.0
        self.step = step

    def time(self) -> float:
        self.current += self.step
        return self.current


def _install_deterministic_time(module) -> None:
    if os.environ.get("PTCG_DETERMINISTIC_AGENT_TIME") not in {"1", "true", "True", "yes", "YES"}:
        return
    time_module = getattr(module, "time", None)
    if time_module is None or not hasattr(time_module, "time"):
        return
    try:
        step = float(os.environ.get("PTCG_DETERMINISTIC_AGENT_TIME_STEP", "0.01"))
    except ValueError:
        step = 0.01
    step = max(step, 1e-6)
    proxy = types.SimpleNamespace()
    for name in dir(time_module):
        setattr(proxy, name, getattr(time_module, name))
    proxy.time = _DeterministicClock(step).time
    setattr(module, "time", proxy)


def _seed_runtime(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np
    except Exception:
        return
    np.random.seed(seed % (2**32 - 1))


def _zone_cards(player: dict, zone: str) -> list[dict]:
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


def _card_summary(card: dict | None) -> dict | None:
    if not isinstance(card, dict):
        return None
    return {
        "id": card.get("id"),
        "hp": card.get("hp"),
        "maxHp": card.get("maxHp"),
        "energies": _energy_count(card),
    }


def _player_summary(player: dict) -> dict:
    active = _zone_cards(player, "active")
    bench = _zone_cards(player, "bench")
    return {
        "active": _card_summary(active[0]) if active else None,
        "bench": [_card_summary(card) for card in bench],
        "bench_count": len(bench),
        "powered_board": sum(1 for card in active + bench if _energy_count(card) > 0),
        "deck_count": player.get("deckCount"),
        "hand_count": player.get("handCount"),
        "prizes_left": len(player.get("prize") or []),
        "discard_count": len(player.get("discard") or []),
    }


def _card_from_option_area(players: list[dict], area: object, player_index: object, index: object) -> dict | None:
    area_map = {
        1: "deck",
        2: "hand",
        3: "discard",
        4: "active",
        5: "bench",
        6: "prize",
        12: "looking",
    }
    if isinstance(area, int):
        area = area_map.get(area)
    if not isinstance(area, str) or not isinstance(index, int):
        return None
    try:
        selected_player = players[int(player_index)] if player_index is not None else None
    except (TypeError, ValueError, IndexError):
        selected_player = None

    if area in {"active", "bench", "hand", "discard", "prize", "looking", "lostZone"} and selected_player is not None:
        cards = _zone_cards(selected_player, area)
        return cards[index] if 0 <= index < len(cards) else None
    return None


def _in_play_card(players: list[dict], player_index: object, in_play_area: object, in_play_index: object) -> dict | None:
    area_map = {
        4: "active",
        5: "bench",
    }
    if isinstance(in_play_area, int):
        in_play_area = area_map.get(in_play_area)
    if not isinstance(in_play_area, str) or not isinstance(in_play_index, int):
        return None
    try:
        selected_player = players[int(player_index)]
    except (TypeError, ValueError, IndexError):
        return None
    cards = _zone_cards(selected_player, in_play_area)
    return cards[in_play_index] if 0 <= in_play_index < len(cards) else None


def _option_summary(players: list[dict], option: dict, index: int, selected: set[int], your_index: int) -> dict:
    player_index = option.get("playerIndex")
    if player_index is None:
        player_index = option.get("targetPlayerIndex")
    if player_index is None:
        player_index = option.get("inPlayPlayerIndex")
    if player_index is None:
        player_index = your_index
    source_area = option.get("area")
    source_index = option.get("index")
    if option.get("type") == 7 and source_area is None:
        source_area = 2
    return {
        "index": index,
        "selected": index in selected,
        "type": option.get("type"),
        "context": option.get("context"),
        "cardId": option.get("cardId"),
        "attackId": option.get("attackId"),
        "area": option.get("area"),
        "area_index": option.get("index"),
        "playerIndex": option.get("playerIndex"),
        "targetPlayerIndex": option.get("targetPlayerIndex"),
        "inPlayArea": option.get("inPlayArea"),
        "inPlayIndex": option.get("inPlayIndex"),
        "source_card": _card_summary(
            _card_from_option_area(players, source_area, player_index, source_index)
        ),
        "target_card": _card_summary(
            _in_play_card(players, player_index, option.get("inPlayArea"), option.get("inPlayIndex"))
        ),
    }


def _trace_step(obs: dict, action: list[int] | None, actor: str) -> dict:
    current = obs.get("current") or {}
    players = current.get("players") or [{}, {}]
    if len(players) < 2:
        players = [{}, {}]
    your = int(current.get("yourIndex") or 0)
    select = obs.get("select") or {}
    options = select.get("option") or []
    selected = set(action or [])
    return {
        "turn": current.get("turn"),
        "turn_action_count": current.get("turnActionCount"),
        "your_index": your,
        "actor": actor,
        "result": current.get("result"),
        "select_context": select.get("context"),
        "select_type": select.get("type"),
        "option_count": len(options) if isinstance(options, list) else None,
        "action": action,
        "options": [
            _option_summary(players, option, index, selected, your)
            for index, option in enumerate(options)
            if isinstance(option, dict)
        ]
        if isinstance(options, list)
        else [],
        "us": _player_summary(players[your] or {}),
        "them": _player_summary(players[1 - your] or {}),
    }


def smoke_native_agent_vs_random(
    *,
    main_path: Path,
    deck_path: Path,
    sdk_path: Path = Path("data/official"),
    games: int = 10,
    seed: int = 1,
    max_steps: int = 1000,
) -> NativeAgentSmokeResult:
    sdk = str(sdk_path.resolve())
    if sdk not in sys.path:
        sys.path.insert(0, sdk)

    game_module = importlib.import_module("cg.game")
    api_module = importlib.import_module("cg.api")
    battle_start = game_module.battle_start
    battle_select = game_module.battle_select
    battle_finish = game_module.battle_finish
    to_observation_class = api_module.to_observation_class

    deck = [int(line) for line in deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    agent = _load_agent(main_path, "ptcg_native_agent")
    rng = random.Random(seed)
    finished = 0
    wins = 0
    losses = 0
    draws = 0
    errors: list[str] = []

    def random_agent(obs_dict):
        obs = to_observation_class(obs_dict)
        if obs.select is None:
            return deck
        return rng.sample(range(len(obs.select.option)), obs.select.maxCount)

    for game_index in range(games):
        obs = None
        try:
            _seed_runtime(seed + game_index)
            agent_first = game_index % 2 == 0
            deck0 = deck
            deck1 = deck
            obs, start_data = battle_start(deck0, deck1)
            if obs is None:
                errors.append(f"battle_start_failed:{start_data.errorPlayer}:{start_data.errorType}")
                continue
            for _ in range(max_steps):
                obs_class = to_observation_class(obs)
                result = obs_class.current.result
                if result >= 0:
                    finished += 1
                    agent_index = 0 if agent_first else 1
                    if result == 2:
                        draws += 1
                    elif result == agent_index:
                        wins += 1
                    else:
                        losses += 1
                    break
                active_agent_is_public = (obs_class.current.yourIndex == 0) == agent_first
                if active_agent_is_public:
                    with _pushd(main_path.parent):
                        action = agent(obs)
                else:
                    action = random_agent(obs)
                obs = battle_select(action)
            else:
                errors.append("max_steps")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}:{exc}")
        finally:
            if obs is not None:
                battle_finish()

    return NativeAgentSmokeResult(games, finished, wins, losses, draws, tuple(errors))


def smoke_native_agent_vs_agent(
    *,
    candidate_main_path: Path,
    candidate_deck_path: Path,
    opponent_main_path: Path,
    opponent_deck_path: Path,
    sdk_path: Path = Path("data/official"),
    games: int = 10,
    seed: int = 1,
    max_steps: int = 1000,
) -> NativeAgentSmokeResult:
    sdk = str(sdk_path.resolve())
    if sdk not in sys.path:
        sys.path.insert(0, sdk)

    game_module = importlib.import_module("cg.game")
    api_module = importlib.import_module("cg.api")
    battle_start = game_module.battle_start
    battle_select = game_module.battle_select
    battle_finish = game_module.battle_finish
    to_observation_class = api_module.to_observation_class

    candidate_deck = [int(line) for line in candidate_deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    opponent_deck = [int(line) for line in opponent_deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidate_agent = _load_agent(candidate_main_path, "ptcg_candidate_agent")
    opponent_agent = _load_agent(opponent_main_path, "ptcg_opponent_agent")
    rng = random.Random(seed)
    finished = 0
    wins = 0
    losses = 0
    draws = 0
    errors: list[str] = []

    for game_index in range(games):
        obs = None
        try:
            _seed_runtime(seed + game_index)
            candidate_first = game_index % 2 == 0
            deck0 = candidate_deck if candidate_first else opponent_deck
            deck1 = opponent_deck if candidate_first else candidate_deck
            obs, start_data = battle_start(deck0, deck1)
            if obs is None:
                errors.append(f"battle_start_failed:{start_data.errorPlayer}:{start_data.errorType}")
                continue
            for _ in range(max_steps):
                obs_class = to_observation_class(obs)
                result = obs_class.current.result
                if result >= 0:
                    finished += 1
                    candidate_index = 0 if candidate_first else 1
                    if result == 2:
                        draws += 1
                    elif result == candidate_index:
                        wins += 1
                    else:
                        losses += 1
                    break
                active_is_candidate = (obs_class.current.yourIndex == 0) == candidate_first
                if active_is_candidate:
                    with _pushd(candidate_main_path.parent):
                        action = candidate_agent(obs)
                else:
                    with _pushd(opponent_main_path.parent):
                        action = opponent_agent(obs)
                obs = battle_select(action)
            else:
                errors.append("max_steps")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}:{exc}")
        finally:
            if obs is not None:
                battle_finish()

    return NativeAgentSmokeResult(games, finished, wins, losses, draws, tuple(errors))


def trace_native_agent_vs_agent(
    *,
    candidate_main_path: Path,
    candidate_deck_path: Path,
    opponent_main_path: Path,
    opponent_deck_path: Path,
    sdk_path: Path = Path("data/official"),
    games: int = 2,
    seed: int = 1,
    max_steps: int = 1000,
    max_trace_steps_per_game: int = 80,
) -> NativeAgentTraceResult:
    sdk = str(sdk_path.resolve())
    if sdk not in sys.path:
        sys.path.insert(0, sdk)

    game_module = importlib.import_module("cg.game")
    api_module = importlib.import_module("cg.api")
    battle_start = game_module.battle_start
    battle_select = game_module.battle_select
    battle_finish = game_module.battle_finish
    to_observation_class = api_module.to_observation_class

    candidate_deck = [int(line) for line in candidate_deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    opponent_deck = [int(line) for line in opponent_deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidate_agent = _load_agent(candidate_main_path, "ptcg_trace_candidate_agent")
    opponent_agent = _load_agent(opponent_main_path, "ptcg_trace_opponent_agent")
    finished = 0
    wins = 0
    losses = 0
    draws = 0
    errors: list[str] = []
    traces: list[dict] = []

    for game_index in range(games):
        obs = None
        game_trace: list[dict] = []
        candidate_first = game_index % 2 == 0
        candidate_result: str | None = None
        termination: str | None = None
        try:
            _seed_runtime(seed + game_index)
            deck0 = candidate_deck if candidate_first else opponent_deck
            deck1 = opponent_deck if candidate_first else candidate_deck
            obs, start_data = battle_start(deck0, deck1)
            if obs is None:
                termination = "battle_start_failed"
                errors.append(f"battle_start_failed:{start_data.errorPlayer}:{start_data.errorType}")
                continue
            for _ in range(max_steps):
                obs_class = to_observation_class(obs)
                result = obs_class.current.result
                if result >= 0:
                    finished += 1
                    candidate_index = 0 if candidate_first else 1
                    if result == 2:
                        draws += 1
                        candidate_result = "draw"
                    elif result == candidate_index:
                        wins += 1
                        candidate_result = "win"
                    else:
                        losses += 1
                        candidate_result = "loss"
                    termination = "finished"
                    break
                active_is_candidate = (obs_class.current.yourIndex == 0) == candidate_first
                if active_is_candidate:
                    with _pushd(candidate_main_path.parent):
                        action = candidate_agent(obs)
                    if len(game_trace) < max_trace_steps_per_game:
                        game_trace.append(_trace_step(obs, action, "candidate"))
                else:
                    with _pushd(opponent_main_path.parent):
                        action = opponent_agent(obs)
                obs = battle_select(action)
            else:
                termination = "max_steps"
                errors.append("max_steps")
        except Exception as exc:
            termination = "exception"
            errors.append(f"{type(exc).__name__}:{exc}")
        finally:
            if obs is not None:
                battle_finish()
            traces.append(
                {
                    "game_index": game_index,
                    "candidate_first": candidate_first,
                    "candidate_result": candidate_result,
                    "termination": termination,
                    "steps": game_trace,
                }
            )

    return NativeAgentTraceResult(games, finished, wins, losses, draws, tuple(errors), tuple(traces))
