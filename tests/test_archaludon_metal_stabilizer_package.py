from __future__ import annotations

from collections import Counter
import importlib.util
import tarfile
from pathlib import Path

from ptcg.kaggle_archive_validator import validate_archive_startup


CANDIDATE_DIR = Path("artifacts/archaludon_metal_stabilizer_v1")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_archaludon_metal_stabilizer_v1.tar.gz")

TARGET_COUNTS = Counter(
    {
        8: 11,  # Basic Metal Energy
        57: 1,  # Relicanth
        169: 4,  # Duraludon
        190: 4,  # Archaludon ex
        666: 4,  # Cinderace
        1097: 3,  # Night Stretcher
        1121: 4,  # Ultra Ball
        1122: 4,  # Pokegear 3.0
        1147: 4,  # Jumbo Ice Cream
        1152: 4,  # Poke Pad
        1159: 1,  # Hero's Cape
        1182: 4,  # Boss's Orders
        1185: 4,  # Explorer's Guidance
        1227: 4,  # Lillie's Determination
        1244: 4,  # Full Metal Lab
    }
)


def _load_candidate_module():
    assert CANDIDATE_MAIN.exists(), f"missing candidate main: {CANDIDATE_MAIN}"
    spec = importlib.util.spec_from_file_location("archaludon_metal_stabilizer_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deck_csv_and_step0_agent_return_archaludon_meta_shell() -> None:
    module = _load_candidate_module()

    deck_csv = [int(line) for line in (CANDIDATE_DIR / "deck.csv").read_text().splitlines() if line.strip()]

    assert len(deck_csv) == 60
    assert Counter(deck_csv) == TARGET_COUNTS
    assert module.agent({}, None) == deck_csv


def test_archaludon_archive_has_kaggle_bundle_shape_and_validates_startup() -> None:
    assert CANDIDATE_ARCHIVE.exists()

    with tarfile.open(CANDIDATE_ARCHIVE, "r:gz") as tf:
        members = {member.name.replace("\\", "/").lstrip("./") for member in tf.getmembers()}

    assert {"main.py", "deck.csv", "cg/api.py"}.issubset(members)
    result = validate_archive_startup(CANDIDATE_ARCHIVE)
    assert result["deck_len"] == 60
    assert result["strict_raw_exec_without_file_or_syspath"] is True
