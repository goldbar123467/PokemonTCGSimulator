from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

import scripts.extract_official_card_assets as extract_official_card_assets
from ptcg.official_cards import (
    build_card_asset_manifest,
    extract_first_pdf_image,
    load_official_card_index,
    official_pdf_page_index,
)


def test_load_official_card_index_normalizes_kaggle_csv_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "EN_Card_Data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Card ID,Card Name,Expansion,Collection No.,Stage (Pokémon)/Type (Energy and Trainer),Rule,Category,Previous stage,HP,Type,Weakness,Resistance (Type),Retreat,Move Name,Cost,Damage,Effect Explanation",
                "678,Mega Lucario ex,MEG,77,Stage 1 Pokémon,Mega Pokémon ex,n/a,Riolu,340,{F},{P},n/a,2,Aura Jab,{F},130,Attach up to 3 Basic {F} Energy cards from your discard pile.",
            ]
        ),
        encoding="utf-8",
    )

    cards = load_official_card_index(csv_path)

    assert cards[678].name == "Mega Lucario ex"
    assert cards[678].expansion == "MEG"
    assert cards[678].collection_no == "77"
    assert cards[678].stage_or_type == "Stage 1 Pokémon"
    assert cards[678].rule == "Mega Pokémon ex"
    assert cards[678].hp == 340
    assert cards[678].move_name == "Aura Jab"
    assert [move["name"] for move in cards[678].moves] == ["Aura Jab"]


def test_load_official_card_index_preserves_multiple_card_moves(tmp_path: Path) -> None:
    csv_path = tmp_path / "EN_Card_Data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Card ID,Card Name,Expansion,Collection No.,Stage (Pokémon)/Type (Energy and Trainer),Rule,Category,Previous stage,HP,Type,Weakness,Resistance (Type),Retreat,Move Name,Cost,Damage,Effect Explanation",
                "675,Lunatone,MEG,74,Basic Pokémon,n/a,n/a,n/a,110,{F},{G},n/a,1,[Ability] Lunar Cycle,n/a,n/a,Draw 3 cards.",
                "675,Lunatone,MEG,74,Basic Pokémon,n/a,n/a,n/a,110,{F},{G},n/a,1,Power Gem,{F}{F},50,n/a",
            ]
        ),
        encoding="utf-8",
    )

    cards = load_official_card_index(csv_path)

    assert cards[675].move_name == "[Ability] Lunar Cycle"
    assert cards[675].moves == (
        {"name": "[Ability] Lunar Cycle", "cost": None, "damage": None, "effect": "Draw 3 cards."},
        {"name": "Power Gem", "cost": "{F}{F}", "damage": "50", "effect": None},
    )


def test_build_card_asset_manifest_uses_local_card_image_urls(tmp_path: Path) -> None:
    csv_path = tmp_path / "EN_Card_Data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Card ID,Card Name,Expansion,Collection No.,Stage (Pokémon)/Type (Energy and Trainer),Rule,Category,Previous stage,HP,Type,Weakness,Resistance (Type),Retreat,Move Name,Cost,Damage,Effect Explanation",
                "675,Lunatone,MEG,74,Basic Pokémon,n/a,n/a,n/a,110,{F},{G},n/a,1,[Ability] Lunar Cycle,n/a,n/a,Draw 3 cards.",
                "678,Mega Lucario ex,MEG,77,Stage 1 Pokémon,Mega Pokémon ex,n/a,Riolu,340,{F},{P},n/a,2,Aura Jab,{F},130,Attach Energy.",
            ]
        ),
        encoding="utf-8",
    )
    image_dir = tmp_path / "cards"
    image_dir.mkdir()
    (image_dir / "678.jpg").write_bytes(b"fake image")

    manifest = build_card_asset_manifest(
        [678, 675, 678],
        csv_path=csv_path,
        image_dir=image_dir,
        public_image_prefix="/assets/cards",
    )

    assert [card["id"] for card in manifest["cards"]] == [675, 678]
    assert manifest["cardsById"]["678"]["name"] == "Mega Lucario ex"
    assert manifest["cardsById"]["678"]["moves"] == [
        {"name": "Aura Jab", "cost": "{F}", "damage": "130", "effect": "Attach Energy."},
    ]
    assert manifest["cardsById"]["678"]["imageUrl"] == "/assets/cards/678.jpg"
    assert manifest["cardsById"]["675"]["imageUrl"] is None
    assert manifest["kaggle_submission_made"] is False


def test_official_pdf_page_index_matches_kaggle_card_id_pdf_layout() -> None:
    assert official_pdf_page_index(1) == 39
    assert official_pdf_page_index(678) == 716


def test_extract_first_pdf_image_writes_embedded_card_jpeg(tmp_path: Path) -> None:
    import fitz

    source_image = tmp_path / "source.jpg"
    Image.new("RGB", (24, 32), color=(240, 32, 48)).save(source_image, "JPEG")
    pdf_path = tmp_path / "one-card.pdf"
    doc = fitz.open()
    page = doc.new_page(width=120, height=160)
    page.insert_image(fitz.Rect(10, 10, 70, 90), filename=str(source_image))
    doc.save(pdf_path)
    doc.close()
    output_image = tmp_path / "card.jpg"

    written = extract_first_pdf_image(pdf_path, page_index=0, output_path=output_image)

    assert written == output_image
    assert output_image.exists()
    with Image.open(output_image) as image:
        assert image.size == (24, 32)


def test_extract_official_card_assets_writes_machine_readable_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text("678\n678\n", encoding="utf-8")
    csv_path = tmp_path / "EN_Card_Data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Card ID,Card Name,Expansion,Collection No.,Stage (Pokémon)/Type (Energy and Trainer),Rule,Category,Previous stage,HP,Type,Weakness,Resistance (Type),Retreat,Move Name,Cost,Damage,Effect Explanation",
                "678,Mega Lucario ex,MEG,77,Stage 1 Pokémon,Mega Pokémon ex,n/a,Riolu,340,{F},{P},n/a,2,Aura Jab,{F},130,Attach Energy.",
            ]
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "cards.pdf"
    pdf_path.write_bytes(b"%PDF fake")
    output_dir = tmp_path / "images"
    manifest_path = tmp_path / "manifest.json"
    summary_path = tmp_path / "summary.json"

    def fake_extract(card_ids, *, pdf_path, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "678.jpg"
        image_path.write_bytes(b"fake")
        return {678: image_path}

    monkeypatch.setattr(extract_official_card_assets, "extract_card_images_from_pdf", fake_extract)

    result = extract_official_card_assets.main(
        [
            "--deck",
            str(deck_path),
            "--csv",
            str(csv_path),
            "--pdf",
            str(pdf_path),
            "--output-dir",
            str(output_dir),
            "--manifest",
            str(manifest_path),
            "--summary",
            str(summary_path),
        ]
    )

    printed = capsys.readouterr().out
    summary = __import__("json").loads(summary_path.read_text(encoding="utf-8"))
    assert result == 0
    assert summary["deck"] == str(deck_path)
    assert summary["unique_card_count"] == 1
    assert summary["image_count"] == 1
    assert summary["kaggle_submission_made"] is False
    assert '"kaggle_submission_made": false' in printed
