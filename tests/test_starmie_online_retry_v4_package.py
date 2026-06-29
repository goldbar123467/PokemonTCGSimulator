from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path


CANDIDATE_DIR = Path("artifacts/starmie_online_retry_v4")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_starmie_online_retry_v4.tar.gz")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("starmie_online_retry_v4_main_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_online_retry_v4_deck_is_legal_role_corrected_online_shell():
    module = _load_main_module()
    counts = Counter(module.agent({}, None))

    assert sum(counts.values()) == 60
    assert counts[module.C.CINDERACE] == 4
    assert counts[module.C.STARYU] == 4
    assert counts[module.C.STARMIE] == 4
    assert counts[module.C.WATER] == 8
    assert counts[module.C.IGNITION] == 4
    assert counts[module.C.BOSS] == 2
    assert counts[module.C.WALLY] == 3
    assert counts[module.C.POKE_PAD] == 2
    assert counts[module.C.ENERGY_SEARCH] == 1
    assert all(count <= 4 for card_id, count in counts.items() if card_id != module.C.WATER)


def test_online_retry_v4_prefers_cinderace_active_and_staryu_bench():
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


def test_online_retry_v4_attaches_to_backup_when_active_can_attack():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.STARMIE, "hp": 330, "maxHp": 330, "energies": [module.C.WATER]}],
                    "bench": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []}],
                    "hand": [{"id": module.C.WATER}],
                    "handCount": 1,
                    "deckCount": 34,
                },
                {
                    "active": [{"id": module.C.LUCARIO, "hp": 270, "maxHp": 270, "energies": [module.C.FIGHTING]}],
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


def test_online_retry_v4_preserves_wally_until_damaged_starmie_exists():
    module = _load_main_module()

    base_current = {
        "players": [
            {
                "active": [{"id": module.C.STARMIE, "hp": 330, "maxHp": 330, "energies": [module.C.WATER]}],
                "bench": [{"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []}],
                "hand": [{"id": module.C.WALLY}, {"id": module.C.HILDA}],
                "handCount": 2,
                "deckCount": 31,
            },
            {
                "active": [{"id": module.C.DRAGAPULT, "hp": 320, "maxHp": 320, "energies": [module.C.FIRE]}],
                "bench": [{"id": module.C.DREEPY, "hp": 70, "maxHp": 70, "energies": []}],
                "handCount": 5,
                "deckCount": 34,
            },
        ],
        "yourIndex": 0,
        "supporterPlayed": False,
    }
    obs = {
        "current": base_current,
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_PLAY, "index": 0},
                {"type": module.OPT_PLAY, "index": 1},
            ],
        },
    }

    assert module.agent(obs, None) == [1]

    damaged = dict(base_current)
    damaged["players"] = [dict(base_current["players"][0]), base_current["players"][1]]
    damaged["players"][0]["active"] = [{"id": module.C.STARMIE, "hp": 190, "maxHp": 330, "energies": [module.C.WATER]}]
    damaged_obs = dict(obs)
    damaged_obs["current"] = damaged

    assert module.agent(damaged_obs, None) == [0]


def test_online_retry_v4_archive_validates_startup_shape():
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
