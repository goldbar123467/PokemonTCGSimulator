from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


CANDIDATE_MAIN = Path(
    os.environ.get(
        "LUCARIO_META_EDGE_MAIN",
        "artifacts/submission_lucario_meta_edge_cleaned/main.py",
    )
)
FRESH_WIN_REPLAYS = [
    (Path(r"C:\Users\Clark\Downloads\81919794.json"), 0),
    (Path(r"C:\Users\Clark\Downloads\81919835.json"), 1),
    (Path(r"C:\Users\Clark\Downloads\81920433.json"), 0),
]
_CANDIDATE_MODULE = None
_CANDIDATE_MAIN_MODULE = None


def _pop_candidate_runtime_modules():
    popped = {}
    for name in list(sys.modules):
        if name in {"cg", "policy_agent"} or name.startswith("cg."):
            popped[name] = sys.modules.pop(name)
    return popped


def _restore_runtime_modules(modules):
    for name, module in modules.items():
        sys.modules[name] = module


def _remove_candidate_package_path():
    package_dir = str(CANDIDATE_MAIN.parent.resolve())
    while package_dir in sys.path:
        sys.path.remove(package_dir)


def _load_candidate_module():
    global _CANDIDATE_MODULE
    if _CANDIDATE_MODULE is not None:
        return _CANDIDATE_MODULE
    previous_runtime_modules = _pop_candidate_runtime_modules()
    package_dir = str(CANDIDATE_MAIN.parent.resolve())
    sys.path.insert(0, package_dir)
    try:
        module_path = CANDIDATE_MAIN.with_name("policy_agent.py")
        if not module_path.exists():
            module_path = CANDIDATE_MAIN
        spec = importlib.util.spec_from_file_location("lucario_meta_edge_under_test", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CANDIDATE_MODULE = module
        return module
    finally:
        _remove_candidate_package_path()
        _pop_candidate_runtime_modules()
        _restore_runtime_modules(previous_runtime_modules)


def _load_candidate_main_module():
    global _CANDIDATE_MAIN_MODULE
    if _CANDIDATE_MAIN_MODULE is not None:
        return _CANDIDATE_MAIN_MODULE
    package_dir = str(CANDIDATE_MAIN.parent.resolve())
    sys.path.insert(0, package_dir)
    try:
        spec = importlib.util.spec_from_file_location("lucario_meta_edge_main_under_test", CANDIDATE_MAIN)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CANDIDATE_MAIN_MODULE = module
        return module
    finally:
        _remove_candidate_package_path()


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
) -> dict:
    data = module.card_table[card_id]
    max_hp = max_hp if max_hp is not None else data.hp
    return {
        "id": card_id,
        "serial": card_id,
        "playerIndex": player,
        "hp": hp if hp is not None else max_hp,
        "maxHp": max_hp,
        "appearThisTurn": False,
        "energies": energies or [],
        "energyCards": [_card(energy_id, player=player) for energy_id in (energy_cards or [])],
        "tools": [],
        "preEvolution": [],
    }


def _player(
    *,
    active: list[dict],
    bench: list[dict] | None = None,
    hand: list[dict] | None = None,
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
        "discard": [],
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
    your_index: int = 0,
    turn: int = 4,
    context: int | None = None,
    options: list[dict] | None = None,
    me: dict,
    opponent: dict,
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
            "deck": [],
            "contextCard": None,
            "effect": None,
        },
        "logs": [],
        "current": {
            "turn": turn,
            "turnActionCount": 0,
            "yourIndex": your_index,
            "firstPlayer": 0,
            "supporterPlayed": False,
            "stadiumPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "result": -1,
            "stadium": [],
            "looking": [],
            "players": [me, opponent] if your_index == 0 else [opponent, me],
        },
    }
    return module.to_observation_class(raw)


def _fresh_win_observations(replay_path: Path, agent_index: int):
    assert replay_path.exists(), f"missing fresh-win replay fixture: {replay_path}"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    assert replay.get("rewards", [None, None])[agent_index] == 1
    assert replay.get("info", {}).get("TeamNames", [None, None])[agent_index] == "Clark Kitchen"

    for step in replay.get("steps") or []:
        if not isinstance(step, list) or agent_index >= len(step):
            continue
        entry = step[agent_index]
        if not isinstance(entry, dict) or entry.get("status") != "ACTIVE":
            continue
        observation = entry.get("observation")
        select = observation.get("select") if isinstance(observation, dict) else None
        options = select.get("option") if isinstance(select, dict) else None
        if isinstance(options, list) and options:
            yield observation


def _assert_legal_action_shape(observation: dict, action: list[int]) -> None:
    select = observation["select"]
    option_count = len(select["option"])
    min_count = int(select.get("minCount", 0) or 0)
    max_count = int(select.get("maxCount", option_count) or option_count)

    assert isinstance(action, list)
    assert min_count <= len(action) <= max_count
    assert len(set(action)) == len(action)
    assert all(isinstance(index, int) and 0 <= index < option_count for index in action)


def test_cleaned_split_main_returns_deck_from_step0_obs():
    module = _load_candidate_main_module()

    deck = module.agent({}, None)

    assert len(deck) == 60
    assert all(isinstance(card_id, int) for card_id in deck)


def test_cleaned_split_main_raw_exec_works_from_package_dir(monkeypatch):
    source = CANDIDATE_MAIN.read_text(encoding="utf-8")
    monkeypatch.chdir(CANDIDATE_MAIN.parent)
    namespace = {"__name__": "lucario_meta_edge_raw_exec_test"}

    try:
        exec(compile(source, str(CANDIDATE_MAIN), "exec"), namespace)

        deck = namespace["agent"]({}, None)
        assert len(deck) == 60
        assert all(isinstance(card_id, int) for card_id in deck)
    finally:
        _remove_candidate_package_path()


def test_fresh_win_replay_observations_stay_executable_and_legal():
    module = _load_candidate_module()

    checked = 0
    for replay_path, agent_index in FRESH_WIN_REPLAYS:
        module.agent({})
        replay_checked = 0
        for observation in _fresh_win_observations(replay_path, agent_index):
            action = module.agent(observation, None)

            _assert_legal_action_shape(observation, action)
            checked += 1
            replay_checked += 1

        assert replay_checked >= 50

    assert checked >= 150


def test_boss_target_choice_uses_pressure_target_when_attack_plan_is_active():
    module = _load_candidate_module()
    module.plan = module.AttackPlan(target=0)
    opponent = _player(
        active=[_pokemon(module, module.C.SOLROCK, player=1)],
        bench=[
            _pokemon(module, module.C.DREEPY, player=1),
            _pokemon(module, module.C.LUNATONE, player=1),
        ],
        hand=[],
    )
    me = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])])
    obs = _obs(
        module,
        context=int(module.SelectContext.SWITCH),
        me=me,
        opponent=opponent,
        options=[
            {"type": int(module.OptionType.CARD), "area": int(module.AreaType.BENCH), "index": 0, "playerIndex": 1},
            {"type": int(module.OptionType.CARD), "area": int(module.AreaType.BENCH), "index": 1, "playerIndex": 1},
        ],
    )

    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_complete_lucario_setup_does_not_chase_hariyama_without_wall_pressure():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])],
        bench=[
            _pokemon(module, module.C.RIOLU),
            _pokemon(module, module.C.SOLROCK, energies=[6], energy_cards=[6]),
            _pokemon(module, module.C.LUNATONE),
        ],
    )
    opponent = _player(active=[_pokemon(module, module.C.SOLROCK, player=1)])
    policy = module.LucarioPolicy(_obs(module, me=me, opponent=opponent))

    assert not policy._needs_setup_piece()
    assert not policy._needs_non_rule_box_piece()


def test_crustle_axis_includes_public_alt_dwebble_crustle_ids():
    module = _load_candidate_module()
    me = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])])
    opponent = _player(active=[_pokemon(module, 533, player=1)])
    policy = module.LucarioPolicy(_obs(module, me=me, opponent=opponent))

    assert policy._opponent_has_crustle_axis()


def test_spread_bench_cap_allows_makuhita_when_crustle_wall_is_present():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6], energy_cards=[6])],
        bench=[
            _pokemon(module, module.C.RIOLU),
            _pokemon(module, module.C.SOLROCK),
            _pokemon(module, module.C.LUNATONE),
            _pokemon(module, module.C.MEGA_LUCARIO_EX),
        ],
        hand=[_card(module.C.MAKUHITA)],
    )
    opponent = _player(
        active=[_pokemon(module, module.C.DREEPY, player=1)],
        bench=[_pokemon(module, 533, player=1)],
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > 0


def test_spread_bench_cap_still_blocks_extra_makuhita_without_wall_pressure():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6], energy_cards=[6])],
        bench=[
            _pokemon(module, module.C.RIOLU),
            _pokemon(module, module.C.SOLROCK),
            _pokemon(module, module.C.LUNATONE),
            _pokemon(module, module.C.MEGA_LUCARIO_EX),
        ],
        hand=[_card(module.C.MAKUHITA)],
    )
    opponent = _player(active=[_pokemon(module, module.C.DREEPY, player=1)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) < 0


def test_spread_without_wall_blocks_early_makuhita_play():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.SOLROCK, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.LUNATONE), _pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.MAKUHITA)],
    )
    opponent = _player(active=[_pokemon(module, module.C.DREEPY, player=1)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) < 0


def test_optional_search_skips_makuhita_into_spread_without_wall():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.SOLROCK, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.LUNATONE), _pokemon(module, module.C.RIOLU)],
        hand=[],
    )
    opponent = _player(active=[_pokemon(module, module.C.DREEPY, player=1)])
    raw = {
        "select": {
            "type": 1,
            "context": int(module.SelectContext.TO_HAND),
            "minCount": 0,
            "maxCount": 1,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": [
                {
                    "type": int(module.OptionType.CARD),
                    "area": int(module.AreaType.LOOKING),
                    "index": 0,
                    "playerIndex": 0,
                }
            ],
            "deck": [],
            "contextCard": None,
            "effect": _card(module.C.DUSK_BALL),
        },
        "logs": [],
        "current": {
            "turn": 1,
            "turnActionCount": 3,
            "yourIndex": 0,
            "firstPlayer": 0,
            "supporterPlayed": False,
            "stadiumPlayed": False,
            "energyAttached": True,
            "retreated": False,
            "result": -1,
            "stadium": [],
            "looking": [_card(module.C.MAKUHITA)],
            "players": [me, opponent],
        },
    }

    assert module.LucarioPolicy(module.to_observation_class(raw)).choose() == []


def test_defensive_energy_discard_selection_prefers_mist_or_rock_fighting():
    module = _load_candidate_module()
    opponent_active = _pokemon(
        module,
        module.C.HOPS_TREVENANT,
        player=1,
        energies=[6, 6],
        energy_cards=[module.C.BASIC_FIGHTING_ENERGY, 11],
    )
    me = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])])
    opponent = _player(active=[opponent_active])
    obs = _obs(
        module,
        context=int(module.SelectContext.DISCARD_ENERGY_CARD),
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.ENERGY_CARD),
                "area": int(module.AreaType.ACTIVE),
                "index": 0,
                "playerIndex": 1,
                "energyIndex": 0,
            },
            {
                "type": int(module.OptionType.ENERGY_CARD),
                "area": int(module.AreaType.ACTIVE),
                "index": 0,
                "playerIndex": 1,
                "energyIndex": 1,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[1]) > policy._score_option(obs.select.option[0])


def test_mirror_delays_naked_bench_mega_when_stable_active_faces_hariyama_gust():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=440, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[
            _pokemon(module, module.C.LUNATONE),
            _pokemon(module, module.C.RIOLU),
        ],
        hand=[_card(module.C.MEGA_LUCARIO_EX)],
    )
    opponent = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, hp=370, max_hp=440, energies=[6, 6], energy_cards=[6, 6])],
        bench=[_pokemon(module, module.C.MAKUHITA, player=1, energies=[6], energy_cards=[6])],
        prize_count=5,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.EVOLVE),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 1,
            },
            {"type": int(module.OptionType.ATTACK), "attackId": 982},
        ],
    )
    policy = module.LucarioPolicy(obs)
    policy._plan_attack()

    assert policy._score_option(obs.select.option[0]) < 0
    assert policy._score_option(obs.select.option[1]) > policy._score_option(obs.select.option[0])


def test_mirror_allows_bench_mega_when_active_is_not_stable():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=200, max_hp=440, energies=[6, 6], energy_cards=[6, 6])],
        bench=[
            _pokemon(module, module.C.LUNATONE),
            _pokemon(module, module.C.RIOLU),
        ],
        hand=[_card(module.C.MEGA_LUCARIO_EX)],
    )
    opponent = _player(
        active=[_pokemon(module, module.C.HARIYAMA, player=1, hp=80, energies=[6, 6, 6], energy_cards=[6, 6, 6])],
        bench=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, energies=[6, 6], energy_cards=[6, 6])],
        prize_count=2,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.EVOLVE),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 1,
            },
            {"type": int(module.OptionType.ATTACK), "attackId": module.MEGA_BRAVE},
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > 0


def test_mirror_prefers_bench_riolu_energy_once_active_lucario_can_attack():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=420, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.BASIC_FIGHTING_ENERGY), _card(module.C.MEGA_LUCARIO_EX)],
    )
    opponent = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, energies=[6, 6], energy_cards=[6, 6])],
        bench=[_pokemon(module, module.C.RIOLU, player=1, energies=[6], energy_cards=[6])],
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)
    policy._plan_attack()

    assert policy._needs_backup_attacker()
    assert policy._score_option(obs.select.option[1]) > policy._score_option(obs.select.option[0])


def test_primary_lucario_energy_still_wins_when_active_cannot_attack_yet():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=420, max_hp=440)],
        bench=[_pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.BASIC_FIGHTING_ENERGY), _card(module.C.MEGA_LUCARIO_EX)],
    )
    opponent = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, energies=[6], energy_cards=[6])])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert not policy._needs_backup_attacker()
    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_crustle_alt_blocks_lucario_damage_in_attack_plan():
    module = _load_candidate_module()
    me = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])])
    opponent = _player(active=[_pokemon(module, module.C.CRUSTLE_ALT, player=1, hp=120, max_hp=120)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.ATTACK), "attackId": module.MEGA_BRAVE}],
    )
    policy = module.LucarioPolicy(obs)
    policy._plan_attack()

    assert module.plan.remain_hp == 120


def test_single_staryu_does_not_force_backup_parity_but_double_starmie_does():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=420, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.BASIC_FIGHTING_ENERGY), _card(module.C.MEGA_LUCARIO_EX)],
    )
    one_staryu = _player(active=[_pokemon(module, module.C.STARYU, player=1)])
    single_policy = module.LucarioPolicy(_obs(module, me=me, opponent=one_staryu))

    assert not single_policy._needs_backup_attacker()

    two_starmie = _player(
        active=[_pokemon(module, module.C.MEGA_STARMIE_EX, player=1, energies=[3], energy_cards=[3])],
        bench=[_pokemon(module, module.C.MEGA_STARMIE_EX, player=1, energies=[3], energy_cards=[3])],
    )
    double_policy = module.LucarioPolicy(_obs(module, me=me, opponent=two_starmie))

    assert double_policy._needs_backup_attacker()


def test_final_prize_active_ko_attacks_instead_of_bossing_bulkier_bench():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])],
        hand=[_card(module.C.BOSS_ORDERS)],
        prize_count=1,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.HARIYAMA, player=1, hp=80, max_hp=210)],
        bench=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, hp=440, max_hp=440, energies=[6], energy_cards=[6])],
        prize_count=3,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {"type": int(module.OptionType.PLAY), "index": 0},
            {"type": int(module.OptionType.ATTACK), "attackId": module.MEGA_BRAVE},
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert policy.choose() == [1]


def test_crustle_window_evolves_hariyama_before_lunatone_ability():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])],
        bench=[
            _pokemon(module, module.C.MAKUHITA, energies=[6, 6], energy_cards=[6, 6]),
            _pokemon(module, module.C.LUNATONE),
        ],
        hand=[_card(module.C.HARIYAMA)],
    )
    opponent = _player(active=[_pokemon(module, module.C.CRUSTLE, player=1, hp=120, max_hp=120)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.EVOLVE),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ABILITY),
                "area": int(module.AreaType.BENCH),
                "index": 1,
                "playerIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_mirror_backup_riolu_evolves_before_lunatone_ability():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6], energy_cards=[6])],
        bench=[
            _pokemon(module, module.C.RIOLU, energies=[6], energy_cards=[6]),
            _pokemon(module, module.C.LUNATONE),
        ],
        hand=[_card(module.C.MEGA_LUCARIO_EX)],
    )
    opponent = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, energies=[6, 6], energy_cards=[6, 6])],
        prize_count=2,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.EVOLVE),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ABILITY),
                "area": int(module.AreaType.BENCH),
                "index": 1,
                "playerIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_one_prize_danger_damaged_active_ex_pushes_energy_to_backup():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=300, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.MEGA_LUCARIO_EX)],
        hand=[_card(module.C.BASIC_FIGHTING_ENERGY)],
        prize_count=3,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, player=1, hp=440, max_hp=440, energies=[6, 6], energy_cards=[6, 6])],
        prize_count=1,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)
    policy._plan_attack()

    assert policy._needs_backup_attacker()
    assert policy._score_option(obs.select.option[1]) > policy._score_option(obs.select.option[0])


def test_twelve_card_deck_does_not_blanket_suppress_lillie_draw():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])],
        hand=[_card(module.C.LILLIE_DETERMINATION)],
        hand_count=4,
        deck_count=12,
    )
    opponent = _player(active=[_pokemon(module, module.C.SOLROCK, player=1)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.LucarioPolicy(obs)

    assert not policy._low_deck()
    assert policy._score_option(obs.select.option[0]) > 0


def test_true_low_deck_suppresses_optional_lillie_draw():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6, 6], energy_cards=[6, 6])],
        hand=[_card(module.C.LILLIE_DETERMINATION)],
        hand_count=4,
        deck_count=9,
    )
    opponent = _player(active=[_pokemon(module, module.C.SOLROCK, player=1)])
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._low_deck()
    assert policy._score_option(obs.select.option[0]) < 0


def test_iono_engine_marks_loaded_voltorb_as_return_ko_threat():
    module = _load_candidate_module()
    me = _player(active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, energies=[6], energy_cards=[6])])
    opponent = _player(
        active=[_pokemon(module, module.C.IONO_VOLTORB, player=1, energies=[4, 4], energy_cards=[4, 4])],
        bench=[_pokemon(module, module.C.IONO_BELLIBOLT_EX, player=1, energies=[4, 4, 4, 4], energy_cards=[4, 4, 4, 4])],
    )
    policy = module.LucarioPolicy(_obs(module, me=me, opponent=opponent))

    assert policy._opponent_is_iono_engine()
    assert policy._opponent_threatens_attack(policy.opponent.active[0])


def test_iono_pressure_prefers_backup_riolu_when_active_lucario_already_attacks():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=340, max_hp=440, energies=[6, 6], energy_cards=[6, 6])],
        bench=[_pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.BASIC_FIGHTING_ENERGY), _card(module.C.MEGA_LUCARIO_EX)],
        prize_count=5,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.IONO_VOLTORB, player=1, energies=[4, 4], energy_cards=[4, 4])],
        bench=[_pokemon(module, module.C.IONO_BELLIBOLT_EX, player=1, energies=[4, 4, 4, 4], energy_cards=[4, 4, 4, 4])],
        prize_count=1,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)
    policy._plan_attack()

    assert policy._needs_backup_attacker()
    assert policy._score_option(obs.select.option[1]) > policy._score_option(obs.select.option[0])


def test_active_energy_still_wins_when_it_unlocks_bellibolt_tempo_ko():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=340, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.BASIC_FIGHTING_ENERGY), _card(module.C.BOSS_ORDERS)],
        prize_count=5,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.IONO_VOLTORB, player=1, energies=[4, 4], energy_cards=[4, 4])],
        bench=[_pokemon(module, module.C.IONO_BELLIBOLT_EX, player=1, hp=280, max_hp=280, energies=[4, 4, 4, 4], energy_cards=[4, 4, 4, 4])],
        prize_count=4,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.ACTIVE),
                "inPlayIndex": 0,
            },
            {
                "type": int(module.OptionType.ATTACH),
                "area": int(module.AreaType.HAND),
                "index": 0,
                "inPlayArea": int(module.AreaType.BENCH),
                "inPlayIndex": 0,
            },
            {"type": int(module.OptionType.PLAY), "index": 1},
            {"type": int(module.OptionType.ATTACK), "attackId": module.MEGA_BRAVE},
        ],
    )
    policy = module.LucarioPolicy(obs)
    policy._plan_attack()

    assert module.plan.attacker == 0
    assert module.plan.needs_energy
    assert module.plan.target == 1
    assert policy._score_option(obs.select.option[0]) > policy._score_option(obs.select.option[1])


def test_closeout_pressure_allows_extra_riolu_even_with_two_lucario_line_bodies():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=200, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[_pokemon(module, module.C.RIOLU)],
        hand=[_card(module.C.RIOLU)],
        prize_count=3,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.IONO_VOLTORB, player=1, energies=[4, 4], energy_cards=[4, 4])],
        bench=[_pokemon(module, module.C.IONO_BELLIBOLT_EX, player=1, energies=[4, 4, 4, 4], energy_cards=[4, 4, 4, 4])],
        prize_count=1,
    )
    obs = _obs(
        module,
        me=me,
        opponent=opponent,
        options=[{"type": int(module.OptionType.PLAY), "index": 0}],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) > 0


def test_iono_closeout_attach_from_suppresses_makuhita_when_lucario_target_exists():
    module = _load_candidate_module()
    me = _player(
        active=[_pokemon(module, module.C.MEGA_LUCARIO_EX, hp=340, max_hp=440, energies=[6], energy_cards=[6])],
        bench=[
            _pokemon(module, module.C.MAKUHITA),
            _pokemon(module, module.C.RIOLU),
        ],
        prize_count=3,
    )
    opponent = _player(
        active=[_pokemon(module, module.C.IONO_VOLTORB, player=1, energies=[4, 4], energy_cards=[4, 4])],
        bench=[_pokemon(module, module.C.IONO_BELLIBOLT_EX, player=1, energies=[4, 4, 4, 4], energy_cards=[4, 4, 4, 4])],
        prize_count=1,
    )
    obs = _obs(
        module,
        context=int(module.SelectContext.ATTACH_FROM),
        me=me,
        opponent=opponent,
        options=[
            {
                "type": int(module.OptionType.CARD),
                "area": int(module.AreaType.BENCH),
                "index": 0,
                "playerIndex": 0,
            },
            {
                "type": int(module.OptionType.CARD),
                "area": int(module.AreaType.BENCH),
                "index": 1,
                "playerIndex": 0,
            },
        ],
    )
    policy = module.LucarioPolicy(obs)

    assert policy._score_option(obs.select.option[0]) < 0
    assert policy._score_option(obs.select.option[1]) > 0
