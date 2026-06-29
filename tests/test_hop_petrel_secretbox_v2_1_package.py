from __future__ import annotations

from collections import Counter
import importlib.util
import sys
import tarfile
from pathlib import Path

from ptcg.kaggle_archive_validator import validate_archive_startup


CANDIDATE_DIR = Path("artifacts/hop_petrel_secretbox_v2_1")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = CANDIDATE_DIR / "hop_petrel_secretbox_v2_1.tar.gz"
_CANDIDATE_MODULE = None

TARGET_COUNTS = Counter(
    {
        1219: 4,  # Team Rocket's Petrel
        1227: 4,  # Lillie's Determination
        1122: 4,  # Pokegear 3.0
        1152: 2,  # Poke Pad
        1182: 2,  # Boss's Orders
        1097: 1,  # Night Stretcher
        11: 4,  # Mist Energy
        878: 4,  # Hop's Phantump
        19: 4,  # Telepath Psychic Energy
        1171: 4,  # Hop's Choice Band
        1255: 4,  # Postwick
        879: 4,  # Hop's Trevenant
        1115: 4,  # Hop's Bag
        311: 3,  # Hop's Cramorant
        304: 2,  # Hop's Snorlax
        1092: 1,  # Secret Box
        1197: 2,  # Xerosic's Machinations
        1134: 4,  # Team Rocket's Transceiver
        1225: 3,  # Hilda
    }
)


def _pop_candidate_runtime_modules() -> dict[str, object]:
    popped = {}
    for name in list(sys.modules):
        if name == "cg" or name.startswith("cg."):
            popped[name] = sys.modules.pop(name)
    return popped


def _restore_modules(modules: dict[str, object]) -> None:
    for name, module in modules.items():
        sys.modules[name] = module


def _load_candidate_module():
    global _CANDIDATE_MODULE
    if _CANDIDATE_MODULE is not None:
        return _CANDIDATE_MODULE
    assert CANDIDATE_MAIN.exists(), f"missing candidate main: {CANDIDATE_MAIN}"
    previous = _pop_candidate_runtime_modules()
    package_dir = str(CANDIDATE_DIR.resolve())
    sys.path.insert(0, package_dir)
    try:
        spec = importlib.util.spec_from_file_location("hop_petrel_secretbox_v2_1_under_test", CANDIDATE_MAIN)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CANDIDATE_MODULE = module
        return module
    finally:
        while package_dir in sys.path:
            sys.path.remove(package_dir)
        _pop_candidate_runtime_modules()
        _restore_modules(previous)


def _card(card_id: int, *, player: int = 0, serial: int | None = None) -> dict:
    return {"id": card_id, "serial": serial or card_id, "playerIndex": player}


def _pokemon(
    module,
    card_id: int,
    *,
    player: int = 0,
    hp: int | None = None,
    max_hp: int | None = None,
    energies: list[int] | None = None,
    energy_cards: list[int] | None = None,
    tools: list[int] | None = None,
    serial: int | None = None,
) -> dict:
    data = module.CARD_TABLE[card_id]
    max_hp = max_hp if max_hp is not None else data.hp
    return {
        "id": card_id,
        "serial": serial or card_id,
        "playerIndex": player,
        "hp": hp if hp is not None else max_hp,
        "maxHp": max_hp,
        "appearThisTurn": False,
        "energies": energies or [],
        "energyCards": [_card(energy_id, player=player) for energy_id in (energy_cards or [])],
        "tools": [_card(tool_id, player=player) for tool_id in (tools or [])],
        "preEvolution": [],
    }


def _player(
    *,
    active: list[dict],
    bench: list[dict] | None = None,
    hand: list[dict] | None = None,
    discard: list[dict] | None = None,
    hand_count: int | None = None,
    deck_count: int = 35,
    prize_count: int = 6,
) -> dict:
    hand = hand or []
    return {
        "active": active,
        "bench": bench or [],
        "benchMax": 5,
        "deckCount": deck_count,
        "discard": discard or [],
        "prize": [None] * prize_count,
        "handCount": len(hand) if hand_count is None else hand_count,
        "hand": hand,
        "poisoned": False,
        "burned": False,
        "asleep": False,
        "paralyzed": False,
        "confused": False,
    }


def _obs(
    module,
    *,
    turn: int = 4,
    context: int | None = None,
    options: list[dict] | None = None,
    me: dict,
    opponent: dict,
    stadium: list[dict] | None = None,
    looking: list[dict] | None = None,
    deck: list[dict] | None = None,
    supporter_played: bool = False,
) -> object:
    context = int(module.SelectContext.MAIN if context is None else context)
    raw = {
        "select": {
            "type": 0,
            "context": context,
            "minCount": 1,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": options or [],
            "deck": deck or [],
            "contextCard": None,
            "effect": None,
        },
        "logs": [],
        "current": {
            "turn": turn,
            "turnActionCount": 0,
            "yourIndex": 0,
            "firstPlayer": 0,
            "supporterPlayed": supporter_played,
            "stadiumPlayed": bool(stadium),
            "energyAttached": False,
            "retreated": False,
            "result": -1,
            "stadium": stadium or [],
            "looking": looking or [],
            "players": [me, opponent],
        },
    }
    return module.to_observation_class(raw)


def test_deck_csv_and_step0_agent_return_exact_petrel_secret_box_shell() -> None:
    module = _load_candidate_module()

    deck_csv = [int(line) for line in (CANDIDATE_DIR / "deck.csv").read_text().splitlines() if line.strip()]

    assert len(deck_csv) == 60
    assert Counter(deck_csv) == TARGET_COUNTS
    assert module.agent({}, None) == deck_csv


def test_candidate_has_kaggle_bundle_shape_and_validates_raw_exec_startup() -> None:
    assert (CANDIDATE_DIR / "main.py").exists()
    assert (CANDIDATE_DIR / "deck.csv").exists()
    assert (CANDIDATE_DIR / "cg" / "api.py").exists()
    assert CANDIDATE_ARCHIVE.exists()

    with tarfile.open(CANDIDATE_ARCHIVE, "r:gz") as tf:
        members = {member.name.replace("\\", "/").lstrip("./") for member in tf.getmembers()}

    assert {"main.py", "deck.csv", "cg/api.py"}.issubset(members)
    result = validate_archive_startup(CANDIDATE_ARCHIVE)
    assert result["deck_len"] == 60
    assert result["strict_raw_exec_without_file_or_syspath"] is True


def test_secret_box_is_prioritized_over_generic_lillie_when_setup_package_is_missing() -> None:
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.PHANTUMP)],
        bench=[],
        hand=[
            _card(module.C.SECRET_BOX),
            _card(module.C.LILLIES_DETERMINATION),
            _card(module.C.HOPS_BAG),
            _card(module.C.POKEGEAR),
            _card(module.C.TEAM_ROCKET_TRANSCEIVER),
        ],
        hand_count=6,
    )
    opponent = _player(active=[_pokemon(module, module.C.DREEPY, player=1)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {"type": int(module.OptionType.PLAY), "index": 0},
            {"type": int(module.OptionType.PLAY), "index": 1},
        ],
    )
    policy = module.HopTrevenantPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_transceiver_petrel_chain_beats_pokegear_when_setup_is_unsolved() -> None:
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.PHANTUMP)],
        hand=[_card(module.C.TEAM_ROCKET_TRANSCEIVER), _card(module.C.POKEGEAR)],
        hand_count=4,
    )
    opponent = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, energies=[6], energy_cards=[6])])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {"type": int(module.OptionType.PLAY), "index": 0},
            {"type": int(module.OptionType.PLAY), "index": 1},
        ],
    )
    policy = module.HopTrevenantPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_xerosic_is_high_priority_when_behind_and_opponent_has_large_hand() -> None:
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.TREVENANT, energies=[5, 0], energy_cards=[module.C.TELEPATH_PSYCHIC, module.C.MIST_ENERGY])],
        bench=[_pokemon(module, module.C.PHANTUMP, energies=[5], energy_cards=[module.C.TELEPATH_PSYCHIC])],
        hand=[_card(module.C.XEROSICS_MACHINATIONS), _card(module.C.LILLIES_DETERMINATION)],
        hand_count=4,
        prize_count=5,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.ALAKAZAM, player=1, energies=[5, 5], energy_cards=[5, 5])],
        bench=[_pokemon(module, module.C.ABRA, player=1), _pokemon(module, module.C.KADABRA, player=1)],
        hand_count=13,
        prize_count=2,
    )
    obs = _obs(
        module,
        turn=8,
        me=me,
        opponent=opponent,
        options=[
            {"type": int(module.OptionType.PLAY), "index": 0},
            {"type": int(module.OptionType.PLAY), "index": 1},
        ],
    )
    policy = module.HopTrevenantPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_cramorant_is_a_real_hop_backup_and_choice_band_target() -> None:
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.TREVENANT, energies=[5, 0], energy_cards=[module.C.TELEPATH_PSYCHIC, module.C.MIST_ENERGY])],
        bench=[],
        hand=[_card(module.C.CRAMORANT), _card(module.C.HOPS_CHOICE_BAND)],
    )
    opponent = _player(active=[_pokemon(module, module.C.DREEPY, player=1)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.HopTrevenantPolicy(obs)

    assert module.C.CRAMORANT in module.HOP_POKEMON
    assert module.C.CRAMORANT in module.PRIMARY_ATTACKERS
    assert policy._score_option(obs.select.option[0]) > 0
    assert policy._target_attach_score(_pokemon_object(module, module.C.CRAMORANT), False, module.C.HOPS_CHOICE_BAND) > 0


def _pokemon_object(module, card_id: int):
    raw = _pokemon(module, card_id)
    me = _player(active=[raw])
    opponent = _player(active=[_pokemon(module, module.C.DREEPY, player=1)])
    return _obs(module, me=me, opponent=opponent).current.players[0].active[0]


def test_cramorant_attack_is_only_pushed_when_fickle_spitting_prize_window_is_open() -> None:
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.CRAMORANT, energies=[0], energy_cards=[module.C.MIST_ENERGY])],
        bench=[_pokemon(module, module.C.PHANTUMP)],
    )
    open_window = _player(active=[_pokemon(module, module.C.DREEPY, player=1)], prize_count=3)
    closed_window = _player(active=[_pokemon(module, module.C.DREEPY, player=1)], prize_count=5)
    option = {"type": int(module.OptionType.ATTACK), "attackId": module.FICKLE_SPITTING}
    open_policy = module.HopTrevenantPolicy(_obs(module, me=me, opponent=open_window, options=[option]))
    closed_policy = module.HopTrevenantPolicy(_obs(module, me=me, opponent=closed_window, options=[option]))

    assert open_policy._score_attack(open_policy.obs.select.option[0]) > closed_policy._score_attack(closed_policy.obs.select.option[0]) + 1500
