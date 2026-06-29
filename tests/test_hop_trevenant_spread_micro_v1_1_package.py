from __future__ import annotations

from collections import Counter
import importlib.util
import sys
import tarfile
from pathlib import Path

from ptcg.kaggle_archive_validator import validate_archive_startup


CANDIDATE_DIR = Path("artifacts/hop_trevenant_spread_micro_v1_1")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_hop_trevenant_spread_micro_v1_1.tar.gz")
PUBLIC_BEST_DIR = Path("artifacts/ptcg_research/current/lb_best_vs_latest_2026_06_28/extracted/v1_best")
_CANDIDATE_MODULE = None


def _pop_candidate_runtime_modules() -> dict[str, object]:
    popped = {}
    for name in list(sys.modules):
        if name == "cg" or name.startswith("cg."):
            popped[name] = sys.modules.pop(name)
    return popped


def _restore_modules(modules: dict[str, object]) -> None:
    for name, module in modules.items():
        sys.modules[name] = module


def _load_candidate_module():
    global _CANDIDATE_MODULE
    if _CANDIDATE_MODULE is not None:
        return _CANDIDATE_MODULE
    assert CANDIDATE_MAIN.exists(), f"missing candidate main: {CANDIDATE_MAIN}"
    previous = _pop_candidate_runtime_modules()
    package_dir = str(CANDIDATE_DIR.resolve())
    sys.path.insert(0, package_dir)
    try:
        spec = importlib.util.spec_from_file_location("hop_trevenant_spread_micro_v1_1_under_test", CANDIDATE_MAIN)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CANDIDATE_MODULE = module
        return module
    finally:
        while package_dir in sys.path:
            sys.path.remove(package_dir)
        _pop_candidate_runtime_modules()
        _restore_modules(previous)


def test_deck_remains_public_best_v1_deck() -> None:
    module = _load_candidate_module()
    candidate_deck = [int(line) for line in (CANDIDATE_DIR / "deck.csv").read_text().splitlines() if line.strip()]
    public_best_deck = [int(line) for line in (PUBLIC_BEST_DIR / "deck.csv").read_text().splitlines() if line.strip()]

    assert len(candidate_deck) == 60
    assert Counter(candidate_deck) == Counter(public_best_deck)
    assert module.agent({}, None) == candidate_deck


def test_candidate_has_kaggle_bundle_shape_and_validates_raw_exec_startup() -> None:
    assert CANDIDATE_MAIN.exists()
    assert (CANDIDATE_DIR / "deck.csv").exists()
    assert (CANDIDATE_DIR / "cg" / "api.py").exists()
    assert CANDIDATE_ARCHIVE.exists()

    with tarfile.open(CANDIDATE_ARCHIVE, "r:gz") as tf:
        members = {member.name.replace("\\", "/").lstrip("./") for member in tf.getmembers()}

    assert {"main.py", "deck.csv", "cg/api.py"}.issubset(members)
    result = validate_archive_startup(CANDIDATE_ARCHIVE)
    assert result["deck_len"] == 60
    assert result["strict_raw_exec_without_file_or_syspath"] is True


def test_spread_restraint_uses_micro_constants_not_v2_extremes() -> None:
    main_text = CANDIDATE_MAIN.read_text(encoding="utf-8")

    assert "score += 100" in main_text
    assert "score -= 575" in main_text
    assert "score -= 75" in main_text
    assert "len(self.me.bench) >= 3:\n                return -200.0" in main_text
    assert "threshold = 600 if self._spread_pressure() else 650" in main_text

    assert "if board_index > 0:\n                score += 520" not in main_text
    assert "score -= 1150" not in main_text
    assert "score -= 420" not in main_text
    assert "len(self.me.bench) >= 2:\n                return -350.0" not in main_text
    assert "threshold = 420 if self._spread_pressure() else 650" not in main_text
