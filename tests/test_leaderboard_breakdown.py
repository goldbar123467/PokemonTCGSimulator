from __future__ import annotations

import json
from pathlib import Path

from ptcg.leaderboard_breakdown import build_label_dataset
from ptcg.leaderboard_breakdown import infer_focus_team
from ptcg.leaderboard_breakdown import load_patch_map_decisions
from ptcg.leaderboard_breakdown import owner_label


def _pokemon(card_id: int, *, hp: int = 100, max_hp: int = 100, energies: int = 0) -> dict:
    return {
        "id": card_id,
        "hp": hp,
        "maxHp": max_hp,
        "energies": [{"id": 1} for _ in range(energies)],
        "energyCards": [],
    }


def _obs(*, your_index: int, turn: int = 1) -> dict:
    players = [
        {
            "active": [_pokemon(878, energies=1)],
            "bench": [_pokemon(65, energies=0)],
            "hand": [{"id": 19}, {"id": 66}],
            "handCount": 2,
            "deckCount": 40,
            "discard": [],
            "prize": [None, None, None, None, None, None],
        },
        {
            "active": [_pokemon(678, hp=150, max_hp=340, energies=2)],
            "bench": [_pokemon(677)],
            "handCount": 4,
            "deckCount": 42,
            "discard": [],
            "prize": [None, None, None, None, None],
        },
    ]
    return {
        "current": {"turn": turn, "yourIndex": your_index, "players": players},
        "select": {
            "context": 0,
            "type": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 14},
                {"type": 8, "area": 2, "index": 0, "playerIndex": 0, "inPlayArea": 5, "inPlayIndex": 0},
                {"type": 13, "attackId": 1267},
            ],
        },
        "logs": [{"type": 0, "playerIndex": your_index}],
    }


def _episode(path: Path, *, teams: list[str], rewards: list[int]) -> Path:
    steps = [
        [
            {"action": [11, 11, 11, 11, 878, 878, 878, 878, 879, 879] + [65] * 50},
            {"action": [673, 674, 675, 676, 677, 677, 678, 678] + [6] * 52},
        ],
        [
            {"observation": _obs(your_index=0), "action": [0], "reward": rewards[0], "status": "ACTIVE"},
            {"observation": _obs(your_index=1), "action": [1], "reward": rewards[1], "status": "INACTIVE"},
        ],
        [
            {"observation": _obs(your_index=0, turn=2), "action": [2], "reward": rewards[0], "status": "ACTIVE"},
            {"observation": _obs(your_index=1, turn=2), "action": [0], "reward": rewards[1], "status": "INACTIVE"},
        ],
    ]
    path.write_text(
        json.dumps({"info": {"EpisodeId": int(path.stem), "TeamNames": teams}, "rewards": rewards, "steps": steps}),
        encoding="utf-8",
    )
    return path


def test_infer_focus_team_prefers_repeated_non_empty_team(tmp_path: Path) -> None:
    one = _episode(tmp_path / "1.json", teams=["Focus", "A"], rewards=[-1, 1])
    two = _episode(tmp_path / "2.json", teams=["B", "Focus"], rewards=[1, -1])

    assert infer_focus_team([one, two]) == "Focus"


def test_owner_label_keeps_clark_and_focus_distinct() -> None:
    assert owner_label("Clark Kitchen", focus_team="CCoffie") == "clark_kitchen"
    assert owner_label("CCoffie", focus_team="CCoffie") == "focus_user_supplied_agent"
    assert owner_label("Other", focus_team="CCoffie") == "external_kaggle_team"


def test_build_label_dataset_writes_focus_loss_corrections(tmp_path: Path) -> None:
    episode = _episode(tmp_path / "81871400.json", teams=["CCoffie", "Other"], rewards=[-1, 1])
    output_dir = tmp_path / "labels"

    result = build_label_dataset([episode], output_dir=output_dir, focus_team="CCoffie", command="test")

    assert result["focus_team"] == "CCoffie"
    assert result["summary"]["games"] == 1
    assert result["summary"]["decision_rows"] == 4
    assert result["summary"]["focus_loss_rows"] == 2
    assert result["summary"]["heuristic_patch_rows"] >= 1
    assert Path(result["paths"]["hard_labels_jsonl"]).exists()
    assert Path(result["paths"]["heuristic_patch_map_jsonl"]).exists()

    rows = [json.loads(line) for line in Path(result["paths"]["hard_labels_jsonl"]).read_text().splitlines()]
    focus_rows = [row for row in rows if row["source_owner"] == "focus_user_supplied_agent"]
    assert focus_rows
    assert focus_rows[0]["actor_archetype"] == "hop_trevenant"
    assert focus_rows[0]["opponent_archetype"] == "lucario"
    assert focus_rows[0]["outcome"] == "loss"
    assert focus_rows[0]["phase"] in {"opening", "midgame", "finish"}
    assert "teacher_preferred_alternative" in focus_rows[0]["flaw_tags"]
    assert focus_rows[0]["research_role"] == "focus_loss_heuristic_patch"

    decisions = load_patch_map_decisions(Path(result["paths"]["heuristic_patch_map_jsonl"]))
    assert decisions
    assert decisions[0].replay_id == "81871400"
    assert decisions[0].action_indices
