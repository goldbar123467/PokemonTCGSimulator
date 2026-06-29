from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path


CANDIDATE_DIR = Path("artifacts/starmie_v2_1")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_starmie_v2_1.tar.gz")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("starmie_v2_1_main_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_starmie_v2_1_deck_is_legal_and_more_line_redundant():
    module = _load_main_module()

    deck = module.agent({}, None)
    counts = Counter(deck)

    assert len(deck) == 60
    assert counts[666] == 3
    assert counts[1030] == 4
    assert counts[1031] == 4
    assert counts[1229] == 3
    assert all(count <= 4 for card_id, count in counts.items() if card_id != 3)


def test_starmie_v2_1_prefers_going_first_for_setup_deck():
    module = _load_main_module()

    obs = {
        "current": {"players": [{}, {}], "yourIndex": 0},
        "select": {
            "context": module.CTX_IS_FIRST,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": module.OPT_YES}, {"type": module.OPT_NO}],
        },
    }

    assert module.agent(obs, None) == [0]


def test_starmie_v2_1_develops_before_attacking_without_backup():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [
                        {
                            "id": 1031,
                            "hp": 270,
                            "maxHp": 270,
                            "energies": [3],
                            "energyCards": [{"id": 3}],
                        }
                    ],
                    "bench": [],
                    "hand": [{"id": 1225}],
                    "handCount": 1,
                    "deckCount": 34,
                    "prize": [None] * 6,
                },
                {
                    "active": [
                        {
                            "id": 678,
                            "hp": 270,
                            "maxHp": 270,
                            "energies": [3],
                            "energyCards": [{"id": 3}],
                        }
                    ],
                    "bench": [],
                    "handCount": 7,
                    "deckCount": 35,
                    "prize": [None] * 6,
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
                {"type": module.OPT_ATTACK, "attackId": module.JETTING_BLOW},
                {"type": module.OPT_END},
            ],
        },
    }

    assert module.agent(obs, None) == [0]


def test_starmie_v2_1_builds_benched_next_attacker_before_overloading_active():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [
                        {
                            "id": 1031,
                            "hp": 270,
                            "maxHp": 270,
                            "energies": [3],
                            "energyCards": [{"id": 3}],
                        }
                    ],
                    "bench": [{"id": 1030, "hp": 70, "maxHp": 70, "energies": [], "energyCards": []}],
                    "hand": [{"id": 17}],
                    "handCount": 1,
                    "deckCount": 34,
                    "prize": [None] * 6,
                },
                {
                    "active": [
                        {
                            "id": 121,
                            "hp": 320,
                            "maxHp": 320,
                            "energies": [3],
                            "energyCards": [{"id": 3}],
                        }
                    ],
                    "bench": [{"id": 120, "hp": 90, "maxHp": 90, "energies": [], "energyCards": []}],
                    "handCount": 7,
                    "deckCount": 35,
                    "prize": [None] * 6,
                },
            ],
            "yourIndex": 0,
            "energyAttached": False,
        },
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {
                    "type": module.OPT_ATTACH,
                    "area": module.AREA_HAND,
                    "index": 0,
                    "inPlayArea": module.AREA_ACTIVE,
                    "inPlayIndex": 0,
                },
                {
                    "type": module.OPT_ATTACH,
                    "area": module.AREA_HAND,
                    "index": 0,
                    "inPlayArea": module.AREA_BENCH,
                    "inPlayIndex": 0,
                },
            ],
        },
    }

    assert module.agent(obs, None) == [1]


def test_starmie_v2_1_archive_validates_startup_shape():
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
