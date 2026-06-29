from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Any


CARD_IMAGE_PAGE_OFFSET = 38


@dataclass(frozen=True)
class OfficialCard:
    card_id: int
    name: str
    expansion: str
    collection_no: str
    stage_or_type: str
    rule: str
    category: str
    previous_stage: str | None
    hp: int | None
    type_text: str | None
    weakness: str | None
    resistance: str | None
    retreat: int | None
    move_name: str | None
    cost: str | None
    damage: str | None
    effect: str | None
    moves: tuple[dict[str, str | None], ...]

    def to_asset_dict(self, *, image_url: str | None = None) -> dict[str, Any]:
        return {
            "id": self.card_id,
            "name": self.name,
            "expansion": self.expansion,
            "collectionNo": self.collection_no,
            "stageOrType": self.stage_or_type,
            "rule": none_if_na(self.rule),
            "category": none_if_na(self.category),
            "previousStage": self.previous_stage,
            "hp": self.hp,
            "type": self.type_text,
            "weakness": self.weakness,
            "resistance": self.resistance,
            "retreat": self.retreat,
            "moveName": self.move_name,
            "cost": self.cost,
            "damage": self.damage,
            "effect": self.effect,
            "moves": list(self.moves),
            "imageUrl": image_url,
        }


def load_official_card_index(csv_path: Path) -> dict[int, OfficialCard]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        grouped: dict[int, list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault(int(row["Card ID"]), []).append(row)
        return {card_id: card_from_rows(card_id, card_rows) for card_id, card_rows in grouped.items()}


def card_from_rows(card_id: int, rows: list[dict[str, str]]) -> OfficialCard:
    first = rows[0]
    moves = tuple(move for row in rows if (move := move_from_row(row)) is not None)
    first_move = moves[0] if moves else None
    return OfficialCard(
        card_id=card_id,
        name=first["Card Name"],
        expansion=first["Expansion"],
        collection_no=first["Collection No."],
        stage_or_type=first["Stage (Pokémon)/Type (Energy and Trainer)"],
        rule=first["Rule"],
        category=first["Category"],
        previous_stage=none_if_na(first["Previous stage"]),
        hp=int_or_none(first["HP"]),
        type_text=none_if_na(first["Type"]),
        weakness=none_if_na(first["Weakness"]),
        resistance=none_if_na(first["Resistance (Type)"]),
        retreat=int_or_none(first["Retreat"]),
        move_name=first_move["name"] if first_move else none_if_na(first["Move Name"]),
        cost=first_move["cost"] if first_move else none_if_na(first["Cost"]),
        damage=first_move["damage"] if first_move else none_if_na(first["Damage"]),
        effect=first_move["effect"] if first_move else none_if_na(first["Effect Explanation"]),
        moves=moves,
    )


def move_from_row(row: dict[str, str]) -> dict[str, str | None] | None:
    name = none_if_na(row["Move Name"])
    if name is None:
        return None
    return {
        "name": name,
        "cost": none_if_na(row["Cost"]),
        "damage": none_if_na(row["Damage"]),
        "effect": none_if_na(row["Effect Explanation"]),
    }


def load_deck_card_ids(deck_path: Path) -> list[int]:
    return [int(line.strip()) for line in deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_card_asset_manifest(
    card_ids: Iterable[int],
    *,
    csv_path: Path,
    image_dir: Path,
    public_image_prefix: str = "/assets/cards",
) -> dict[str, Any]:
    cards = load_official_card_index(csv_path)
    unique_ids = sorted(set(int(card_id) for card_id in card_ids))
    asset_cards = []
    for card_id in unique_ids:
        card = cards.get(card_id)
        if card is None:
            continue
        image_url = None
        if (image_dir / f"{card_id}.jpg").exists():
            image_url = f"{public_image_prefix.rstrip('/')}/{card_id}.jpg"
        asset_cards.append(card.to_asset_dict(image_url=image_url))
    return {
        "source": {
            "csv": str(csv_path),
            "imageDir": str(image_dir),
            "publicImagePrefix": public_image_prefix.rstrip("/"),
        },
        "cards": asset_cards,
        "cardsById": {str(card["id"]): card for card in asset_cards},
        "kaggle_submission_made": False,
    }


def official_pdf_page_index(card_id: int) -> int:
    if card_id < 1:
        raise ValueError("card_id must be positive")
    return card_id + CARD_IMAGE_PAGE_OFFSET


def extract_card_images_from_pdf(
    card_ids: Iterable[int],
    *,
    pdf_path: Path,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths = []
    for card_id in sorted(set(int(card_id) for card_id in card_ids)):
        written_paths.append(
            extract_first_pdf_image(
                pdf_path,
                page_index=official_pdf_page_index(card_id),
                output_path=output_dir / f"{card_id}.jpg",
            )
        )
    return written_paths


def extract_first_pdf_image(pdf_path: Path, *, page_index: int, output_path: Path) -> Path:
    import fitz

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf_path)
    try:
        page = document[page_index]
        images = page.get_images(full=True)
        if not images:
            raise ValueError(f"PDF page {page_index + 1} has no embedded images")
        xref = images[0][0]
        image = document.extract_image(xref)
        output_path.write_bytes(image["image"])
    finally:
        document.close()
    return output_path


def none_if_na(value: str) -> str | None:
    cleaned = value.strip()
    if cleaned == "" or cleaned.lower() == "n/a":
        return None
    return cleaned


def int_or_none(value: str) -> int | None:
    cleaned = none_if_na(value)
    if cleaned is None:
        return None
    return int(cleaned)
