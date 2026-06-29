from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "artifacts" / "submission_3_cg_fix"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "starmie_start_guard_v1"
DEFAULT_ARCHIVE = ROOT / "artifacts" / "submission_starmie_start_guard_v1.tar.gz"

STARYU = 1030
CINDERACE = 666
WATER_ENERGY = 3


def _require_source() -> None:
    missing = [path for path in (SOURCE_DIR / "main.py", SOURCE_DIR / "deck.csv", SOURCE_DIR / "cg") if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing source package pieces: {missing}")


def _read_source_deck() -> list[int]:
    return [int(line) for line in (SOURCE_DIR / "deck.csv").read_text(encoding="utf-8").splitlines() if line]


def _validate_deck(deck: list[int]) -> None:
    counts = Counter(deck)
    if len(deck) != 60:
        raise ValueError(f"deck must contain 60 cards, got {len(deck)}")
    illegal = {card_id: count for card_id, count in counts.items() if card_id != WATER_ENERGY and count > 4}
    if illegal:
        raise ValueError(f"illegal non-basic counts: {illegal}")


def _start_guard_deck() -> list[int]:
    deck = _read_source_deck()
    deck[deck.index(CINDERACE)] = STARYU
    _validate_deck(deck)
    return deck


def _write_deck(path: Path, deck: list[int]) -> None:
    path.write_text("\n".join(str(card_id) for card_id in deck) + "\n", encoding="utf-8")


def _make_archive(candidate_dir: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tf:
        for name in ("main.py", "deck.csv", "cg"):
            tf.add(candidate_dir / name, arcname=name)


def build_starmie_start_guard_candidate(
    output_root: Path = DEFAULT_OUTPUT_DIR,
    *,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    _require_source()
    output_root = Path(output_root)
    archive_path = Path(archive_path) if archive_path is not None else output_root.with_suffix(".tar.gz")
    output_root.mkdir(parents=True, exist_ok=True)

    deck = _start_guard_deck()
    shutil.copy2(SOURCE_DIR / "main.py", output_root / "main.py")
    shutil.rmtree(output_root / "cg", ignore_errors=True)
    shutil.copytree(SOURCE_DIR / "cg", output_root / "cg", ignore=shutil.ignore_patterns("__pycache__"))
    _write_deck(output_root / "deck.csv", deck)
    _make_archive(output_root, archive_path)

    report = {
        "candidate": "starmie_start_guard_v1",
        "source_dir": str(SOURCE_DIR),
        "output_dir": str(output_root),
        "archive_path": str(archive_path),
        "deck_counts": dict(Counter(deck)),
        "strategy": (
            "Mega Starmie ex parent policy with one-card deck delta: +1 Staryu, -1 Cinderace "
            "to reduce lone-Cinderace starts into Lucario while preserving Wally, Harlequin, Ultra Ball, and Boss counts."
        ),
        "kaggle_submission_made": False,
    }
    report_path = output_root / "build_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "candidate": report["candidate"],
        "main_path": output_root / "main.py",
        "deck_path": output_root / "deck.csv",
        "archive_path": archive_path,
        "report_path": report_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build heuristic-only Starmie start-guard candidate.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    result = build_starmie_start_guard_candidate(args.output_dir, archive_path=args.archive)
    print(json.dumps({key: str(value) for key, value in result.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
