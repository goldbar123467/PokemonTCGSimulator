from __future__ import annotations

import importlib.util
from pathlib import Path

from scripts.build_adaptive_shell666_candidate import build
from scripts.generate_heuristic_candidates import _write_candidate


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("adaptive_candidate_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_source(tmp_path: Path, name: str, key_weight: float) -> dict:
    return _write_candidate(
        tmp_path,
        name,
        [666] * 60,
        {
            "strategy": name,
            "key_cards": [666],
            "setup_cards": [666],
            "attackers": [666],
            "evolvers": [],
            "disruption": [1122],
            "energy_ids": [3],
            "gate_targets": [678],
            "rng_noise": 0.0,
            "weights": {"key_card": key_weight},
        },
    )


def test_adaptive_builder_accepts_profile_sources_and_selects_lucario_profile(tmp_path):
    default_source = _write_source(tmp_path, "default_source", 101.0)
    lucario_source = _write_source(tmp_path, "lucario_source", 202.0)
    output_dir = tmp_path / "adaptive"

    build(
        output_dir,
        profile_sources={
            "default": Path(default_source["main_path"]),
            "lucario": Path(lucario_source["main_path"]),
        },
        base_main=Path(default_source["main_path"]),
        base_deck=Path(default_source["deck_path"]),
    )

    module = _load_module(output_dir / "main.py")

    assert module.WEIGHT_PROFILES["default"]["key_card"] == 101.0
    assert module.WEIGHT_PROFILES["lucario"]["key_card"] == 202.0
    assert module._choose_profile(
        {
            "current": {
                "yourIndex": 0,
                "players": [
                    {"active": [], "bench": [], "discard": []},
                    {"active": [{"id": 678}], "bench": [], "discard": []},
                ],
            }
        }
    ) == module.WEIGHT_PROFILES["lucario"]
