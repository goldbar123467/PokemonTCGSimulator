import json

from ptcg.teacher_evaluator import choose_teacher_action
from ptcg.teacher_evaluator import label_selected_decision
from ptcg.teacher_evaluator import teacher_patch_decisions
from ptcg.teacher_evaluator import score_options
from ptcg.teacher_evaluator import write_labeled_decision_windows


def _pokemon(card_id, *, hp=100, max_hp=100, energies=0):
    return {
        "id": card_id,
        "hp": hp,
        "maxHp": max_hp,
        "energies": [{"id": 1} for _ in range(energies)],
        "energyCards": [],
    }


def _card(card_id):
    return {"id": card_id}


def test_teacher_scores_setup_next_attacker_over_end_and_raw_attack():
    obs = {
        "current": {
            "turn": 3,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(677, hp=90, max_hp=340, energies=2)],
                    "bench": [_pokemon(676, hp=80, max_hp=80, energies=0)],
                    "hand": [_card(6)],
                    "handCount": 5,
                    "deckCount": 30,
                    "prize": [None, None, None, None, None, None],
                },
                {
                    "active": [_pokemon(878, hp=140, max_hp=140, energies=1)],
                    "bench": [],
                    "handCount": 4,
                    "deckCount": 30,
                    "prize": [None, None, None, None, None, None],
                },
            ],
        },
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 14},
                {"type": 13, "attackId": 982},
                {"type": 8, "area": 2, "index": 0, "playerIndex": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }

    scored = score_options(obs)

    assert "setup_next_attacker" in scored[2].labels
    assert "end_with_constructive_setup" in scored[0].penalties
    assert scored[2].score > scored[1].score
    assert scored[2].score > scored[0].score
    assert choose_teacher_action(obs) == [2]


def test_teacher_labels_punish_overpowered_active_attack():
    obs = {
        "current": {
            "turn": 7,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(743, hp=110, max_hp=110, energies=1)],
                    "bench": [_pokemon(742, hp=140, max_hp=140, energies=0)],
                    "hand": [],
                    "handCount": 20,
                    "deckCount": 18,
                    "prize": [None, None, None],
                },
                {
                    "active": [_pokemon(677, hp=340, max_hp=340, energies=3)],
                    "bench": [_pokemon(676, hp=80, max_hp=80, energies=0)],
                    "handCount": 6,
                    "deckCount": 14,
                    "prize": [None, None, None, None, None],
                },
            ],
        },
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 13, "attackId": 1072}, {"type": 14}],
        },
    }

    scored = score_options(obs)

    assert "punish_overpowered_active" in scored[0].labels
    assert "dead_or_random_move" in scored[1].penalties
    assert choose_teacher_action(obs) == [0]


def test_teacher_separates_trap_and_sleep_tempo_attacks():
    obs = {
        "current": {
            "turn": 12,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(879, hp=120, max_hp=120, energies=1)],
                    "bench": [_pokemon(878, hp=140, max_hp=140, energies=1)],
                    "hand": [],
                    "handCount": 5,
                    "deckCount": 22,
                    "prize": [None, None, None, None],
                },
                {
                    "active": [_pokemon(677, hp=340, max_hp=340, energies=2)],
                    "bench": [],
                    "handCount": 8,
                    "deckCount": 10,
                    "prize": [None, None],
                },
            ],
        },
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 13, "attackId": 1267}, {"type": 13, "attackId": 1488}, {"type": 14}],
        },
    }

    scored = score_options(obs)

    assert "trap_active" in scored[0].labels
    assert "sleep_tempo" in scored[1].labels
    assert "behind_on_prizes_recovery" in scored[1].labels
    assert scored[0].score > scored[2].score
    assert scored[1].score > scored[2].score


def test_label_selected_decision_writes_decision_window_labels():
    obs = {
        "current": {
            "turn": 8,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(120, hp=320, max_hp=320, energies=2)],
                    "bench": [_pokemon(119, hp=90, max_hp=90, energies=1)],
                    "hand": [],
                    "handCount": 7,
                    "deckCount": 21,
                    "prize": [None, None, None, None, None],
                },
                {
                    "active": [_pokemon(741, hp=80, max_hp=80, energies=1)],
                    "bench": [_pokemon(742, hp=140, max_hp=140, energies=0)],
                    "handCount": 22,
                    "deckCount": 9,
                    "prize": [None, None],
                },
            ],
        },
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 13, "attackId": 153}, {"type": 14}],
        },
    }

    row = label_selected_decision(
        "81489022",
        step_index=88,
        agent_index=0,
        observation=obs,
        action_indices=(0,),
        game_label="anti_dragapult_alakazam_gate",
    )

    assert row["replay_id"] == "81489022"
    assert row["turn"] == 8
    assert row["game_label"] == "anti_dragapult_alakazam_gate"
    assert row["selected_labels"] == ["spread_pressure"]
    assert row["teacher_labels"] == ["spread_pressure"]
    assert row["selected_score"] > 0


def test_write_labeled_decision_windows_emits_jsonl_rows(tmp_path):
    obs = {
        "current": {
            "turn": 7,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(743, hp=110, max_hp=110, energies=1)],
                    "bench": [_pokemon(742, hp=140, max_hp=140, energies=0)],
                    "hand": [],
                    "handCount": 20,
                    "deckCount": 18,
                    "prize": [None, None, None],
                },
                {
                    "active": [_pokemon(677, hp=340, max_hp=340, energies=3)],
                    "bench": [_pokemon(676, hp=80, max_hp=80, energies=0)],
                    "handCount": 6,
                    "deckCount": 14,
                    "prize": [None, None, None, None, None],
                },
            ],
        },
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 13, "attackId": 1072}, {"type": 14}],
        },
    }
    replay = {
        "info": {"EpisodeId": "seed-game"},
        "steps": [[{"observation": obs, "action": [0]}]],
    }
    replay_path = tmp_path / "seed-game.json"
    output_path = tmp_path / "windows.jsonl"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    summary = write_labeled_decision_windows(
        [replay_path],
        output_path,
        game_labels={"seed-game": "anti_lucario_hand_damage"},
    )

    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert summary["written_rows"] == 1
    assert rows[0]["replay_id"] == "seed-game"
    assert rows[0]["game_label"] == "anti_lucario_hand_damage"
    assert rows[0]["decision_window"] == "attack_choice"
    assert rows[0]["selected_labels"] == ["punish_overpowered_active"]
    assert rows[0]["teacher_labels"] == ["punish_overpowered_active"]


def test_teacher_patch_decisions_rewrite_bad_actions_to_teacher_action(tmp_path):
    obs = {
        "current": {
            "turn": 3,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(677, hp=90, max_hp=340, energies=2)],
                    "bench": [_pokemon(676, hp=80, max_hp=80, energies=0)],
                    "hand": [_card(6)],
                    "handCount": 5,
                    "deckCount": 30,
                    "prize": [None, None, None, None, None, None],
                },
                {
                    "active": [_pokemon(878, hp=140, max_hp=140, energies=1)],
                    "bench": [],
                    "handCount": 4,
                    "deckCount": 30,
                    "prize": [None, None, None, None, None, None],
                },
            ],
        },
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 14},
                {"type": 13, "attackId": 982},
                {"type": 8, "area": 2, "index": 0, "playerIndex": 0, "inPlayArea": 5, "inPlayIndex": 0},
            ],
        },
    }
    replay_path = tmp_path / "seed-game.json"
    replay_path.write_text(
        json.dumps({"info": {"EpisodeId": "seed-game"}, "steps": [[{"observation": obs, "action": [0]}]]}),
        encoding="utf-8",
    )

    result = teacher_patch_decisions([replay_path], game_labels={"seed-game": "lucario_direct_aggression_gate"})

    assert result.sample_count == 1
    assert result.decisions[0].action_indices == (2,)
    assert result.rewritten_count == 1
    assert result.label_counts["setup_next_attacker"] == 1
