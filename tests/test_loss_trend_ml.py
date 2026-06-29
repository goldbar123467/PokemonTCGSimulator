from __future__ import annotations

import json
from pathlib import Path

from ptcg.loss_trend_ml import build_feature_row, write_loss_trend_report


def test_build_feature_row_uses_matchup_agent_labels_and_flaws() -> None:
    row = {
        "agent_family": "hop",
        "matchup_tag": "lucario",
        "actor_archetype": "hop_trevenant",
        "opponent_archetype": "lucario",
        "decision_window": "setup_turn",
        "teacher_decision_window": "attack_choice",
        "teacher_agrees": False,
        "selected_penalties": ["attack_without_backup"],
        "flaw_tags": ["attack_without_backup"],
        "pipeline_labels": ["setup", "bench_develop"],
    }

    features = build_feature_row(row)

    assert features["matchup=lucario"] == 1
    assert features["agent_family=hop"] == 1
    assert features["teacher_disagrees"] == 1
    assert features["flaw=attack_without_backup"] == 1
    assert features["pipeline=bench_develop"] == 1


def test_write_loss_trend_report_outputs_model_and_markdown(tmp_path: Path) -> None:
    rows = []
    for index in range(12):
        rows.append(
            {
                "outcome": "loss",
                "agent_family": "hop",
                "matchup_tag": "lucario",
                "actor_archetype": "hop_trevenant",
                "opponent_archetype": "lucario",
                "decision_window": "setup_turn",
                "teacher_decision_window": "setup_turn",
                "teacher_agrees": False,
                "selected_penalties": ["attack_without_backup"],
                "flaw_tags": ["attack_without_backup"],
                "pipeline_labels": ["bench_develop"],
            }
        )
        rows.append(
            {
                "outcome": "win",
                "agent_family": "hop",
                "matchup_tag": "unknown",
                "actor_archetype": "hop_trevenant",
                "opponent_archetype": "unknown",
                "decision_window": "attack_choice",
                "teacher_decision_window": "attack_choice",
                "teacher_agrees": True,
                "selected_penalties": [],
                "flaw_tags": [],
                "pipeline_labels": ["attack_prize_race"],
            }
        )
    input_path = tmp_path / "decision_labels.jsonl"
    input_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    report = write_loss_trend_report(input_path=input_path, output_dir=tmp_path / "ml")

    assert report["rows"] == 24
    assert report["loss_rows"] == 12
    assert Path(report["paths"]["json_report"]).exists()
    markdown = Path(report["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "Kaggle submission made: no" in markdown
    assert report["top_loss_signals"]
