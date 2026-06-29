from __future__ import annotations

import json
import subprocess
import sys

from scripts.native_official_observed_startup import observed_setup_prompt_player


def test_official_visualize_snapshot_script_emits_visualizer_timeline() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/official_visualize_snapshot.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--max-frames",
            "3",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["source"] == "official cg.VisualizeData"
    assert payload["decks"]["player"]["count"] == 60
    assert payload["decks"]["opponent"]["count"] == 60
    assert payload["visualizer"]["frame_count"] >= 1
    assert len(payload["visualizer"]["frames"]) <= 3
    assert payload["visualizer"]["frames"][0]["select"]["context"] == "IsFirst"
    assert payload["visualizer"]["frames"][0]["current"]["players"][0]["deckCount"] == 60
    assert payload["kaggle_submission_made"] is False


def test_official_setup_branch_probe_captures_drawcount_branch() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/official_setup_branch_probe.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--attempts",
            "80",
            "--draw-count-choice",
            "0",
            "--max-frames",
            "6",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    draw_count_example = payload["examples"]["DrawCount"]

    assert payload["source"] == "official cg setup branch probe"
    assert payload["branch_counts"]["DrawCount"] > 0
    assert payload["branch_counts"]["SetupBenchPokemon"] > 0 or payload["branch_counts"]["Main"] > 0
    assert draw_count_example["fourth_frame"]["select"]["context"] == "DrawCount"
    assert draw_count_example["draw_count_choice"] == 0
    assert draw_count_example["after_draw_count"]["frame_count"] >= 5
    assert draw_count_example["after_draw_count"]["frames"][-1]["select"]["context"] in {
        "SetupBenchPokemon",
        "Main",
    }
    assert payload["kaggle_submission_made"] is False


def test_official_shuffle_probe_documents_seed_surface_and_startup_order_gap() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/official_shuffle_probe.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--attempts",
            "6",
            "--first-player",
            "1",
            "--native-seed",
            "17",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)

    assert payload["source"] == "official shuffle and seed-surface probe"
    assert payload["command"][:2] == [sys.executable, "scripts/official_shuffle_probe.py"]
    assert payload["input_paths"]["deck"].endswith("deck.csv")
    assert payload["input_paths"]["opponent_deck"].endswith("deck.csv")
    assert payload["source_metadata"]["official_library"].endswith("libcg.so")
    assert payload["decks"]["player"]["count"] == 60
    assert payload["seed_surface"]["exported_seed_symbols"] == []
    assert payload["seed_surface"]["has_random_device_symbol"] is True
    assert payload["seed_surface"]["has_mt19937_symbol"] is True
    assert payload["official"]["attempt_count"] == 6
    assert payload["official"]["unique_order_count"] >= 2
    assert payload["official"]["deterministic_replay_available"] is False
    assert payload["native"]["same_seed_deterministic"] is True
    assert payload["native"]["different_seed_changes_order"] is True
    assert payload["conclusion"]["standalone_exact_order_requires_official_seed_control"] is True
    assert payload["kaggle_submission_made"] is False


def test_native_official_observed_startup_replay_matches_reference_order() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/native_official_observed_startup.py",
            "--deck",
            "deck.csv",
            "--opponent-deck",
            "deck.csv",
            "--first-player",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)

    assert payload["source"] == "native official-observed startup replay"
    assert payload["status"] == "observed_order_replay_match"
    assert payload["command"][:2] == [sys.executable, "scripts/native_official_observed_startup.py"]
    assert payload["input_paths"]["deck"].endswith("deck.csv")
    assert payload["official"]["first_player"] == 1
    assert payload["official"]["frame"]["select"]["context"] == "SetupActivePokemon"
    assert payload["native"]["started_from"] == "official_observed_ordered_zones"
    assert payload["native"]["frame"]["select"]["context"] == "SetupActivePokemon"
    assert payload["comparison"]["status"] == "pass"
    assert payload["comparison"]["official"]["players"] == payload["comparison"]["native"]["players"]
    assert payload["comparison"]["official"]["selector_option_card_ids"] == payload["comparison"]["native"][
        "selector_option_card_ids"
    ]
    assert payload["comparison"]["official"]["selector_option_serials"] == payload["comparison"]["native"][
        "selector_option_serials"
    ]
    assert payload["kaggle_submission_made"] is False


def test_observed_startup_uses_official_prompt_player_after_opening_mulligan() -> None:
    assert observed_setup_prompt_player({"yourIndex": 0}, first_player=1) == 0
