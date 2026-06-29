from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path


CANDIDATE_DIR = Path("artifacts/starmie_lucario_farm_v2")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_starmie_lucario_farm_v2.tar.gz")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("starmie_lucario_farm_v2_main_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lucario_farm_v2_deck_is_legal_lucario_focused_online_shell():
    module = _load_main_module()
    counts = Counter(module.agent({}, None))

    assert sum(counts.values()) == 60
    assert counts[module.C.CINDERACE] == 4
    assert counts[module.C.STARYU] == 4
    assert counts[module.C.STARMIE] == 4
    assert counts[module.C.BOSS] == 3
    assert counts[module.C.HAMMER] == 4
    assert counts[module.C.WALLY] == 2
    assert counts[module.C.ULTRA_BALL] == 2
    assert counts[module.C.POKE_PAD] == 0
    assert counts[module.C.WATER] == 8
    assert all(count <= 4 for card_id, count in counts.items() if card_id != module.C.WATER)


def test_lucario_farm_v2_boss_targets_riolu_before_active_lucario():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.STARMIE, "hp": 330, "maxHp": 330, "energies": [module.C.WATER]}],
                    "bench": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []}],
                    "deckCount": 31,
                },
                {
                    "active": [{"id": module.C.LUCARIO, "hp": 270, "maxHp": 270, "energies": [module.C.FIGHTING]}],
                    "bench": [{"id": module.C.RIOLU, "hp": 70, "maxHp": 70, "energies": []}],
                    "deckCount": 34,
                },
            ],
            "yourIndex": 0,
        },
        "select": {
            "context": module.CTX_TO_ACTIVE,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_CARD, "area": module.AREA_ACTIVE, "index": 0, "playerIndex": 1},
                {"type": module.OPT_CARD, "area": module.AREA_BENCH, "index": 0, "playerIndex": 1},
            ],
        },
    }

    assert module.agent(obs, None) == [1]


def test_lucario_farm_v2_plays_boss_when_ready_starmie_can_punish_setup_piece():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.STARMIE, "hp": 330, "maxHp": 330, "energies": [module.C.WATER]}],
                    "bench": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []}],
                    "hand": [{"id": module.C.BOSS}, {"id": module.C.HILDA}],
                    "deckCount": 31,
                },
                {
                    "active": [{"id": module.C.LUCARIO, "hp": 270, "maxHp": 270, "energies": [module.C.FIGHTING]}],
                    "bench": [{"id": module.C.RIOLU, "hp": 70, "maxHp": 70, "energies": []}],
                    "deckCount": 34,
                },
            ],
            "yourIndex": 0,
            "supporterPlayed": False,
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_PLAY, "index": 0},
                {"type": module.OPT_PLAY, "index": 1},
            ],
        },
    }

    assert module.agent(obs, None) == [0]


def test_lucario_farm_v2_evolves_staryu_before_playing_boss():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": [module.C.WATER]}],
                    "bench": [{"id": module.C.CINDERACE, "hp": 160, "maxHp": 160, "energies": []}],
                    "hand": [{"id": module.C.BOSS}, {"id": module.C.STARMIE}],
                    "deckCount": 31,
                },
                {
                    "active": [{"id": module.C.LUCARIO, "hp": 270, "maxHp": 270, "energies": [module.C.FIGHTING]}],
                    "bench": [{"id": module.C.RIOLU, "hp": 70, "maxHp": 70, "energies": []}],
                    "deckCount": 34,
                },
            ],
            "yourIndex": 0,
            "supporterPlayed": False,
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_PLAY, "index": 0},
                {
                    "type": module.OPT_EVOLVE,
                    "area": module.AREA_HAND,
                    "index": 1,
                    "inPlayArea": module.AREA_ACTIVE,
                    "inPlayIndex": 0,
                },
            ],
        },
    }

    assert module.agent(obs, None) == [1]


def test_lucario_farm_v2_hammers_single_powered_lucario():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.STARMIE, "hp": 330, "maxHp": 330, "energies": [module.C.WATER]}],
                    "bench": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []}],
                    "hand": [{"id": module.C.HAMMER}, {"id": module.C.POKEGEAR}],
                    "deckCount": 31,
                },
                {
                    "active": [{"id": module.C.LUCARIO, "hp": 270, "maxHp": 270, "energies": [module.C.FIGHTING]}],
                    "bench": [],
                    "deckCount": 34,
                },
            ],
            "yourIndex": 0,
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_PLAY, "index": 0},
                {"type": module.OPT_PLAY, "index": 1},
            ],
        },
    }

    assert module.agent(obs, None) == [0]


def test_lucario_farm_v2_archive_validates_startup_shape():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ptcg.kaggle_archive_validator",
            "--archive",
            str(CANDIDATE_ARCHIVE),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
