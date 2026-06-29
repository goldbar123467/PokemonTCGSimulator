from pathlib import Path

from ptcg.public_kaggle_research import PublicKernelRef, write_source_ledger


def test_write_source_ledger_records_usage_boundary(tmp_path):
    output = tmp_path / "public-source-ledger.md"
    refs = [
        PublicKernelRef(
            ref="skarin/phantom-dive-or-go-home-a-dragapult-ex-deck",
            title="Phantom Dive or Go Home: A Dragapult ex Deck",
            author="SK Arin",
            votes=25,
            pulled_path=Path("artifacts/public_meta/skarin_dragapult"),
            usage="opponent_gate_strategy",
        )
    ]

    write_source_ledger(output, refs)

    text = output.read_text(encoding="utf-8")
    assert "skarin/phantom-dive-or-go-home-a-dragapult-ex-deck" in text
    assert "opponent_gate_strategy" in text
    assert "not copied as final submission" in text
