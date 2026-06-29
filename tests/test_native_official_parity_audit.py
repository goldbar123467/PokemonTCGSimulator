from __future__ import annotations

import json
import subprocess
import sys


def test_native_official_parity_audit_reports_passes_and_known_gaps() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_official_parity_audit.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--seed",
            "3",
            "--max-frames",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    comparisons = {entry["id"]: entry for entry in payload["comparisons"]}

    assert payload["source"] == "native-official parity audit"
    assert payload["status"] == "partial_not_1_to_1"
    assert payload["decks"]["player"]["count"] == 60
    assert payload["decks"]["player"]["sha256"] == "2a541d7bf3d9e6b36037123f53f4dfef6348223f79fd27095dafc602a5357c19"
    assert payload["official"]["source"] == "official cg.VisualizeData"
    assert payload["official"]["first_frame_context"] == "IsFirst"
    assert payload["official"]["setup_branch_probe"]["branch_counts"]["DrawCount"] > 0
    assert payload["official"]["setup_branch_probe"]["examples"]["DrawCount"]["fourth_frame"]["select"]["context"] == (
        "DrawCount"
    )
    assert payload["official"]["shuffle_probe"]["seed_surface"]["exported_seed_symbols"] == []
    assert payload["official"]["shuffle_probe"]["seed_surface"]["has_random_device_symbol"] is True
    assert payload["official"]["shuffle_probe"]["seed_surface"]["has_mt19937_symbol"] is True
    assert payload["official"]["shuffle_probe"]["unique_order_count"] >= 2
    assert payload["native"]["draw_count_replay"]["phase"] == "post_mulligan_draw_count_selected"
    assert payload["native"]["draw_count_replay"]["setup"]["mulligan_draw_choices"] == [None, 2]
    assert payload["native"]["draw_count_replay"]["draw_count_selection"] == {
        "player_index": 1,
        "count": 2,
        "max_count": 5,
    }
    assert payload["native"]["draw_count_replay"]["first_frame"]["select"]["context"] == "SetupBenchPokemon"
    official_setup_option = payload["official"]["post_isfirst"]["first_frame"]["select"]["option"][0]
    assert payload["official"]["post_setup_active"]["active_selection"]["player_index"] == payload["official"][
        "post_isfirst"
    ]["first_frame"]["current"]["yourIndex"]
    assert payload["official"]["post_setup_active"]["active_selection"]["option_index"] == 0
    assert payload["official"]["post_setup_active"]["active_selection"]["option_hand_index"] == official_setup_option[
        "index"
    ]
    assert payload["native"]["wrapper"] == "clean-room C native core"
    assert payload["native"]["pregame"]["setup"]["players"][0] == {
        "deck_count": 60,
        "hand_count": 0,
        "prize_count": 0,
    }
    assert payload["native"]["pregame"]["first_frame"]["select"]["context"] == "IsFirst"
    assert payload["official"]["frames"][0]["current"]["turnActionCount"] == 1
    assert payload["native"]["pregame"]["first_frame"]["current"]["turnActionCount"] == 1
    assert payload["native"]["post_isfirst"]["setup"]["players"][0] == {
        "deck_count": 53,
        "hand_count": 7,
        "prize_count": 0,
    }
    assert payload["native"]["post_isfirst"]["first_frame"]["select"]["context"] == "SetupActivePokemon"
    assert payload["native"]["post_setup_active"]["setup"]["players"][1]["hand_count"] == 6
    assert payload["native"]["post_setup_active"]["first_frame"]["current"]["yourIndex"] == 0
    assert payload["native"]["post_setup_active"]["first_frame"]["select"]["context"] == "SetupActivePokemon"
    assert payload["native"]["post_both_actives"]["setup"]["players"][0]["deck_count"] == 47
    assert payload["native"]["post_both_actives"]["setup"]["players"][0]["prize_count"] == 6
    assert payload["native"]["post_both_actives"]["setup"]["players"][1]["deck_count"] == 47
    assert payload["native"]["post_both_actives"]["setup"]["players"][1]["prize_count"] == 6
    assert payload["native"]["post_both_actives"]["first_frame"]["select"]["context"] == "SetupBenchPokemon"
    assert payload["native"]["post_both_actives"]["first_frame"]["current"]["yourIndex"] == 1
    assert payload["native"]["post_setup_bench"]["setup"]["players"][1]["hand_count"] == 5
    assert payload["native"]["post_setup_bench"]["setup"]["players"][1]["bench_count"] == 1
    assert payload["native"]["post_setup_bench"]["setup"]["players"][1]["setup_complete"] is True
    assert payload["native"]["post_setup_bench"]["first_frame"]["select"]["context"] == "SetupBenchPokemon"
    assert payload["native"]["post_setup_bench"]["first_frame"]["current"]["yourIndex"] == 0
    assert payload["official"]["post_setup_bench_skip"]["selection"] == []
    assert payload["official"]["post_setup_bench_skip"]["first_frame_summary"]["context"] == "SetupBenchPokemon"
    assert payload["official"]["post_setup_bench_skip"]["first_frame_summary"]["yourIndex"] == 0
    assert payload["official"]["post_setup_bench_skip"]["first_frame_summary"]["players"][1]["benchCount"] == 0
    assert payload["native"]["post_setup_bench_skip"]["selection"] == []
    assert payload["native"]["post_setup_bench_skip"]["first_frame"]["select"]["context"] == "SetupBenchPokemon"
    assert payload["native"]["post_setup_bench_skip"]["first_frame"]["current"]["yourIndex"] == 0
    assert payload["native"]["post_setup_bench_skip"]["setup"]["players"][1]["bench_count"] == 0
    assert payload["native"]["post_setup_bench_skip"]["setup"]["players"][1]["setup_complete"] is True
    assert payload["official"]["post_setup_complete_main"]["selection_sequence"] == [[], []]
    assert payload["official"]["post_setup_complete_main"]["first_frame_summary"]["context"] == "Main"
    assert payload["official"]["post_setup_complete_main"]["first_frame_summary"]["turn"] == 1
    assert payload["official"]["post_setup_complete_main"]["first_frame_summary"]["yourIndex"] == 1
    official_main_option_types = set(
        payload["official"]["post_setup_complete_main"]["selector_summary"]["normalized_option_types"]
    )
    assert {"End", "Play"}.issubset(official_main_option_types)
    assert payload["native"]["post_setup_complete_main"]["selection_sequence"] == [[], []]
    assert payload["native"]["post_setup_complete_main"]["first_frame"]["select"]["context"] == "Main"
    assert payload["native"]["post_setup_complete_main"]["first_frame"]["select"]["type"] == "Action"
    assert payload["native"]["post_setup_complete_main"]["first_frame"]["current"]["turn"] == 1
    assert payload["native"]["post_setup_complete_main"]["first_frame"]["current"]["yourIndex"] == 1
    assert payload["native"]["post_setup_complete_main"]["selector_summary"]["normalized_option_types"] == [
        "Attach",
        "End",
        "Play",
    ]
    assert payload["native"]["setup_bench_optional_replay"]["skip"]["setup"]["players"][1]["bench_count"] == 0
    assert payload["native"]["setup_bench_optional_replay"]["skip"]["setup"]["players"][1]["setup_complete"] is True
    assert payload["native"]["setup_bench_optional_replay"]["multi"]["setup"]["players"][1]["bench_count"] == 2
    assert payload["native"]["setup_bench_optional_replay"]["multi"]["setup"]["players"][1]["hand_count"] == 4
    assert comparisons["deck_csv_sha256"]["status"] == "pass"
    assert comparisons["official_initial_context"]["status"] == "pass"
    assert comparisons["native_initial_context"]["status"] == "pass"
    assert comparisons["initial_turn_action_count"]["status"] == "pass"
    assert comparisons["initial_turn_action_count"]["official"] == 1
    assert comparisons["initial_turn_action_count"]["native"] == 1
    assert comparisons["post_isfirst_opening_hand_counts"]["status"] == "pass"
    assert comparisons["post_isfirst_setup_active_frame"]["status"] == "pass"
    assert comparisons["post_setup_active_visible_counts"]["status"] == "pass"
    assert comparisons["post_setup_active_prize_timing"]["status"] == "pass"
    assert comparisons["post_setup_active_prize_timing"]["official"]["selected_player_counts"] == {
        "deck_count": 53,
        "hand_count": 6,
        "prize_count": 0,
    }
    assert comparisons["post_setup_active_prize_timing"]["native"]["selected_player_counts"] == {
        "deck_count": 53,
        "hand_count": 6,
        "prize_count": 0,
    }
    assert comparisons["official_draw_count_branch_semantics"]["status"] == "pass"
    assert comparisons["official_draw_count_branch_semantics"]["native"]["modeled"] is True
    assert comparisons["post_setup_active_next_prompt"]["status"] == "pass"
    assert comparisons["post_both_actives_setup_bench_frame"]["status"] == "pass"
    assert comparisons["post_both_actives_prize_counts"]["status"] == "pass"
    assert comparisons["startup_frame_prefix_core"]["status"] == "pass"
    assert comparisons["startup_frame_prefix_core"]["official"]["frame_count"] == 4
    assert comparisons["startup_frame_prefix_core"]["native"]["frame_count"] == 4
    assert comparisons["startup_frame_prefix_core"]["official"]["matched_fields"] == [
        "select.context",
        "select.normalized_type",
        "select.minCount",
        "current.turn",
        "current.turnActionCount",
        "current.yourIndex",
        "current.players.deckCount",
        "current.players.handCount",
        "current.players.prizeCount",
    ]
    assert comparisons["startup_frame_prefix_core"]["official"]["excluded_fields"] == [
        "select.maxCount",
        "select.option_count",
        "select.option.card_ids",
        "select.option.card_order",
    ]
    assert [frame["context"] for frame in comparisons["startup_frame_prefix_core"]["official"]["frames"]] == [
        "IsFirst",
        "SetupActivePokemon",
        "SetupActivePokemon",
        "SetupBenchPokemon",
    ]
    assert comparisons["startup_frame_prefix_core"]["official"]["frames"] == comparisons[
        "startup_frame_prefix_core"
    ]["native"]["frames"]
    assert comparisons["setup_bench_selector_bounds_semantics"]["status"] == "pass"
    assert comparisons["setup_bench_selector_bounds_semantics"]["official"]["context"] == "SetupBenchPokemon"
    assert comparisons["setup_bench_selector_bounds_semantics"]["native"]["context"] == "SetupBenchPokemon"
    assert comparisons["setup_bench_selector_bounds_semantics"]["official"]["minCount"] == 0
    assert comparisons["setup_bench_selector_bounds_semantics"]["native"]["minCount"] == 0
    assert comparisons["setup_bench_selector_bounds_semantics"]["official"]["max_equals_option_count"] is True
    assert comparisons["setup_bench_selector_bounds_semantics"]["native"]["max_equals_option_count"] is True
    assert comparisons["setup_bench_selector_bounds_semantics"]["official"]["branch_dependent_fields"] == [
        "maxCount",
        "option_count",
        "option.card_ids",
        "option.card_order",
    ]
    assert comparisons["startup_selector_option_card_ids"]["status"] == "pass"
    assert comparisons["startup_selector_option_card_ids"]["official"]["frame_count"] == 4
    assert comparisons["startup_selector_option_card_ids"]["native"]["frame_count"] == 4
    assert comparisons["startup_selector_option_card_ids"]["official"]["unresolved_option_count"] == 0
    assert comparisons["startup_selector_option_card_ids"]["native"]["unresolved_option_count"] == 0
    assert comparisons["startup_selector_option_card_ids"]["official"]["branch_dependent_fields"] == [
        "option_count",
        "option.card_ids",
        "option.card_order",
    ]
    assert all(
        isinstance(card_id, int)
        for frame in comparisons["startup_selector_option_card_ids"]["official"]["frames"]
        for card_id in frame["option_card_ids"]
    )
    assert comparisons["post_isfirst_ordered_zone_sync"]["status"] == "pass"
    assert comparisons["post_isfirst_ordered_zone_sync"]["official"]["players"] == comparisons[
        "post_isfirst_ordered_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_isfirst_ordered_zone_sync"]["official"]["selector_option_card_ids"] == comparisons[
        "post_isfirst_ordered_zone_sync"
    ]["native"]["selector_option_card_ids"]
    assert comparisons["post_isfirst_ordered_zone_sync"]["official"]["selector_option_indexes"] == comparisons[
        "post_isfirst_ordered_zone_sync"
    ]["native"]["selector_option_indexes"]
    for player_summary in comparisons["post_isfirst_ordered_zone_sync"]["official"]["players"]:
        serials = player_summary["hand_serials"] + player_summary["deck_serials"] + player_summary["prize_serials"]
        assert len(serials) == 60
        assert len(serials) == len(set(serials))
    assert comparisons["post_isfirst_ordered_zone_sync"]["official"]["selector_option_serials"] == comparisons[
        "post_isfirst_ordered_zone_sync"
    ]["native"]["selector_option_serials"]
    assert comparisons["post_isfirst_ordered_zone_sync"]["native"]["source"] == (
        "official observed ordered hand/deck zones"
    )
    assert comparisons["post_ordered_first_active_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_first_active_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_first_active_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_first_active_zone_sync"]["official"]["selector_option_card_ids"] == comparisons[
        "post_ordered_first_active_zone_sync"
    ]["native"]["selector_option_card_ids"]
    assert comparisons["post_ordered_first_active_zone_sync"]["official"]["selector_option_indexes"] == comparisons[
        "post_ordered_first_active_zone_sync"
    ]["native"]["selector_option_indexes"]
    assert comparisons["post_ordered_first_active_zone_sync"]["official"]["selector_option_serials"] == comparisons[
        "post_ordered_first_active_zone_sync"
    ]["native"]["selector_option_serials"]
    active_serials = [
        player_summary["active_serial"]
        for player_summary in comparisons["post_ordered_first_active_zone_sync"]["official"]["players"]
        if player_summary["active_serial"] is not None
    ]
    assert active_serials
    assert comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_both_actives_setup_bench_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["official"][
        "selector_option_card_ids"
    ] == comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["native"]["selector_option_card_ids"]
    assert comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["official"][
        "selector_option_indexes"
    ] == comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["native"]["selector_option_indexes"]
    assert comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["official"][
        "selector_option_serials"
    ] == comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["native"]["selector_option_serials"]
    for player_summary in comparisons["post_ordered_both_actives_setup_bench_zone_sync"]["official"]["players"]:
        assert player_summary["active_serial"] is not None
        assert len(player_summary["prize_serials"]) == 6
        assert len(player_summary["deck_serials"]) == 47
        zone_serials = (
            player_summary["hand_serials"]
            + player_summary["deck_serials"]
            + player_summary["prize_serials"]
            + player_summary["bench_serials"]
            + [player_summary["active_serial"]]
        )
        assert len(zone_serials) == 60
        assert len(zone_serials) == len(set(zone_serials))
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_first_setup_bench_skip_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["official"][
        "selector_option_card_ids"
    ] == comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["native"]["selector_option_card_ids"]
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["official"][
        "selector_option_indexes"
    ] == comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["native"]["selector_option_indexes"]
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["official"][
        "selector_option_serials"
    ] == comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["native"]["selector_option_serials"]
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["official"]["yourIndex"] == 0
    assert comparisons["post_ordered_first_setup_bench_skip_zone_sync"]["native"]["yourIndex"] == 0
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_both_setup_bench_skips_main_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"][
        "selector_hand_backed_option_card_ids"
    ] == comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["native"][
        "selector_hand_backed_option_card_ids"
    ]
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"][
        "selector_hand_backed_option_indexes"
    ] == comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["native"][
        "selector_hand_backed_option_indexes"
    ]
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"][
        "selector_hand_backed_option_serials"
    ] == comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["native"][
        "selector_hand_backed_option_serials"
    ]
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"][
        "selector_hand_backed_option_type_counts"
    ] == comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["native"][
        "selector_hand_backed_option_type_counts"
    ]
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"]["context"] == "Main"
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["native"]["context"] == "Main"
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["official"]["yourIndex"] == 1
    assert comparisons["post_ordered_both_setup_bench_skips_main_zone_sync"]["native"]["yourIndex"] == 1
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_first_main_end_next_main_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"][
        "selector_hand_backed_option_card_ids"
    ] == comparisons["post_ordered_first_main_end_next_main_zone_sync"]["native"][
        "selector_hand_backed_option_card_ids"
    ]
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"][
        "selector_hand_backed_option_indexes"
    ] == comparisons["post_ordered_first_main_end_next_main_zone_sync"]["native"][
        "selector_hand_backed_option_indexes"
    ]
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"][
        "selector_hand_backed_option_serials"
    ] == comparisons["post_ordered_first_main_end_next_main_zone_sync"]["native"][
        "selector_hand_backed_option_serials"
    ]
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"][
        "selector_hand_backed_option_type_counts"
    ] == comparisons["post_ordered_first_main_end_next_main_zone_sync"]["native"][
        "selector_hand_backed_option_type_counts"
    ]
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"]["context"] == "Main"
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["native"]["context"] == "Main"
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["official"]["yourIndex"] == 0
    assert comparisons["post_ordered_first_main_end_next_main_zone_sync"]["native"]["yourIndex"] == 0
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_next_main_attach_active_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"]["energyAttached"] is True
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["native"]["energyAttached"] is True
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"]["players"][0][
        "active_energy_card_ids"
    ] == [6]
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"]["players"][0][
        "active_energy_serials"
    ] == comparisons["post_ordered_next_main_attach_active_zone_sync"]["native"]["players"][0][
        "active_energy_serials"
    ]
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"][
        "selector_hand_backed_option_card_ids"
    ] == comparisons["post_ordered_next_main_attach_active_zone_sync"]["native"][
        "selector_hand_backed_option_card_ids"
    ]
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"][
        "selector_hand_backed_option_indexes"
    ] == comparisons["post_ordered_next_main_attach_active_zone_sync"]["native"][
        "selector_hand_backed_option_indexes"
    ]
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"]["context"] == "Main"
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["native"]["context"] == "Main"
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["official"]["yourIndex"] == 0
    assert comparisons["post_ordered_next_main_attach_active_zone_sync"]["native"]["yourIndex"] == 0
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_next_main_attack_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["official"]["energyAttached"] is False
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["native"]["energyAttached"] is False
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["official"][
        "selector_hand_backed_option_card_ids"
    ] == comparisons["post_ordered_next_main_attack_zone_sync"]["native"][
        "selector_hand_backed_option_card_ids"
    ]
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["official"][
        "selector_hand_backed_option_indexes"
    ] == comparisons["post_ordered_next_main_attack_zone_sync"]["native"][
        "selector_hand_backed_option_indexes"
    ]
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["official"]["context"] == "Main"
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["native"]["context"] == "Main"
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["official"]["yourIndex"] == 1
    assert comparisons["post_ordered_next_main_attack_zone_sync"]["native"]["yourIndex"] == 1
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_after_attack_attach_active_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"]["energyAttached"] is True
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["native"]["energyAttached"] is True
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"]["players"][1][
        "active_energy_card_ids"
    ] == [6]
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"]["players"][1][
        "active_energy_serials"
    ] == comparisons["post_ordered_after_attack_attach_active_zone_sync"]["native"]["players"][1][
        "active_energy_serials"
    ]
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"][
        "selector_hand_backed_option_card_ids"
    ] == comparisons["post_ordered_after_attack_attach_active_zone_sync"]["native"][
        "selector_hand_backed_option_card_ids"
    ]
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"]["context"] == "Main"
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["native"]["context"] == "Main"
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["official"]["yourIndex"] == 1
    assert comparisons["post_ordered_after_attack_attach_active_zone_sync"]["native"]["yourIndex"] == 1
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["status"] == "pass"
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["official"]["players"] == comparisons[
        "post_ordered_after_attack_attach_attack_zone_sync"
    ]["native"]["players"]
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["official"]["energyAttached"] is False
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["native"]["energyAttached"] is False
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["official"][
        "selector_hand_backed_option_card_ids"
    ] == comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["native"][
        "selector_hand_backed_option_card_ids"
    ]
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["official"]["context"] == "Main"
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["native"]["context"] == "Main"
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["official"]["yourIndex"] == 0
    assert comparisons["post_ordered_after_attack_attach_attack_zone_sync"]["native"]["yourIndex"] == 0
    assert comparisons["post_setup_progression_frame_prefix_core"]["status"] == "pass"
    assert comparisons["post_setup_progression_frame_prefix_core"]["official"]["frame_count"] == 2
    assert comparisons["post_setup_progression_frame_prefix_core"]["native"]["frame_count"] == 2
    assert [frame["context"] for frame in comparisons["post_setup_progression_frame_prefix_core"]["official"]["frames"]] == [
        "SetupBenchPokemon",
        "Main",
    ]
    assert comparisons["post_setup_progression_frame_prefix_core"]["official"]["frames"] == comparisons[
        "post_setup_progression_frame_prefix_core"
    ]["native"]["frames"]
    assert comparisons["post_setup_bench_optional_selection_semantics"]["status"] == "pass"
    assert comparisons["post_setup_bench_optional_selection_semantics"]["official"]["empty_select_probe"][
        "accepted"
    ] is True
    assert comparisons["post_setup_bench_optional_selection_semantics"]["native"]["skip_modeled"] is True
    assert comparisons["post_setup_bench_optional_selection_semantics"]["native"]["multi_modeled"] is True
    assert comparisons["post_setup_bench_skip_next_prompt"]["status"] == "pass"
    assert comparisons["post_setup_bench_skip_next_prompt"]["official"]["selection"] == []
    assert comparisons["post_setup_bench_skip_next_prompt"]["native"]["selection"] == []
    assert comparisons["post_setup_bench_skip_next_prompt"]["official"]["next_yourIndex"] == 0
    assert comparisons["post_setup_bench_skip_next_prompt"]["native"]["next_yourIndex"] == 0
    assert comparisons["post_both_setup_bench_skips_main_frame"]["status"] == "pass"
    assert comparisons["post_both_setup_bench_skips_main_frame"]["official"]["selection_sequence"] == [[], []]
    assert comparisons["post_both_setup_bench_skips_main_frame"]["native"]["selection_sequence"] == [[], []]
    assert comparisons["post_both_setup_bench_skips_main_frame"]["official"]["main_context"] == "Main"
    assert comparisons["post_both_setup_bench_skips_main_frame"]["native"]["main_context"] == "Main"
    assert comparisons["post_setup_complete_main_selector_core"]["status"] == "pass"
    assert comparisons["post_setup_complete_main_selector_core"]["official"]["required_common_option_types"] == [
        "End",
        "Play",
    ]
    assert comparisons["post_setup_complete_main_selector_core"]["official"]["branch_dependent_option_types"] == [
        "Attach"
    ]
    assert comparisons["post_setup_complete_main_selector_core"]["official"]["required_common_present"] is True
    assert comparisons["post_setup_complete_main_selector_core"]["official"]["normalized_type"] == "Action"
    assert comparisons["post_setup_complete_main_selector_core"]["native"]["normalized_type"] == "Action"
    assert set(
        comparisons["post_setup_complete_main_selector_core"]["official"]["normalized_option_types"]
    ).issuperset({"End", "Play"})
    assert comparisons["post_setup_complete_main_selector_core"]["native"]["normalized_option_types"] == [
        "Attach",
        "End",
        "Play",
    ]
    assert comparisons["post_setup_complete_main_selector_core"]["official"]["minCount"] == 1
    assert comparisons["post_setup_complete_main_selector_core"]["native"]["minCount"] == 1
    assert comparisons["post_setup_complete_main_option_card_ids"]["status"] == "pass"
    assert comparisons["post_setup_complete_main_option_card_ids"]["official"]["frame_count"] == 1
    assert comparisons["post_setup_complete_main_option_card_ids"]["native"]["frame_count"] == 1
    assert comparisons["post_setup_complete_main_option_card_ids"]["official"]["unresolved_option_count"] == 0
    assert comparisons["post_setup_complete_main_option_card_ids"]["native"]["unresolved_option_count"] == 0
    assert comparisons["post_setup_complete_main_option_card_ids"]["official"]["hand_backed_option_types"] == [
        "Attach",
        "Evolve",
        "Play",
    ]
    assert comparisons["post_setup_complete_main_option_card_ids"]["official"]["frames"][0]["context"] == "Main"
    assert comparisons["post_setup_complete_main_option_card_ids"]["native"]["frames"][0]["context"] == "Main"
    assert comparisons["post_setup_complete_main_option_card_ids"]["official"]["resolved_option_count"] > 0
    assert comparisons["post_setup_complete_main_option_card_ids"]["native"]["resolved_option_count"] > 0
    assert all(
        isinstance(card_id, int)
        for frame in comparisons["post_setup_complete_main_option_card_ids"]["official"]["frames"]
        for card_id in frame["option_card_ids"]
    )
    assert comparisons["post_first_main_end_frame_prefix_core"]["status"] == "pass"
    assert comparisons["post_first_main_end_frame_prefix_core"]["official"]["frame_count"] == 1
    assert comparisons["post_first_main_end_frame_prefix_core"]["native"]["frame_count"] == 1
    assert comparisons["post_first_main_end_frame_prefix_core"]["official"]["frames"] == comparisons[
        "post_first_main_end_frame_prefix_core"
    ]["native"]["frames"]
    first_end_frame = comparisons["post_first_main_end_frame_prefix_core"]["official"]["frames"][0]
    assert first_end_frame["context"] == "Main"
    assert first_end_frame["turn"] == 2
    assert first_end_frame["turnActionCount"] == 1
    assert first_end_frame["yourIndex"] == 0
    assert first_end_frame["players"] == [
        {"deckCount": 46, "handCount": 7, "prizeCount": 6},
        {"deckCount": 46, "handCount": 7, "prizeCount": 6},
    ]
    assert comparisons["post_first_main_end_selector_core"]["status"] == "pass"
    assert comparisons["post_first_main_end_selector_core"]["official"]["required_common_option_types"] == [
        "End",
        "Play",
    ]
    assert comparisons["post_first_main_end_selector_core"]["official"]["required_common_present"] is True
    assert comparisons["post_first_main_end_selector_core"]["official"]["normalized_type"] == "Action"
    assert comparisons["post_first_main_end_selector_core"]["native"]["normalized_type"] == "Action"
    assert set(comparisons["post_first_main_end_selector_core"]["official"]["normalized_option_types"]).issuperset(
        {"End", "Play"}
    )
    assert comparisons["post_first_main_end_selector_core"]["native"]["normalized_option_types"] == [
        "Attach",
        "End",
        "Play",
    ]
    assert comparisons["post_first_main_end_selector_core"]["official"]["minCount"] == 1
    assert comparisons["post_first_main_end_selector_core"]["native"]["minCount"] == 1
    assert comparisons["post_first_main_end_option_card_ids"]["status"] == "pass"
    assert comparisons["post_first_main_end_option_card_ids"]["official"]["frame_count"] == 1
    assert comparisons["post_first_main_end_option_card_ids"]["native"]["frame_count"] == 1
    assert comparisons["post_first_main_end_option_card_ids"]["official"]["unresolved_option_count"] == 0
    assert comparisons["post_first_main_end_option_card_ids"]["native"]["unresolved_option_count"] == 0
    assert comparisons["post_first_main_end_option_card_ids"]["official"]["frames"][0]["context"] == "Main"
    assert comparisons["post_first_main_end_option_card_ids"]["native"]["frames"][0]["context"] == "Main"
    assert comparisons["post_first_main_end_option_card_ids"]["official"]["resolved_option_count"] > 0
    assert comparisons["post_first_main_end_option_card_ids"]["native"]["resolved_option_count"] > 0
    assert all(
        isinstance(card_id, int)
        for frame in comparisons["post_first_main_end_option_card_ids"]["official"]["frames"]
        for card_id in frame["option_card_ids"]
    )
    assert comparisons["phase_alignment"]["status"] == "pass"
    assert comparisons["official_seed_surface"]["status"] == "pass"
    assert comparisons["official_seed_surface"]["official"]["exported_seed_symbols"] == []
    assert comparisons["official_seed_surface"]["official"]["unique_order_count"] >= 2
    assert comparisons["frame_by_frame_engine_parity"]["status"] == "gap"
    assert payload["summary"]["pass_count"] >= 27
    assert payload["summary"]["gap_count"] == 1
    assert payload["kaggle_submission_made"] is False
