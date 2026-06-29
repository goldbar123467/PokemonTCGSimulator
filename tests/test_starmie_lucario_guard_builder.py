from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

from scripts.build_starmie_lucario_guard_candidates import (
    SOURCE_DIR,
    build_lucario_energy_guard_candidate,
    build_lucario_guard_candidate,
    build_lucario_guard_policy_candidate,
)


def _card(card_id: int, serial: int = 1, player_index: int = 0) -> dict:
    return {"id": card_id, "serial": serial, "playerIndex": player_index}


def _pokemon(
    card_id: int,
    *,
    hp: int,
    max_hp: int,
    energies: list[int] | None = None,
    serial: int = 1,
    player_index: int = 0,
) -> dict:
    energies = list(energies or [])
    return {
        "id": card_id,
        "serial": serial,
        "hp": hp,
        "maxHp": max_hp,
        "appearThisTurn": False,
        "energies": energies,
        "energyCards": [_card(energy_id, serial + 100 + index, player_index) for index, energy_id in enumerate(energies)],
        "tools": [],
        "preEvolution": [],
    }


def _player(
    *,
    active: list[dict],
    bench: list[dict] | None = None,
    hand: list[dict] | None = None,
    hand_count: int | None = None,
    deck_count: int = 40,
    prizes_left: int = 6,
) -> dict:
    return {
        "active": active,
        "bench": list(bench or []),
        "benchMax": 5,
        "deckCount": deck_count,
        "discard": [],
        "prize": [None] * prizes_left,
        "handCount": len(hand or []) if hand_count is None else hand_count,
        "hand": hand,
        "poisoned": False,
        "burned": False,
        "asleep": False,
        "paralyzed": False,
        "confused": False,
    }


def _observation(module, *, players: list[dict], options: list[dict], context: int = 0) -> dict:
    return {
        "logs": [],
        "search_begin_input": None,
        "current": {
            "turn": 2,
            "turnActionCount": 0,
            "yourIndex": 0,
            "firstPlayer": 0,
            "supporterPlayed": False,
            "stadiumPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "result": -1,
            "stadium": [],
            "looking": None,
            "players": players,
        },
        "select": {
            "type": 0,
            "context": context,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options,
            "deck": None,
            "contextCard": None,
            "effect": None,
        },
    }


def _load_module(main_path: Path):
    package_dir = str(main_path.parent)
    for name in list(sys.modules):
        if name == "cg" or name.startswith("cg."):
            sys.modules.pop(name)
    sys.path.insert(0, package_dir)
    spec = importlib.util.spec_from_file_location("starmie_lucario_guard_under_test", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        while package_dir in sys.path:
            sys.path.remove(package_dir)
    return module


def test_lucario_guard_deck_restores_full_starmie_line_and_boss_pressure(tmp_path: Path) -> None:
    candidate = build_lucario_guard_candidate(tmp_path)
    module = _load_module(candidate["main_path"])
    counts = Counter(module.agent({}, None))

    assert sum(counts.values()) == 60
    assert counts[module.C.STARYU] == 4
    assert counts[module.C.MEGA_STARMIE] == 4
    assert counts[module.C.BOSS_ORDERS] == 3
    assert counts[module.C.WALLY] == 3
    assert counts[module.C.HARLEQUIN] == 0
    assert all(count <= 4 for card_id, count in counts.items() if card_id != module.C.WATER_ENERGY)


def test_lucario_guard_policy_only_preserves_parent_deck_and_patch(tmp_path: Path) -> None:
    candidate = build_lucario_guard_policy_candidate(tmp_path)
    module = _load_module(candidate["main_path"])
    parent_deck = [int(line) for line in (SOURCE_DIR / "deck.csv").read_text(encoding="utf-8").splitlines() if line]

    assert module.agent({}, None) == parent_deck

    obs = _observation(
        module,
        players=[
            _player(
                active=[_pokemon(module.C.STARYU, hp=70, max_hp=70, serial=10)],
                hand=[_card(module.C.MEGA_SIGNAL, 20), _card(module.C.WATER_ENERGY, 21)],
                deck_count=44,
            ),
            _player(
                active=[_pokemon(677, hp=80, max_hp=80, serial=30, player_index=1)],
                hand=None,
                hand_count=7,
                deck_count=46,
            ),
        ],
        options=[
            {"type": int(module.OptionType.PLAY), "area": int(module.AreaType.HAND), "index": 0},
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 1,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
        ],
    )

    assert module.agent(obs, None) == [1]


def test_lucario_energy_guard_preserves_parent_deck_without_gust_override(tmp_path: Path) -> None:
    candidate = build_lucario_energy_guard_candidate(tmp_path)
    module = _load_module(candidate["main_path"])
    parent_deck = [int(line) for line in (SOURCE_DIR / "deck.csv").read_text(encoding="utf-8").splitlines() if line]

    assert module.agent({}, None) == parent_deck

    attach_obs = _observation(
        module,
        players=[
            _player(
                active=[_pokemon(module.C.STARYU, hp=70, max_hp=70, serial=10)],
                hand=[_card(module.C.MEGA_SIGNAL, 20), _card(module.C.WATER_ENERGY, 21)],
                deck_count=44,
            ),
            _player(
                active=[_pokemon(677, hp=80, max_hp=80, serial=30, player_index=1)],
                hand=None,
                hand_count=7,
                deck_count=46,
            ),
        ],
        options=[
            {"type": int(module.OptionType.PLAY), "area": int(module.AreaType.HAND), "index": 0},
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 1,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
        ],
    )
    assert module.agent(attach_obs, None) == [1]

    gust_obs = _observation(
        module,
        players=[
            _player(
                active=[_pokemon(module.C.MEGA_STARMIE, hp=330, max_hp=330, energies=[3], serial=10)],
                bench=[_pokemon(module.C.STARYU, hp=70, max_hp=70, serial=11)],
                hand=[],
                hand_count=4,
                deck_count=33,
            ),
            _player(
                active=[_pokemon(678, hp=340, max_hp=340, energies=[6], serial=30, player_index=1)],
                bench=[_pokemon(677, hp=80, max_hp=80, serial=31, player_index=1)],
                hand=None,
                hand_count=7,
                deck_count=35,
            ),
        ],
        context=int(module.SelectContext.TO_ACTIVE),
        options=[
            {"type": int(module.OptionType.CARD), "area": int(module.AreaType.ACTIVE), "index": 0, "playerIndex": 1},
            {"type": int(module.OptionType.CARD), "area": int(module.AreaType.BENCH), "index": 0, "playerIndex": 1},
        ],
    )
    assert module.agent(gust_obs, None) == [0]


def test_lucario_guard_attaches_before_search_churn_when_lone_staryu_faces_lucario(tmp_path: Path) -> None:
    candidate = build_lucario_guard_candidate(tmp_path)
    module = _load_module(candidate["main_path"])

    obs = _observation(
        module,
        players=[
            _player(
                active=[_pokemon(module.C.STARYU, hp=70, max_hp=70, serial=10)],
                hand=[_card(module.C.MEGA_SIGNAL, 20), _card(module.C.WATER_ENERGY, 21)],
                deck_count=44,
            ),
            _player(
                active=[_pokemon(677, hp=80, max_hp=80, serial=30, player_index=1)],
                hand=None,
                hand_count=7,
                deck_count=46,
            ),
        ],
        options=[
            {"type": int(module.OptionType.PLAY), "area": int(module.AreaType.HAND), "index": 0},
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 1,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
        ],
    )

    assert module.agent(obs, None) == [1]


def test_lucario_guard_boss_targets_riolu_before_active_lucario(tmp_path: Path) -> None:
    candidate = build_lucario_guard_candidate(tmp_path)
    module = _load_module(candidate["main_path"])

    obs = _observation(
        module,
        players=[
            _player(
                active=[_pokemon(module.C.MEGA_STARMIE, hp=330, max_hp=330, energies=[3], serial=10)],
                bench=[_pokemon(module.C.STARYU, hp=70, max_hp=70, serial=11)],
                hand=[],
                hand_count=4,
                deck_count=33,
            ),
            _player(
                active=[_pokemon(678, hp=340, max_hp=340, energies=[6], serial=30, player_index=1)],
                bench=[_pokemon(677, hp=80, max_hp=80, serial=31, player_index=1)],
                hand=None,
                hand_count=7,
                deck_count=35,
            ),
        ],
        context=int(module.SelectContext.TO_ACTIVE),
        options=[
            {"type": int(module.OptionType.CARD), "area": int(module.AreaType.ACTIVE), "index": 0, "playerIndex": 1},
            {"type": int(module.OptionType.CARD), "area": int(module.AreaType.BENCH), "index": 0, "playerIndex": 1},
        ],
    )

    assert module.agent(obs, None) == [1]


def test_lucario_guard_penalizes_attack_without_backup_into_lucario(tmp_path: Path) -> None:
    candidate = build_lucario_guard_candidate(tmp_path)
    module = _load_module(candidate["main_path"])

    obs = _observation(
        module,
        players=[
            _player(
                active=[_pokemon(module.C.CINDERACE, hp=160, max_hp=160, energies=[3], serial=10)],
                hand=[_card(module.C.WATER_ENERGY, 20)],
                deck_count=39,
            ),
            _player(
                active=[_pokemon(676, hp=60, max_hp=110, energies=[6], serial=30, player_index=1)],
                bench=[_pokemon(678, hp=340, max_hp=340, energies=[6, 6], serial=31, player_index=1)],
                hand=None,
                hand_count=7,
                deck_count=32,
                prizes_left=5,
            ),
        ],
        options=[
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
            {"type": int(module.OptionType.ATTACK), "attackId": module.TURBO_FLARE},
        ],
    )

    assert module.agent(obs, None) == [0]


def test_lucario_guard_archive_validates_startup_shape(tmp_path: Path) -> None:
    candidate = build_lucario_guard_candidate(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ptcg.kaggle_archive_validator",
            "--archive",
            str(candidate["archive_path"]),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
