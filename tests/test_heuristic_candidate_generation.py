from __future__ import annotations

import importlib.util
import inspect

from scripts.generate_family_deck_variants import _apply_variant
from scripts.generate_heuristic_candidates import _write_candidate


def _load_agent(main_path):
    module = _load_module(main_path)
    return module.agent


def _load_module(main_path):
    spec = importlib.util.spec_from_file_location("generated_candidate_under_test", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_last_callable(main_path):
    spec = importlib.util.spec_from_file_location("generated_candidate_last_callable_under_test", main_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    callables = [value for value in vars(module).values() if inspect.isfunction(value)]
    assert callables
    return callables[-1]


def test_generated_candidate_prefers_building_bench_attacker(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "target-aware smoke",
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attach": 0,
                "attach_setup": 0,
                "bench_attach": 0,
                "own_attacker_target": 100,
                "own_bench_target": 100,
                "unpowered_next_attacker": 100,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 1,
            "turnActionCount": 0,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [{"id": 666, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 40,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 40,
                },
            ],
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_last_callable_is_kaggle_agent(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "kaggle callable smoke",
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
        },
    )
    kaggle_callable = _load_last_callable(candidate["main_path"])

    assert kaggle_callable({"select": None}, None) == [666] * 60
    assert kaggle_callable.__name__ == "agent"


def test_generated_candidate_counts_duplicate_energy_fields_once(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "energy count smoke",
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
        },
    )
    module = _load_module(candidate["main_path"])

    assert module._card_energy_count({"energies": [{"id": 3}], "energyCards": [{"id": 3, "serial": 1}]}) == 1
    assert module._card_energy_count({"energies": [3, 3], "energyCards": [{"id": 3}, {"id": 3}]}) == 2
    assert module._card_energy_count({"energies": [{"id": 3}, {"id": 3}], "energyCards": []}) == 2
    assert module._energy_count(
        [
            {"energies": [{"id": 3}], "energyCards": [{"id": 3}]},
            {"energies": [{"id": 3}, {"id": 3}], "energyCards": []},
        ]
    ) == 3


def test_generated_candidate_avoids_overattaching_powered_active_without_next_attacker(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "next attacker smoke",
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attach": 0,
                "attach_setup": 0,
                "bench_attach": 0,
                "own_attacker_target": 0,
                "own_bench_target": 0,
                "unpowered_next_attacker": 0,
                "overattach_active_penalty": 200,
                "build_next_attacker_bonus": 200,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 2,
            "turnActionCount": 0,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [{"id": 666, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
            ],
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_targets_only_powered_enemy_attacker(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "single powered threat smoke",
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "card_select": 0,
                "enemy_gate_target": 0,
                "enemy_powered_target": 0,
                "enemy_bench_target": 0,
                "enemy_pressure_target": 0,
                "single_powered_target": 250,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 3,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [{"id": 666, "energies": [{"id": 3}]}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}]}],
                    "bench": [{"id": 741, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 13,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "playerIndex": 1, "area": 5, "index": 0},
                {"type": 3, "playerIndex": 1, "area": 4, "index": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_develops_empty_bench_before_attacking(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "empty bench development smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 100,
                "attack_empty_bench_penalty": 200,
                "card_select": 0,
                "card_select_setup": 0,
                "bench_development_card": 100,
                "bench_development_select": 150,
                "constructive_context": 0,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 3,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}]}],
                    "bench": [{"id": 676, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13},
                {"type": 3, "cardId": 1030},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_attaches_to_bench_when_active_is_in_danger(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "active danger bench floor smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attach": 0,
                "attach_setup": 0,
                "bench_attach": 0,
                "own_attacker_target": 0,
                "own_bench_target": 0,
                "unpowered_next_attacker": 0,
                "active_danger_attach_penalty": 180,
                "bench_floor_attach": 180,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 5,
            "turnActionCount": 0,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "hp": 50, "maxHp": 130, "energies": [{"id": 3}]}],
                    "bench": [{"id": 1030, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
                {
                    "active": [{"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}, {"id": 6}]}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_builds_bench_attacker_under_lucario_pressure(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "lucario bench energy smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attach": 0,
                "attach_setup": 0,
                "bench_attach": 0,
                "own_attacker_target": 0,
                "own_bench_target": 0,
                "unpowered_next_attacker": 0,
                "lucario_build_bench_attacker_attach": 220,
                "lucario_overfeed_active_penalty": 220,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 4,
            "turnActionCount": 0,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "hp": 120, "maxHp": 160, "energies": [{"id": 3}, {"id": 3}]}],
                    "bench": [{"id": 1030, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}]}, {"id": 676, "energies": []}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_searches_backup_when_active_is_doomed(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "doomed active backup search smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 100,
                "attack_active_danger_penalty": 200,
                "card_select": 0,
                "card_select_setup": 0,
                "bench_floor_card": 120,
                "bench_floor_select": 140,
                "constructive_context": 0,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 6,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "hp": 40, "maxHp": 130, "energies": [{"id": 3}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
                {
                    "active": [{"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}, {"id": 6}]}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13},
                {"type": 3, "cardId": 1030},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_targets_powered_lucario_bench_chain(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "lucario chain targeting smoke",
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "card_select": 0,
                "enemy_gate_target": 0,
                "enemy_powered_target": 0,
                "enemy_bench_target": 0,
                "enemy_pressure_target": 0,
                "targeting_context_gate_bonus": 0,
                "lucario_chain_target": 100,
                "lucario_bench_chain_target": 150,
                "lucario_powered_chain_target": 200,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 5,
            "turnActionCount": 2,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [{"id": 666, "energies": [{"id": 3}]}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
                {
                    "active": [{"id": 741, "energies": [{"id": 5}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}, {"id": 6}]}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "context": 13,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "playerIndex": 1, "area": 4, "index": 0},
                {"type": 3, "playerIndex": 1, "area": 5, "index": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_delays_attack_into_lucario_rebuild_pressure(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "anti lucario rebuild smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 120,
                "attack_setup_penalty": 0,
                "attack_empty_bench_penalty": 0,
                "attack_lucario_rebuild_penalty": 220,
                "card_select": 0,
                "card_select_setup": 0,
                "bench_floor_card": 80,
                "bench_floor_select": 100,
                "constructive_context": 0,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 6,
            "turnActionCount": 2,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}]}, {"id": 676, "energies": []}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13},
                {"type": 3, "cardId": 1030},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_uses_turn_shape_to_delay_attack_without_backup(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "turn shape no backup smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 120,
                "attack_setup_penalty": 0,
                "attack_empty_bench_penalty": 0,
                "card_select": 0,
                "card_select_setup": 0,
                "bench_floor_card": 80,
                "bench_floor_select": 100,
                "constructive_context": 0,
                "bad_shape_attack_without_backup": 240,
                "early_shape_constructive_select": 120,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 4,
            "turnActionCount": 2,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}]}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "context": 7,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13},
                {"type": 3, "cardId": 1030},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_uses_turn_shape_for_early_constructive_selection(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "turn shape early setup smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "card_select": 0,
                "card_select_setup": 0,
                "constructive_context": 0,
                "early_shape_constructive_select": 180,
                "disruption_pressure": 0,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 2,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": []}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 35,
                },
            ],
        },
        "select": {
            "context": 7,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "cardId": 1122},
                {"type": 3, "cardId": 1030},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_uses_projected_board_to_find_backup(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "projected board backup smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 150,
                "attack_setup_penalty": 0,
                "attack_empty_bench_penalty": 0,
                "card_select": 0,
                "card_select_setup": 0,
                "constructive_context": 0,
                "bench_floor_select": 0,
                "early_shape_constructive_select": 0,
                "bad_shape_attack_without_backup": 0,
                "projected_second_attacker_bonus": 120,
                "projected_powered_backup_bonus": 170,
                "projected_attack_race_penalty": 220,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 5,
            "turnActionCount": 3,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 28,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}]}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "context": 7,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13},
                {"type": 3, "cardId": 1030},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_candidate_uses_projected_board_for_lucario_bench_attach(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "candidate",
        [666] * 60,
        {
            "strategy": "projected lucario bench attach smoke",
            "key_cards": [666],
            "setup_cards": [666, 1030],
            "attackers": [666, 1030],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "attach": 0,
                "attach_setup": 0,
                "bench_attach": 0,
                "own_attacker_target": 0,
                "own_bench_target": 0,
                "unpowered_next_attacker": 0,
                "overattach_active_penalty": 0,
                "bench_floor_attach": 0,
                "lucario_build_bench_attacker_attach": 0,
                "lucario_overfeed_active_penalty": 0,
                "projected_powered_backup_bonus": 180,
                "projected_lucario_parity_bonus": 220,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 6,
            "turnActionCount": 3,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "energies": [{"id": 3}, {"id": 3}]}],
                    "bench": [{"id": 1030, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 28,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}]}],
                    "prize": [1, 2, 3, 4, 5],
                    "deckCount": 25,
                },
            ],
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_dragapult_candidate_finishes_stage_two_chain(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "dragapult",
        [119] * 4 + [120] * 4 + [121] * 3 + [2] * 25 + [5] * 24,
        {
            "strategy": "dragapult chain completion smoke",
            "key_cards": [119, 120, 121],
            "setup_cards": [119, 120],
            "attackers": [119, 120, 121],
            "evolvers": [120, 121],
            "disruption": [],
            "energy_ids": [2, 5],
            "gate_targets": [677, 678],
            "rng_noise": 0.0,
            "weights": {
                "key_card": 0,
                "attacker": 0,
                "evolver": 0,
                "setup_card_setup": 0,
                "card_select": 0,
                "card_select_setup": 0,
                "constructive_context": 0,
                "dragapult_chain_needed_piece": 240,
                "dragapult_wrong_chain_piece_penalty": 160,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 4,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 120, "energies": [{"id": 2}, {"id": 5}]}],
                    "bench": [{"id": 119, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 34,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 7,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "cardId": 120},
                {"type": 3, "cardId": 121},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_dragapult_candidate_uses_phantom_dive_when_spread_is_live(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "dragapult",
        [119] * 4 + [120] * 4 + [121] * 3 + [2] * 25 + [5] * 24,
        {
            "strategy": "dragapult phantom dive attack smoke",
            "key_cards": [119, 120, 121],
            "setup_cards": [119, 120],
            "attackers": [119, 120, 121],
            "evolvers": [120, 121],
            "disruption": [],
            "energy_ids": [2, 5],
            "gate_targets": [677, 678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 0,
                "attack_single_powered_bonus": 0,
                "attack_ahead": 0,
                "dragapult_phantom_dive_attack": 220,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 5,
            "turnActionCount": 2,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 121, "energies": [{"id": 2}, {"id": 5}], "hp": 320, "maxHp": 320}],
                    "bench": [{"id": 120, "energies": [{"id": 5}]}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 32,
                },
                {
                    "active": [{"id": 678, "hp": 270, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "hp": 60, "maxHp": 80, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 35,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13, "attackId": 154},
                {"type": 13, "attackId": 153},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_dragapult_candidate_places_counters_on_low_hp_rebuild_piece(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "dragapult",
        [119] * 4 + [120] * 4 + [121] * 3 + [2] * 25 + [5] * 24,
        {
            "strategy": "dragapult counter placement smoke",
            "key_cards": [119, 120, 121],
            "setup_cards": [119, 120],
            "attackers": [119, 120, 121],
            "evolvers": [120, 121],
            "disruption": [],
            "energy_ids": [2, 5],
            "gate_targets": [677, 678],
            "rng_noise": 0.0,
            "weights": {
                "card_select": 0,
                "enemy_gate_target": 0,
                "enemy_powered_target": 0,
                "enemy_bench_target": 0,
                "enemy_pressure_target": 0,
                "lucario_chain_target": 0,
                "lucario_bench_chain_target": 0,
                "lucario_powered_chain_target": 0,
                "targeting_context_gate_bonus": 0,
                "dragapult_counter_finish_target": 320,
                "dragapult_counter_bench_rebuild_target": 180,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 6,
            "turnActionCount": 4,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 121, "energies": [{"id": 2}, {"id": 5}]}],
                    "bench": [{"id": 120, "energies": [{"id": 5}]}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 28,
                },
                {
                    "active": [{"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "hp": 60, "maxHp": 80, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 26,
                },
            ],
        },
        "select": {
            "context": 13,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "playerIndex": 1, "area": 4, "index": 0},
                {"type": 3, "playerIndex": 1, "area": 5, "index": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_archaludon_candidate_starts_duraludon_over_cinderace(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [169] * 4 + [190] * 4 + [666] * 4 + [8] * 48,
        {
            "strategy": "archaludon broad setup smoke",
            "key_cards": [169, 190, 666],
            "setup_cards": [169, 190, 666],
            "attackers": [169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [119, 120, 121, 677, 678],
            "rng_noise": 0.0,
            "weights": {
                "key_card": 0,
                "attacker": 0,
                "setup_card_setup": 0,
                "card_select": 0,
                "card_select_setup": 0,
                "constructive_context": 0,
                "archaludon_setup_active_duraludon": 300,
                "archaludon_setup_active_cinderace_penalty": 180,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 0,
            "turnActionCount": 0,
            "yourIndex": 0,
            "players": [
                {"active": [], "bench": [], "prize": [1, 2, 3, 4, 5, 6], "deckCount": 53},
                {"active": [], "bench": [], "prize": [1, 2, 3, 4, 5, 6], "deckCount": 53},
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "cardId": 169},
                {"type": 3, "cardId": 666},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_archaludon_candidate_starts_duraludon_over_relicanth(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [57] + [169] * 4 + [190] * 4 + [666] * 4 + [8] * 47,
        {
            "strategy": "archaludon broad setup smoke",
            "key_cards": [57, 169, 190, 666],
            "setup_cards": [169, 190, 666],
            "attackers": [57, 169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [119, 120, 121, 677, 678],
            "rng_noise": 0.0,
            "weights": {
                "key_card": 0,
                "attacker": 0,
                "setup_card_setup": 0,
                "card_select": 0,
                "card_select_setup": 0,
                "constructive_context": 0,
                "archaludon_setup_active_duraludon": 0,
                "archaludon_setup_active_relicanth_penalty": 180,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 0,
            "turnActionCount": 0,
            "yourIndex": 0,
            "players": [
                {"active": [], "bench": [], "prize": [1, 2, 3, 4, 5, 6], "deckCount": 53},
                {"active": [], "bench": [], "prize": [1, 2, 3, 4, 5, 6], "deckCount": 53},
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "cardId": 169},
                {"type": 3, "cardId": 57},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_archaludon_candidate_attaches_to_line_over_relicanth(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [57] + [169] * 4 + [190] * 4 + [666] * 4 + [8] * 47,
        {
            "strategy": "archaludon broad attach smoke",
            "key_cards": [57, 169, 190, 666],
            "setup_cards": [169, 190, 666],
            "attackers": [57, 169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [119, 120, 121, 677, 678],
            "rng_noise": 0.0,
            "weights": {
                "attach": 0,
                "attach_setup": 0,
                "own_attacker_target": 0,
                "own_bench_target": 0,
                "unpowered_next_attacker": 0,
                "bench_floor_attach": 0,
                "bench_attach": 0,
                "projected_second_attacker_bonus": 0,
                "projected_powered_backup_bonus": 0,
                "archaludon_attach_line": 0,
                "archaludon_attach_relicanth_penalty": 220,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 3,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "hand": [{"id": 8}],
                    "active": [{"id": 57, "hp": 80, "maxHp": 100, "energies": [{"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 36,
                },
                {
                    "active": [{"id": 121, "energies": [{"id": 2}, {"id": 5}]}],
                    "bench": [{"id": 120, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_archaludon_candidate_uses_metal_defender_when_clean_attack_is_ready(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [169] * 4 + [190] * 4 + [666] * 4 + [8] * 48,
        {
            "strategy": "archaludon metal defender smoke",
            "key_cards": [169, 190, 666],
            "setup_cards": [169, 190, 666],
            "attackers": [169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [119, 120, 121, 677, 678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 0,
                "attack_single_powered_bonus": 0,
                "attack_ahead": 0,
                "archaludon_metal_defender_ready": 300,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 4,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "energies": [{"id": 8}]}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 34,
                },
                {
                    "active": [{"id": 678, "hp": 300, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 35,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13, "attackId": 253},
                {"type": 13, "attackId": 224},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_archaludon_candidate_applies_boss_pressure_in_context_3(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [169] * 4 + [190] * 4 + [666] * 4 + [8] * 48,
        {
            "strategy": "archaludon boss context smoke",
            "key_cards": [169, 190, 666],
            "setup_cards": [169, 190, 666],
            "attackers": [169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {
                "card_select": 0,
                "enemy_gate_target": 0,
                "enemy_powered_target": 0,
                "enemy_bench_target": 0,
                "enemy_pressure_target": 0,
                "single_powered_target": 0,
                "archaludon_boss_pressure": 320,
                "archaludon_powered_target_pressure": 0,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 5,
            "turnActionCount": 2,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 34,
                },
                {
                    "active": [{"id": 674, "hp": 150, "maxHp": 150, "energies": [{"id": 6}]}],
                    "bench": [
                        {"id": 999, "hp": 90, "maxHp": 90, "energies": []},
                        {"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]},
                    ],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 3,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 5, "index": 0, "playerIndex": 1},
                {"type": 3, "area": 5, "index": 1, "playerIndex": 1},
            ],
        },
    }

    assert agent(obs) == [1]


def test_generated_archaludon_candidate_uses_raging_hammer_when_duraludon_is_damaged(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [169] * 4 + [190] * 4 + [666] * 4 + [8] * 48,
        {
            "strategy": "archaludon raging hammer smoke",
            "key_cards": [169, 190, 666],
            "setup_cards": [169, 190, 666],
            "attackers": [169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [119, 120, 121, 677, 678],
            "rng_noise": 0.0,
            "weights": {
                "attack_option": 0,
                "attack_single_powered_bonus": 0,
                "attack_ahead": 0,
                "archaludon_raging_hammer_damaged": 260,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 5,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 169, "hp": 40, "maxHp": 130, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 190, "energies": [{"id": 8}]}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 34,
                },
                {
                    "active": [{"id": 121, "hp": 300, "maxHp": 320, "energies": [{"id": 2}, {"id": 5}]}],
                    "bench": [{"id": 120, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 35,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13, "attackId": 224},
                {"type": 13, "attackId": 223},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_archaludon_candidate_attaches_hero_cape_to_archaludon_over_cinderace(tmp_path):
    candidate = _write_candidate(
        tmp_path,
        "archaludon",
        [169] * 4 + [190] * 4 + [666] * 4 + [8] * 48,
        {
            "strategy": "archaludon hero cape smoke",
            "key_cards": [169, 190, 666, 1159],
            "setup_cards": [169, 190, 666],
            "attackers": [169, 190, 666],
            "evolvers": [190],
            "disruption": [1182],
            "energy_ids": [8],
            "gate_targets": [119, 120, 121, 677, 678],
            "rng_noise": 0.0,
            "weights": {
                "card_select": 0,
                "own_attacker_target": 0,
                "own_evolver_target": 0,
                "own_bench_target": 0,
                "archaludon_hero_cape_target": 320,
            },
        },
    )
    agent = _load_agent(candidate["main_path"])
    obs = {
        "current": {
            "turn": 4,
            "turnActionCount": 1,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 169, "energies": [{"id": 8}]}],
                    "bench": [
                        {"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]},
                        {"id": 666, "hp": 160, "maxHp": 160, "energies": [{"id": 8}]},
                    ],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 34,
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": []}],
                    "prize": [1, 2, 3, 4, 5, 6],
                    "deckCount": 30,
                },
            ],
        },
        "select": {
            "context": 22,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "playerIndex": 0, "area": 5, "index": 0},
                {"type": 3, "playerIndex": 0, "area": 5, "index": 1},
            ],
        },
    }

    assert agent(obs) == [0]


def test_generated_lucario_candidate_has_valid_deck(tmp_path):
    deck = [678, 1102, 1141, 1142, 1152, 1192, 1227] * 4 + [6] * 13 + [676] * 3 + [677] * 3 + [673] * 2 + [674] * 2 + [675] * 2 + [1123] * 2 + [1182] * 2 + [1252] * 2 + [1159]
    candidate = _write_candidate(
        tmp_path,
        "lucario",
        deck,
        {
            "strategy": "lucario smoke",
            "key_cards": [676, 677, 678, 1102, 1141, 1142, 1152, 1192, 1227],
            "setup_cards": [676, 677, 678, 1102, 1141, 1142, 1152, 1192, 1227, 1123],
            "attackers": [676, 677, 678],
            "evolvers": [677, 678],
            "disruption": [1123, 1182, 1252],
            "energy_ids": [6],
            "gate_targets": [119, 120, 121, 673, 674, 675, 676, 677, 678, 741, 742, 743],
            "rng_noise": 0.0,
        },
    )

    assert candidate["deck_size"] == 60
    assert (tmp_path / "lucario" / "main.py").exists()
    assert (tmp_path / "lucario" / "deck.csv").exists()


def test_family_deck_variant_preserves_sixty_cards_and_copy_limits():
    base_deck = [673] * 2 + [674] * 2 + [675] * 2 + [676] * 3 + [677] * 3 + [678] * 4 + [6] * 13
    base_deck += [1102] * 4 + [1141] * 4 + [1142] * 4
    base_deck += [1152] * 4 + [1192] * 4 + [1227] * 4 + [1123] * 2 + [1182] * 2 + [1252] * 2 + [1159]
    assert len(base_deck) == 60

    deck = _apply_variant(base_deck, {676: 1, 677: 1, 6: 1}, {1159: 1, 1182: 1, 1252: 1})

    assert len(deck) == 60
    assert deck.count(676) == 4
    assert deck.count(677) == 4
    assert deck.count(6) == 14
