from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg.daily_episode_labeling import (
    LABEL_TAXONOMY,
    consolidate_label_files,
    load_leaderboard_scores,
    rank_episode_summaries,
    summarize_episode,
    write_phase_packets,
)


def _card(card_id: int, name: str) -> dict:
    return {"id": card_id, "name": name}


def _decision(
    *,
    action: list[int],
    options: list[dict],
    turn: int = 1,
    status: str = "ACTIVE",
    agent_index: int = 0,
) -> dict:
    players = [
        {
            "active": [_card(10, "Active A")],
            "bench": [_card(11, "Bench A")],
            "hand": [_card(100, "Search A"), _card(101, "Energy A")],
            "deck": [_card(200, "Deck A")],
            "discard": [],
            "prize": [1, 2, 3, 4, 5, 6],
        },
        {
            "active": [_card(20, "Active B")],
            "bench": [_card(21, "Bench B")],
            "hand": [_card(102, "Search B")],
            "deck": [_card(201, "Deck B")],
            "discard": [_card(202, "Discard B")],
            "prize": [1, 2, 3, 4, 5],
        },
    ]
    return {
        "action": action,
        "observation": {
            "current": {"turn": turn, "yourIndex": agent_index, "players": players},
            "logs": [{"type": 0, "playerIndex": agent_index}],
            "search_begin_input": "state",
            "select": {
                "context": 1,
                "type": 2,
                "minCount": 1,
                "maxCount": 1,
                "option": options,
            },
        },
        "reward": 0,
        "status": status,
    }


def _episode(path: Path) -> Path:
    steps = [
        [
            {"action": [1] * 60, "observation": {}, "reward": 0, "status": "ACTIVE"},
            {"action": [2] * 60, "observation": {}, "reward": 0, "status": "ACTIVE"},
        ]
    ]
    for turn in range(1, 7):
        steps.append(
            [
                _decision(
                    action=[0],
                    options=[
                        {"type": 3, "area": 2, "index": 0, "playerIndex": 0},
                        {"type": 14, "attackId": 44},
                    ],
                    turn=turn,
                    agent_index=0,
                ),
                _decision(
                    action=[],
                    options=[{"type": 13}],
                    turn=turn,
                    status="INACTIVE",
                    agent_index=1,
                ),
            ]
        )
    episode = {
        "configuration": {"seed": 123},
        "info": {"EpisodeId": 999, "TeamNames": ["Alpha", "Beta"]},
        "rewards": [1, -1],
        "steps": steps,
    }
    path.write_text(json.dumps(episode), encoding="utf-8")
    return path


def test_summarize_episode_uses_leaderboard_scores_and_decision_counts(tmp_path: Path) -> None:
    leaderboard = tmp_path / "leaderboard.csv"
    leaderboard.write_text("teamName,score\nAlpha,1400.5\nBeta,1300.25\n", encoding="utf-8")
    episode_path = _episode(tmp_path / "999.json")

    summary = summarize_episode(episode_path, load_leaderboard_scores(leaderboard))

    assert summary["episode_id"] == 999
    assert summary["teams"] == ["Alpha", "Beta"]
    assert summary["winner_team"] == "Alpha"
    assert summary["leaderboard_scores"] == [1400.5, 1300.25]
    assert summary["known_leaderboard_score_sum"] == pytest.approx(2700.75)
    assert summary["decision_count"] == 6
    assert summary["active_decision_count"] == 6


def test_rank_episode_summaries_prefers_known_top_scores_and_decision_richness() -> None:
    lower = {
        "leaderboard_scores": [1000.0, None],
        "known_leaderboard_score_sum": 1000.0,
        "winner_leaderboard_score": 1000.0,
        "active_decision_count": 20,
        "steps": 90,
    }
    richer = {
        "leaderboard_scores": [1100.0, 1200.0],
        "known_leaderboard_score_sum": 2300.0,
        "winner_leaderboard_score": 1100.0,
        "active_decision_count": 10,
        "steps": 70,
    }

    assert rank_episode_summaries([lower, richer])[0] is richer


def test_write_phase_packets_splits_decisions_and_resolves_selected_cards(tmp_path: Path) -> None:
    episode_path = _episode(tmp_path / "999.json")
    manifest = write_phase_packets(episode_path, tmp_path / "packets")

    assert manifest["decision_count"] == 6
    assert set(manifest["phase_packets"]) == {"opening", "midgame", "finish"}
    opening = json.loads(Path(manifest["phase_packets"]["opening"]).read_text(encoding="utf-8"))
    assert opening["decision_count"] == 2
    assert opening["decisions"][0]["selected_options"][0]["resolved_card"] == "Search A#100"
    assert LABEL_TAXONOMY[0] == "setup"


def test_consolidate_label_files_validates_taxonomy_and_counts(tmp_path: Path) -> None:
    episode_path = _episode(tmp_path / "999.json")
    manifest = write_phase_packets(episode_path, tmp_path / "packets")
    label_dir = tmp_path / "labels"
    label_dir.mkdir()
    label_files = {}
    for phase, packet_path in manifest["phase_packets"].items():
        packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
        label_path = label_dir / f"{phase}.labels.json"
        label_path.write_text(
            json.dumps(
                {
                    "phase": phase,
                    "source_packet": packet_path,
                    "summary": f"{phase} labels",
                    "label_counts": {"setup": packet["decision_count"]},
                    "key_decisions": [
                        {
                            "step_index": packet["decisions"][0]["step_index"],
                            "agent_index": 0,
                            "team": "Alpha",
                            "intent_label": "setup",
                            "why": "visible search option develops board",
                            "teacher_rule": "prefer setup search when board is undeveloped",
                            "confidence": 0.8,
                        }
                    ],
                    "teacher_rules": ["prefer setup search when board is undeveloped"],
                    "uncertainty_notes": [],
                }
            ),
            encoding="utf-8",
        )
        label_files[phase] = label_path

    report = consolidate_label_files(
        packet_manifest=manifest,
        label_files=label_files,
        output_path=tmp_path / "consolidated.json",
    )

    assert report["validation"]["passed"] is True
    assert report["key_decision_count"] == 3
    assert report["combined_label_counts"]["setup"] == 6

    bad_path = label_dir / "bad.labels.json"
    bad_path.write_text(
        json.dumps(
            {
                "label_counts": {"made_up": 1},
                "key_decisions": [],
                "teacher_rules": [],
                "uncertainty_notes": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown count label"):
        consolidate_label_files(
            packet_manifest=manifest,
            label_files={"opening": bad_path},
            output_path=tmp_path / "bad.json",
        )
