from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_heuristic_candidates import _write_candidate


BASE_DECK_COUNTS = {
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

NO_RELIC_METAL_DECK_COUNTS = {
    **BASE_DECK_COUNTS,
    8: 12,  # Basic Metal Energy
    57: 0,  # Relicanth
}

NO_RELIC_JUDGE_METAL_DECK_COUNTS = {
    **NO_RELIC_METAL_DECK_COUNTS,
    1213: 1,  # Judge
    1244: 3,  # Full Metal Lab
}


BASE_CONFIG = {
    "key_cards": [169, 190, 8, 57, 666, 1097, 1121, 1122, 1147, 1152, 1159, 1182, 1185, 1227, 1244],
    "setup_cards": [169, 190, 8, 1097, 1121, 1122, 1147, 1152, 1185, 1227, 1244, 666],
    "attackers": [57, 169, 190, 666],
    "evolvers": [190],
    "disruption": [1182],
    "energy_ids": [8],
    "gate_targets": [119, 120, 121, 169, 190, 673, 674, 675, 676, 677, 678, 741, 742, 743, 878, 879, 1030, 1031, 1219, 1220],
}

NO_RELIC_CONFIG_OVERRIDES = {
    "key_cards": [169, 190, 8, 666, 1097, 1121, 1122, 1147, 1152, 1159, 1182, 1185, 1227, 1244],
    "attackers": [169, 190, 666],
}

NO_RELIC_JUDGE_CONFIG_OVERRIDES = {
    **NO_RELIC_CONFIG_OVERRIDES,
    "key_cards": [169, 190, 8, 666, 1097, 1121, 1122, 1147, 1152, 1159, 1182, 1185, 1213, 1227, 1244],
    "setup_cards": [169, 190, 8, 1097, 1121, 1122, 1147, 1152, 1185, 1213, 1227, 1244, 666],
    "disruption": [1182, 1213],
}


COMMON_WEIGHTS = {
    "key_card": 180,
    "setup_card_setup": 180,
    "attacker": 130,
    "evolver": 160,
    "energy_setup": 155,
    "energy_other": 55,
    "play_setup": 125,
    "evolve_option": 210,
    "attach_setup": 115,
    "bench_attach": 125,
    "build_next_attacker_bonus": 185,
    "projected_second_attacker_bonus": 170,
    "projected_powered_backup_bonus": 240,
    "projected_attack_race_penalty": 175,
    "bad_shape_attack_without_backup": 260,
    "attack_empty_bench_penalty": 155,
    "attack_active_danger_penalty": 145,
    "overattach_active_penalty": 190,
    "active_danger_attach_penalty": 170,
    "enemy_gate_target": 230,
    "enemy_powered_target": 190,
    "enemy_bench_target": 120,
    "single_powered_target": 210,
    "discard_core_penalty": 260,
    "discard_setup_penalty": 180,
    "low_deck_setup_penalty": 90,
    "end_low_deck": 80,
    "archaludon_setup_active_duraludon": 700,
    "archaludon_setup_active_cinderace_penalty": 250,
    "archaludon_setup_active_archaludon_penalty": 160,
    "archaludon_setup_active_relicanth_penalty": 300,
    "archaludon_setup_bench_duraludon": 500,
    "archaludon_setup_bench_cinderace": 280,
    "archaludon_need_duraludon_card": 620,
    "archaludon_need_archaludon_card": 700,
    "archaludon_need_metal_energy_card": 220,
    "archaludon_evolve_finish": 850,
    "archaludon_evolve_line": 260,
    "archaludon_attach_line": 520,
    "archaludon_attach_bench_line": 650,
    "archaludon_attach_finish_archaludon": 360,
    "archaludon_overfeed_active_penalty": 260,
    "archaludon_attach_cinderace_bridge": 180,
    "archaludon_attach_relicanth_penalty": 300,
    "archaludon_metal_defender_ready": 700,
    "archaludon_raging_hammer_damaged": 520,
    "archaludon_raging_hammer_ready": 180,
    "archaludon_hammer_in_when_raging_live_penalty": 260,
    "archaludon_turbo_flare_setup": 500,
    "archaludon_turbo_flare_when_line_ready_penalty": 120,
    "archaludon_hero_cape_target": 650,
    "archaludon_hero_cape_duraludon_target": 240,
    "archaludon_hero_cape_cinderace_penalty": 160,
    "archaludon_powered_target_pressure": 130,
}


VARIANTS = {
    "archaludon_broad_stabilizer_v2": {
        "strategy": (
            "archaludon broad stabilizer v2: start Duraludon, finish Archaludon, "
            "build a second Metal attacker, prefer clean Metal Defender, and avoid active overfeed"
        ),
        "rng_noise": 4.0,
        "weights": {
            **COMMON_WEIGHTS,
            "archaludon_boss_pressure": 120,
            "targeting_context_gate_bonus": 90,
        },
    },
    "archaludon_broad_pressure_v2": {
        "strategy": (
            "archaludon broad pressure v2: same Duraludon/Archaludon setup floor with "
            "slightly stronger Boss pressure into powered engines and evolving bridges"
        ),
        "rng_noise": 6.0,
        "weights": {
            **COMMON_WEIGHTS,
            "enemy_gate_target": 275,
            "enemy_powered_target": 230,
            "enemy_bench_target": 145,
            "archaludon_boss_pressure": 220,
            "targeting_context_gate_bonus": 145,
            "disruption_pressure": 150,
            "archaludon_need_duraludon_card": 560,
            "archaludon_need_archaludon_card": 640,
        },
    },
    "archaludon_broad_floor_v3": {
        "strategy": (
            "archaludon broad floor v3: same meta deck, but Relicanth is treated as a support piece, "
            "Metal Energy is pushed back onto Duraludon/Archaludon, and Boss pressure stays moderate"
        ),
        "rng_noise": 4.0,
        "config_overrides": {
            "attackers": [169, 190, 666],
        },
        "weights": {
            **COMMON_WEIGHTS,
            "archaludon_setup_active_relicanth_penalty": 430,
            "archaludon_attach_relicanth_penalty": 420,
            "archaludon_boss_pressure": 165,
            "targeting_context_gate_bonus": 115,
            "enemy_gate_target": 250,
            "enemy_powered_target": 205,
            "attack_setup_penalty": 20,
            "archaludon_need_duraludon_card": 640,
            "archaludon_need_archaludon_card": 720,
            "archaludon_attach_bench_line": 700,
        },
    },
    "archaludon_broad_no_relic_stabilizer_v1": {
        "strategy": (
            "archaludon broad no-relic stabilizer v1: convert the Relicanth slot into Metal Energy, "
            "remove Relicanth from policy targets, and use the broad scorer to build Duraludon/Archaludon backup"
        ),
        "deck_counts": NO_RELIC_METAL_DECK_COUNTS,
        "rng_noise": 4.0,
        "config_overrides": NO_RELIC_CONFIG_OVERRIDES,
        "weights": {
            **COMMON_WEIGHTS,
            "archaludon_boss_pressure": 120,
            "targeting_context_gate_bonus": 90,
            "archaludon_need_duraludon_card": 650,
            "archaludon_need_archaludon_card": 735,
            "archaludon_attach_bench_line": 725,
            "archaludon_metal_defender_ready": 735,
        },
    },
    "archaludon_broad_no_relic_judge_stabilizer_v1": {
        "strategy": (
            "archaludon broad no-relic judge stabilizer v1: use the round20 no-Relic Judge shell, "
            "keep setup-first Archaludon scoring, and use Judge only as a broad pressure valve"
        ),
        "deck_counts": NO_RELIC_JUDGE_METAL_DECK_COUNTS,
        "rng_noise": 4.0,
        "config_overrides": NO_RELIC_JUDGE_CONFIG_OVERRIDES,
        "weights": {
            **COMMON_WEIGHTS,
            "archaludon_boss_pressure": 145,
            "targeting_context_gate_bonus": 105,
            "disruption_pressure": 115,
            "archaludon_need_duraludon_card": 650,
            "archaludon_need_archaludon_card": 735,
            "archaludon_attach_bench_line": 725,
            "archaludon_metal_defender_ready": 735,
        },
    },
    "archaludon_broad_no_relic_judge_pressure_v1": {
        "strategy": (
            "archaludon broad no-relic judge pressure v1: keep the no-Relic Judge shell but push harder "
            "on Boss/Judge target pressure into powered gates and evolving bridges"
        ),
        "deck_counts": NO_RELIC_JUDGE_METAL_DECK_COUNTS,
        "rng_noise": 6.0,
        "config_overrides": NO_RELIC_JUDGE_CONFIG_OVERRIDES,
        "weights": {
            **COMMON_WEIGHTS,
            "enemy_gate_target": 290,
            "enemy_powered_target": 245,
            "enemy_bench_target": 155,
            "archaludon_boss_pressure": 245,
            "targeting_context_gate_bonus": 165,
            "disruption_pressure": 175,
            "archaludon_need_duraludon_card": 600,
            "archaludon_need_archaludon_card": 680,
            "archaludon_attach_bench_line": 690,
        },
    },
}


def _deck_from_counts(counts: dict[int, int]) -> list[int]:
    deck: list[int] = []
    for card_id, count in counts.items():
        deck.extend([card_id] * count)
    if len(deck) != 60:
        raise ValueError(f"deck has {len(deck)} cards, expected 60")
    return deck


def _safe_remove_tree(path: Path) -> None:
    resolved = path.resolve()
    artifact_root = (ROOT / "artifacts").resolve()
    if artifact_root != resolved and artifact_root not in resolved.parents:
        raise ValueError(f"refusing to remove outside artifacts: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def _copy_cg_bundle(candidate_dir: Path) -> None:
    source = ROOT / "data" / "official" / "cg"
    if not source.exists():
        source = ROOT / "artifacts" / "archaludon_metal_stabilizer_v1" / "cg"
    if not source.exists():
        raise FileNotFoundError("could not find cg runtime bundle")
    destination = candidate_dir / "cg"
    if destination.exists():
        _safe_remove_tree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _write_archive(candidate_dir: Path, archive_path: Path) -> str:
    if archive_path.exists():
        archive_path.unlink()
    members = [candidate_dir / "main.py", candidate_dir / "deck.csv"]
    members.extend(path for path in sorted((candidate_dir / "cg").rglob("*")) if path.is_file() and "__pycache__" not in path.parts)
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in members:
            tar.add(path, arcname=path.relative_to(candidate_dir).as_posix())
    return _sha256(archive_path)


def _git_status_short() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return [result.stderr.strip() or "git status failed"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def _meta_summary(meta_path: Path) -> dict[str, Any]:
    data = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    source = data.get("source") or {}
    return {
        "meta_date": data.get("date"),
        "latest_date": data.get("latestDate"),
        "redirected": data.get("redirected"),
        "total_decks": data.get("totalDecks"),
        "dataset_url": source.get("datasetUrl"),
        "source": source,
    }


def build(output_root: Path, meta_path: Path, variant_names: list[str] | None = None, report_name: str = "archaludon_broad_candidates_build_report.json") -> dict[str, Any]:
    meta = _meta_summary(meta_path)
    manifest: list[dict[str, Any]] = []
    selected = set(variant_names or [])
    unknown = selected.difference(VARIANTS)
    if unknown:
        raise ValueError(f"unknown variant(s): {', '.join(sorted(unknown))}")

    for name, variant in VARIANTS.items():
        if selected and name not in selected:
            continue
        deck = _deck_from_counts(variant.get("deck_counts", BASE_DECK_COUNTS))
        candidate_dir = output_root / name
        _safe_remove_tree(candidate_dir)
        config = {
            **BASE_CONFIG,
            **variant.get("config_overrides", {}),
            "strategy": variant["strategy"],
            "rng_noise": variant["rng_noise"],
            "weights": variant["weights"],
        }
        candidate = _write_candidate(output_root, name, deck, config)
        _copy_cg_bundle(candidate_dir)
        shutil.copy2(meta_path, candidate_dir / "meta_snapshot.json")
        strategy_path = candidate_dir / "strategy.md"
        strategy_path.write_text(
            "\n".join(
                [
                    f"# {name}",
                    "",
                    variant["strategy"],
                    "",
                    "Broad policy shape:",
                    "- Start and bench Duraludon before Cinderace when choosing a setup Pokemon.",
                    "- Finish Archaludon ex from Duraludon before taking low-value attacks.",
                    "- Attach Metal Energy to the line and the next attacker before overfeeding active.",
                    "- Prefer Metal Defender when Archaludon ex is clean and ready.",
                    "- Prefer Raging Hammer only when the active Duraludon/Archaludon line is damaged.",
                    "- Put Hero's Cape on Archaludon ex before bridge attackers.",
                    "",
                    "Kaggle submission made: false",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        archive = output_root / f"submission_{name}.tar.gz"
        sha256 = _write_archive(candidate_dir, archive)
        report = {
            "candidate": name,
            "strategy": variant["strategy"],
            "artifact_dir": str(candidate_dir),
            "archive": str(archive),
            "archive_sha256": sha256,
            "deck_size": len(deck),
            "deck_counts": dict(sorted(Counter(deck).items())),
            "meta": meta,
            "source_metadata": {
                "live_api_url": "https://ptcg-kaggle-meta.vercel.app/api/meta?page=1",
                "user_supplied_archaludon_meta_share": 0.146,
                "user_supplied_parsed_decklists": 1725,
                "user_supplied_win_rate": 0.622,
            },
            "kaggle_submission_made": False,
        }
        (candidate_dir / "build_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        manifest.append({**candidate, **report})

    aggregate = {
        "command": [sys.executable, *sys.argv],
        "git_status_short": _git_status_short(),
        "candidate_count": len(manifest),
        "candidates": manifest,
        "meta": meta,
        "deck_counts_by_candidate": {
            item["candidate"]: item["deck_counts"]
            for item in manifest
        },
        "kaggle_submission_made": False,
    }
    (output_root / report_name).write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description="Build broad Archaludon/Duraludon v2 heuristic packages.")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--meta-json", type=Path, default=Path("artifacts/latest_meta_api_raw_archaludon_broad_run.json"))
    parser.add_argument("--variant", action="append", choices=sorted(VARIANTS), help="Build only this variant. May be repeated.")
    parser.add_argument("--report-name", default="archaludon_broad_candidates_build_report.json")
    args = parser.parse_args()
    report = build(args.output_root, args.meta_json, variant_names=args.variant, report_name=args.report_name)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
