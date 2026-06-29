from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import ptcg.native_core as native_core


ROOT = Path(__file__).resolve().parents[1]
HEADER_PATH = ROOT / "ptcg" / "native_core" / "ptcg_native_core.h"
SOURCE_PATH = ROOT / "ptcg" / "native_core" / "ptcg_native_core.c"
CATALOG_PATH = ROOT / "ptcg" / "native_core" / "ptcg_card_catalog.generated.h"


def _exported_c_functions() -> set[str]:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"PTCG_API\s+(?:const\s+char\s+\*|int)\s+(ptcg_[A-Za-z0-9_]+)\s*\(", source))


def _header_declared_functions() -> set[str]:
    header = HEADER_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"PTCG_API\s+(?:const\s+char\s+\*|int)\s+(ptcg_[A-Za-z0-9_]+)\s*\(", header))


def test_public_native_header_declares_every_exported_function() -> None:
    exported = _exported_c_functions()
    declared = _header_declared_functions()

    assert exported
    assert declared == exported


def test_public_native_header_exposes_deckcsv_struct_contract() -> None:
    header = HEADER_PATH.read_text(encoding="utf-8")

    required_fragments = [
        "#define PTCG_DECK_SIZE 60",
        "#define PTCG_HAND_SIZE 60",
        "#define PTCG_DISCARD_SIZE 120",
        "typedef struct PtcgDeck",
        "typedef struct PtcgBattlePlayer",
        "typedef struct PtcgBattleSetup",
        "typedef struct PtcgCardMetadata",
        "typedef struct PtcgAttackMetadata",
        "ptcg_start_battle_pregame_from_csv",
        "ptcg_select_pregame_first_player",
        "int pending_retreat_remaining;",
        "int pending_aura_jab_remaining;",
        "int bench_energy[PTCG_BENCH_SIZE][PTCG_ATTACHED_SIZE];",
        "int attacks[PTCG_CARD_ATTACK_SIZE];",
    ]

    for fragment in required_fragments:
        assert fragment in header


def test_public_native_header_is_self_contained_c_contract(tmp_path: Path) -> None:
    gcc = shutil.which("gcc")
    assert gcc is not None, "gcc is required to verify the native SDK header"

    smoke = tmp_path / "header_smoke.c"
    smoke.write_text(
        textwrap.dedent(
            f"""
            #include <stddef.h>
            #include "{HEADER_PATH.as_posix()}"

            int main(void) {{
                PtcgDeck deck;
                PtcgBattleSetup setup;
                PtcgCardMetadata card;
                PtcgAttackMetadata attack;
                deck.card_count = PTCG_DECK_SIZE;
                setup.pending_retreat_remaining = 0;
                card.retreat_cost = 0;
                attack.energy_count = PTCG_ATTACK_COST_SIZE;
                return deck.card_count
                    + setup.pending_retreat_remaining
                    + card.retreat_cost
                    + attack.energy_count
                    + (int)offsetof(PtcgBattleSetup, players);
            }}
            """
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [gcc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", str(smoke), "-o", str(tmp_path / "header_smoke.o")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_native_core_build_inputs_track_header_and_generated_catalog() -> None:
    assert native_core.SOURCE_PATH.resolve() == SOURCE_PATH
    assert HEADER_PATH in {path.resolve() for path in native_core.NATIVE_BUILD_INPUTS}
    assert CATALOG_PATH in {path.resolve() for path in native_core.NATIVE_BUILD_INPUTS}


def test_build_native_core_script_emits_compiled_api_manifest_from_deck_csv(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_native_core.py",
            "--force",
            "--build-dir",
            str(tmp_path),
            "--deck",
            "deck.csv",
            "--setup-seed",
            "17",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    manifest = payload["api_manifest"]
    deck_cards = payload["deck_cards"]

    assert payload["card_count"] == 60
    assert payload["deck_sha256"] == "2a541d7bf3d9e6b36037123f53f4dfef6348223f79fd27095dafc602a5357c19"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["library_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["source_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["header_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["catalog_sha256"])
    assert manifest["abi_constants"]["deck_size"] == 60
    assert manifest["function_count"] == len(manifest["exported_functions"])
    assert "ptcg_load_deck_csv" in manifest["exported_functions"]
    assert "ptcg_start_battle_pregame_from_csv" in manifest["exported_functions"]
    assert "ptcg_use_attack" in manifest["exported_functions"]
    assert manifest["parity_contract"] == {
        "deck_source": "deck.csv",
        "core": "clean-room C shared library",
        "verified_scope": "deck.csv load, public setup/main rules, and official-observed ordered-zone replay",
        "one_to_one_status": "not_1_to_1_standalone",
        "remaining_gap": "standalone official shuffle/RNG reproduction from deck.csv is not proven",
    }
    assert deck_cards["first_card_ids"][:3] == [673, 673, 674]
    assert deck_cards["unique_count"] > 10
    assert deck_cards["basic_pokemon_count"] > 0
    assert deck_cards["energy_count"] > 0
    assert deck_cards["named_counts"][0]["card_id"] == 673
    assert deck_cards["named_counts"][0]["count"] == 2
    assert deck_cards["named_counts"][0]["name"]
    assert payload["kaggle_submission_made"] is False
