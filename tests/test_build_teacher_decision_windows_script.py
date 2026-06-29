import json
import subprocess
import sys


def _pokemon(card_id, *, energies=0):
    return {
        "id": card_id,
        "hp": 120,
        "maxHp": 120,
        "energies": [{"id": 1} for _ in range(energies)],
        "energyCards": [],
    }


def test_build_teacher_decision_windows_cli_writes_jsonl_and_summary(tmp_path):
    obs = {
        "current": {
            "turn": 12,
            "yourIndex": 0,
            "players": [
                {
                    "active": [_pokemon(879, energies=1)],
                    "bench": [_pokemon(878, energies=1)],
                    "hand": [],
                    "handCount": 5,
                    "deckCount": 22,
                    "prize": [None, None, None, None],
                },
                {
                    "active": [_pokemon(677, energies=2)],
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
            "option": [{"type": 13, "attackId": 1488}, {"type": 14}],
        },
    }
    replay_path = tmp_path / "seed-game.json"
    output_path = tmp_path / "teacher_windows.jsonl"
    replay_path.write_text(
        json.dumps({"info": {"EpisodeId": "seed-game"}, "steps": [[{"observation": obs, "action": [0]}]]}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_teacher_decision_windows.py",
            "--replay-dir",
            str(tmp_path),
            "--replay-ids",
            "seed-game",
            "--game-label",
            "seed-game=sleep_tempo_comeback_control",
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_summary = json.loads(result.stdout)
    file_summary = json.loads((tmp_path / "teacher_windows.summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert stdout_summary["written_rows"] == 1
    assert file_summary["written_rows"] == 1
    assert rows[0]["decision_window"] == "trap_status_turn"
    assert rows[0]["selected_labels"] == ["sleep_tempo", "behind_on_prizes_recovery"]
