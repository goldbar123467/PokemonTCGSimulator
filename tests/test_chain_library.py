from __future__ import annotations

import json
from pathlib import Path

from ptcg.chain_library import build_chain_report
from ptcg.chain_library import build_chain_rows
from ptcg.chain_library import write_chain_library


def _row(
    *,
    step_index: int,
    turn: int,
    outcome: str = "loss",
    matchup: str = "lucario",
    chosen_action: list[int] | None = None,
    teacher_action: list[int] | None = None,
    teacher_agrees: bool = False,
    flaw_tags: list[str] | None = None,
    pipeline_labels: list[str] | None = None,
    legal_actions: list[dict] | None = None,
) -> dict:
    return {
        "episode_id": 81890921,
        "replay_id": "81890921",
        "step_index": step_index,
        "submission_id": 54050816,
        "agent_family": "submission-lucario-loss-guard-iter5-inline-v2",
        "team_name": "Clark Kitchen",
        "data_source": "kaggle_public_episode",
        "actor_owner": "Clark Kitchen",
        "actor_index": 1,
        "opponent_index": 0,
        "opponent_team_name": "Opponent",
        "outcome": outcome,
        "winner_side": 0 if outcome == "loss" else 1,
        "reward": -1.0 if outcome == "loss" else 1.0,
        "matchup_tag": matchup,
        "actor_archetype": "lucario",
        "opponent_archetype": matchup,
        "observation": {
            "current": {
                "turn": turn,
                "yourIndex": 1,
                "players": [
                    {
                        "active": [{"id": 678, "hp": 280, "maxHp": 280, "energies": [6, 6]}],
                        "bench": [{"id": 677, "hp": 70, "maxHp": 70, "energies": []}],
                        "deckCount": 28,
                        "handCount": 4,
                        "prize_count": 4,
                    },
                    {
                        "active": [{"id": 676, "hp": 110, "maxHp": 110, "energies": [6]}],
                        "bench": [{"id": 677, "hp": 70, "maxHp": 70, "energies": []}],
                        "deckCount": 27,
                        "handCount": 5,
                        "prize_count": 5,
                    },
                ],
            },
            "select": {"context": 0, "option": legal_actions or [{"type": 13, "attackId": 1488}, {"type": 14}]},
        },
        "legal_actions": legal_actions or [{"type": 13, "attackId": 1488}, {"type": 14}],
        "chosen_action": chosen_action if chosen_action is not None else [1],
        "teacher_action": teacher_action if teacher_action is not None else [0],
        "teacher_agrees": teacher_agrees,
        "selected_labels": [],
        "selected_penalties": [],
        "teacher_labels": [],
        "teacher_penalties": [],
        "selected_score": 0.0,
        "teacher_score": 2.0,
        "pipeline_labels": pipeline_labels or [],
        "flaw_tags": flaw_tags or [],
        "sample_weight": 2.0,
        "research_role": "loss_correction_patch" if outcome == "loss" else "winning_reference",
        "leaderboard_score": 799.1,
    }


def test_build_chain_rows_groups_turn_and_labels_loss_correction() -> None:
    rows = [
        _row(
            step_index=10,
            turn=4,
            chosen_action=[0],
            flaw_tags=["missed_setup"],
            pipeline_labels=["setup", "bench_develop"],
        ),
        _row(
            step_index=11,
            turn=4,
            legal_actions=[{"type": 8, "inPlayArea": 5, "inPlayIndex": 0}, {"type": 14}],
            chosen_action=[1],
            teacher_action=[0],
            flaw_tags=["attack_without_backup"],
            pipeline_labels=["energy_attach_bench_next_attacker"],
        ),
    ]

    chains = build_chain_rows(rows)

    assert len(chains) == 1
    chain = chains[0]
    assert chain["chain_id"] == "81890921:1:4:10-11"
    assert chain["chain_quality"] == "loss_correction"
    assert chain["step_indices"] == [10, 11]
    assert chain["action_type_counts"]["attack"] == 1
    assert chain["action_type_counts"]["end"] == 1
    assert "setup" in chain["posture_tags"]
    assert "next_attacker_gap" in chain["posture_tags"]
    assert "anti_lucario_gate" in chain["strategy_labels"]
    assert "loss_correction_patch" in chain["strategy_labels"]
    assert chain["teacher_disagreements"] == 2


def test_build_chain_rows_marks_clean_winning_chain_as_successful_strategy() -> None:
    rows = [
        _row(
            step_index=20,
            turn=8,
            outcome="win",
            matchup="mega_starmie",
            chosen_action=[0],
            teacher_action=[0],
            teacher_agrees=True,
            flaw_tags=[],
            pipeline_labels=["attack_prize_race", "energy_attach_bench_next_attacker"],
        )
    ]

    chains = build_chain_rows(rows)

    assert len(chains) == 1
    assert chains[0]["chain_quality"] == "successful_strategy"
    assert "successful_strategy_to_imitate" in chains[0]["strategy_labels"]
    assert "anti_mega_starmie_spread_gate" in chains[0]["strategy_labels"]
    assert chains[0]["teacher_agreement_rate"] == 1.0


def test_build_chain_report_summarizes_quality_matchups_and_no_submission() -> None:
    chains = build_chain_rows(
        [
            _row(step_index=1, turn=1, flaw_tags=["missed_setup"]),
            _row(step_index=2, turn=2, outcome="win", teacher_agrees=True, chosen_action=[0], teacher_action=[0]),
        ]
    )

    report = build_chain_report(
        chains,
        decision_rows=[{"episode_id": 81890921}, {"episode_id": 81890921}],
        command="pytest",
        decision_labels_path=Path("decision_labels.jsonl"),
        output_dir=Path("out"),
        source_run_report={"dataset_report": {"decision_rows": 2}},
    )

    assert report["total_chains"] == 2
    assert report["total_decisions"] == 2
    assert report["usable_decisions"] == 2
    assert report["filtered_startup_deck_rows"] == 0
    assert report["chain_quality_counts"]["loss_correction"] == 1
    assert report["matchup_counts"]["lucario"] == 2
    assert report["kaggle_submission_made"] is False
    assert report["research_role"] == "replay_chain_library_for_heuristic_patch_and_engine_audit"


def test_write_chain_library_emits_jsonl_json_and_markdown(tmp_path: Path) -> None:
    decision_path = tmp_path / "decision_labels.jsonl"
    rows = [
        _row(step_index=1, turn=1, flaw_tags=["missed_setup"]),
        _row(step_index=2, turn=1, flaw_tags=["teacher_preferred_alternative"]),
        _row(step_index=3, turn=2, outcome="win", chosen_action=[0], teacher_action=[0], teacher_agrees=True),
    ]
    decision_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    report = write_chain_library(
        decision_labels_path=decision_path,
        output_dir=tmp_path / "library",
        command="pytest chain write",
    )

    assert report["total_decisions"] == 3
    assert report["total_chains"] == 2
    chain_path = Path(report["paths"]["chain_library_jsonl"])
    report_path = Path(report["paths"]["chain_library_report_json"])
    markdown_path = Path(report["paths"]["chain_library_report_md"])
    assert chain_path.exists()
    assert report_path.exists()
    assert markdown_path.exists()
    assert len(chain_path.read_text(encoding="utf-8").splitlines()) == 2
    assert "Kaggle submission made: no" in markdown_path.read_text(encoding="utf-8")


def test_build_chain_rows_filters_startup_deck_payloads() -> None:
    startup = _row(
        step_index=1,
        turn=0,
        chosen_action=[677] * 60,
        teacher_action=[0],
        flaw_tags=["unconverted_decision"],
        legal_actions=[{"type": 3, "area": 2, "index": 0, "playerIndex": 1}],
    )
    real_move = _row(step_index=2, turn=0, chosen_action=[0], teacher_action=[0], teacher_agrees=True)

    chains = build_chain_rows([startup, real_move])

    assert len(chains) == 1
    assert chains[0]["step_indices"] == [2]
    assert chains[0]["chain_length"] == 1
