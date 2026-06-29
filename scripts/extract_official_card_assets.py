from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.official_cards import build_card_asset_manifest
from ptcg.official_cards import extract_card_images_from_pdf
from ptcg.official_cards import load_deck_card_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract official competition card images for a deck.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--csv", type=Path, default=Path("data/official_kaggle/EN_Card_Data.csv"))
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("artifacts/official_card_assets/raw/Card_ID%20List_EN.pdf"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/official_card_assets/images"))
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/official_card_assets/manifest.json"))
    parser.add_argument("--summary", type=Path, default=Path("artifacts/official_card_assets/extract_summary.json"))
    parser.add_argument("--public-image-prefix", default="/assets/cards")
    args = parser.parse_args(argv)

    deck_ids = load_deck_card_ids(args.deck)
    image_paths = extract_card_images_from_pdf(deck_ids, pdf_path=args.pdf, output_dir=args.output_dir)
    manifest = build_card_asset_manifest(
        deck_ids,
        csv_path=args.csv,
        image_dir=args.output_dir,
        public_image_prefix=args.public_image_prefix,
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "deck": str(args.deck),
        "csv": str(args.csv),
        "pdf": str(args.pdf),
        "output_dir": str(args.output_dir),
        "manifest": str(args.manifest),
        "summary": str(args.summary),
        "unique_card_count": len(set(deck_ids)),
        "image_count": len(image_paths),
        "kaggle_submission_made": False,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
