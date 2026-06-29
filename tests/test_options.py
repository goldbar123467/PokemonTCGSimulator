from ptcg.options import choose_legal_action, option_feature_tokens


def test_option_feature_tokens_include_board_and_option_context():
    obs = {
        "current": {
            "turn": 3,
            "turnActionCount": 2,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 666, "hp": 80, "maxHp": 120, "energies": [{"id": 3}]}],
                    "bench": [],
                    "handCount": 5,
                    "deckCount": 31,
                    "prize": [1, 2, 3],
                },
                {
                    "active": [{"id": 678, "hp": 300, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": [{"id": 6}]}],
                    "handCount": 4,
                    "deckCount": 28,
                    "prize": [1, 2],
                },
            ],
        },
        "select": {"context": 13, "type": 1, "option": [{"type": 3, "playerIndex": 1, "area": 5, "index": 0}]},
    }

    tokens = option_feature_tokens(obs, obs["select"]["option"][0], option_index=0)

    assert "turn:3" in tokens
    assert "us_active:666" in tokens
    assert "them_active:678" in tokens
    assert "them_bench_id:677" in tokens
    assert "option_type:3" in tokens
    assert "context:13" in tokens


def test_choose_legal_action_respects_min_max_count_and_scores():
    options = [{"type": 1}, {"type": 2}, {"type": 3}]
    action = choose_legal_action(options, min_count=1, max_count=2, scores=[0.1, 9.0, 5.0])

    assert action == [1, 2]


def test_option_feature_tokens_label_lucario_meta_card_and_damage_plan():
    obs = {
        "current": {
            "turn": 7,
            "turnActionCount": 4,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [
                        {"id": 675, "energies": []},
                        {"id": 676, "energies": []},
                        {"id": 674, "energies": [{"id": 6}]},
                    ],
                    "hand": [{"id": 1142}, {"id": 1141}, {"id": 1182}, {"id": 1152}, {"id": 1227}],
                    "discard": [{"id": 6}],
                    "handCount": 5,
                    "deckCount": 24,
                    "prize": [1, 2],
                },
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "energies": []}],
                    "handCount": 3,
                    "deckCount": 25,
                    "prize": [1, 2, 3],
                },
            ],
        },
        "select": {
            "context": 13,
            "type": 1,
            "option": [{"type": 1, "playerIndex": 0, "area": 2, "index": 0}],
        },
    }

    tokens = option_feature_tokens(obs, obs["select"]["option"][0], option_index=0)

    assert "option_source_card:1142" in tokens
    assert "lucario_core_card:fighting_gong" in tokens
    assert "lucario_board:mega_lucario_ready" in tokens
    assert "lucario_board:solrock_lunatone_online" in tokens
    assert "lucario_board:fighting_energy_in_discard" in tokens
    assert "lucario_board:next_attacker_available" in tokens


def test_option_feature_tokens_label_lucario_damage_amplification_cards():
    obs = {
        "current": {
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 678, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [],
                    "hand": [{"id": 1141}, {"id": 1252}],
                    "handCount": 2,
                    "deckCount": 30,
                    "prize": [],
                },
                {"active": [], "bench": [], "handCount": 0, "deckCount": 30, "prize": []},
            ],
        },
        "select": {
            "context": 13,
            "type": 1,
            "option": [
                {"type": 1, "playerIndex": 0, "area": 2, "index": 0},
                {"type": 1, "playerIndex": 0, "area": 2, "index": 1},
            ],
        },
    }

    premium_tokens = option_feature_tokens(obs, obs["select"]["option"][0], option_index=0)
    mountain_tokens = option_feature_tokens(obs, obs["select"]["option"][1], option_index=1)

    assert "lucario_damage_amp:premium_power_pro" in premium_tokens
    assert "lucario_damage_amp:gravity_mountain" in mountain_tokens


def test_option_feature_tokens_include_observable_target_and_posture_context():
    obs = {
        "current": {
            "turn": 6,
            "turnActionCount": 3,
            "yourIndex": 0,
            "players": [
                {
                    "active": [{"id": 678, "hp": 210, "maxHp": 340, "energies": [{"id": 6}, {"id": 6}]}],
                    "bench": [{"id": 677, "hp": 70, "maxHp": 80, "energies": []}],
                    "handCount": 4,
                    "deckCount": 25,
                    "prize": [None, None, None, None],
                },
                {
                    "active": [{"id": 121, "hp": 250, "maxHp": 320, "energies": [{"id": 3}]}],
                    "bench": [{"id": 677, "hp": 80, "maxHp": 80, "energies": []}],
                    "handCount": 5,
                    "deckCount": 29,
                    "prize": [None, None],
                },
            ],
        },
        "select": {
            "context": 13,
            "type": 1,
            "option": [{"type": 8, "playerIndex": 1, "inPlayArea": 5, "inPlayIndex": 0}],
        },
    }

    tokens = option_feature_tokens(obs, obs["select"]["option"][0], option_index=0)

    assert "option_target_card:677" in tokens
    assert "option_target_energy:0" in tokens
    assert "option_target_hp_bucket:healthy" in tokens
    assert "option_target_lucario_pokemon:riolu" in tokens
    assert "them_active_dragapult_line" in tokens
    assert "us_bench_count:1" in tokens
    assert "them_bench_count:1" in tokens
    assert "us_powered_board:1" in tokens
    assert "them_powered_board:1" in tokens
    assert "posture:behind_on_prizes" in tokens
    assert "posture:has_ready_attacker" in tokens
