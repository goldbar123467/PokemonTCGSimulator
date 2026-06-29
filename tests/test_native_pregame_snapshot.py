from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_native_pregame_snapshot_emits_official_shaped_isfirst_frame() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][0]

    assert payload["source"] == "clean-room native pregame"
    assert payload["native"]["phase"] == "pre_setup_is_first"
    assert payload["native"]["setup"]["first_player"] is None
    assert payload["native"]["setup"]["players"][0] == {"deck_count": 60, "hand_count": 0, "prize_count": 0}
    assert payload["observation"]["select"]["context"] == 41
    assert payload["observation"]["select"]["type"] == 9
    assert [option["type"] for option in payload["observation"]["select"]["option"]] == [1, 2]
    assert frame["select"]["context"] == "IsFirst"
    assert frame["select"]["type"] == "YesNo"
    assert [option["type"] for option in frame["select"]["option"]] == ["Yes", "No"]
    assert frame["current"]["turnActionCount"] == 1
    assert frame["current"]["players"][0]["deckCount"] == 60
    assert frame["current"]["players"][1]["deckCount"] == 60
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_apply_first_player_choice_and_emit_setup_active_frame() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "17",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][1]

    assert payload["native"]["phase"] == "post_isfirst_opening_hand"
    assert payload["native"]["setup"]["first_player"] == 1
    assert payload["native"]["setup"]["current_player"] == 1
    assert payload["native"]["setup"]["players"][0] == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
    assert payload["native"]["setup"]["players"][1] == {"deck_count": 53, "hand_count": 7, "prize_count": 0}
    assert payload["observation"]["current"]["players"][0]["deckCount"] == 53
    assert payload["observation"]["current"]["players"][0]["prize"] == []
    assert payload["observation"]["current"]["turnActionCount"] == 2
    assert payload["observation"]["select"]["context"] == 1
    assert payload["observation"]["select"]["type"] == 1
    assert payload["observation"]["select"]["option"]
    assert {option["type"] for option in payload["observation"]["select"]["option"]} == {3}
    assert {option["playerIndex"] for option in payload["observation"]["select"]["option"]} == {1}
    assert payload["visualizer"]["frame_count"] == 2
    assert payload["visualizer"]["frames"][0]["select"]["context"] == "IsFirst"
    assert frame["select"]["context"] == "SetupActivePokemon"
    assert frame["select"]["type"] == "Card"
    assert frame["select"]["option"]
    assert {option["type"] for option in frame["select"]["option"]} == {"Card"}
    assert {option["playerIndex"] for option in frame["select"]["option"]} == {1}
    assert frame["current"]["turnActionCount"] == 2
    assert frame["current"]["players"][0]["deckCount"] == 53
    assert frame["current"]["players"][0]["prize"] == []
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_apply_setup_active_choice_and_prompt_other_player() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "17",
            "--setup-active-option-index",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][2]

    assert payload["native"]["phase"] == "post_setup_active_selected"
    assert payload["native"]["active_selection"]["player_index"] == 1
    assert payload["native"]["active_selection"]["option_index"] == 0
    assert payload["native"]["setup"]["players"][1]["hand_count"] == 6
    assert payload["native"]["setup"]["players"][1]["deck_count"] == 53
    assert payload["native"]["setup"]["players"][1]["prize_count"] == 0
    assert payload["observation"]["current"]["yourIndex"] == 0
    assert payload["observation"]["current"]["turnActionCount"] == 3
    assert {option["playerIndex"] for option in payload["observation"]["select"]["option"]} == {0}
    assert payload["visualizer"]["frame_count"] == 3
    assert frame["select"]["context"] == "SetupActivePokemon"
    assert frame["select"]["type"] == "Card"
    assert {option["type"] for option in frame["select"]["option"]} == {"Card"}
    assert {option["playerIndex"] for option in frame["select"]["option"]} == {0}
    assert frame["current"]["yourIndex"] == 0
    assert frame["current"]["turnActionCount"] == 3
    assert len(frame["current"]["players"][1]["active"]) == 1
    assert frame["current"]["players"][1]["handCount"] == 6
    assert frame["current"]["players"][1]["prize"] == []
    assert frame["current"]["players"][0]["active"] == []
    assert frame["current"]["players"][0]["handCount"] == 7
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_apply_both_active_choices_and_emit_setup_bench_frame() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "3",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][3]

    assert payload["native"]["phase"] == "post_both_setup_actives_selected"
    assert [selection["player_index"] for selection in payload["native"]["active_selections"]] == [1, 0]
    assert payload["native"]["setup"]["players"][0]["deck_count"] == 47
    assert payload["native"]["setup"]["players"][0]["hand_count"] == 6
    assert payload["native"]["setup"]["players"][0]["prize_count"] == 6
    assert payload["native"]["setup"]["players"][1]["deck_count"] == 47
    assert payload["native"]["setup"]["players"][1]["hand_count"] == 6
    assert payload["native"]["setup"]["players"][1]["prize_count"] == 6
    assert payload["observation"]["select"]["context"] == 2
    assert payload["observation"]["current"]["yourIndex"] == 1
    assert payload["observation"]["current"]["turnActionCount"] == 4
    assert payload["visualizer"]["frame_count"] == 4
    assert frame["select"]["context"] == "SetupBenchPokemon"
    assert frame["select"]["type"] == "Card"
    assert frame["current"]["yourIndex"] == 1
    assert frame["current"]["turnActionCount"] == 4
    assert frame["current"]["players"][0]["deckCount"] == 47
    assert frame["current"]["players"][0]["handCount"] == 6
    assert frame["current"]["players"][0]["prize"] == [None, None, None, None, None, None]
    assert len(frame["current"]["players"][0]["active"]) == 1
    assert frame["current"]["players"][1]["deckCount"] == 47
    assert frame["current"]["players"][1]["handCount"] == 6
    assert frame["current"]["players"][1]["prize"] == [None, None, None, None, None, None]
    assert len(frame["current"]["players"][1]["active"]) == 1
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_apply_first_setup_bench_choice_and_prompt_other_player() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "3",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
            "--setup-bench-option-index",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][4]

    assert payload["native"]["phase"] == "post_setup_bench_selected"
    assert payload["native"]["bench_selection"]["player_index"] == 1
    assert payload["native"]["bench_selection"]["option_index"] == 0
    assert payload["native"]["setup"]["players"][1]["hand_count"] == 5
    assert payload["native"]["setup"]["players"][1]["bench_count"] == 1
    assert payload["native"]["setup"]["players"][1]["setup_complete"] is True
    assert payload["native"]["setup"]["players"][0]["setup_complete"] is False
    assert payload["observation"]["current"]["yourIndex"] == 0
    assert payload["observation"]["current"]["turnActionCount"] == 5
    assert payload["visualizer"]["frame_count"] == 5
    assert frame["select"]["context"] == "SetupBenchPokemon"
    assert frame["select"]["type"] == "Card"
    assert frame["current"]["yourIndex"] == 0
    assert frame["current"]["turnActionCount"] == 5
    assert len(frame["current"]["players"][1]["bench"]) == 1
    assert frame["current"]["players"][1]["handCount"] == 5
    assert len(frame["current"]["players"][0]["active"]) == 1
    assert frame["current"]["players"][0]["prize"] == [None, None, None, None, None, None]
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_apply_multiple_setup_bench_choices_at_once() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "3",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
            "--setup-bench-option-index",
            "0",
            "--setup-bench-option-index",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][4]

    assert payload["native"]["phase"] == "post_setup_bench_selected"
    assert payload["native"]["setup"]["players"][1]["hand_count"] == 4
    assert payload["native"]["setup"]["players"][1]["bench_count"] == 2
    assert payload["native"]["setup"]["players"][1]["setup_complete"] is True
    assert [selection["option_index"] for selection in payload["native"]["bench_selections"]] == [0, 1]
    assert [selection["original_hand_index"] for selection in payload["native"]["bench_selections"]] == [0, 2]
    assert [selection["applied_hand_index"] for selection in payload["native"]["bench_selections"]] == [0, 1]
    assert payload["native"]["bench_selection"] == payload["native"]["bench_selections"][0]
    assert frame["select"]["context"] == "SetupBenchPokemon"
    assert frame["current"]["yourIndex"] == 0
    assert len(frame["current"]["players"][1]["bench"]) == 2
    assert frame["current"]["players"][1]["handCount"] == 4
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_skip_setup_bench_choices() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "3",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
            "--finish-setup-bench",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][4]

    assert payload["native"]["phase"] == "post_setup_bench_selected"
    assert payload["native"]["setup"]["players"][1]["hand_count"] == 6
    assert payload["native"]["setup"]["players"][1]["bench_count"] == 0
    assert payload["native"]["setup"]["players"][1]["setup_complete"] is True
    assert payload["native"]["bench_selection"] is None
    assert payload["native"]["bench_selections"] == []
    assert frame["select"]["context"] == "SetupBenchPokemon"
    assert frame["current"]["yourIndex"] == 0
    assert len(frame["current"]["players"][1]["bench"]) == 0
    assert frame["current"]["players"][1]["handCount"] == 6
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_can_finish_both_setup_benches_and_begin_first_turn() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "3",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
            "--setup-bench-option-index",
            "0",
            "--next-setup-bench-option-index",
            "0",
            "--begin-first-turn",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][5]

    assert payload["native"]["phase"] == "post_setup_complete_first_turn_started"
    assert payload["native"]["setup"]["turn"] == 1
    assert payload["native"]["setup"]["current_player"] == 1
    assert payload["native"]["setup"]["players"][0]["bench_count"] == 1
    assert payload["native"]["setup"]["players"][0]["setup_complete"] is True
    assert payload["native"]["setup"]["players"][1]["bench_count"] == 1
    assert payload["native"]["setup"]["players"][1]["setup_complete"] is True
    assert [selection["player_index"] for selection in payload["native"]["bench_selections"]] == [1, 0]
    assert payload["observation"]["current"]["turn"] == 1
    assert payload["observation"]["current"]["yourIndex"] == 1
    assert payload["visualizer"]["frame_count"] == 6
    assert payload["visualizer"]["frames"][4]["select"]["context"] == "SetupBenchPokemon"
    assert payload["visualizer"]["frames"][4]["current"]["yourIndex"] == 0
    assert frame["select"]["context"] == "Main"
    assert frame["select"]["type"] == "Action"
    assert frame["current"]["turn"] == 1
    assert frame["current"]["yourIndex"] == 1
    assert frame["current"]["players"][0]["bench"]
    assert frame["current"]["players"][1]["bench"]
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_emits_mulligan_draw_count_frame(tmp_path: Path) -> None:
    sparse_basic_deck = tmp_path / "sparse_basic_deck.csv"
    sparse_basic_deck.write_text("675\n" + ("1227\n" * 59), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            str(sparse_basic_deck),
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "1",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    frame = payload["visualizer"]["frames"][3]

    assert payload["native"]["phase"] == "post_both_setup_actives_draw_count"
    assert payload["native"]["setup"]["mulligans"] == [5, 0]
    assert payload["native"]["draw_count"]["player_index"] == 1
    assert payload["native"]["draw_count"]["max_count"] == 5
    assert payload["native"]["draw_count"]["source_mulligan_player_index"] == 0
    assert payload["visualizer"]["frame_count"] == 4
    assert frame["select"]["context"] == "DrawCount"
    assert frame["select"]["type"] == "Count"
    assert frame["select"]["option"] == [
        {"type": "Number", "number": 0},
        {"type": "Number", "number": 1},
        {"type": "Number", "number": 2},
        {"type": "Number", "number": 3},
        {"type": "Number", "number": 4},
        {"type": "Number", "number": 5},
    ]
    assert frame["current"]["yourIndex"] == 1
    assert payload["kaggle_submission_made"] is False


def test_native_pregame_snapshot_applies_mulligan_draw_count_choice(tmp_path: Path) -> None:
    sparse_basic_deck = tmp_path / "sparse_basic_deck.csv"
    sparse_basic_deck.write_text("675\n" + ("1227\n" * 59), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_pregame_snapshot.py",
            "--deck",
            str(sparse_basic_deck),
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
            "--seed",
            "1",
            "--setup-active-option-index",
            "0",
            "--next-setup-active-option-index",
            "0",
            "--draw-count-choice",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    draw_count_frame = payload["visualizer"]["frames"][3]
    post_choice_frame = payload["visualizer"]["frames"][4]

    assert payload["native"]["phase"] == "post_mulligan_draw_count_selected"
    assert payload["native"]["setup"]["mulligans"] == [5, 0]
    assert payload["native"]["setup"]["mulligan_draw_choices"] == [None, 2]
    assert payload["native"]["draw_count_selection"] == {
        "player_index": 1,
        "count": 2,
        "max_count": 5,
    }
    assert payload["native"]["setup"]["players"][1]["hand_count"] == 8
    assert payload["native"]["setup"]["players"][1]["deck_count"] == 45
    assert payload["observation"]["select"]["context"] == 2
    assert payload["observation"]["current"]["yourIndex"] == 1
    assert payload["observation"]["logs"][-1]["kind"] == "setup_mulligan_draw_count"
    assert payload["visualizer"]["frame_count"] == 5
    assert draw_count_frame["select"]["context"] == "DrawCount"
    assert post_choice_frame["select"]["context"] == "SetupBenchPokemon"
    assert post_choice_frame["current"]["players"][1]["handCount"] == 8
    assert post_choice_frame["current"]["players"][1]["deckCount"] == 45
    assert payload["kaggle_submission_made"] is False
