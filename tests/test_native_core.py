from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from ptcg.native_core import NativeBattlePlayer, NativeBattleSetup, NativeCore, build_native_core


def test_native_core_loads_repo_deck_csv_and_reports_stable_summary() -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)

    deck = core.load_deck_csv(Path("deck.csv"))

    assert deck.card_count == 60
    assert deck.cards[:4] == (673, 673, 674, 674)
    assert deck.cards[-4:] == (6, 1182, 677, 1252)
    assert deck.sha256 == "2a541d7bf3d9e6b36037123f53f4dfef6348223f79fd27095dafc602a5357c19"


def test_native_core_reports_deck_counts_from_compiled_c_api() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)

    deck = core.load_deck_csv(Path("deck.csv"))
    summary = core.deck_summary(deck)

    assert summary.card_count == 60
    assert summary.unique_count == 17
    assert summary.basic_pokemon_count == 11
    assert summary.energy_count == 14
    assert summary.count_card(673) == 2
    assert summary.count_card(6) == 14
    assert summary.named_counts[:3] == (
        {"card_id": 673, "count": 2, "name": "Makuhita"},
        {"card_id": 674, "count": 2, "name": "Hariyama"},
        {"card_id": 675, "count": 2, "name": "Lunatone"},
    )


def test_native_core_exposes_pregame_isfirst_state_before_setup_deal() -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)

    pregame = core.start_battle_pregame("deck.csv", "deck.csv")

    assert pregame.turn == 0
    assert pregame.first_player == -1
    assert pregame.current_player == 0
    assert pregame.players[0].deck_count == 60
    assert pregame.players[0].hand_count == 0
    assert pregame.players[0].prize_count == 0
    assert pregame.players[1].deck_count == 60
    assert pregame.players[1].hand_count == 0
    assert pregame.players[1].prize_count == 0


def test_native_core_deals_opening_hands_after_explicit_first_player_selection() -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)
    pregame = core.start_battle_pregame("deck.csv", "deck.csv")

    setup = core.select_pregame_first_player(pregame, first_player=1, seed=17)

    assert setup.turn == 0
    assert setup.first_player == 1
    assert setup.current_player == 1
    assert setup.players[0].deck_count == 53
    assert setup.players[0].hand_count == 7
    assert setup.players[0].prize_count == 0
    assert setup.players[1].deck_count == 53
    assert setup.players[1].hand_count == 7
    assert setup.players[1].prize_count == 0


def test_native_core_can_start_from_observed_ordered_opening_zones() -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)
    cards = core.load_deck_csv(Path("deck.csv")).cards
    player0_hand = cards[:7]
    player1_hand = cards[7:14]
    player0_hand_serials = tuple(range(101, 108))
    player0_deck_serials = tuple(range(108, 161))
    player1_hand_serials = tuple(range(201, 208))
    player1_deck_serials = tuple(range(208, 261))

    setup = core.start_battle_setup_from_ordered_zones(
        player0_hand_card_ids=player0_hand,
        player0_deck_card_ids=cards[7:],
        player0_hand_serials=player0_hand_serials,
        player0_deck_serials=player0_deck_serials,
        player1_hand_card_ids=player1_hand,
        player1_deck_card_ids=cards[:7] + cards[14:],
        player1_hand_serials=player1_hand_serials,
        player1_deck_serials=player1_deck_serials,
        first_player=1,
    )

    assert setup.turn == 0
    assert setup.first_player == 1
    assert setup.current_player == 1
    assert setup.players[0].hand_card_ids == player0_hand
    assert setup.players[0].deck_card_ids == cards[7:]
    assert setup.players[0].hand_card_serials == player0_hand_serials
    assert setup.players[0].deck_card_serials == player0_deck_serials
    assert setup.players[1].hand_card_ids == player1_hand
    assert setup.players[1].deck_card_ids == cards[:7] + cards[14:]
    assert setup.players[1].hand_card_serials == player1_hand_serials
    assert setup.players[1].deck_card_serials == player1_deck_serials
    assert setup.players[0].prize_card_ids == ()
    assert setup.players[1].prize_card_ids == ()

    observation = setup.to_observation(player_index=1, native_core=core)
    expected_active_card_ids = [
        card_id for card_id in player1_hand if core.is_basic_pokemon_card(card_id)
    ]
    assert [option["cardId"] for option in observation["select"]["option"]] == expected_active_card_ids
    assert [card["serial"] for card in observation["current"]["players"][1]["hand"]] == list(
        player1_hand_serials
    )

    selected_hand_index = observation["select"]["option"][0]["index"]
    after_active = core.select_setup_active(
        setup,
        player_index=1,
        hand_index=selected_hand_index,
    )
    assert after_active.players[1].active_card_id == expected_active_card_ids[0]
    selected_active_serial = player1_hand_serials[selected_hand_index]
    expected_player1_hand_serials_after_active = (
        player1_hand_serials[:selected_hand_index]
        + player1_hand_serials[selected_hand_index + 1 :]
    )
    assert after_active.players[1].active_card_serial == selected_active_serial
    assert after_active.players[1].hand_card_serials == expected_player1_hand_serials_after_active
    assert after_active.players[1].deck_card_serials == player1_deck_serials

    after_active_observation = after_active.to_observation(player_index=1, native_core=core)
    assert after_active_observation["current"]["players"][1]["active"][0]["serial"] == selected_active_serial
    assert [card["serial"] for card in after_active_observation["current"]["players"][1]["hand"]] == list(
        expected_player1_hand_serials_after_active
    )

    second_player_active_index = after_active.to_observation(player_index=0, native_core=core)["select"][
        "option"
    ][0]["index"]
    after_both_actives = core.select_setup_active(
        after_active,
        player_index=0,
        hand_index=second_player_active_index,
    )
    expected_player0_hand_serials_after_active = (
        player0_hand_serials[:second_player_active_index]
        + player0_hand_serials[second_player_active_index + 1 :]
    )
    assert after_both_actives.players[0].active_card_serial == player0_hand_serials[
        second_player_active_index
    ]
    assert after_both_actives.players[0].hand_card_serials == expected_player0_hand_serials_after_active

    after_prizes = core.deal_setup_prizes(after_both_actives)
    assert after_prizes.players[0].prize_card_serials == tuple(reversed(player0_deck_serials[-6:]))
    assert after_prizes.players[0].deck_card_serials == player0_deck_serials[:-6]
    assert after_prizes.players[1].prize_card_serials == tuple(reversed(player1_deck_serials[-6:]))
    assert after_prizes.players[1].deck_card_serials == player1_deck_serials[:-6]
    assert after_prizes.players[1].active_card_serial == selected_active_serial

    setup_bench_observation = after_prizes.to_observation(player_index=1, native_core=core)
    setup_bench_index = setup_bench_observation["select"]["option"][0]["index"]
    selected_bench_serial = after_prizes.players[1].hand_card_serials[setup_bench_index]
    after_setup_bench = core.select_setup_bench(
        after_prizes,
        player_index=1,
        hand_index=setup_bench_index,
    )
    expected_player1_hand_serials_after_bench = (
        after_prizes.players[1].hand_card_serials[:setup_bench_index]
        + after_prizes.players[1].hand_card_serials[setup_bench_index + 1 :]
    )
    assert after_setup_bench.players[1].bench_card_serials == (selected_bench_serial,)
    assert after_setup_bench.players[1].hand_card_serials == expected_player1_hand_serials_after_bench
    assert after_setup_bench.players[1].active_card_serial == selected_active_serial
    assert after_setup_bench.players[1].prize_card_serials == tuple(reversed(player1_deck_serials[-6:]))

    after_setup_finish = core.finish_setup_player(after_setup_bench, player_index=1)
    assert after_setup_finish.players[1].bench_card_serials == (selected_bench_serial,)
    assert after_setup_finish.players[1].hand_card_serials == expected_player1_hand_serials_after_bench
    assert after_setup_finish.players[1].active_card_serial == selected_active_serial
    assert after_setup_finish.players[1].prize_card_serials == tuple(reversed(player1_deck_serials[-6:]))


def test_native_core_deals_prizes_after_both_pregame_actives_are_selected() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    pregame = core.start_battle_pregame("deck.csv", "deck.csv")
    setup = core.select_pregame_first_player(pregame, first_player=1, seed=17)
    first_active = setup.to_observation(player_index=1, native_core=core)["select"]["option"][0]
    setup = core.select_setup_active(setup, player_index=1, hand_index=first_active["index"])
    second_active = setup.to_observation(player_index=0, native_core=core)["select"]["option"][0]
    setup = core.select_setup_active(setup, player_index=0, hand_index=second_active["index"])

    after = core.deal_setup_prizes(setup)

    assert after.first_player == 1
    assert after.current_player == 1
    assert after.players[0].deck_count == 47
    assert after.players[0].hand_count == 6
    assert after.players[0].prize_count == 6
    assert after.players[0].active_card_id is not None
    assert after.players[1].deck_count == 47
    assert after.players[1].hand_count == 6
    assert after.players[1].prize_count == 6
    assert after.players[1].active_card_id is not None
    observation = after.to_observation(player_index=1, native_core=core)
    assert observation["select"]["context"] == 2
    assert observation["select"]["minCount"] == 0
    assert observation["current"]["yourIndex"] == 1
    assert observation["current"]["players"][0]["prize"] == [None, None, None, None, None, None]
    assert observation["current"]["players"][1]["prize"] == [None, None, None, None, None, None]


def test_native_core_rejects_non_60_card_deck(tmp_path: Path) -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)
    bad_deck = tmp_path / "deck.csv"
    bad_deck.write_text("673\n674\n", encoding="utf-8")

    result = core.try_load_deck_csv(bad_deck)

    assert result.ok is False
    assert result.error_code == 2
    assert "expected 60 cards" in result.message


def test_native_core_rejects_non_integer_card_id(tmp_path: Path) -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)
    bad_deck = tmp_path / "deck.csv"
    bad_deck.write_text("\n".join(["673"] * 59 + ["not-a-card"]), encoding="utf-8")

    result = core.try_load_deck_csv(bad_deck)

    assert result.ok is False
    assert result.error_code == 3
    assert "invalid integer" in result.message


def test_force_rebuild_after_library_load_returns_loadable_library(tmp_path: Path) -> None:
    first_library = build_native_core(build_dir=tmp_path, force=True)
    first_core = NativeCore(first_library)
    assert first_core.version == "ptcg-native-core/0.1.0"

    rebuilt_library = build_native_core(build_dir=tmp_path, force=True)
    rebuilt_core = NativeCore(rebuilt_library)

    assert rebuilt_library.exists()
    assert rebuilt_core.version == "ptcg-native-core/0.1.0"


def test_build_script_runs_directly_from_repo_root(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_native_core.py",
            "--force",
            "--build-dir",
            str(tmp_path),
            "--deck",
            "deck.csv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["card_count"] == 60
    assert payload["deck_sha256"] == "2a541d7bf3d9e6b36037123f53f4dfef6348223f79fd27095dafc602a5357c19"
    assert payload["setup"]["seed"] == 17
    assert payload["setup"]["players"][0] == {"deck_count": 47, "hand_count": 7, "prize_count": 6}
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_outputs_player_observation() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "17",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["first_player"] == 1
    assert payload["setup"]["players"][0]["deck_count"] == 47
    assert payload["observation"]["current"]["yourIndex"] == 0
    assert payload["observation"]["current"]["players"][1]["hand"] is None
    assert [option["cardId"] for option in payload["observation"]["select"]["option"]] == [676]
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_can_apply_setup_active_choice() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "17",
            "--active-hand-index",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["observation"]["current"]["players"][0]["active"][0]["id"] == 676
    assert payload["setup"]["players"][0]["active_card_id"] == 676
    assert payload["setup"]["players"][0]["hand_count"] == 6
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_can_apply_bench_and_finish_setup() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "1",
            "--seed",
            "1",
            "--active-hand-index",
            "0",
            "--bench-hand-index",
            "0",
            "--finish-setup",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["players"][1]["active_card_id"] == 675
    assert payload["setup"]["players"][1]["bench_count"] == 1
    assert payload["setup"]["players"][1]["setup_complete"] is True
    assert payload["setup"]["complete"] is False
    assert payload["observation"]["current"]["players"][1]["bench"][0]["id"] == 677
    assert payload["observation"]["select"]["option"] == []
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_can_begin_and_end_turn() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "17",
            "--player0-active-hand-index",
            "2",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "3",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--end-turn-count",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["turn"] == 2
    assert payload["setup"]["current_player"] == 0
    assert payload["setup"]["players"][0]["hand_count"] == 7
    assert payload["setup"]["players"][0]["deck_count"] == 46
    assert payload["observation"]["current"]["yourIndex"] == 0
    assert payload["observation"]["current"]["players"][1]["hand"] is None
    assert payload["observation"]["select"]["type"] == 0
    assert payload["observation"]["select"]["context"] == 0
    assert {"type": 14} in payload["observation"]["select"]["option"]
    assert [option["type"] for option in payload["observation"]["select"]["option"]].count(8) == 3
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_can_apply_main_attach_action() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "17",
            "--active-hand-index",
            "2",
            "--finish-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--main-action",
            "end",
            "--main-action",
            "attach:2:4:0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["turn"] == 2
    assert payload["setup"]["current_player"] == 0
    assert payload["setup"]["players"][0]["hand_count"] == 6
    assert payload["observation"]["current"]["energyAttached"] is True
    active = payload["observation"]["current"]["players"][0]["active"][0]
    assert active["energyCards"] == [{"id": 6, "playerIndex": 0, "serial": 200000}]
    assert active["energies"] == [6]
    assert [option for option in payload["observation"]["select"]["option"] if option["type"] == 8] == []
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_can_apply_main_attack_action() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "1",
            "--seed",
            "1",
            "--active-hand-index",
            "0",
            "--finish-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--main-action",
            "end",
            "--main-action",
            "attach:2:4:0",
            "--main-action",
            "attack:981",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["turn"] == 3
    assert payload["setup"]["current_player"] == 1
    assert payload["observation"]["current"]["result"] == -1
    active = payload["observation"]["current"]["players"][1]["active"][0]
    assert active["id"] == 675
    assert active["hp"] == 80
    assert active["maxHp"] == 110
    assert payload["kaggle_submission_made"] is False


def test_native_setup_snapshot_script_can_apply_main_evolve_action(tmp_path: Path) -> None:
    deck = tmp_path / "evolve_deck.csv"
    deck.write_text("\n".join(str(card_id) for card_id in ([677, 678] * 30)) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            str(deck),
            "--opponent-deck",
            str(deck),
            "--player-index",
            "0",
            "--seed",
            "0",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--main-action",
            "end",
            "--main-action",
            "end",
            "--main-action",
            "evolve:0:4:0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    active = payload["observation"]["current"]["players"][0]["active"][0]
    assert active["id"] == 678
    assert [card["id"] for card in active["preEvolution"]] == [677]
    assert payload["setup"]["players"][0]["hand_count"] == 7
    assert payload["observation"]["logs"][-1]["kind"] == "evolve"
    assert payload["kaggle_submission_made"] is False


def test_native_core_offers_and_applies_stage1_evolution_from_hand_to_active() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=3,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(678,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_damage=30,
                bench_card_ids=(),
                active_energy_card_ids=(6,),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    observation = setup.to_observation(player_index=0, native_core=core)

    assert {
        "type": 9,
        "area": 2,
        "index": 0,
        "cardId": 678,
        "inPlayArea": 4,
        "inPlayIndex": 0,
    } in observation["select"]["option"]

    after = core.evolve_from_hand(setup, hand_index=0, in_play_area=4, in_play_index=0)

    assert after.players[0].active_card_id == 678
    assert after.players[0].active_damage == 30
    assert after.players[0].active_energy_card_ids == (6,)
    assert after.players[0].active_pre_evolution_card_ids == (677,)
    assert after.players[0].hand_card_ids == ()
    evolved_observation = after.to_observation(player_index=0, native_core=core)
    active = evolved_observation["current"]["players"][0]["active"][0]
    assert active["hp"] == 310
    assert active["maxHp"] == 340
    assert [card["id"] for card in active["preEvolution"]] == [677]
    assert after.logs[-1]["kind"] == "evolve"
    assert after.logs[-1]["message"] == "P0 evolved Riolu into Mega Lucario ex."


def test_native_core_rejects_evolution_on_a_players_first_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=1,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(678,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    observation = setup.to_observation(player_index=0, native_core=core)
    result = core.try_evolve_from_hand(setup, hand_index=0, in_play_area=4, in_play_index=0)

    assert all(option["type"] != 9 for option in observation["select"]["option"])
    assert result.ok is False
    assert "first turn" in result.message


def test_native_core_rejects_evolving_a_basic_played_this_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=3,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(678, 677),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_play = core.play_basic_to_bench(setup, hand_index=1)
    observation = after_play.to_observation(player_index=0, native_core=core)
    result = core.try_evolve_from_hand(after_play, hand_index=0, in_play_area=5, in_play_index=0)

    assert observation["current"]["players"][0]["bench"][0]["appearThisTurn"] is True
    assert {
        "type": 9,
        "area": 2,
        "index": 0,
        "cardId": 678,
        "inPlayArea": 5,
        "inPlayIndex": 0,
    } not in observation["select"]["option"]
    assert result.ok is False
    assert "this turn" in result.message


def test_native_core_hariyama_evolution_enters_heave_ho_catcher_target_state() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=3,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(674, 6),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=673,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(677, 676),
                setup_complete=True,
            ),
        ),
    )

    after = core.evolve_from_hand(setup, hand_index=0, in_play_area=4, in_play_index=0)
    observation = after.to_observation(player_index=0, native_core=core)
    blocked_end = core.try_end_turn(after)

    assert after.players[0].active_card_id == 674
    assert after.pending_heave_ho_player == 0
    assert observation["current"]["looking"] == {"effect": "heave_ho_catcher", "playerIndex": 0}
    assert observation["select"]["context"] == 8
    assert observation["select"]["minCount"] == 0
    assert observation["select"]["maxCount"] == 1
    assert observation["select"]["contextCard"] == {"id": 674, "playerIndex": 0}
    assert observation["select"]["effect"] == "heave_ho_catcher"
    assert observation["select"]["option"] == [
        {"type": 3, "area": 5, "index": 0, "playerIndex": 1, "cardId": 677, "effect": "heave_ho_catcher_target"},
        {"type": 3, "area": 5, "index": 1, "playerIndex": 1, "cardId": 676, "effect": "heave_ho_catcher_target"},
        {"type": 16, "effect": "heave_ho_catcher_skip"},
    ]
    assert blocked_end.ok is False
    assert "pending Heave-Ho Catcher target must be resolved" in blocked_end.message


def test_native_core_heave_ho_catcher_switches_opponent_active_with_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=3,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(674,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=673,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                active_damage=20,
                active_energy_card_ids=(6,),
                bench_card_ids=(677, 676),
                bench_damage=(10, 30),
                bench_energy_card_ids=((6, 6), ()),
                setup_complete=True,
            ),
        ),
    )

    pending = core.evolve_from_hand(setup, hand_index=0, in_play_area=4, in_play_index=0)
    after = core.resolve_heave_ho_catcher(pending, bench_index=1)

    assert after.pending_heave_ho_player is None
    assert after.current_player == 0
    assert after.players[1].active_card_id == 676
    assert after.players[1].active_damage == 30
    assert after.players[1].active_energy_card_ids == ()
    assert after.players[1].bench_card_ids == (677, 675)
    assert after.players[1].bench_damage == (10, 20)
    assert after.players[1].bench_energy_card_ids == ((6, 6), (6,))
    assert after.logs[-1]["kind"] == "heave_ho_catcher_target"
    assert after.logs[-1]["message"] == "P0 used Heave-Ho Catcher to switch in Solrock."


def test_native_core_heave_ho_catcher_can_be_skipped() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=3,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(674,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=673,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(677,),
                setup_complete=True,
            ),
        ),
    )

    pending = core.evolve_from_hand(setup, hand_index=0, in_play_area=4, in_play_index=0)
    after = core.skip_heave_ho_catcher(pending)

    assert after.pending_heave_ho_player is None
    assert after.players[1].active_card_id == 675
    assert after.players[1].bench_card_ids == (677,)
    assert after.logs[-1]["kind"] == "heave_ho_catcher_skip"
    assert after.logs[-1]["message"] == "P0 chose not to use Heave-Ho Catcher."


def test_native_core_hariyama_evolution_without_opponent_bench_has_no_pending_ability() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=3,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(674,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=673,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after = core.evolve_from_hand(setup, hand_index=0, in_play_area=4, in_play_index=0)
    observation = after.to_observation(player_index=0, native_core=core)

    assert after.pending_heave_ho_player is None
    assert observation["current"]["looking"] is None
    assert all(option.get("effect") != "heave_ho_catcher_target" for option in observation["select"]["option"])


def test_native_setup_snapshot_script_emits_ordered_battle_logs() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--player-index",
            "1",
            "--view-player-index",
            "0",
            "--seed",
            "1",
            "--active-hand-index",
            "0",
            "--finish-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--main-action",
            "end",
            "--main-action",
            "attach:2:4:0",
            "--main-action",
            "attack:981",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    logs = payload["observation"]["logs"]
    assert [item["kind"] for item in logs] == [
        "setup_active",
        "setup_finish",
        "setup_active",
        "setup_finish",
        "begin_first_turn",
        "end_turn",
        "attach_energy",
        "attack",
    ]
    assert logs[0] == {
        "kind": "setup_active",
        "turn": 0,
        "playerIndex": 1,
        "handIndex": 0,
        "cardId": 675,
        "message": "P1 set Lunatone as Active Pokemon.",
    }
    assert logs[-2]["message"] == "P0 attached Basic {F} Energy to Riolu."
    assert logs[-1]["message"] == "P0 used Accelerating Stab for 30 damage."
    assert payload["viewer_observation"]["logs"] == logs
    assert payload["kaggle_submission_made"] is False


def test_native_core_starts_deterministic_hidden_information_setup() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)

    setup_a = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)
    setup_b = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)
    setup_c = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=18)

    assert setup_a == setup_b
    assert setup_a != setup_c
    assert setup_a.turn == 0
    assert setup_a.first_player == 1
    assert setup_a.current_player == 1

    player0 = setup_a.players[0]
    player1 = setup_a.players[1]
    assert player0.hand_count == 7
    assert player0.prize_count == 6
    assert player0.deck_count == 47
    assert player0.active_card_id is None
    assert player0.bench_card_ids == ()
    assert sorted(player0.hand_card_ids + player0.prize_card_ids + player0.deck_card_ids) == sorted(
        core.load_deck_csv(Path("deck.csv")).cards
    )
    assert player1.hand_count == 7
    assert player1.prize_count == 6
    assert player1.deck_count == 47


def test_native_core_mulligans_setup_hands_until_a_basic_is_available(tmp_path: Path) -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    opponent_deck_cards = [
        169, 169, 169, 169, 190, 190, 190, 190, 666, 666, 666, 666,
        57, 1152, 1152, 1152, 1152, 1121, 1121, 1121, 1121, 1227,
        1227, 1227, 1227, 1122, 1122, 1122, 1122, 1244, 1244, 1244,
        1244, 1182, 1182, 1182, 1182, 1097, 1097, 1097, 1159, 1185,
        1185, 1185, 1185, 1147, 1147, 1147, 1147, 8, 8, 8, 8, 8, 8,
        8, 8, 8, 8, 8,
    ]
    opponent_deck = tmp_path / "archaludon_deck.csv"
    opponent_deck.write_text("".join(f"{card_id}\n" for card_id in opponent_deck_cards), encoding="utf-8")

    setup = core.start_battle_setup(Path("deck.csv"), opponent_deck, seed=17)
    observation = setup.to_observation(player_index=1, native_core=core)

    assert setup.players[1].hand_count == 7
    assert setup.players[1].deck_count == 47
    assert any(core.is_basic_pokemon_card(card_id) for card_id in setup.players[1].hand_card_ids)
    assert observation["select"]["minCount"] == 1
    assert observation["select"]["option"]
    assert sorted(
        setup.players[1].hand_card_ids + setup.players[1].prize_card_ids + setup.players[1].deck_card_ids
    ) == sorted(opponent_deck_cards)


def test_native_core_records_opening_hand_mulligan_counts(tmp_path: Path) -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    sparse_basic_deck_cards = [675] + [1227] * 59
    sparse_basic_deck = tmp_path / "sparse_basic_deck.csv"
    sparse_basic_deck.write_text("".join(f"{card_id}\n" for card_id in sparse_basic_deck_cards), encoding="utf-8")
    pregame = core.start_battle_pregame(sparse_basic_deck, Path("deck.csv"))

    setup = core.select_pregame_first_player(pregame, first_player=1, seed=1)

    assert setup.setup_mulligans[0] == 5
    assert setup.setup_mulligans[1] == 0
    assert setup.players[0].hand_count == 7
    assert setup.players[0].deck_count == 53
    assert any(core.is_basic_pokemon_card(card_id) for card_id in setup.players[0].hand_card_ids)


def test_native_core_applies_mulligan_draw_count_without_erasing_counts(tmp_path: Path) -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    sparse_basic_deck_cards = [675] + [1227] * 59
    sparse_basic_deck = tmp_path / "sparse_basic_deck.csv"
    sparse_basic_deck.write_text("".join(f"{card_id}\n" for card_id in sparse_basic_deck_cards), encoding="utf-8")
    pregame = core.start_battle_pregame(sparse_basic_deck, Path("deck.csv"))
    setup = core.select_pregame_first_player(pregame, first_player=1, seed=1)
    player1_active = setup.to_observation(player_index=1, native_core=core)["select"]["option"][0]
    setup = core.select_setup_active(setup, player_index=1, hand_index=player1_active["index"])
    player0_active = setup.to_observation(player_index=0, native_core=core)["select"]["option"][0]
    setup = core.select_setup_active(setup, player_index=0, hand_index=player0_active["index"])
    setup = core.deal_setup_prizes(setup)

    assert setup.pending_draw_count_player() == 1
    before_hand = setup.players[1].hand_card_ids
    before_deck = setup.players[1].deck_card_ids

    after = core.apply_pregame_draw_count(setup, count=2)

    assert after.setup_mulligans == (5, 0)
    assert after.setup_mulligan_draw_choices == (None, 2)
    assert after.pending_draw_count_player() is None
    assert after.players[1].hand_card_ids == before_hand + before_deck[:2]
    assert after.players[1].deck_card_ids == before_deck[2:]
    assert after.logs[-1]["kind"] == "setup_mulligan_draw_count"
    assert after.logs[-1]["drawnCount"] == 2


def test_native_setup_observation_hides_opponent_hand_and_prize_identities() -> None:
    library_path = build_native_core()
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)

    observation = setup.to_observation(player_index=0)

    assert observation["current"]["yourIndex"] == 0
    assert observation["current"]["firstPlayer"] == 1
    assert observation["current"]["players"][0]["handCount"] == 7
    assert len(observation["current"]["players"][0]["hand"]) == 7
    assert observation["current"]["players"][0]["prize"] == [None, None, None, None, None, None]
    assert observation["current"]["players"][1]["hand"] is None
    assert observation["current"]["players"][1]["handCount"] == 7
    assert observation["current"]["players"][1]["prize"] == [None, None, None, None, None, None]
    assert observation["select"]["type"] == 1
    assert observation["select"]["context"] == 1
    assert observation["select"]["minCount"] == 1
    assert observation["select"]["maxCount"] == 1


def test_native_setup_active_options_only_include_basic_pokemon() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)

    observation = setup.to_observation(player_index=0, native_core=core)

    assert [option["index"] for option in observation["select"]["option"]] == [2]
    assert [option["cardId"] for option in observation["select"]["option"]] == [676]
    assert core.card_metadata(676).name == "Solrock"
    assert core.card_metadata(676).basic is True
    assert core.card_metadata(1227).basic is False


def test_native_core_selects_setup_active_by_hand_index() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)

    after = core.select_setup_active(setup, player_index=0, hand_index=2)

    assert after.players[0].active_card_id == 676
    assert after.players[0].hand_count == 6
    assert after.players[0].hand_card_ids == (1227, 1102, 6, 1141, 6, 6)
    assert after.players[0].deck_count == 47
    assert after.players[0].prize_count == 6
    observation = after.to_observation(player_index=0, native_core=core)
    assert observation["current"]["players"][0]["active"][0]["id"] == 676
    assert observation["select"]["context"] == 2
    assert observation["select"]["minCount"] == 0


def test_native_core_selects_setup_bench_by_hand_index() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=1)
    after_active = core.select_setup_active(setup, player_index=1, hand_index=0)

    observation = after_active.to_observation(player_index=1, native_core=core)
    assert after_active.players[1].active_card_id == 675
    assert [option["index"] for option in observation["select"]["option"]] == [0, 1, 4]
    assert [option["cardId"] for option in observation["select"]["option"]] == [677, 677, 676]

    after_bench = core.select_setup_bench(after_active, player_index=1, hand_index=0)

    assert after_bench.players[1].bench_card_ids == (677,)
    assert after_bench.players[1].hand_card_ids == (677, 6, 674, 676, 6)
    assert after_bench.players[1].setup_complete is False
    observation = after_bench.to_observation(player_index=1, native_core=core)
    assert observation["current"]["players"][1]["bench"][0]["id"] == 677
    assert observation["select"]["context"] == 2
    assert [option["index"] for option in observation["select"]["option"]] == [0, 3]


def test_native_core_finishes_setup_player_and_reports_readiness() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)
    assert core.is_setup_complete(setup) is False

    player0_done = core.finish_setup_player(
        core.select_setup_active(setup, player_index=0, hand_index=2),
        player_index=0,
    )

    assert player0_done.players[0].setup_complete is True
    assert core.is_setup_complete(player0_done) is False
    observation = player0_done.to_observation(player_index=0, native_core=core)
    assert observation["select"]["context"] == 2
    assert observation["select"]["minCount"] == 0
    assert observation["select"]["maxCount"] == 0
    assert observation["select"]["option"] == []

    player1_done = core.finish_setup_player(
        core.select_setup_active(player0_done, player_index=1, hand_index=3),
        player_index=1,
    )

    assert player1_done.players[1].setup_complete is True
    assert core.is_setup_complete(player1_done) is True


def test_native_core_rejects_setup_bench_before_active() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=1)

    result = core.try_select_setup_bench(setup, player_index=1, hand_index=0)

    assert result.ok is False
    assert result.error_code == 8
    assert "Active Pokemon must be selected" in result.message


def test_native_core_rejects_non_basic_setup_bench_choice() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=1)
    after_active = core.select_setup_active(setup, player_index=1, hand_index=0)

    result = core.try_select_setup_bench(after_active, player_index=1, hand_index=2)

    assert result.ok is False
    assert result.error_code == 7
    assert "not a Basic Pokemon" in result.message


def test_native_core_rejects_finish_setup_without_active() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)

    result = core.try_finish_setup_player(setup, player_index=0)

    assert result.ok is False
    assert result.error_code == 8
    assert "Active Pokemon must be selected" in result.message


def test_native_core_rejects_non_basic_setup_active_choice() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)

    result = core.try_select_setup_active(setup, player_index=0, hand_index=0)

    assert result.ok is False
    assert result.error_code == 7
    assert "not a Basic Pokemon" in result.message


def _finished_seed_17_setup(core: NativeCore):
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17)
    setup = core.finish_setup_player(
        core.select_setup_active(setup, player_index=0, hand_index=2),
        player_index=0,
    )
    return core.finish_setup_player(
        core.select_setup_active(setup, player_index=1, hand_index=3),
        player_index=1,
    )


def test_native_core_begins_first_turn_after_both_players_finish_setup() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = _finished_seed_17_setup(core)

    battle = core.begin_first_turn(setup)

    assert battle.turn == 1
    assert battle.current_player == battle.first_player == 1
    assert battle.players[1].hand_count == 7
    assert battle.players[1].deck_count == 46
    assert battle.players[1].hand_card_ids[-1] == 673
    observation = battle.to_observation(player_index=1, native_core=core)
    assert observation["select"]["type"] == 0
    assert observation["select"]["context"] == 0
    assert observation["select"]["minCount"] == 1
    assert observation["select"]["maxCount"] == 1
    assert {"type": 14} in observation["select"]["option"]
    assert [option["type"] for option in observation["select"]["option"]].count(8) == 1
    assert observation["current"]["turn"] == 1
    assert observation["current"]["yourIndex"] == 1


def test_native_core_rejects_begin_first_turn_before_setup_complete() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = core.finish_setup_player(
        core.select_setup_active(
            core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=17),
            player_index=0,
            hand_index=2,
        ),
        player_index=0,
    )

    result = core.try_begin_first_turn(setup)

    assert result.ok is False
    assert result.error_code == 11
    assert "both players must finish setup" in result.message


def test_native_core_ends_turn_and_draws_for_next_player() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = core.begin_first_turn(_finished_seed_17_setup(core))

    next_turn = core.end_turn(battle)

    assert next_turn.turn == 2
    assert next_turn.current_player == 0
    assert next_turn.players[0].hand_count == 7
    assert next_turn.players[0].deck_count == 46
    assert next_turn.players[0].hand_card_ids[-1] == 1142
    observation = next_turn.to_observation(player_index=0, native_core=core)
    assert observation["select"]["type"] == 0
    assert observation["select"]["context"] == 0
    assert {"type": 14} in observation["select"]["option"]
    assert [option["type"] for option in observation["select"]["option"]].count(8) == 3


def test_native_core_rejects_end_turn_before_battle_begins() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = _finished_seed_17_setup(core)

    result = core.try_end_turn(setup)

    assert result.ok is False
    assert result.error_code == 12
    assert "battle has not begun" in result.message


def _turn2_seed_17_battle(core: NativeCore):
    return core.end_turn(core.begin_first_turn(_finished_seed_17_setup(core)))


def _seed_1_first_turn_with_p1_extra_basics(core: NativeCore):
    setup = core.start_battle_setup(Path("deck.csv"), Path("deck.csv"), seed=1)
    setup = core.finish_setup_player(core.select_setup_active(setup, player_index=0, hand_index=0), player_index=0)
    setup = core.finish_setup_player(core.select_setup_active(setup, player_index=1, hand_index=0), player_index=1)
    return core.begin_first_turn(setup)


def _seed_1_turn2_p0_riolu_with_energy(core: NativeCore):
    battle = core.end_turn(_seed_1_first_turn_with_p1_extra_basics(core))
    return core.attach_energy(battle, hand_index=2, in_play_area=4, in_play_index=0)


def test_native_main_options_include_end_and_attach_energy_to_active() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _turn2_seed_17_battle(core)

    observation = battle.to_observation(player_index=0, native_core=core)

    assert observation["select"]["type"] == 0
    assert observation["select"]["context"] == 0
    assert {"type": 14} in observation["select"]["option"]
    attach_options = [option for option in observation["select"]["option"] if option["type"] == 8]
    assert attach_options == [
        {"type": 8, "area": 2, "index": 2, "cardId": 6, "inPlayArea": 4, "inPlayIndex": 0},
        {"type": 8, "area": 2, "index": 4, "cardId": 6, "inPlayArea": 4, "inPlayIndex": 0},
        {"type": 8, "area": 2, "index": 5, "cardId": 6, "inPlayArea": 4, "inPlayIndex": 0},
    ]
    assert core.card_metadata(6).card_type == 5
    assert core.card_metadata(6).energy_type == 6


def test_native_core_attaches_energy_from_hand_to_active_once_per_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _turn2_seed_17_battle(core)

    after_attach = core.attach_energy(battle, hand_index=2, in_play_area=4, in_play_index=0)

    assert after_attach.energy_attached is True
    assert after_attach.players[0].hand_card_ids == (1227, 1102, 1141, 6, 6, 1142)
    assert after_attach.players[0].active_energy_card_ids == (6,)
    observation = after_attach.to_observation(player_index=0, native_core=core)
    active = observation["current"]["players"][0]["active"][0]
    assert active["energyCards"] == [{"id": 6, "serial": 200000, "playerIndex": 0}]
    assert active["energies"] == [6]
    assert [option for option in observation["select"]["option"] if option["type"] == 8] == []
    assert {"type": 14} in observation["select"]["option"]

    result = core.try_attach_energy(after_attach, hand_index=3, in_play_area=4, in_play_index=0)
    assert result.ok is False
    assert result.error_code == 16
    assert "Energy has already been attached" in result.message


def test_native_main_options_include_play_basic_pokemon_to_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _seed_1_first_turn_with_p1_extra_basics(core)

    observation = battle.to_observation(player_index=1, native_core=core)

    play_options = [
        option
        for option in observation["select"]["option"]
        if option["type"] == 7 and option.get("effect") is None
    ]
    assert play_options == [
        {"type": 7, "index": 0, "cardId": 677},
        {"type": 7, "index": 1, "cardId": 677},
        {"type": 7, "index": 4, "cardId": 676},
    ]
    assert all(option.get("effect") != "poke_pad" for option in observation["select"]["option"])
    assert {"type": 14} in observation["select"]["option"]


def test_native_core_plays_basic_pokemon_from_hand_to_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _seed_1_first_turn_with_p1_extra_basics(core)

    after_play = core.play_basic_to_bench(battle, hand_index=0)

    assert after_play.players[1].bench_card_ids == (677,)
    assert after_play.players[1].hand_card_ids == (677, 6, 674, 676, 6, 678)
    observation = after_play.to_observation(player_index=1, native_core=core)
    assert observation["current"]["players"][1]["bench"][0]["id"] == 677
    play_options = [
        option
        for option in observation["select"]["option"]
        if option["type"] == 7 and option.get("effect") is None
    ]
    assert [option["index"] for option in play_options] == [0, 3]
    assert all(option.get("effect") != "poke_pad" for option in observation["select"]["option"])


def test_native_core_playing_dusk_ball_enters_bottom_seven_search_state() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6, 6, 6, 1141, 677, 6, 678, 6, 676, 1102),
                hand_card_ids=(1102,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    dusk_options = [option for option in before["select"]["option"] if option.get("effect") == "dusk_ball"]
    after = core.play_dusk_ball(setup, hand_index=0)
    observation = after.to_observation(player_index=0, native_core=core)

    assert dusk_options == [{"type": 7, "index": 0, "cardId": 1102, "effect": "dusk_ball"}]
    assert "deckIndex" not in dusk_options[0]
    assert "targetCardId" not in dusk_options[0]
    assert after.pending_dusk_ball_player == 0
    assert after.players[0].hand_card_ids == ()
    assert after.players[0].discard_card_ids == (1102,)
    assert observation["current"]["looking"] == {"effect": "dusk_ball", "playerIndex": 0}
    assert observation["select"]["context"] == 7
    assert observation["select"]["minCount"] == 0
    assert observation["select"]["maxCount"] == 1
    assert [
        {key: option[key] for key in ("type", "area", "index", "playerIndex", "cardId", "effect")}
        for option in observation["select"]["option"]
        if option["type"] == 3
    ] == [
        {"type": 3, "area": 1, "index": 4, "playerIndex": 0, "cardId": 677, "effect": "dusk_ball_pick"},
        {"type": 3, "area": 1, "index": 6, "playerIndex": 0, "cardId": 678, "effect": "dusk_ball_pick"},
        {"type": 3, "area": 1, "index": 8, "playerIndex": 0, "cardId": 676, "effect": "dusk_ball_pick"},
    ]
    assert {"type": 16, "effect": "dusk_ball_skip"} in observation["select"]["option"]
    assert after.logs[-1]["kind"] == "play_dusk_ball"
    assert after.logs[-1]["message"] == "P0 played Dusk Ball and looked at the bottom 7 cards."


def test_native_core_resolves_dusk_ball_pick_without_leaking_unselected_cards() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6, 6, 6, 1141, 677, 6, 678, 6, 676, 1102),
                hand_card_ids=(1102,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    pending = core.play_dusk_ball(setup, hand_index=0)
    after = core.resolve_dusk_ball(pending, deck_index=6, reveal=True)
    observation = after.to_observation(player_index=0, native_core=core)

    assert after.pending_dusk_ball_player is None
    assert after.players[0].hand_card_ids == (678,)
    assert after.players[0].deck_count == 9
    assert 678 not in after.players[0].deck_card_ids
    assert after.players[0].discard_card_ids == (1102,)
    assert observation["current"]["looking"] is None
    assert all(option.get("effect") != "dusk_ball_pick" for option in observation["select"]["option"])
    assert after.logs[-1]["kind"] == "dusk_ball_pick"
    assert after.logs[-1]["message"] == "P0 revealed Mega Lucario ex with Dusk Ball."


def test_native_setup_snapshot_script_can_apply_dusk_ball_search(tmp_path: Path) -> None:
    deck = tmp_path / "dusk_deck.csv"
    deck.write_text(
        "\n".join(str(card_id) for card_id in ([1102] * 4 + [678] + [676] * 55))
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            str(deck),
            "--opponent-deck",
            str(deck),
            "--player-index",
            "0",
            "--seed",
            "2",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--main-action",
            "dusk:1",
            "--main-action",
            "duskpick:40",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["observation"]["current"]["looking"] is None
    assert 678 in [card["id"] for card in payload["observation"]["current"]["players"][0]["hand"]]
    assert payload["observation"]["logs"][-2]["kind"] == "play_dusk_ball"
    assert payload["observation"]["logs"][-1]["kind"] == "dusk_ball_pick"
    assert payload["kaggle_submission_made"] is False


def test_native_core_playing_fighting_gong_enters_basic_fighting_search_state() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(674, 6, 677, 678, 1141, 675, 1, 676, 1152),
                hand_card_ids=(1142, 1227),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=673,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    gong_options = [option for option in before["select"]["option"] if option.get("effect") == "fighting_gong"]
    after = core.play_fighting_gong(setup, hand_index=0)
    blocked_supporter = core.try_play_lillies_determination(after, hand_index=0)
    observation = after.to_observation(player_index=0, native_core=core)

    assert gong_options == [{"type": 7, "index": 0, "cardId": 1142, "effect": "fighting_gong"}]
    assert after.pending_fighting_gong_player == 0
    assert after.players[0].hand_card_ids == (1227,)
    assert after.players[0].discard_card_ids == (1142,)
    assert observation["current"]["looking"] == {"effect": "fighting_gong", "playerIndex": 0}
    assert observation["select"]["context"] == 9
    assert observation["select"]["minCount"] == 0
    assert observation["select"]["maxCount"] == 1
    assert [
        {key: option[key] for key in ("type", "area", "index", "playerIndex", "cardId", "effect")}
        for option in observation["select"]["option"]
        if option["type"] == 3
    ] == [
        {"type": 3, "area": 1, "index": 1, "playerIndex": 0, "cardId": 6, "effect": "fighting_gong_pick"},
        {"type": 3, "area": 1, "index": 2, "playerIndex": 0, "cardId": 677, "effect": "fighting_gong_pick"},
        {"type": 3, "area": 1, "index": 5, "playerIndex": 0, "cardId": 675, "effect": "fighting_gong_pick"},
        {"type": 3, "area": 1, "index": 7, "playerIndex": 0, "cardId": 676, "effect": "fighting_gong_pick"},
    ]
    assert {"type": 16, "effect": "fighting_gong_skip"} in observation["select"]["option"]
    assert blocked_supporter.ok is False
    assert "pending Fighting Gong search must be resolved" in blocked_supporter.message
    assert after.logs[-1]["kind"] == "play_fighting_gong"
    assert after.logs[-1]["message"] == "P0 played Fighting Gong and searched the deck."


def test_native_core_resolves_fighting_gong_pick_from_deck_to_hand() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(674, 6, 677, 678, 1141, 675, 1, 676, 1152),
                hand_card_ids=(1142, 1227),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=673,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    pending = core.play_fighting_gong(setup, hand_index=0)
    after = core.resolve_fighting_gong(pending, deck_index=2, reveal=True)
    observation = after.to_observation(player_index=0, native_core=core)

    assert after.pending_fighting_gong_player is None
    assert after.players[0].hand_card_ids == (1227, 677)
    assert after.players[0].deck_count == 8
    assert 677 not in after.players[0].deck_card_ids
    assert after.players[0].discard_card_ids == (1142,)
    assert observation["current"]["looking"] is None
    assert all(option.get("effect") != "fighting_gong_pick" for option in observation["select"]["option"])
    assert after.logs[-1]["kind"] == "fighting_gong_pick"
    assert after.logs[-1]["message"] == "P0 revealed Riolu with Fighting Gong."


def test_native_setup_snapshot_script_can_apply_fighting_gong_search(tmp_path: Path) -> None:
    deck = tmp_path / "fighting_gong_deck.csv"
    deck.write_text(
        "\n".join(str(card_id) for card_id in ([1142] * 4 + [676] * 48 + [6] * 8))
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            str(deck),
            "--opponent-deck",
            str(deck),
            "--player-index",
            "0",
            "--seed",
            "2",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--main-action",
            "gong:1",
            "--main-action",
            "gongpick:0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["observation"]["current"]["looking"] is None
    assert 676 in [card["id"] for card in payload["observation"]["current"]["players"][0]["hand"]]
    assert payload["observation"]["logs"][-2]["kind"] == "play_fighting_gong"
    assert payload["observation"]["logs"][-1]["kind"] == "fighting_gong_pick"
    assert payload["kaggle_submission_made"] is False


def test_native_core_poke_pad_searches_non_rulebox_pokemon() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(678, 677, 6, 674, 675),
                hand_card_ids=(1152, 1227),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    pad_options = [option for option in before["select"]["option"] if option.get("effect") == "poke_pad"]
    pending = core.play_poke_pad(setup, hand_index=0)
    blocked_supporter = core.try_play_lillies_determination(pending, hand_index=0)
    pending_observation = pending.to_observation(player_index=0, native_core=core)
    pick_options = [
        {key: option[key] for key in ("type", "area", "index", "playerIndex", "cardId", "effect")}
        for option in pending_observation["select"]["option"]
        if option.get("effect") == "poke_pad_pick"
    ]
    after = core.resolve_poke_pad(pending, deck_index=1, reveal=True)

    assert pad_options == [{"type": 7, "index": 0, "cardId": 1152, "effect": "poke_pad"}]
    assert pending.pending_poke_pad_player == 0
    assert pending.players[0].hand_card_ids == (1227,)
    assert pending.players[0].discard_card_ids == (1152,)
    assert pending_observation["current"]["looking"] == {"effect": "poke_pad", "playerIndex": 0}
    assert pending_observation["select"]["context"] == 10
    assert pick_options == [
        {"type": 3, "area": 1, "index": 1, "playerIndex": 0, "cardId": 677, "effect": "poke_pad_pick"},
        {"type": 3, "area": 1, "index": 3, "playerIndex": 0, "cardId": 674, "effect": "poke_pad_pick"},
        {"type": 3, "area": 1, "index": 4, "playerIndex": 0, "cardId": 675, "effect": "poke_pad_pick"},
    ]
    assert {"type": 16, "effect": "poke_pad_skip"} in pending_observation["select"]["option"]
    assert blocked_supporter.ok is False
    assert "pending Poke Pad search must be resolved" in blocked_supporter.message
    assert after.pending_poke_pad_player is None
    assert after.players[0].hand_card_ids == (1227, 677)
    assert 678 in after.players[0].deck_card_ids
    assert 677 not in after.players[0].deck_card_ids
    assert after.logs[-2]["kind"] == "play_poke_pad"
    assert after.logs[-1]["kind"] == "poke_pad_pick"
    assert after.logs[-1]["message"] == "P0 revealed Riolu with Poke Pad."


def test_native_setup_snapshot_script_can_apply_poke_pad_from_deckcsv() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "86",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "pokepad:3",
            "--main-action",
            "pokepadpick:2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["pending_poke_pad_player"] is None
    assert payload["observation"]["current"]["players"][0]["discard"][0]["id"] == 1152
    assert payload["observation"]["current"]["players"][0]["hand"][-1]["id"] == 677
    assert payload["observation"]["logs"][-1]["kind"] == "poke_pad_pick"
    assert payload["kaggle_submission_made"] is False


def test_native_core_switch_swaps_active_with_bench_target() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(1123, 1227),
                discard_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_damage=10,
                active_energy_card_ids=(6,),
                bench_card_ids=(676, 675),
                bench_damage=(20, 0),
                bench_energy_card_ids=((6, 6), ()),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    switch_options = [option for option in before["select"]["option"] if option.get("effect") == "switch"]
    pending = core.play_switch(setup, hand_index=0)
    blocked_attack = core.try_use_attack(pending, attack_id=981)
    pending_observation = pending.to_observation(player_index=0, native_core=core)
    target_options = [
        {key: option[key] for key in ("type", "area", "index", "playerIndex", "cardId", "effect")}
        for option in pending_observation["select"]["option"]
        if option.get("effect") == "switch_target"
    ]
    after = core.resolve_switch(pending, bench_index=1)

    assert switch_options == [{"type": 7, "index": 0, "cardId": 1123, "effect": "switch"}]
    assert pending.pending_switch_player == 0
    assert pending.players[0].hand_card_ids == (1227,)
    assert pending.players[0].discard_card_ids == (1123,)
    assert pending_observation["current"]["looking"] == {"effect": "switch", "playerIndex": 0}
    assert pending_observation["select"]["context"] == 11
    assert target_options == [
        {"type": 3, "area": 5, "index": 0, "playerIndex": 0, "cardId": 676, "effect": "switch_target"},
        {"type": 3, "area": 5, "index": 1, "playerIndex": 0, "cardId": 675, "effect": "switch_target"},
    ]
    assert blocked_attack.ok is False
    assert "pending Switch target must be resolved" in blocked_attack.message
    assert after.pending_switch_player is None
    assert after.players[0].active_card_id == 675
    assert after.players[0].active_damage == 0
    assert after.players[0].active_energy_card_ids == ()
    assert after.players[0].bench_card_ids == (676, 677)
    assert after.players[0].bench_damage == (20, 10)
    assert after.players[0].bench_energy_card_ids == ((6, 6), (6,))
    assert after.logs[-2]["kind"] == "play_switch"
    assert after.logs[-1]["kind"] == "switch_target"
    assert after.logs[-1]["message"] == "P0 switched Riolu with Lunatone."


def test_native_setup_snapshot_script_can_apply_switch_from_deckcsv() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "38",
            "--player0-active-hand-index",
            "0",
            "--player0-bench-hand-index",
            "3",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "6",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "switch:3",
            "--main-action",
            "switchtarget:0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["pending_switch_player"] is None
    assert payload["observation"]["current"]["players"][0]["discard"][0]["id"] == 1123
    assert payload["observation"]["current"]["players"][0]["active"][0]["id"] == 677
    assert payload["observation"]["current"]["players"][0]["bench"][0]["id"] == 675
    assert payload["observation"]["logs"][-1]["kind"] == "switch_target"
    assert payload["kaggle_submission_made"] is False


def test_native_core_plays_lillies_determination_as_once_per_turn_supporter() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(675, 676, 677, 678, 6, 6, 673, 674),
                hand_card_ids=(1227, 1102, 673, 6),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    lillie_options = [
        option for option in before["select"]["option"] if option.get("effect") == "lillies_determination"
    ]
    after = core.play_lillies_determination(setup, hand_index=0)
    observation = after.to_observation(player_index=0, native_core=core)
    second_supporter = core.try_play_lillies_determination(after, hand_index=0)

    assert lillie_options == [
        {"type": 7, "index": 0, "cardId": 1227, "effect": "lillies_determination"}
    ]
    assert after.players[0].hand_count == 8
    assert after.players[0].deck_count == 3
    assert after.players[0].discard_card_ids == (1227,)
    assert observation["current"]["supporterPlayed"] is True
    assert all(option.get("effect") != "lillies_determination" for option in observation["select"]["option"])
    assert after.logs[-1]["kind"] == "play_lillies_determination"
    assert after.logs[-1]["message"] == "P0 played Lillie's Determination and drew 8 cards."
    assert second_supporter.ok is False
    assert second_supporter.error_code == 27
    assert "Supporter has already been played" in second_supporter.message


def test_native_core_blocks_non_carmine_supporters_on_first_players_first_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=1,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(675, 676, 677, 678, 6, 6, 673, 674),
                hand_card_ids=(1227, 1182, 1192),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(673,),
                setup_complete=True,
            ),
        ),
    )

    observation = setup.to_observation(player_index=0, native_core=core)
    supporter_effects = {
        option.get("effect")
        for option in observation["select"]["option"]
        if option.get("effect") in {"lillies_determination", "boss_orders", "carmine"}
    }
    blocked_lillie = core.try_play_lillies_determination(setup, hand_index=0)
    blocked_boss = core.try_play_boss_orders(setup, hand_index=1)
    after_carmine = core.play_carmine(setup, hand_index=2)

    assert supporter_effects == {"carmine"}
    assert blocked_lillie.ok is False
    assert blocked_lillie.error_code == 44
    assert "first player's first turn" in blocked_lillie.message
    assert blocked_boss.ok is False
    assert blocked_boss.error_code == 44
    assert "first player's first turn" in blocked_boss.message
    assert after_carmine.supporter_played is True
    assert after_carmine.logs[-1]["message"] == "P0 played Carmine and drew 5 cards."


def test_native_setup_snapshot_script_can_apply_lillies_determination(tmp_path: Path) -> None:
    deck = tmp_path / "lillie_deck.csv"
    deck.write_text(
        "\n".join(str(card_id) for card_id in ([676] * 48 + [1227] * 4 + [6] * 8))
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            str(deck),
            "--opponent-deck",
            str(deck),
            "--player-index",
            "0",
            "--seed",
            "1",
            "--player0-active-hand-index",
            "1",
            "--finish-player0-setup",
            "--auto-finish-remaining-setup",
            "--begin-first-turn",
            "--end-turn-count",
            "1",
            "--main-action",
            "lillie:4",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["observation"]["current"]["supporterPlayed"] is True
    assert payload["setup"]["players"][0]["hand_count"] == 8
    assert payload["observation"]["current"]["players"][0]["discard"][0]["id"] == 1227
    assert payload["observation"]["logs"][-1]["kind"] == "play_lillies_determination"
    assert payload["kaggle_submission_made"] is False


def test_native_core_plays_carmine_by_discarding_hand_and_drawing_5() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=1,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(675, 676, 677, 678, 6, 6),
                hand_card_ids=(1192, 1102, 673, 6),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    carmine_options = [option for option in before["select"]["option"] if option.get("effect") == "carmine"]
    after = core.play_carmine(setup, hand_index=0)
    observation = after.to_observation(player_index=0, native_core=core)
    second_supporter = core.try_play_lillies_determination(after, hand_index=0)

    assert carmine_options == [{"type": 7, "index": 0, "cardId": 1192, "effect": "carmine"}]
    assert after.supporter_played is True
    assert after.players[0].hand_card_ids == (6, 6, 678, 677, 676)
    assert after.players[0].deck_card_ids == (675,)
    assert after.players[0].discard_card_ids == (1192, 1102, 673, 6)
    assert observation["current"]["supporterPlayed"] is True
    assert all(option.get("effect") != "carmine" for option in observation["select"]["option"])
    assert after.logs[-1]["kind"] == "play_carmine"
    assert after.logs[-1]["message"] == "P0 played Carmine and drew 5 cards."
    assert second_supporter.ok is False
    assert second_supporter.error_code == 27
    assert "Supporter has already been played" in second_supporter.message


def test_native_setup_snapshot_script_can_apply_carmine_from_deckcsv() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "4",
            "--player0-active-hand-index",
            "3",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "carmine:2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["observation"]["current"]["supporterPlayed"] is True
    assert payload["setup"]["players"][0]["hand_count"] == 5
    assert payload["observation"]["current"]["players"][0]["discard"][0]["id"] == 1192
    assert payload["observation"]["logs"][-1]["kind"] == "play_carmine"
    assert payload["kaggle_submission_made"] is False


def test_native_core_boss_orders_enters_opponent_bench_target_state() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6, 6, 6),
                hand_card_ids=(1182, 1227),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(677, 673),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    boss_options = [option for option in before["select"]["option"] if option.get("effect") == "boss_orders"]
    after = core.play_boss_orders(setup, hand_index=0)
    observation = after.to_observation(player_index=0, native_core=core)
    blocked_supporter = core.try_play_lillies_determination(after, hand_index=0)

    assert boss_options == [{"type": 7, "index": 0, "cardId": 1182, "effect": "boss_orders"}]
    assert after.pending_boss_orders_player == 0
    assert after.supporter_played is True
    assert after.players[0].hand_card_ids == (1227,)
    assert after.players[0].discard_card_ids == (1182,)
    assert observation["current"]["looking"] == {"effect": "boss_orders", "playerIndex": 0}
    assert observation["select"]["context"] == 8
    assert observation["select"]["option"] == [
        {"type": 3, "area": 5, "index": 0, "playerIndex": 1, "cardId": 677, "effect": "boss_orders_target"},
        {"type": 3, "area": 5, "index": 1, "playerIndex": 1, "cardId": 673, "effect": "boss_orders_target"},
    ]
    assert blocked_supporter.ok is False
    assert "pending Boss's Orders target must be resolved" in blocked_supporter.message
    assert after.logs[-1]["kind"] == "play_boss_orders"


def test_native_core_resolves_boss_orders_by_switching_opponent_active_with_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6, 6, 6),
                hand_card_ids=(1182,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                active_damage=20,
                active_energy_card_ids=(6,),
                bench_card_ids=(677, 673),
                bench_damage=(0, 10),
                bench_energy_card_ids=((), (6, 6)),
                setup_complete=True,
            ),
        ),
    )

    pending = core.play_boss_orders(setup, hand_index=0)
    after = core.resolve_boss_orders(pending, bench_index=1)
    observation = after.to_observation(player_index=0, native_core=core)

    assert after.pending_boss_orders_player is None
    assert after.current_player == 0
    assert after.players[1].active_card_id == 673
    assert after.players[1].active_damage == 10
    assert after.players[1].active_energy_card_ids == (6, 6)
    assert after.players[1].bench_card_ids == (677, 675)
    assert after.players[1].bench_damage == (0, 20)
    assert after.players[1].bench_energy_card_ids == ((), (6,))
    assert observation["current"]["looking"] is None
    assert all(option.get("effect") != "boss_orders_target" for option in observation["select"]["option"])
    assert after.logs[-1]["kind"] == "boss_orders_target"
    assert after.logs[-1]["message"] == "P0 used Boss's Orders to switch in Makuhita."


def test_native_setup_snapshot_script_can_apply_boss_orders(tmp_path: Path) -> None:
    deck = tmp_path / "boss_deck.csv"
    deck.write_text(
        "\n".join(str(card_id) for card_id in ([676] * 44 + [677] * 8 + [1182] * 4 + [6] * 4))
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            str(deck),
            "--opponent-deck",
            str(deck),
            "--player-index",
            "0",
            "--seed",
            "1",
            "--player0-active-hand-index",
            "1",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--player1-bench-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "end",
            "--main-action",
            "boss:2",
            "--main-action",
            "bosstarget:0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["observation"]["current"]["players"][1]["active"][0]["id"] == 676
    assert payload["observation"]["current"]["players"][1]["bench"][0]["id"] == 676
    assert payload["observation"]["current"]["supporterPlayed"] is True
    assert payload["observation"]["logs"][-2]["kind"] == "play_boss_orders"
    assert payload["observation"]["logs"][-1]["kind"] == "boss_orders_target"
    assert payload["kaggle_submission_made"] is False


def test_native_core_rejects_non_basic_play_and_non_energy_attach() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _turn2_seed_17_battle(core)

    play_result = core.try_play_basic_to_bench(battle, hand_index=0)
    assert play_result.ok is False
    assert play_result.error_code == 7
    assert "not a Basic Pokemon" in play_result.message

    attach_result = core.try_attach_energy(battle, hand_index=0, in_play_area=4, in_play_index=0)
    assert attach_result.ok is False
    assert attach_result.error_code == 15
    assert "not an Energy card" in attach_result.message


def test_native_core_offers_and_attaches_heros_cape_to_active() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(1159,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_damage=30,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    observation = setup.to_observation(player_index=0, native_core=core)

    assert {
        "type": 8,
        "area": 2,
        "index": 0,
        "cardId": 1159,
        "effect": "heros_cape",
        "inPlayArea": 4,
        "inPlayIndex": 0,
    } in observation["select"]["option"]

    after = core.attach_heros_cape(setup, hand_index=0, in_play_area=4, in_play_index=0)
    active = after.to_observation(player_index=0, native_core=core)["current"]["players"][0]["active"][0]

    assert after.players[0].active_tool_card_id == 1159
    assert after.players[0].hand_card_ids == ()
    assert active["maxHp"] == 180
    assert active["hp"] == 150
    assert [card["id"] for card in active["tools"]] == [1159]
    assert after.logs[-1]["kind"] == "attach_tool"
    assert after.logs[-1]["message"] == "P0 attached Hero's Cape to Riolu."


def test_native_core_heros_cape_prevents_knockout_until_boosted_hp_is_reached() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    survives = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=1,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_damage=140,
                active_tool_card_id=1159,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=677,
                active_energy_card_ids=(6,),
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )
    knocked_out = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=1,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_damage=150,
                active_tool_card_id=1159,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=677,
                active_energy_card_ids=(6,),
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_survival_attack = core.use_attack(survives, attack_id=981)
    after_knockout_attack = core.use_attack(knocked_out, attack_id=981)

    survival_active = after_survival_attack.to_observation(player_index=0, native_core=core)["current"]["players"][0][
        "active"
    ][0]
    assert survival_active["hp"] == 10
    assert survival_active["maxHp"] == 180
    assert after_survival_attack.players[0].active_card_id == 677
    assert after_survival_attack.players[1].prize_count == 6

    assert after_knockout_attack.players[0].active_card_id is None
    assert after_knockout_attack.players[0].discard_card_ids == (677, 1159)
    assert after_knockout_attack.players[1].prize_count == 5
    assert after_knockout_attack.result == 1


def test_native_core_heros_cape_moves_with_switch() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_tool_card_id=1159,
                bench_card_ids=(676,),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after = core.resolve_switch(replace(setup, pending_switch_player=0), bench_index=0)
    observation = after.to_observation(player_index=0, native_core=core)

    assert after.players[0].active_card_id == 676
    assert after.players[0].active_tool_card_id is None
    assert after.players[0].bench_card_ids == (677,)
    assert after.players[0].bench_tool_card_ids == (1159,)
    assert observation["current"]["players"][0]["active"][0]["tools"] == []
    assert [card["id"] for card in observation["current"]["players"][0]["bench"][0]["tools"]] == [1159]


def test_native_core_offers_and_plays_gravity_mountain_stadium() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(1252,),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=167,
                active_damage=30,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=121,
                active_damage=30,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)

    assert {"type": 7, "index": 0, "cardId": 1252, "effect": "gravity_mountain"} in before["select"]["option"]

    after = core.play_gravity_mountain(setup, hand_index=0)
    observation = after.to_observation(player_index=0, native_core=core)
    active = observation["current"]["players"][0]["active"][0]
    opponent_active = observation["current"]["players"][1]["active"][0]

    assert after.stadium_card_id == 1252
    assert after.stadium_player_index == 0
    assert after.stadium_played is True
    assert after.players[0].hand_card_ids == ()
    assert observation["current"]["stadiumPlayed"] is True
    assert observation["current"]["stadium"] == [{"id": 1252, "serial": 600000, "playerIndex": 0}]
    assert active["maxHp"] == 110
    assert active["hp"] == 80
    assert opponent_active["maxHp"] == 290
    assert opponent_active["hp"] == 260
    assert after.logs[-1]["kind"] == "play_stadium"
    assert after.logs[-1]["message"] == "P0 played Gravity Mountain."


def test_native_setup_snapshot_script_can_apply_gravity_mountain(tmp_path: Path) -> None:
    deck = tmp_path / "gravity_deck.csv"
    deck.write_text(
        "\n".join(str(card_id) for card_id in ([677] * 54 + [1252] * 6)) + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            str(deck),
            "--opponent-deck",
            str(deck),
            "--player-index",
            "0",
            "--seed",
            "0",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "stadium:0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["stadium_card_id"] == 1252
    assert payload["setup"]["stadium_player_index"] == 0
    assert payload["setup"]["stadium_played"] is True
    assert payload["observation"]["current"]["stadium"] == [{"id": 1252, "playerIndex": 0, "serial": 600000}]
    assert payload["observation"]["current"]["stadiumPlayed"] is True
    assert payload["observation"]["logs"][-1]["kind"] == "play_stadium"
    assert payload["kaggle_submission_made"] is False


def test_native_core_gravity_mountain_changes_stage2_knockout_threshold() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    base = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=1,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=167,
                active_damage=80,
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=677,
                active_energy_card_ids=(6,),
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    without_stadium = core.use_attack(base, attack_id=981)
    with_stadium = core.use_attack(
        replace(base, stadium_card_id=1252, stadium_player_index=0),
        attack_id=981,
    )

    assert without_stadium.players[0].active_card_id == 167
    assert without_stadium.players[0].active_damage == 110
    assert without_stadium.players[1].prize_count == 6

    assert with_stadium.players[0].active_card_id is None
    assert with_stadium.players[0].discard_card_ids == (167,)
    assert with_stadium.players[1].prize_count == 5
    assert with_stadium.result == 1


def test_native_main_options_include_ready_active_attack() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _seed_1_turn2_p0_riolu_with_energy(core)

    observation = battle.to_observation(player_index=0, native_core=core)

    assert observation["current"]["players"][0]["active"][0]["hp"] == 80
    assert observation["current"]["players"][0]["active"][0]["maxHp"] == 80
    attack_options = [option for option in observation["select"]["option"] if option["type"] == 13]
    assert attack_options == [{"type": 13, "attackId": 981}]
    assert {"type": 14} in observation["select"]["option"]


def test_native_core_resolves_basic_attack_damage_and_turn_advance() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _seed_1_turn2_p0_riolu_with_energy(core)

    after_attack = core.use_attack(battle, attack_id=981)

    assert after_attack.turn == 3
    assert after_attack.current_player == 1
    assert after_attack.players[1].hand_count == 8
    observation = after_attack.to_observation(player_index=1, native_core=core)
    damaged_active = observation["current"]["players"][1]["active"][0]
    assert damaged_active["id"] == 675
    assert damaged_active["hp"] == 80
    assert damaged_active["maxHp"] == 110
    assert observation["current"]["result"] == -1
    assert {"type": 14} in observation["select"]["option"]


def test_native_card_metadata_exposes_weakness_and_resistance_types() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)

    hippopotas = core.card_metadata(22)
    girafarig = core.card_metadata(38)

    assert hippopotas.energy_type == 6
    assert hippopotas.weakness_type == 1
    assert hippopotas.resistance_type is None
    assert girafarig.energy_type == 5
    assert girafarig.weakness_type == 7
    assert girafarig.resistance_type == 6


def test_native_card_metadata_exposes_retreat_cost() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)

    assert core.card_metadata(675).retreat_cost == 1
    assert core.card_metadata(677).retreat_cost == 2


def test_native_core_retreat_discards_cost_then_promotes_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_energy_card_ids=(6, 6),
                bench_card_ids=(675, 676),
                bench_energy_card_ids=((), (6,)),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    observation = setup.to_observation(player_index=0, native_core=core)
    pending = core.start_retreat(setup)
    discard_observation = pending.to_observation(player_index=0, native_core=core)
    after_first_discard = core.resolve_retreat_discard(pending, energy_index=0)
    after_second_discard = core.resolve_retreat_discard(after_first_discard, energy_index=0)
    promote_observation = after_second_discard.to_observation(player_index=0, native_core=core)
    after_promote = core.resolve_retreat_promote(after_second_discard, bench_index=1)
    next_turn = core.end_turn(after_promote)

    assert {"type": 12} in observation["select"]["option"]
    assert pending.retreated is True
    assert pending.pending_retreat_player == 0
    assert pending.pending_retreat_remaining == 2
    assert discard_observation["current"]["retreated"] is True
    assert discard_observation["select"]["type"] == 4
    assert discard_observation["select"]["context"] == 30
    assert [
        (option["type"], option["area"], option["index"], option["energyIndex"], option["effect"])
        for option in discard_observation["select"]["option"]
    ] == [
        (6, 4, 0, 0, "retreat_discard"),
        (6, 4, 1, 1, "retreat_discard"),
    ]
    assert after_first_discard.players[0].active_energy_card_ids == (6,)
    assert after_first_discard.players[0].discard_card_ids == (6,)
    assert after_first_discard.pending_retreat_remaining == 1
    assert after_second_discard.players[0].active_energy_card_ids == ()
    assert after_second_discard.players[0].discard_card_ids == (6, 6)
    assert after_second_discard.pending_retreat_remaining == 0
    assert promote_observation["select"]["context"] == 3
    assert [
        (option["type"], option["area"], option["index"], option["effect"])
        for option in promote_observation["select"]["option"]
    ] == [
        (3, 5, 0, "retreat_promote"),
        (3, 5, 1, "retreat_promote"),
    ]
    assert after_promote.players[0].active_card_id == 676
    assert after_promote.players[0].active_energy_card_ids == (6,)
    assert after_promote.players[0].bench_card_ids == (675, 677)
    assert after_promote.players[0].bench_energy_card_ids == ((), ())
    assert after_promote.retreated is True
    assert after_promote.pending_retreat_player is None
    assert after_promote.logs[-1]["message"] == "P0 retreated Riolu and promoted Solrock."
    assert next_turn.current_player == 1
    assert next_turn.retreated is False


def test_native_core_blocks_second_retreat_until_turn_changes() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=675,
                active_energy_card_ids=(6,),
                bench_card_ids=(676,),
                bench_energy_card_ids=((6,),),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=677,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    pending = core.start_retreat(setup)
    paid = core.resolve_retreat_discard(pending, energy_index=0)
    after_promote = core.resolve_retreat_promote(paid, bench_index=0)
    blocked = core.try_start_retreat(after_promote)

    assert after_promote.retreated is True
    assert blocked.ok is False
    assert blocked.error_code == 37
    assert "already retreated this turn" in blocked.message
    assert {"type": 12} not in after_promote.to_observation(player_index=0, native_core=core)["select"]["option"]


def test_native_core_applies_weakness_by_doubling_attack_damage() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(1,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=28,
                active_energy_card_ids=(1,),
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=22,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=14)

    assert after_attack.players[1].active_damage == 20
    assert after_attack.logs[-1]["damage"] == 20
    assert after_attack.logs[-1]["message"] == "P0 used Hook for 20 damage."


def test_native_core_applies_resistance_after_weakness_with_thirty_damage_reduction() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=23,
                active_energy_card_ids=(6, 6),
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(5,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=38,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=4)

    assert after_attack.players[1].active_damage == 30
    assert after_attack.logs[-1]["damage"] == 30
    assert after_attack.logs[-1]["message"] == "P0 used Ram for 30 damage."


def test_native_core_accelerating_stab_is_blocked_on_next_turn_only() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    battle = _seed_1_turn2_p0_riolu_with_energy(core)

    after_attack = core.use_attack(battle, attack_id=981)
    next_owner_turn = core.end_turn(after_attack)
    locked_observation = next_owner_turn.to_observation(player_index=0, native_core=core)
    locked_attack = core.try_use_attack(next_owner_turn, attack_id=981)
    skipped_locked_turn = core.end_turn(next_owner_turn)
    unlocked_turn = core.end_turn(skipped_locked_turn)
    unlocked_observation = unlocked_turn.to_observation(player_index=0, native_core=core)
    after_second_attack = core.use_attack(unlocked_turn, attack_id=981)

    assert next_owner_turn.turn == 4
    assert next_owner_turn.current_player == 0
    assert [option for option in locked_observation["select"]["option"] if option["type"] == 13] == []
    assert locked_attack.ok is False
    assert locked_attack.error_code == 34
    assert "Accelerating Stab cannot be used during this Pokemon's next turn" in locked_attack.message
    assert unlocked_turn.turn == 6
    assert unlocked_turn.current_player == 0
    assert [option for option in unlocked_observation["select"]["option"] if option["type"] == 13] == [
        {"type": 13, "attackId": 981}
    ]
    assert after_second_attack.players[1].active_damage == 60


def test_native_core_mega_brave_lock_does_not_block_aura_jab() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6, 6, 6),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=678,
                active_energy_card_ids=(6, 6),
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6, 6, 6),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=678,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_mega_brave = core.use_attack(setup, attack_id=983)
    next_owner_turn = core.end_turn(after_mega_brave)
    locked_observation = next_owner_turn.to_observation(player_index=0, native_core=core)
    locked_mega_brave = core.try_use_attack(next_owner_turn, attack_id=983)
    aura_jab = core.try_use_attack(next_owner_turn, attack_id=982)

    assert after_mega_brave.players[1].active_damage == 270
    assert [option for option in locked_observation["select"]["option"] if option["type"] == 13] == [
        {"type": 13, "attackId": 982}
    ]
    assert locked_mega_brave.ok is False
    assert locked_mega_brave.error_code == 34
    assert "Mega Brave cannot be used during this Pokemon's next turn" in locked_mega_brave.message
    assert aura_jab.ok is True
    assert aura_jab.setup is not None
    assert aura_jab.setup.result == 0
    assert aura_jab.setup.logs[-1]["message"] == "P0 used Aura Jab for 130 damage."


def test_native_core_aura_jab_opens_pending_discard_energy_attachment_choices() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(1141, 1142, 1152),
                hand_card_ids=(677,),
                discard_card_ids=(6, 1192, 6, 6),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=678,
                active_energy_card_ids=(6,),
                bench_card_ids=(677, 673),
                bench_energy_card_ids=((), (6,)),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102, 1123, 1182),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=678,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=982)
    blocked_end = core.try_end_turn(after_attack)
    observation = after_attack.to_observation(player_index=0, native_core=core)
    attach_options = [
        option
        for option in observation["select"]["option"]
        if option.get("effect") == "aura_jab_attach"
    ]

    assert after_attack.players[1].active_damage == 130
    assert after_attack.turn == 2
    assert after_attack.current_player == 0
    assert after_attack.pending_aura_jab_player == 0
    assert after_attack.pending_aura_jab_remaining == 3
    assert observation["current"]["looking"] == {"effect": "aura_jab", "playerIndex": 0}
    assert observation["select"]["effect"] == "aura_jab"
    assert observation["select"]["context"] == 12
    assert {(option["index"], option["inPlayIndex"]) for option in attach_options} == {
        (0, 0),
        (0, 1),
        (2, 0),
        (2, 1),
        (3, 0),
        (3, 1),
    }
    assert {"type": 16, "effect": "aura_jab_skip"} in observation["select"]["option"]
    assert blocked_end.ok is False
    assert blocked_end.error_code == 36
    assert "pending Aura Jab attachments must be resolved" in blocked_end.message


def test_native_core_resolves_aura_jab_attachment_and_skip_advances_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(1141, 1142, 1152),
                hand_card_ids=(),
                discard_card_ids=(6, 1192, 6),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=678,
                active_energy_card_ids=(6,),
                bench_card_ids=(677, 673),
                bench_energy_card_ids=((), (6,)),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102, 1123, 1182),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=678,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    pending = core.use_attack(setup, attack_id=982)
    after_attach = core.resolve_aura_jab_attach(pending, discard_index=0, bench_index=1)
    after_skip = core.skip_aura_jab(after_attach)

    assert after_attach.pending_aura_jab_player == 0
    assert after_attach.pending_aura_jab_remaining == 1
    assert after_attach.players[0].discard_card_ids == (1192, 6)
    assert after_attach.players[0].bench_energy_card_ids == ((), (6, 6))
    assert after_attach.logs[-1]["message"] == "P0 attached Basic {F} Energy from discard to Makuhita with Aura Jab."
    assert after_skip.pending_aura_jab_player is None
    assert after_skip.pending_aura_jab_remaining == 0
    assert after_skip.turn == 3
    assert after_skip.current_player == 1
    assert after_skip.players[1].hand_card_ids == (1182,)
    assert after_skip.players[1].deck_card_ids == (1102, 1123)
    assert after_skip.logs[-1]["message"] == "P0 finished Aura Jab attachments."


def test_native_setup_snapshot_blocks_accelerating_stab_after_deckcsv_attack() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "2",
            "--player0-active-hand-index",
            "4",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "attach:1:4:0",
            "--main-action",
            "attack:981",
            "--main-action",
            "end",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    attack_options = [
        option for option in payload["observation"]["select"]["option"] if option["type"] == 13
    ]
    assert payload["setup"]["turn"] == 3
    assert payload["setup"]["current_player"] == 0
    assert attack_options == []
    assert payload["observation"]["logs"][-2]["kind"] == "attack"
    assert payload["observation"]["logs"][-1]["kind"] == "end_turn"
    assert payload["kaggle_submission_made"] is False


def test_native_core_cosmic_beam_does_nothing_without_lunatone_on_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                active_energy_card_ids=(6,),
                bench_card_ids=(677,),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=980)

    assert after_attack.players[1].active_damage == 0
    assert after_attack.turn == 3
    assert after_attack.current_player == 1
    assert after_attack.logs[-1]["kind"] == "attack"
    assert after_attack.logs[-1]["damage"] == 0
    assert after_attack.logs[-1]["message"] == "P0 used Cosmic Beam for 0 damage."


def test_native_core_cosmic_beam_damages_when_lunatone_is_on_bench() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=0,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=676,
                active_energy_card_ids=(6,),
                bench_card_ids=(675,),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=24,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=980)

    assert core.card_metadata(24).weakness_type == 6
    assert after_attack.players[1].active_damage == 70
    assert after_attack.logs[-1]["damage"] == 70
    assert after_attack.logs[-1]["message"] == "P0 used Cosmic Beam for 70 damage."


def test_native_core_wild_press_damages_defender_and_hariyama() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=674,
                active_pre_evolution_card_ids=(673,),
                active_energy_card_ids=(6, 6, 6),
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=678,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=978)

    assert after_attack.players[1].active_damage == 210
    assert after_attack.players[0].active_damage == 70
    assert after_attack.turn == 3
    assert after_attack.current_player == 1
    assert after_attack.logs[-1]["kind"] == "attack"
    assert after_attack.logs[-1]["attackId"] == 978
    assert after_attack.logs[-1]["damage"] == 210
    assert after_attack.logs[-1]["selfDamage"] == 70
    assert after_attack.logs[-1]["message"] == "P0 used Wild Press for 210 damage and 70 self-damage."


def test_native_core_wild_press_self_knockout_awards_prize_to_defender() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=674,
                active_damage=90,
                active_pre_evolution_card_ids=(673,),
                active_energy_card_ids=(6, 6, 6),
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=678,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=978)

    assert after_attack.result == 1
    assert after_attack.players[1].prize_count == 5
    assert after_attack.players[1].hand_card_ids == (2006,)
    assert after_attack.players[0].active_card_id is None
    assert after_attack.players[0].discard_card_ids == (674, 673, 6, 6, 6)
    assert after_attack.players[1].active_damage == 210
    assert after_attack.logs[-1]["selfDamage"] == 70


def test_native_core_wild_press_self_knockout_pending_promotion_passes_turn_to_defender() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(6,),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=674,
                active_damage=90,
                active_pre_evolution_card_ids=(673,),
                active_energy_card_ids=(6, 6, 6),
                bench_card_ids=(676, 677),
                bench_damage=(0, 20),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=678,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=978)
    after_promote = core.promote_bench_to_active(after_attack, player_index=0, bench_index=1)

    assert after_attack.result == -1
    assert after_attack.turn == 2
    assert after_attack.current_player == 0
    assert after_attack.pending_promotion_player == 0
    assert after_attack.pending_promotion_next_player == 1
    assert after_attack.players[1].prize_count == 5
    assert after_attack.players[1].hand_card_ids == (2006,)
    assert after_attack.players[0].active_card_id is None
    assert after_attack.players[0].bench_card_ids == (676, 677)
    assert after_promote.pending_promotion_player is None
    assert after_promote.turn == 3
    assert after_promote.current_player == 1
    assert after_promote.players[0].active_card_id == 677
    assert after_promote.players[0].active_damage == 20
    assert after_promote.players[0].bench_card_ids == (676,)
    assert after_promote.players[1].hand_card_ids == (2006, 1102)
    assert after_promote.logs[-1]["message"] == "P0 promoted Riolu to Active Pokemon."


def test_native_setup_snapshot_cosmic_beam_does_nothing_without_lunatone_from_deckcsv() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "2",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "attach:0:4:0",
            "--main-action",
            "attack:980",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    opponent_active = payload["observation"]["current"]["players"][1]["active"][0]
    assert opponent_active["id"] == 676
    assert opponent_active["hp"] == 110
    assert opponent_active["maxHp"] == 110
    assert payload["observation"]["logs"][-1]["kind"] == "attack"
    assert payload["observation"]["logs"][-1]["attackId"] == 980
    assert payload["observation"]["logs"][-1]["damage"] == 0
    assert payload["kaggle_submission_made"] is False


def test_native_core_premium_power_pro_boosts_fighting_attack_damage_this_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(1141, 1141),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=677,
                active_energy_card_ids=(6,),
                bench_card_ids=(),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    power_options = [option for option in before["select"]["option"] if option.get("effect") == "premium_power_pro"]
    after_power = core.play_premium_power_pro(setup, hand_index=0)
    after_second_power = core.play_premium_power_pro(after_power, hand_index=0)
    boosted_observation = after_second_power.to_observation(player_index=0, native_core=core)
    after_attack = core.use_attack(after_second_power, attack_id=981)

    assert power_options == [
        {"type": 7, "index": 0, "cardId": 1141, "effect": "premium_power_pro"},
        {"type": 7, "index": 1, "cardId": 1141, "effect": "premium_power_pro"},
    ]
    assert after_power.fighting_attack_bonus == 30
    assert after_second_power.fighting_attack_bonus == 60
    assert after_second_power.players[0].hand_card_ids == ()
    assert after_second_power.players[0].discard_card_ids == (1141, 1141)
    assert boosted_observation["current"]["fightingAttackBonus"] == 60
    assert after_attack.players[1].active_damage == 90
    assert after_attack.fighting_attack_bonus == 0
    assert after_attack.logs[-2]["kind"] == "play_premium_power_pro"
    assert after_attack.logs[-1]["kind"] == "attack"
    assert after_attack.logs[-1]["damage"] == 90
    assert after_attack.logs[-1]["message"] == "P0 used Accelerating Stab for 90 damage."


def test_native_setup_snapshot_script_can_apply_premium_power_pro() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_setup_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--player-index",
            "0",
            "--seed",
            "98",
            "--player0-active-hand-index",
            "0",
            "--finish-player0-setup",
            "--player1-active-hand-index",
            "0",
            "--finish-player1-setup",
            "--begin-first-turn",
            "--main-action",
            "powerpro:1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["setup"]["fighting_attack_bonus"] == 30
    assert payload["observation"]["current"]["fightingAttackBonus"] == 30
    assert payload["observation"]["current"]["players"][0]["discard"][0]["id"] == 1141
    assert payload["observation"]["logs"][-1]["kind"] == "play_premium_power_pro"
    assert payload["kaggle_submission_made"] is False


def test_native_core_offers_and_uses_lunatone_lunar_cycle_once_per_turn() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        supporter_played=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(1102, 1123, 1141, 6),
                hand_card_ids=(6, 1192),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=675,
                bench_card_ids=(676,),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=677,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )

    before = setup.to_observation(player_index=0, native_core=core)
    lunar_options = [option for option in before["select"]["option"] if option.get("effect") == "lunar_cycle"]
    after = core.use_lunar_cycle(setup, hand_index=0)
    after_observation = after.to_observation(player_index=0, native_core=core)

    assert lunar_options == [{"type": 7, "index": 0, "cardId": 6, "effect": "lunar_cycle"}]
    assert after.lunar_cycle_used is True
    assert after.energy_attached is False
    assert after.supporter_played is False
    assert after.players[0].hand_card_ids == (1192, 6, 1141, 1123)
    assert after.players[0].deck_card_ids == (1102,)
    assert after.players[0].discard_card_ids == (6,)
    assert after_observation["current"]["lunarCycleUsed"] is True
    assert [option for option in after_observation["select"]["option"] if option.get("effect") == "lunar_cycle"] == []
    assert after.logs[-1]["kind"] == "use_lunar_cycle"
    assert after.logs[-1]["message"] == "P0 used Lunar Cycle and drew 3 cards."


def test_native_core_knockout_discards_active_and_attached_energy() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=678,
                bench_card_ids=(),
                active_energy_card_ids=(6, 6),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(),
                active_energy_card_ids=(6,),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=983)

    assert after_attack.result == 0
    assert after_attack.players[0].prize_count == 5
    assert after_attack.players[0].hand_card_ids == (1006,)
    assert after_attack.players[1].active_card_id is None
    assert sorted(after_attack.players[1].discard_card_ids) == [6, 675]
    observation = after_attack.to_observation(player_index=0, native_core=core)
    assert observation["current"]["result"] == 0
    assert [card["id"] for card in observation["current"]["players"][1]["discard"]] == [675, 6]


def test_native_core_knockout_with_multiple_bench_requires_promotion_choice() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=678,
                bench_card_ids=(),
                active_energy_card_ids=(6, 6),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=675,
                bench_card_ids=(676, 677),
                bench_damage=(10, 20),
                active_energy_card_ids=(6,),
                setup_complete=True,
            ),
        ),
    )

    after_attack = core.use_attack(setup, attack_id=983)

    assert after_attack.result == -1
    assert after_attack.turn == 2
    assert after_attack.current_player == 1
    assert after_attack.pending_promotion_player == 1
    assert after_attack.players[0].prize_count == 5
    assert after_attack.players[1].active_card_id is None
    assert after_attack.players[1].bench_card_ids == (676, 677)
    assert sorted(after_attack.players[1].discard_card_ids) == [6, 675]
    observation = after_attack.to_observation(player_index=1, native_core=core)
    assert observation["select"]["context"] == 3
    assert observation["select"]["minCount"] == 1
    assert observation["select"]["maxCount"] == 1
    assert observation["select"]["option"] == [
        {"type": 15, "area": 5, "index": 0, "playerIndex": 1, "cardId": 676},
        {"type": 15, "area": 5, "index": 1, "playerIndex": 1, "cardId": 677},
    ]

    after_promote = core.promote_bench_to_active(after_attack, player_index=1, bench_index=1)

    assert after_promote.pending_promotion_player is None
    assert after_promote.turn == 3
    assert after_promote.current_player == 1
    assert after_promote.players[1].active_card_id == 677
    assert after_promote.players[1].active_damage == 20
    assert after_promote.players[1].bench_card_ids == (676,)
    assert after_promote.players[1].bench_damage == (10,)
    assert after_promote.players[1].hand_card_ids == (1102,)
    assert after_promote.logs[-1]["kind"] == "promote_active"
    assert after_promote.logs[-1]["message"] == "P1 promoted Riolu to Active Pokemon."


def test_native_core_knockout_uses_ex_and_mega_ex_prize_values() -> None:
    library_path = build_native_core(force=True)
    core = NativeCore(library_path)
    assert core.card_metadata(210).ex is True
    assert core.card_metadata(754).mega_ex is True
    regular_ex_setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=904,
                bench_card_ids=(),
                active_energy_card_ids=(3, 4, 4),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=210,
                bench_card_ids=(),
                setup_complete=True,
            ),
        ),
    )
    mega_ex_setup = NativeBattleSetup(
        turn=2,
        first_player=1,
        current_player=0,
        energy_attached=False,
        result=-1,
        players=(
            NativeBattlePlayer(
                deck_card_ids=(),
                hand_card_ids=(),
                prize_card_ids=(1001, 1002, 1003, 1004, 1005, 1006),
                active_card_id=678,
                bench_card_ids=(),
                active_energy_card_ids=(6, 6),
                setup_complete=True,
            ),
            NativeBattlePlayer(
                deck_card_ids=(1102,),
                hand_card_ids=(),
                prize_card_ids=(2001, 2002, 2003, 2004, 2005, 2006),
                active_card_id=754,
                bench_card_ids=(),
                active_damage=20,
                setup_complete=True,
            ),
        ),
    )

    regular_ex_ko = core.use_attack(regular_ex_setup, attack_id=1302)
    mega_ex_ko = core.use_attack(mega_ex_setup, attack_id=983)

    assert regular_ex_ko.players[0].prize_count == 4
    assert regular_ex_ko.players[0].hand_card_ids == (1006, 1005)
    assert regular_ex_ko.result == 0
    assert mega_ex_ko.players[0].prize_count == 3
    assert mega_ex_ko.players[0].hand_card_ids == (1006, 1005, 1004)
    assert mega_ex_ko.result == 0
