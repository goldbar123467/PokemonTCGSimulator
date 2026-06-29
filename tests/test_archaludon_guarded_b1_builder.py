from __future__ import annotations

from collections import Counter

from scripts.build_archaludon_guarded_b1_candidates import (
    NO_RELIC_BASE_METAL_DECK_COUNTS,
    NO_RELIC_JUDGE_LAB_DECK_COUNTS,
    NO_RELIC_JUDGE_METAL_DECK_COUNTS,
    PUBLIC_DISRUPTOR_DECK_COUNTS,
    _deck_from_counts,
    _meta_summary,
    _render_main,
)


BASE_OBS = {
    "current": {
        "turn": 4,
        "turnActionCount": 1,
        "yourIndex": 0,
        "players": [
            {
                "hand": [],
                "active": [],
                "bench": [],
                "discard": [],
                "prize": [1, 2, 3, 4, 5, 6],
                "deckCount": 40,
            },
            {
                "hand": [],
                "active": [],
                "bench": [],
                "discard": [],
                "prize": [1, 2, 3, 4, 5, 6],
                "deckCount": 40,
            },
        ],
    },
    "select": {"context": 0, "minCount": 1, "maxCount": 1, "option": []},
}


def _agent(params: dict | None = None):
    env = _render_env(params)
    return env["agent"]


def _render_env(params: dict | None = None) -> dict:
    deck = [169] * 4 + [190] * 4 + [666] * 4 + [8] * 48
    env: dict = {}
    exec(_render_main(deck, "archaludon_guarded_b1_test", params or {}), env)
    return env


def test_no_relic_judge_metal_deck_is_legal_and_removes_relicanth_sink() -> None:
    deck = _deck_from_counts(NO_RELIC_JUDGE_METAL_DECK_COUNTS)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[57] == 0
    assert counts[8] == 12
    assert counts[1213] == 1


def test_no_relic_judge_lab_deck_is_legal_and_restores_fourth_lab() -> None:
    deck = _deck_from_counts(NO_RELIC_JUDGE_LAB_DECK_COUNTS)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[57] == 0
    assert counts[1244] == 4
    assert counts[1213] == 1


def test_no_relic_base_metal_deck_is_legal_without_judge() -> None:
    deck = _deck_from_counts(NO_RELIC_BASE_METAL_DECK_COUNTS)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[57] == 0
    assert counts[8] == 12
    assert counts[1213] == 0
    assert counts[1244] == 4


def test_public_disruptor_deck_is_legal_and_keeps_relicanth_shell() -> None:
    deck = _deck_from_counts(PUBLIC_DISRUPTOR_DECK_COUNTS)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[57] == 1
    assert counts[666] == 0
    assert counts[1192] == 4
    assert counts[1213] == 4
    assert counts[1123] == 2
    assert counts[1197] == 1
    assert counts[1087] == 1


def test_guarded_meta_summary_accepts_utf8_bom(tmp_path) -> None:
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        '{"date":"2026-06-27","latestDate":"2026-06-27","redirected":false,"totalDecks":11838,"source":{"datasetUrl":"https://example.test/meta"}}',
        encoding="utf-8-sig",
    )

    summary = _meta_summary(meta_path)

    assert summary["date"] == "2026-06-27"
    assert summary["totalDecks"] == 11838
    assert summary["datasetUrl"] == "https://example.test/meta"


def test_guarded_policy_counts_duplicate_energy_fields_once() -> None:
    env = _render_env()
    energy_count = env["_energy_count"]

    assert energy_count({"energies": [{"id": 8}], "energyCards": [{"id": 8, "serial": 1}]}) == 1
    assert energy_count({"energies": [8, 8], "energyCards": [{"id": 8}, {"id": 8}]}) == 2
    assert energy_count({"energies": [{"id": 8}, {"id": 8}], "energyCards": []}) == 2
    assert energy_count({"energies": 3, "energyCards": []}) == 3


def test_fumi_ranked_variant_prefers_cinderace_setup_active_and_skips_optional_bench() -> None:
    agent = _agent(
        {
            "return_full_ranking": True,
            "skip_optional_setup_bench": True,
            "duraludon_setup_active_bonus": 260,
            "cinderace_setup_active_bonus": 900,
            "optional_threshold": 9999,
        }
    )
    active_obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "turn": 0,
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 169}, {"id": 666}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 2, "index": 1, "playerIndex": 0},
            ],
        },
    }
    bench_obs = {
        **active_obs,
        "select": {
            "context": 2,
            "minCount": 0,
            "maxCount": 3,
            "option": [
                {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 2, "index": 1, "playerIndex": 0},
            ],
        },
    }

    assert agent(active_obs)[0] == 1
    assert agent(bench_obs) == []


def test_ranked_variant_returns_more_than_one_index_for_required_windows() -> None:
    agent = _agent({"return_full_ranking": True, "order_weight": 50})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 21,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 4, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 5, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
            ],
        },
    }

    assert len(agent(obs)) == 3


def test_b1_patch_mode_keeps_optional_first_option_floor() -> None:
    agent = _agent({"b1_patch_mode": "retreat"})
    obs = {
        **BASE_OBS,
        "select": {
            "context": 2,
            "minCount": 0,
            "maxCount": 3,
            "option": [
                {"type": 3, "cardId": 169},
                {"type": 3, "cardId": 666},
            ],
        },
    }

    assert agent(obs) == [0]


def test_b1_patch_mode_fills_required_multi_select_windows() -> None:
    agent = _agent({"b1_patch_mode": "retreat"})
    obs = {
        **BASE_OBS,
        "select": {
            "context": 8,
            "minCount": 2,
            "maxCount": 2,
            "option": [
                {"type": 3, "cardId": 1121},
                {"type": 3, "cardId": 1122},
                {"type": 3, "cardId": 1185},
            ],
        },
    }

    assert agent(obs) == [0, 1]


def test_b1_backup_patch_moves_active_overfeed_to_bench_line() -> None:
    agent = _agent({"b1_patch_mode": "backup"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": [{"id": 8}]}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_b1_patch_handles_pregame_negative_your_index() -> None:
    agent = _agent({"b1_patch_mode": "retreat"})
    obs = {
        "current": {
            "turn": 0,
            "turnActionCount": 1,
            "yourIndex": -1,
            "players": [
                {"active": [], "bench": [], "hand": [], "prize": [], "deckCount": 60},
                {"active": [], "bench": [], "hand": [], "prize": [], "deckCount": 60},
            ],
        },
        "select": {
            "context": 41,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 1}, {"type": 2}],
        },
    }

    assert agent(obs) == [0]


def test_cinderace_turbo_mode_prefers_cinderace_setup_active() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 169}, {"id": 666}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 2, "index": 1, "playerIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_turbo_mode_attacks_with_turbo_flare_when_bench_arch_exists() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 666, "hp": 160, "maxHp": 160, "energies": [{"id": 8}]}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 14},
                {"type": 13, "attackId": 965},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_turbo_mode_selects_max_metal_energy_for_search() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo"})
    obs = {
        **BASE_OBS,
        "select": {
            "context": 22,
            "minCount": 0,
            "maxCount": 3,
            "option": [
                {"type": 3, "cardId": 8},
                {"type": 3, "cardId": 169},
                {"type": 3, "cardId": 8},
                {"type": 3, "cardId": 8},
            ],
        },
    }

    assert agent(obs) == [0, 2, 3]


def test_cinderace_turbo_mode_can_choose_second_when_configured() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo", "prefer_second": True})
    obs = {
        **BASE_OBS,
        "select": {
            "context": 41,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 1},
                {"type": 2},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_discard_mode_uses_metal_as_discard_fuel_and_fills_count() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo_discard"})
    obs = {
        **BASE_OBS,
        "select": {
            "context": 8,
            "minCount": 2,
            "maxCount": 2,
            "option": [
                {"type": 3, "cardId": 8},
                {"type": 3, "cardId": 1122},
                {"type": 3, "cardId": 169},
            ],
        },
    }

    assert agent(obs) == [0, 1]


def test_cinderace_spread_mode_promotes_ready_arch_before_relicanth() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo_spread"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [],
                    "bench": [
                        {"id": 57, "hp": 100, "maxHp": 100, "energies": [{"id": 8}]},
                        {"id": 169, "hp": 130, "maxHp": 130, "energies": [{"id": 8}, {"id": 8}]},
                        {"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]},
                    ],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 4,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 5, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 5, "index": 1, "playerIndex": 0},
                {"type": 3, "area": 5, "index": 2, "playerIndex": 0},
            ],
        },
    }

    assert agent(obs) == [2]


def test_cinderace_spread_mode_targets_low_energy_bench_arch_line() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo_spread"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}] * 6}],
                    "bench": [
                        {"id": 169, "hp": 130, "maxHp": 130, "energies": []},
                        {"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}]},
                    ],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 21,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 4, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 5, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 5, "index": 1, "playerIndex": 0},
            ],
        },
    }

    assert agent(obs) == [2]


def test_cinderace_spread_mode_redirects_active_overfeed_to_bench() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo_spread"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}] * 5}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": [{"id": 8}]}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
                {"type": 13, "attackId": 253},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_spread_mode_targets_gate_piece_over_filler() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo_spread"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                BASE_OBS["current"]["players"][0],
                {
                    **BASE_OBS["current"]["players"][1],
                    "bench": [
                        {"id": 999, "hp": 90, "maxHp": 90, "energies": [{"id": 4}]},
                        {"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 4}, {"id": 4}]},
                    ],
                },
            ],
        },
        "select": {
            "context": 13,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 5, "index": 0, "playerIndex": 1},
                {"type": 3, "area": 5, "index": 1, "playerIndex": 1},
            ],
        },
    }

    assert agent(obs) == [1]


def test_guarded_policy_targets_powered_lucario_in_boss_bench_context() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "bench": [
                        {"id": 676, "hp": 110, "maxHp": 110, "energies": []},
                        {"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]},
                        {"id": 677, "hp": 80, "maxHp": 80, "energies": []},
                    ],
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
                {"type": 3, "area": 5, "index": 2, "playerIndex": 1},
            ],
        },
    }

    assert agent(obs) == [1]


def test_guarded_policy_does_not_boss_target_own_gate_piece() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "bench": [{"id": 678, "hp": 340, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "bench": [{"id": 676, "hp": 110, "maxHp": 110, "energies": []}],
                },
            ],
        },
        "select": {
            "context": 3,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 5, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 5, "index": 0, "playerIndex": 1},
            ],
        },
    }

    assert agent(obs) == [1]


def test_memory_dive_redirects_hero_cape_to_archaludon_over_cinderace() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_memory_dive"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1159}],
                    "active": [{"id": 666, "hp": 160, "maxHp": 160, "energies": [{"id": 8}]}],
                    "bench": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 22,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_memory_dive_attaches_third_energy_to_damaged_duraludon_before_hammer_in() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_memory_dive"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 169, "hp": 40, "maxHp": 130, "energies": [{"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 57, "hp": 100, "maxHp": 100, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 13, "attackId": 223},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [0]


def test_memory_dive_builds_second_duraludon_line_before_relicanth() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_memory_dive"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 57}, {"id": 169}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "area": 2, "index": 0},
                {"type": 7, "area": 2, "index": 1},
                {"type": 13, "attackId": 253},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_spread_mode_keeps_hero_cape_off_relicanth() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_turbo_spread"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1159}],
                    "active": [{"id": 57, "hp": 100, "maxHp": 100, "energies": []}],
                    "bench": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 7, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_tempo_guard_attaches_before_search_churn() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_tempo_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1122}, {"id": 8}],
                    "active": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 1030, "hp": 90, "maxHp": 90, "energies": [{"id": 3}, {"id": 3}]}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 8, "area": 2, "index": 1, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_tempo_guard_evolves_damaged_duraludon_before_draw() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_tempo_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1227}, {"id": 190}],
                    "active": [{"id": 169, "hp": 40, "maxHp": 130, "energies": [{"id": 8}]}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 1031, "hp": 330, "maxHp": 330, "energies": [{"id": 3}, {"id": 3}]}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 9, "area": 2, "index": 1, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 13, "attackId": 223},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_tempo_guard_caps_active_archaludon_overfeed() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_tempo_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": 4}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 13, "attackId": 253},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_tempo_guard_builds_bench_after_active_is_online() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_tempo_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 169, "hp": 100, "maxHp": 130, "energies": 2}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
                {"type": 13, "attackId": 223},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_line_guard_benches_second_duraludon_before_churn() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_line_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1122}, {"id": 169}],
                    "active": [{"id": 169, "hp": 130, "maxHp": 130, "energies": 2}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 7, "index": 1},
                {"type": 13, "attackId": 223},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_line_guard_attacks_with_ready_duraludon_before_trainer() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_line_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1122}],
                    "active": [{"id": 169, "hp": 130, "maxHp": 130, "energies": 2}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 13, "attackId": 223},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_line_guard_attacks_with_ready_archaludon_before_trainer() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_line_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1185}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": 3}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 13, "attackId": 253},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_line_guard_does_not_feed_active_archaludon_past_attack_threshold() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_line_guard"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": 3}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 13, "attackId": 253},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_backup_lock_benches_second_line_before_low_backup_attack() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_backup_lock"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 169}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": 3}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 678, "hp": 340, "maxHp": 340, "energies": 2}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 13, "attackId": 253},
            ],
        },
    }

    assert agent(obs) == [0]


def test_cinderace_backup_lock_redirects_active_overfeed_to_bench_line() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_backup_lock"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 8}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": 3}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 1031, "hp": 330, "maxHp": 330, "energies": 2}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
                {"type": 8, "area": 2, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_backup_lock_attacks_once_backup_exists() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_backup_lock"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 1122}],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": 3}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": 2}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 678, "hp": 340, "maxHp": 340, "energies": 2}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 0},
                {"type": 13, "attackId": 253},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_memory_dive_benches_relicanth_as_support_piece() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_memory_dive"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 57}, {"id": 1122}],
                    "active": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 7, "index": 1},
                {"type": 7, "index": 0},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_cinderace_memory_dive_prefers_damaged_raging_hammer() -> None:
    agent = _agent({"b1_patch_mode": "cinderace_memory_dive"})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 120, "maxHp": 300, "energies": 3}],
                    "bench": [{"id": 57, "hp": 100, "maxHp": 100, "energies": []}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 678, "hp": 340, "maxHp": 340, "energies": 2}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 13, "attackId": 253},
                {"type": 13, "attackId": 224},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_guarded_policy_prefers_duraludon_setup_active_over_cinderace() -> None:
    agent = _agent()
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "turn": 0,
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "hand": [{"id": 666}, {"id": 169}],
                },
                BASE_OBS["current"]["players"][1],
            ],
        },
        "select": {
            "context": 1,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
                {"type": 3, "area": 2, "index": 1, "playerIndex": 0},
            ],
        },
    }

    assert agent(obs) == [1]


def test_guarded_policy_vetoes_unsafe_retreat_when_attack_is_live() -> None:
    agent = _agent()
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": []}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 1031, "hp": 330, "maxHp": 330, "energies": [{"id": 3}]}],
                    "bench": [{"id": 1030, "hp": 70, "maxHp": 70, "energies": []}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 12},
                {"type": 13, "attackId": 253},
                {"type": 14},
            ],
        },
    }

    assert agent(obs) == [1]


def test_guarded_policy_attacks_instead_of_ending_with_powered_archaludon() -> None:
    agent = _agent()
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 260, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "hp": 130, "maxHp": 130, "energies": [{"id": 8}]}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 678, "hp": 300, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "hp": 70, "maxHp": 70, "energies": []}],
                },
            ],
        },
        "select": {
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 14},
                {"type": 13, "attackId": 253},
            ],
        },
    }

    assert agent(obs) == [1]


def test_guarded_policy_targets_starmie_bridge_over_generic_active() -> None:
    agent = _agent({"starmie_target_bonus": 420, "target_bonus": 140})
    obs = {
        **BASE_OBS,
        "current": {
            **BASE_OBS["current"],
            "players": [
                {
                    **BASE_OBS["current"]["players"][0],
                    "active": [{"id": 190, "hp": 300, "maxHp": 300, "energies": [{"id": 8}, {"id": 8}, {"id": 8}]}],
                    "bench": [{"id": 169, "energies": [{"id": 8}]}],
                },
                {
                    **BASE_OBS["current"]["players"][1],
                    "active": [{"id": 666, "hp": 160, "maxHp": 160, "energies": []}],
                    "bench": [{"id": 1030, "hp": 70, "maxHp": 70, "energies": []}],
                },
            ],
        },
        "select": {
            "context": 13,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 3, "area": 4, "index": 0, "playerIndex": 1},
                {"type": 3, "area": 5, "index": 0, "playerIndex": 1},
            ],
        },
    }

    assert agent(obs) == [1]
