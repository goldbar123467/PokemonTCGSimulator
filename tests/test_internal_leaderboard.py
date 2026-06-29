from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from ptcg.internal_leaderboard import (
    build_candidate_registry,
    build_gate_rows,
    build_submit_offer,
    meta_weights_from_snapshot,
    rank_candidates,
)


def _write_archive(root: Path, name: str, main_text: str, deck_ids: list[int], include_cg: bool = True) -> Path:
    package = root / name
    package.mkdir()
    (package / "main.py").write_text(main_text, encoding="utf-8")
    (package / "deck.csv").write_text("\n".join(str(card_id) for card_id in deck_ids) + "\n", encoding="utf-8")
    if include_cg:
        cg_dir = package / "cg"
        cg_dir.mkdir()
        (cg_dir / "__init__.py").write_text("", encoding="utf-8")
        (cg_dir / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = root / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))
    return archive


def test_candidate_registry_records_validation_warning_without_blocking_policyless_archive(tmp_path: Path):
    good = _write_archive(
        tmp_path,
        "submission_archaludon_policyless",
        "def agent(obs):\n    return [169, 190, 8, 1227, 1182] + [1] * 55\n",
        [169, 190, 8, 1227, 1182] + [1] * 55,
    )
    broken = _write_archive(
        tmp_path,
        "submission_broken_missing_cg",
        "def agent(obs):\n    return [9] * 60\n",
        [9] * 60,
        include_cg=False,
    )

    rows = build_candidate_registry([good, broken], extract_root=tmp_path / "extracted")

    good_row = next(row for row in rows if row["name"] == "submission_archaludon_policyless")
    assert good_row["validator_ok"] is True
    assert good_row["eligible_for_benchmark"] is True
    assert good_row["policy_module_loaded"] is False
    assert "policy_module_not_loaded" in good_row["warnings"]
    assert good_row["archetype"] == "archaludon"
    assert Path(good_row["main_path"]).exists()
    assert Path(good_row["deck_path"]).exists()

    broken_row = next(row for row in rows if row["name"] == "submission_broken_missing_cg")
    assert broken_row["validator_ok"] is False
    assert broken_row["eligible_for_benchmark"] is False
    assert "cg/api.py" in broken_row["validation_error"]


def test_meta_weights_from_snapshot_combines_alias_rows_and_records_source():
    weights = meta_weights_from_snapshot(
        {
            "date": "2026-06-26",
            "latestDate": "2026-06-26",
            "redirected": False,
            "totalDecks": 11200,
            "source": {"datasetUrl": "https://example.test/dataset"},
            "archetypes": [
                {"name": "Legacy Energy / Hop's Phantump", "metaShare": 0.1524107142857143},
                {"name": "Hop's Phantump / Hop's Trevenant", "metaShare": 0.019285714285714285},
                {"name": "Archaludon ex / Duraludon", "metaShare": 0.08696428571428572},
            ],
        }
    )

    assert weights["hop_trevenant"]["raw_weight"] == pytest.approx(17.16964285714286)
    assert weights["hop_trevenant"]["date"] == "2026-06-26"
    assert weights["hop_trevenant"]["dataset_url"] == "https://example.test/dataset"
    assert weights["archaludon"]["raw_weight"] == pytest.approx(8.696428571428571)


def test_gate_rows_mark_missing_live_meta_gate_as_unavailable(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """[
          {
            "ref": "current_meta/lucario",
            "archetype": "lucario",
            "ok": true,
            "main_path": "gates/lucario/main.py",
            "deck_path": "gates/lucario/deck.csv",
            "raw_weight": 22.6
          }
        ]""",
        encoding="utf-8",
    )

    rows = build_gate_rows(
        [manifest],
        meta_snapshot={
            "date": "2026-06-26",
            "source": {"datasetUrl": "https://example.test/dataset"},
            "archetypes": [
                {"name": "Mega Lucario ex / Riolu", "metaShare": 0.210625},
                {"name": "Archaludon ex / Duraludon", "metaShare": 0.08696428571428572},
            ],
        },
    )

    lucario = next(row for row in rows if row["archetype"] == "lucario")
    archaludon = next(row for row in rows if row["archetype"] == "archaludon")
    assert lucario["available"] is True
    assert lucario["gate_weight"] == 21.0625
    assert archaludon["available"] is False
    assert archaludon["ok"] is False
    assert archaludon["errors"] == ["no available local gate for live meta archetype"]


def test_rank_candidates_penalizes_hard_gate_collapse_over_raw_aggregate():
    candidates = [
        {"name": "fragile_high_aggregate", "eligible_for_benchmark": True},
        {"name": "broad_lower_aggregate", "eligible_for_benchmark": True},
    ]
    matchup_rows = [
        {
            "candidate": "fragile_high_aggregate",
            "gate_ref": "current_meta/lucario",
            "archetype": "lucario",
            "wins": 1,
            "finished": 10,
            "losses": 9,
            "draws": 0,
            "errors": [],
            "gate_weight": 0.45,
            "hard_gate": True,
        },
        {
            "candidate": "fragile_high_aggregate",
            "gate_ref": "current_meta/starmie",
            "archetype": "mega_starmie",
            "wins": 10,
            "finished": 10,
            "losses": 0,
            "draws": 0,
            "errors": [],
            "gate_weight": 0.55,
            "hard_gate": True,
        },
        {
            "candidate": "broad_lower_aggregate",
            "gate_ref": "current_meta/lucario",
            "archetype": "lucario",
            "wins": 5,
            "finished": 10,
            "losses": 5,
            "draws": 0,
            "errors": [],
            "gate_weight": 0.45,
            "hard_gate": True,
        },
        {
            "candidate": "broad_lower_aggregate",
            "gate_ref": "current_meta/starmie",
            "archetype": "mega_starmie",
            "wins": 5,
            "finished": 10,
            "losses": 5,
            "draws": 0,
            "errors": [],
            "gate_weight": 0.55,
            "hard_gate": True,
        },
    ]

    ranked = rank_candidates(candidates, matchup_rows, hard_gate_floor=0.35)

    assert ranked[0]["candidate"] == "broad_lower_aggregate"
    assert ranked[0]["promotable"] is True
    fragile = next(row for row in ranked if row["candidate"] == "fragile_high_aggregate")
    assert fragile["raw_win_rate"] > ranked[0]["raw_win_rate"]
    assert fragile["hard_gate_collapses"][0]["archetype"] == "lucario"
    assert fragile["promotable"] is False


def test_submit_offer_never_marks_kaggle_submission_made():
    offer = build_submit_offer(
        [
            {
                "candidate": "broad_lower_aggregate",
                "promotable": True,
                "errors": 0,
                "hard_gate_collapses": [],
            }
        ],
        champion_ref="54079056",
    )

    assert offer["kaggle_submission_made"] is False
    assert offer["requires_user_approval"] is True
    assert offer["recommend_submit"] is True
    assert offer["champion_floor_ref"] == "54079056"
