from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path


CANDIDATE_DIR = Path("artifacts/starmie_online_simple_v3")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_starmie_online_simple_v3.tar.gz")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("starmie_online_simple_v3_main_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_online_simple_v3_matches_rounded_online_aggregate_deck():
    module = _load_main_module()
    counts = Counter(module.agent({}, None))

    assert sum(counts.values()) == 60
    assert counts[666] == 4
    assert counts[1030] == 3
    assert counts[1031] == 3
    assert counts[1189] == 4
    assert counts[1229] == 4
    assert counts[1227] == 4
    assert counts[1086] == 4
    assert counts[1122] == 4
    assert counts[1145] == 4
    assert counts[17] == 4
    assert counts[3] == 9
    assert counts[1120] == 4
    assert counts[1182] == 1
    assert counts[1152] == 0
    assert all(count <= 4 for card_id, count in counts.items() if card_id != 3)


def test_online_simple_v3_prefers_cinderace_active_and_staryu_bench():
    module = _load_main_module()

    active_obs = {
        "current": {"players": [{}, {}], "yourIndex": 0},
        "select": {
            "context": module.CTX_SETUP_ACTIVE,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_CARD, "cardId": module.C.STARYU},
                {"type": module.OPT_CARD, "cardId": module.C.CINDERACE},
            ],
        },
    }
    bench_obs = {
        "current": {"players": [{"active": [{"id": module.C.CINDERACE}], "bench": []}, {}], "yourIndex": 0},
        "select": {
            "context": module.CTX_SETUP_BENCH,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_CARD, "cardId": module.C.CINDERACE},
                {"type": module.OPT_CARD, "cardId": module.C.STARYU},
            ],
        },
    }

    assert module.agent(active_obs, None) == [1]
    assert module.agent(bench_obs, None) == [1]


def test_online_simple_v3_attaches_to_backup_when_active_is_ready():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.STARMIE, "hp": 330, "maxHp": 330, "energies": [3]}],
                    "bench": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []}],
                    "hand": [{"id": module.C.WATER}],
                    "handCount": 1,
                    "deckCount": 34,
                },
                {
                    "active": [{"id": module.C.LUCARIO, "hp": 270, "maxHp": 270, "energies": [6]}],
                    "bench": [],
                    "handCount": 5,
                    "deckCount": 34,
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


def test_online_simple_v3_archive_validates_startup_shape():
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
