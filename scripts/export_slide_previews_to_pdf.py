from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def export_pdf(preview_dir: Path, output_pdf: Path) -> None:
    slide_paths = sorted(preview_dir.glob("slide-*.png"))
    if not slide_paths:
        raise SystemExit(f"No slide PNGs found in {preview_dir}")

    first = Image.open(slide_paths[0])
    width, height = first.size
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_pdf), pagesize=(width, height))
    for slide_path in slide_paths:
        image = Image.open(slide_path).convert("RGB")
        pdf.drawImage(ImageReader(image), 0, 0, width=width, height=height)
        pdf.showPage()
    pdf.save()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--output-pdf", required=True, type=Path)
    args = parser.parse_args()
    export_pdf(args.preview_dir, args.output_pdf)
    print(f"Wrote PDF: {args.output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
