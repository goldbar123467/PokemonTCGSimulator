from __future__ import annotations

from pathlib import Path

from ptcg.trace_analysis import summarize_trace_report, summarize_trace_reports, write_trace_failure_summary


def _step(*, action: list[int], options: list[dict], us: dict, them: dict, turn: int = 2) -> dict:
    return {
        "turn": turn,
        "select_context": 0,
        "select_type": 0,
        "action": action,
        "options": options,
        "us": us,
        "them": them,
    }


def test_summarize_trace_report_flags_empty_bench_attacks_and_overactive_attachment():
    report = {
        "opponent": "public/lucario",
        "games": 1,
        "finished": 1,
        "wins": 0,
        "losses": 1,
        "draws": 0,
        "errors": [],
        "traces": [
            {
                "game_index": 0,
                "candidate_first": True,
                "candidate_result": "loss",
                "steps": [
                    _step(
                        action=[0],
                        options=[
                            {
                                "index": 0,
                                "selected": True,
                                "type": 8,
                                "inPlayArea": 4,
                                "target_card": {"id": 721, "hp": 40, "maxHp": 150, "energies": 2},
                            },
                            {
                                "index": 1,
                                "selected": False,
                                "type": 8,
                                "inPlayArea": 5,
                                "target_card": {"id": 722, "hp": 90, "maxHp": 90, "energies": 0},
                            },
                        ],
                        us={
                            "active": {"id": 721, "hp": 40, "maxHp": 150, "energies": 2},
                            "bench": [{"id": 722, "hp": 90, "maxHp": 90, "energies": 0}],
                            "bench_count": 1,
                            "powered_board": 1,
                        },
                        them={
                            "active": {"id": 676, "hp": 110, "maxHp": 110, "energies": 2},
                            "bench": [],
                            "bench_count": 0,
                            "powered_board": 1,
                        },
                    ),
                    _step(
                        action=[0],
                        options=[{"index": 0, "selected": True, "type": 13, "attackId": 1044}],
                        us={
                            "active": {"id": 721, "hp": 40, "maxHp": 150, "energies": 4},
                            "bench": [],
                            "bench_count": 0,
                            "powered_board": 1,
                        },
                        them={
                            "active": {"id": 676, "hp": 110, "maxHp": 110, "energies": 2},
                            "bench": [{"id": 677, "hp": 180, "maxHp": 180, "energies": 0}],
                            "bench_count": 1,
                            "powered_board": 1,
                        },
                    ),
                ],
            }
        ],
    }

    summary = summarize_trace_report(report)

    assert summary["opponent"] == "public/lucario"
    assert summary["metrics"]["candidate_steps"] == 2
    assert summary["metrics"]["active_overattach_steps"] == 1
    assert summary["metrics"]["bench_attach_available_but_missed"] == 1
    assert summary["metrics"]["empty_bench_attacks"] == 1
    assert "overfeeding_active" in summary["failure_tags"]
    assert "single_active_attack_race" in summary["failure_tags"]


def test_summarize_trace_reports_aggregates_multiple_files(tmp_path):
    first = {
        "opponent": "public/a",
        "games": 1,
        "finished": 1,
        "wins": 1,
        "losses": 0,
        "draws": 0,
        "errors": [],
        "traces": [{"steps": []}],
    }
    second = {
        "opponent": "public/b",
        "games": 1,
        "finished": 1,
        "wins": 0,
        "losses": 1,
        "draws": 0,
        "errors": ["boom"],
        "traces": [
            {
                "steps": [
                    _step(
                        action=[0],
                        options=[{"index": 0, "selected": True, "type": 14}],
                        us={
                            "active": {"id": 1, "hp": 70, "maxHp": 100, "energies": 0},
                            "bench": [],
                            "bench_count": 0,
                            "powered_board": 0,
                        },
                        them={
                            "active": {"id": 2, "hp": 100, "maxHp": 100, "energies": 2},
                            "bench": [],
                            "bench_count": 0,
                            "powered_board": 1,
                        },
                    )
                ]
            }
        ],
    }
    first_path = tmp_path / "a.json"
    second_path = tmp_path / "b.json"
    first_path.write_text(__import__("json").dumps(first), encoding="utf-8")
    second_path.write_text(__import__("json").dumps(second), encoding="utf-8")

    summary = summarize_trace_reports([first_path, second_path])

    assert summary["aggregate"]["reports"] == 2
    assert summary["aggregate"]["wins"] == 1
    assert summary["aggregate"]["errors"] == 1
    assert summary["aggregate"]["end_without_backup_steps"] == 1
    tagged = [report for report in summary["reports"] if report["failure_tags"]]
    assert "ending_without_backup" in tagged[0]["failure_tags"]


def test_write_trace_failure_summary_writes_json(tmp_path):
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(
        __import__("json").dumps(
            {
                "opponent": "public/a",
                "games": 0,
                "finished": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "errors": [],
                "traces": [],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "summary.json"

    write_trace_failure_summary([trace_path], output)

    assert output.exists()
