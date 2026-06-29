import json
from pathlib import Path

from scripts.build_current_meta_replay_gates import build_current_meta_replay_gates


def test_build_current_meta_replay_gates_extracts_replay_deck_and_manifest(tmp_path):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    gate_root = tmp_path / "gates"
    mining_dir = tmp_path / "mining"
    pilot_main = tmp_path / "main.py"
    candidate_main = tmp_path / "candidate.py"
    candidate_deck = tmp_path / "candidate_deck.csv"
    coverage_path = tmp_path / "coverage.json"
    output_manifest = tmp_path / "manifest.json"

    hop_deck = [878, 879, 1171, 11, 19] + [1] * 55
    lucario_deck = [677, 678, 6, 1142, 1227] + [1] * 55
    replay_path = replay_dir / "episode-1-replay.json"
    replay_path.write_text(
        json.dumps(
            {
                "steps": [
                    [
                        {"action": lucario_deck},
                        {"action": hop_deck},
                    ]
                ]
            }
        ),
        encoding="utf-8",
    )
    coverage_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "episode_id": "1",
                        "file": replay_path.name,
                        "classification": "hop_trevenant",
                        "opponent_index": 1,
                        "outcome": "loss",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pilot_main.write_text("def agent(obs):\n    return []\n", encoding="utf-8")
    candidate_main.write_text("def agent(obs):\n    return []\n", encoding="utf-8")
    candidate_deck.write_text("\n".join(str(card_id) for card_id in lucario_deck), encoding="utf-8")

    rows = build_current_meta_replay_gates(
        coverage_path=coverage_path,
        replay_dir=replay_dir,
        gate_root=gate_root,
        mining_dir=mining_dir,
        output_manifest=output_manifest,
        pilot_main=pilot_main,
        candidate_main=candidate_main,
        candidate_deck=candidate_deck,
        smoke_games=0,
        seed=101,
    )

    row = next(item for item in rows if item["archetype"] == "hop_trevenant")
    assert row["archetype"] == "hop_trevenant"
    assert row["raw_weight"] == 15.4
    assert row["deck_source"] == "public_local_replay:episode-1-replay.json:player1"
    assert row["pilot_source"] == str(pilot_main)
    assert row["snapshot_date"] == "2026-06-24"
    assert row["smoke_ok"] is True
    assert row["ok"] is True
    assert row["errors"] == []
    assert "hop_trevenant" in row["tags"]
    assert Path(row["main_path"]).read_text(encoding="utf-8") == "def agent(obs):\n    return []\n"
    assert len(Path(row["deck_path"]).read_text(encoding="utf-8").splitlines()) == 60
    evidence = json.loads((mining_dir / "hop_trevenant_evidence.json").read_text(encoding="utf-8"))
    assert evidence["archetype"] == "hop_trevenant"
    assert evidence["games"][0]["episode_id"] == "1"
    assert output_manifest.exists()


def test_build_current_meta_replay_gates_uses_live_meta_snapshot_weights(tmp_path):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()
    gate_root = tmp_path / "gates"
    mining_dir = tmp_path / "mining"
    pilot_main = tmp_path / "main.py"
    candidate_main = tmp_path / "candidate.py"
    candidate_deck = tmp_path / "candidate_deck.csv"
    coverage_path = tmp_path / "coverage.json"
    output_manifest = tmp_path / "manifest.json"

    lucario_deck = [677, 678, 6, 1142, 1227] + [1] * 55
    replay_path = replay_dir / "episode-2-replay.json"
    replay_path.write_text(
        json.dumps({"steps": [[{"action": lucario_deck}, {"action": lucario_deck}]]}),
        encoding="utf-8",
    )
    coverage_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "episode_id": "2",
                        "file": replay_path.name,
                        "classification": "lucario_mirror",
                        "opponent_index": 1,
                        "outcome": "win",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pilot_main.write_text("def agent(obs):\n    return []\n", encoding="utf-8")
    candidate_main.write_text("def agent(obs):\n    return []\n", encoding="utf-8")
    candidate_deck.write_text("\n".join(str(card_id) for card_id in lucario_deck), encoding="utf-8")

    rows = build_current_meta_replay_gates(
        coverage_path=coverage_path,
        replay_dir=replay_dir,
        gate_root=gate_root,
        mining_dir=mining_dir,
        output_manifest=output_manifest,
        pilot_main=pilot_main,
        candidate_main=candidate_main,
        candidate_deck=candidate_deck,
        smoke_games=0,
        seed=101,
        meta_snapshot={
            "date": "2026-06-26",
            "latestDate": "2026-06-26",
            "redirected": False,
            "totalDecks": 11200,
            "source": {
                "datasetUrl": "https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-06-26"
            },
            "archetypes": [
                {"name": "Mega Lucario ex / Riolu", "metaShare": 0.210625},
                {"name": "Dragapult ex / Drakloak", "metaShare": 0.0775},
            ],
        },
    )

    lucario = next(item for item in rows if item["archetype"] == "lucario")
    assert lucario["raw_weight"] == 21.0625
    assert lucario["snapshot_date"] == "2026-06-26"
    assert lucario["latest_date"] == "2026-06-26"
    assert lucario["redirected"] is False
    assert lucario["total_decks"] == 11200
    assert lucario["kaggle_dataset_url"].endswith("2026-06-26")
