from __future__ import annotations

from collections import Counter

from scripts.build_archaludon_broad_candidates import (
    BASE_CONFIG,
    NO_RELIC_JUDGE_METAL_DECK_COUNTS,
    NO_RELIC_METAL_DECK_COUNTS,
    VARIANTS,
    _deck_from_counts,
    _meta_summary,
)


def _merged_config(name: str) -> dict:
    return {
        **BASE_CONFIG,
        **VARIANTS[name].get("config_overrides", {}),
    }


def test_no_relic_metal_deck_is_legal_and_removes_relicanth() -> None:
    deck = _deck_from_counts(NO_RELIC_METAL_DECK_COUNTS)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[57] == 0
    assert counts[8] == 12
    assert counts[1244] == 4
    assert counts[1213] == 0


def test_no_relic_judge_metal_deck_is_legal_and_uses_one_judge() -> None:
    deck = _deck_from_counts(NO_RELIC_JUDGE_METAL_DECK_COUNTS)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[57] == 0
    assert counts[8] == 12
    assert counts[1213] == 1
    assert counts[1244] == 3


def test_no_relic_broad_policy_removes_relicanth_from_card_roles() -> None:
    for name in (
        "archaludon_broad_no_relic_stabilizer_v1",
        "archaludon_broad_no_relic_judge_stabilizer_v1",
        "archaludon_broad_no_relic_judge_pressure_v1",
    ):
        config = _merged_config(name)

        assert 57 not in config["key_cards"]
        assert 57 not in config["attackers"]


def test_meta_summary_accepts_utf8_bom(tmp_path) -> None:
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        '{"date":"2026-06-27","latestDate":"2026-06-27","redirected":false,"totalDecks":11838,"source":{"datasetUrl":"https://example.test/meta"}}',
        encoding="utf-8-sig",
    )

    summary = _meta_summary(meta_path)

    assert summary["meta_date"] == "2026-06-27"
    assert summary["total_decks"] == 11838
    assert summary["dataset_url"] == "https://example.test/meta"
