from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path


CANDIDATE_DIR = Path("artifacts/starmie_froslass_petrel_v3")
CANDIDATE_MAIN = CANDIDATE_DIR / "main.py"
CANDIDATE_ARCHIVE = Path("artifacts/submission_starmie_froslass_petrel_v3.tar.gz")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("starmie_froslass_petrel_v3_main_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_starmie_froslass_petrel_v3_uses_public_rewrite_shell():
    module = _load_main_module()

    counts = Counter(module.agent({}, None))

    assert sum(counts.values()) == 60
    assert counts[666] == 0
    assert counts[3] == 3
    assert counts[7] == 5
    assert counts[104] == 2
    assert counts[112] == 4
    assert counts[235] == 1
    assert counts[860] == 3
    assert counts[861] == 1
    assert counts[1030] == 3
    assert counts[1031] == 3
    assert counts[1092] == 1
    assert counts[1097] == 3
    assert counts[1152] == 4
    assert counts[1219] == 2
    assert all(count <= 4 for card_id, count in counts.items() if card_id not in {3, 7})


def test_starmie_froslass_petrel_v3_prefers_staryu_active_and_snorunt_bench_setup():
    module = _load_main_module()

    active_obs = {
        "current": {"players": [{}, {}], "yourIndex": 0},
        "select": {
            "context": module.CTX_SETUP_ACTIVE,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_CARD, "cardId": module.C.MUNKIDORI},
                {"type": module.OPT_CARD, "cardId": module.C.STARYU},
                {"type": module.OPT_CARD, "cardId": module.C.SNORUNT},
                {"type": module.OPT_CARD, "cardId": module.C.BUDEW},
            ],
        },
    }
    bench_obs = {
        "current": {
            "players": [{"active": [{"id": module.C.STARYU}], "bench": []}, {}],
            "yourIndex": 0,
        },
        "select": {
            "context": module.CTX_SETUP_BENCH,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_CARD, "cardId": module.C.MUNKIDORI},
                {"type": module.OPT_CARD, "cardId": module.C.SNORUNT},
                {"type": module.OPT_CARD, "cardId": module.C.BUDEW},
            ],
        },
    }

    assert module.agent(active_obs, None) == [1]
    assert module.agent(bench_obs, None) == [1]


def test_starmie_froslass_petrel_v3_uses_petrel_and_secret_box_after_setup():
    module = _load_main_module()
    base_current = {
        "players": [
            {
                "active": [{"id": module.C.MEGA_STARMIE_EX, "hp": 330, "maxHp": 330, "energies": [3]}],
                "bench": [
                    {"id": module.C.FROSLASS, "hp": 90, "maxHp": 90, "energies": []},
                    {"id": module.C.MUNKIDORI, "hp": 110, "maxHp": 110, "energies": [7]},
                    {"id": module.C.SNORUNT, "hp": 70, "maxHp": 70, "energies": []},
                ],
                "hand": [
                    {"id": module.C.TEAM_ROCKETS_PETREL},
                    {"id": module.C.LILLIES_DETERMINATION},
                    {"id": module.C.SECRET_BOX},
                    {"id": module.C.BASIC_DARK_ENERGY},
                    {"id": module.C.POKE_PAD},
                ],
                "handCount": 5,
                "deckCount": 26,
                "prize": [None] * 5,
            },
            {
                "active": [{"id": module.C.MEGA_STARMIE_EX, "hp": 330, "maxHp": 330, "energies": [3]}],
                "bench": [
                    {"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []},
                    {"id": module.C.MEGA_FROSLASS_EX, "hp": 310, "maxHp": 310, "energies": [3]},
                ],
                "handCount": 7,
                "deckCount": 29,
                "prize": [None] * 5,
            },
        ],
        "yourIndex": 0,
        "supporterPlayed": False,
    }

    petrel_obs = {
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
    box_obs = {
        "current": base_current,
        "select": {
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_PLAY, "index": 1},
                {"type": module.OPT_PLAY, "index": 2},
            ],
        },
    }

    assert module.agent(petrel_obs, None) == [0]
    assert module.agent(box_obs, None) == [1]


def test_starmie_froslass_petrel_v3_attaches_dark_to_munkidori_support_engine():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.MEGA_STARMIE_EX, "hp": 330, "maxHp": 330, "energies": [3]}],
                    "bench": [{"id": module.C.MUNKIDORI, "hp": 110, "maxHp": 110, "energies": []}],
                    "hand": [{"id": module.C.BASIC_DARK_ENERGY}],
                    "handCount": 1,
                    "deckCount": 32,
                    "prize": [None] * 6,
                },
                {
                    "active": [{"id": module.C.HOPS_TREVENANT, "hp": 160, "maxHp": 160, "energies": [11, 19]}],
                    "bench": [{"id": module.C.HOPS_PHANTUMP, "hp": 70, "maxHp": 70, "energies": []}],
                    "handCount": 6,
                    "deckCount": 33,
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


def test_starmie_froslass_petrel_v3_boss_targeting_removes_mirror_bridge():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.MEGA_STARMIE_EX, "hp": 330, "maxHp": 330, "energies": [3]}],
                    "bench": [{"id": module.C.FROSLASS, "hp": 90, "maxHp": 90, "energies": []}],
                    "handCount": 4,
                    "deckCount": 30,
                    "prize": [None] * 5,
                },
                {
                    "active": [{"id": module.C.MUNKIDORI, "hp": 110, "maxHp": 110, "energies": [7]}],
                    "bench": [
                        {"id": module.C.BUDEW, "hp": 30, "maxHp": 30, "energies": []},
                        {"id": module.C.STARYU, "hp": 70, "maxHp": 70, "energies": []},
                        {"id": module.C.MEGA_STARMIE_EX, "hp": 330, "maxHp": 330, "energies": [3]},
                    ],
                    "handCount": 5,
                    "deckCount": 31,
                    "prize": [None] * 5,
                },
            ],
            "yourIndex": 0,
        },
        "select": {
            "context": module.CTX_TO_ACTIVE,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": module.OPT_CARD, "area": module.AREA_BENCH, "index": 0, "playerIndex": 1},
                {"type": module.OPT_CARD, "area": module.AREA_BENCH, "index": 1, "playerIndex": 1},
                {"type": module.OPT_CARD, "area": module.AREA_BENCH, "index": 2, "playerIndex": 1},
            ],
        },
    }

    assert module.agent(obs, None) == [1]


def test_starmie_froslass_petrel_v3_rebuilds_before_no_backup_attack():
    module = _load_main_module()

    obs = {
        "current": {
            "players": [
                {
                    "active": [{"id": module.C.MEGA_STARMIE_EX, "hp": 120, "maxHp": 330, "energies": [3]}],
                    "bench": [],
                    "hand": [{"id": module.C.NIGHT_STRETCHER}],
                    "handCount": 1,
                    "discard": [{"id": module.C.STARYU}, {"id": module.C.SNORUNT}, {"id": module.C.BASIC_WATER_ENERGY}],
                    "deckCount": 20,
                    "prize": [None] * 5,
                },
                {
                    "active": [{"id": module.C.MEGA_LUCARIO_EX, "hp": 270, "maxHp": 270, "energies": [6, 6]}],
                    "bench": [{"id": module.C.RIOLU, "hp": 80, "maxHp": 80, "energies": []}],
                    "handCount": 5,
                    "deckCount": 26,
                    "prize": [None] * 4,
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


def test_starmie_froslass_petrel_v3_archive_validates_startup_shape():
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
