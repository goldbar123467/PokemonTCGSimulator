from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ptcg.top_ranked_gameplay_report import (
    agent_gap_rows,
    build_report_data,
    label_share_rows,
    ranking_summary,
    read_episode_index_manifest,
    write_markdown_report,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_read_episode_index_manifest_selects_requested_date(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "daily_dataset_slug",
                "daily_dataset_url",
                "episode_count",
                "total_bytes",
                "top_avg_score",
                "median_avg_score",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "date": "2026-06-24",
                "daily_dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-06-24",
                "daily_dataset_url": "https://example.invalid/dataset",
                "episode_count": "5516",
                "total_bytes": "21471061743",
                "top_avg_score": "1343.560242",
                "median_avg_score": "1004.755931",
            }
        )

    row = read_episode_index_manifest(manifest, "2026-06-24")

    assert row["date"] == "2026-06-24"
    assert row["episode_count"] == 5516
    assert row["total_bytes"] == 21471061743
    assert row["total_gb"] == pytest.approx(19.997)
    assert row["daily_dataset_url"] == "https://example.invalid/dataset"


def test_ranking_summary_counts_top_teams_and_decision_burden() -> None:
    rankings = {
        "scanned_count": 3,
        "error_count": 0,
        "top_50": [
            {
                "episode_id": 1,
                "teams": ["Alpha", "Beta"],
                "winner_team": "Alpha",
                "leaderboard_scores": [1400.0, 1300.0],
                "known_leaderboard_score_sum": 2700.0,
                "winner_leaderboard_score": 1400.0,
                "decision_count": 100,
                "active_decision_count": 80,
                "steps": 120,
            },
            {
                "episode_id": 2,
                "teams": ["Alpha", "Gamma"],
                "winner_team": "Gamma",
                "leaderboard_scores": [1400.0, 1280.0],
                "known_leaderboard_score_sum": 2680.0,
                "winner_leaderboard_score": 1280.0,
                "decision_count": 50,
                "active_decision_count": 40,
                "steps": 75,
            },
        ],
    }

    summary = ranking_summary(rankings)

    assert summary["scanned_count"] == 3
    assert summary["top_count"] == 2
    assert summary["top_team_counts"][0] == {"team": "Alpha", "count": 2}
    assert summary["winner_counts"][0] == {"team": "Alpha", "count": 1}
    assert summary["decision_count_avg"] == pytest.approx(75.0)
    assert summary["score_sum_max"] == pytest.approx(2700.0)


def test_label_share_rows_and_agent_gaps_translate_counts() -> None:
    counts = {
        "attack_prize_race": 30,
        "draw/search/thin": 20,
        "energy_attach_active": 12,
        "energy_attach_bench_next_attacker": 3,
        "gust_target": 1,
        "disruption": 2,
        "unclear_or_forced": 32,
    }

    shares = label_share_rows(counts)
    gaps = agent_gap_rows(counts)

    assert shares[0]["label"] == "unclear_or_forced"
    assert shares[0]["count"] == 32
    assert any(row["gap"] == "next_attacker_underbuilt" for row in gaps)
    assert any(row["gap"] == "low_disruption_and_gust" for row in gaps)


def test_build_report_data_and_markdown_are_agent_facing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "\n".join(
            [
                "date,daily_dataset_slug,daily_dataset_url,episode_count,total_bytes,top_avg_score,median_avg_score",
                "2026-06-24,slug,https://example.invalid/dataset,5516,21471061743,1343.56,1004.75",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rankings = _write_json(
        tmp_path / "rankings.json",
        {
            "scanned_count": 5516,
            "error_count": 0,
            "source_dataset": "kaggle/pokemon-tcg-ai-battle-episodes-2026-06-24",
            "top_50": [
                {
                    "episode_id": 815,
                    "teams": ["Alpha", "Beta"],
                    "winner_team": "Alpha",
                    "known_leaderboard_score_sum": 2700.0,
                    "leaderboard_scores": [1400.0, 1300.0],
                    "winner_leaderboard_score": 1400.0,
                    "decision_count": 100,
                    "active_decision_count": 80,
                    "steps": 120,
                }
            ],
        },
    )
    labels = _write_json(
        tmp_path / "labels.json",
        {
            "episode_count_scanned": 5516,
            "selected_game_count": 1,
            "total_decision_count": 100,
            "total_key_decision_count": 8,
            "combined_label_counts": {"attack_prize_race": 60, "energy_attach_active": 20},
            "teacher_rules": ["build a bench attacker before racing"],
            "validation": {"passed": True},
            "kaggle_submission_made": False,
        },
    )
    meta = _write_json(
        tmp_path / "meta.json",
        {
            "date": "2026-06-24",
            "latestDate": "2026-06-24",
            "redirected": False,
            "totalDecks": 11032,
            "source": {"datasetUrl": "https://example.invalid/dataset"},
            "archetypes": [
                {"name": "Mega Lucario ex / Riolu", "metaShare": 0.22, "winRate": 0.42, "appearances": 2492},
            ],
        },
    )

    data = build_report_data(
        date="2026-06-24",
        full_dataset_dir=tmp_path,
        episode_manifest_path=manifest,
        rankings_path=rankings,
        labels_path=labels,
        meta_snapshot_path=meta,
    )
    out = tmp_path / "report.md"
    write_markdown_report(data, out, figure_rel_paths={"x": "figures/x.png"})
    text = out.read_text(encoding="utf-8")

    assert data["dataset"]["local_full_dataset_files"] >= 4
    assert data["ranking_summary"]["scanned_count"] == 5516
    assert data["label_summary"]["selected_game_count"] == 1
    assert "Kaggle submission made: `no`" in text
    assert "Learned-policy claim: `no`" in text
