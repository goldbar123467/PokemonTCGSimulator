from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_eval import smoke_native_agent_vs_agent, smoke_native_agent_vs_random
from scripts.generate_heuristic_candidates import _pick_deck, _write_candidate


BASE_CONFIGS = {
    "dragapult": {
        "family": "dragapult_120_119",
        "strategy": "spread-aware stabilizer tuned by RNG",
        "key_cards": [119, 120, 121, 1086, 1152, 1121, 1227],
        "setup_cards": [119, 120, 121, 1086, 1121, 1152, 1227, 305, 140, 235],
        "attackers": [119, 120, 121, 305, 112],
        "evolvers": [120, 121],
        "disruption": [1182, 1198],
        "energy_ids": [2, 5],
        "gate_targets": [119, 120, 121, 673, 674, 675, 676, 677, 678, 741, 742, 743],
        "rng_noise": 24.0,
    },
    "alakazam": {
        "family": "alakazam_741_742",
        "strategy": "stabilizer tuned by RNG",
        "key_cards": [741, 742, 743, 1086, 1152, 1231],
        "setup_cards": [741, 742, 1086, 1152, 1225, 1231, 305, 66],
        "attackers": [741, 742, 743, 305, 66],
        "evolvers": [742, 743],
        "disruption": [1079, 1156, 1231],
        "energy_ids": [5, 19],
        "gate_targets": [119, 120, 121, 673, 677, 678],
        "rng_noise": 18.0,
    },
    "shell666": {
        "family": "shell_666",
        "strategy": "disruptor tuned by RNG",
        "key_cards": [666, 1030, 1031, 1086, 1122, 1145],
        "setup_cards": [666, 1030, 1031, 1086, 1120, 1122, 1227],
        "attackers": [666, 1030, 1031],
        "evolvers": [1031],
        "disruption": [1122, 1145, 1189, 1229],
        "energy_ids": [3, 17],
        "gate_targets": [119, 120, 121, 673, 677, 678, 741, 742, 743],
        "rng_noise": 36.0,
    },
    "lucario": {
        "family": "lucario",
        "strategy": "lucario mirror/race tuned by RNG",
        "key_cards": [676, 677, 678, 1102, 1141, 1142, 1152, 1192, 1227],
        "setup_cards": [676, 677, 678, 1102, 1141, 1142, 1152, 1192, 1227, 1123],
        "attackers": [676, 677, 678],
        "evolvers": [677, 678],
        "disruption": [1123, 1182, 1252],
        "energy_ids": [6],
        "gate_targets": [119, 120, 121, 673, 674, 675, 676, 677, 678, 741, 742, 743],
        "rng_noise": 20.0,
    },
}


def _mutate(base: dict, rng: random.Random, index: int) -> dict:
    config = dict(base)
    config["rng_noise"] = round(max(4.0, base["rng_noise"] * rng.uniform(0.4, 1.8)), 3)
    weights = {}
    for key in [
        "key_card",
        "attacker",
        "evolver",
        "setup_card_setup",
        "disruption_pressure",
        "energy_setup",
        "gate_target",
        "play_setup",
        "bench_attach",
        "evolve_option",
        "attack_option",
        "attack_setup_penalty",
        "behind_bonus",
        "gate_pressure_bonus",
        "low_deck_setup_penalty",
        "own_attacker_target",
        "own_evolver_target",
        "own_bench_target",
        "unpowered_next_attacker",
        "enemy_gate_target",
        "enemy_powered_target",
        "single_powered_target",
        "enemy_bench_target",
        "enemy_pressure_target",
        "attack_single_powered_bonus",
        "bench_development_card",
        "bench_development_play",
        "bench_development_select",
        "attack_empty_bench_penalty",
        "constructive_context",
        "discard_core_penalty",
        "discard_setup_penalty",
        "targeting_context_gate_bonus",
        "overattach_active_penalty",
        "build_next_attacker_bonus",
        "bench_floor_card",
        "bench_floor_play",
        "bench_floor_select",
        "bench_floor_attach",
        "active_danger_attach_penalty",
        "attack_active_danger_penalty",
        "lucario_chain_target",
        "lucario_bench_chain_target",
        "lucario_evolving_basic_target",
        "lucario_powered_chain_target",
        "attack_lucario_rebuild_penalty",
        "lucario_disruption_bonus",
        "lucario_tempo_option_bonus",
        "lucario_build_bench_attacker_attach",
        "lucario_overfeed_active_penalty",
        "early_shape_setup_action",
        "early_shape_constructive_select",
        "bad_shape_attack_without_backup",
        "bad_shape_end_without_backup",
        "behind_shape_target_live_threat",
        "behind_shape_play_out",
        "ahead_shape_end_when_stable",
        "ahead_shape_discard_disruption",
        "projected_second_attacker_bonus",
        "projected_powered_backup_bonus",
        "projected_lucario_parity_bonus",
        "projected_attack_race_penalty",
        "projected_end_race_penalty",
        "projected_discard_backup_penalty",
        "dragapult_chain_needed_piece",
        "dragapult_wrong_chain_piece_penalty",
        "dragapult_evolve_bridge",
        "dragapult_evolve_finish",
        "dragapult_phantom_dive_attack",
        "dragapult_jet_headbutt_when_phantom_live_penalty",
        "dragapult_counter_finish_target",
        "dragapult_counter_bench_rebuild_target",
        "dragapult_counter_powered_bench_target",
        "dragapult_counter_active_penalty",
        "dragapult_attack_before_chain_penalty",
    ]:
        weights[key] = round(rng.uniform(0.55, 1.75), 4)
    # Convert multipliers around the template defaults into actual values.
    defaults = {
        "key_card": 200,
        "attacker": 140,
        "evolver": 110,
        "setup_card_setup": 90,
        "disruption_pressure": 120,
        "energy_setup": 85,
        "gate_target": 160,
        "play_setup": 80,
        "bench_attach": 80,
        "evolve_option": 135,
        "attack_option": 180,
        "attack_setup_penalty": 35,
        "behind_bonus": 55,
        "gate_pressure_bonus": 45,
        "low_deck_setup_penalty": 45,
        "own_attacker_target": 95,
        "own_evolver_target": 65,
        "own_bench_target": 55,
        "unpowered_next_attacker": 70,
        "enemy_gate_target": 210,
        "enemy_powered_target": 160,
        "single_powered_target": 180,
        "enemy_bench_target": 90,
        "enemy_pressure_target": 75,
        "attack_single_powered_bonus": 80,
        "bench_development_card": 130,
        "bench_development_play": 150,
        "bench_development_select": 120,
        "attack_empty_bench_penalty": 85,
        "constructive_context": 70,
        "discard_core_penalty": 180,
        "discard_setup_penalty": 120,
        "targeting_context_gate_bonus": 85,
        "overattach_active_penalty": 140,
        "build_next_attacker_bonus": 120,
        "bench_floor_card": 115,
        "bench_floor_play": 135,
        "bench_floor_select": 125,
        "bench_floor_attach": 105,
        "active_danger_attach_penalty": 120,
        "attack_active_danger_penalty": 95,
        "lucario_chain_target": 165,
        "lucario_bench_chain_target": 145,
        "lucario_evolving_basic_target": 120,
        "lucario_powered_chain_target": 190,
        "attack_lucario_rebuild_penalty": 130,
        "lucario_disruption_bonus": 115,
        "lucario_tempo_option_bonus": 60,
        "lucario_build_bench_attacker_attach": 150,
        "lucario_overfeed_active_penalty": 150,
        "early_shape_setup_action": 120,
        "early_shape_constructive_select": 115,
        "bad_shape_attack_without_backup": 170,
        "bad_shape_end_without_backup": 150,
        "behind_shape_target_live_threat": 130,
        "behind_shape_play_out": 80,
        "ahead_shape_end_when_stable": 55,
        "ahead_shape_discard_disruption": 80,
        "projected_second_attacker_bonus": 120,
        "projected_powered_backup_bonus": 150,
        "projected_lucario_parity_bonus": 130,
        "projected_attack_race_penalty": 175,
        "projected_end_race_penalty": 155,
        "projected_discard_backup_penalty": 145,
        "dragapult_chain_needed_piece": 210,
        "dragapult_wrong_chain_piece_penalty": 80,
        "dragapult_evolve_bridge": 220,
        "dragapult_evolve_finish": 260,
        "dragapult_phantom_dive_attack": 190,
        "dragapult_jet_headbutt_when_phantom_live_penalty": 70,
        "dragapult_counter_finish_target": 260,
        "dragapult_counter_bench_rebuild_target": 150,
        "dragapult_counter_powered_bench_target": 100,
        "dragapult_counter_active_penalty": 80,
        "dragapult_attack_before_chain_penalty": 110,
    }
    config["weights"] = {name: round(defaults[name] * scale, 3) for name, scale in weights.items()}
    config["strategy"] = f"{base['strategy']} variant {index}"
    return config


def _hard_gate_opponents(manifest_path: Path) -> list[dict]:
    rows = [row for row in json.loads(manifest_path.read_text(encoding="utf-8")) if row.get("ok")]
    priority = [
        "mega-lucario",
        "lucario",
        "alakazam",
        "crustle",
        "multiply",
    ]
    selected = []
    for token in priority:
        for row in rows:
            if token in row["ref"].lower() and row not in selected:
                selected.append(row)
                break
    return selected[:5] or rows[:5]


def _focused_opponents(manifest_path: Path, focus_path: Path | None) -> list[dict]:
    rows = [row for row in json.loads(manifest_path.read_text(encoding="utf-8")) if row.get("ok")]
    if focus_path is None:
        return _hard_gate_opponents(manifest_path)
    focus_payload = json.loads(focus_path.read_text(encoding="utf-8"))
    if isinstance(focus_payload, dict):
        focus_rows = focus_payload.get("hard_opponents") or focus_payload.get("best_by_opponent") or []
    else:
        focus_rows = focus_payload
    refs = [row["opponent"] for row in focus_rows if row.get("opponent")]
    selected = []
    for ref in refs:
        for row in rows:
            if row["ref"] == ref and row not in selected:
                selected.append(row)
                break
    return selected or _hard_gate_opponents(manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="RNG tune scout-guided heuristic candidates.")
    parser.add_argument("--scout-decks", type=Path, default=Path("artifacts/candidates/scout_decks.json"))
    parser.add_argument("--opponents-manifest", type=Path, default=Path("artifacts/public_code/opponents_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/candidates/tuned"))
    parser.add_argument("--variants-per-family", type=int, default=4)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--focus-opponents", type=Path, default=None)
    parser.add_argument(
        "--families",
        default=None,
        help="Comma-separated family names to tune; defaults to all configured families.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    scout = json.loads(args.scout_decks.read_text(encoding="utf-8"))
    opponents = _focused_opponents(args.opponents_manifest, args.focus_opponents)
    results = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected_families = list(BASE_CONFIGS)
    if args.families:
        selected_families = [family.strip() for family in args.families.split(",") if family.strip()]
        unknown = sorted(set(selected_families) - set(BASE_CONFIGS))
        if unknown:
            raise ValueError(f"unknown families: {', '.join(unknown)}")
    for family_name in selected_families:
        base = BASE_CONFIGS[family_name]
        deck = _pick_deck(scout, base["family"])
        for index in range(args.variants_per_family):
            config = _mutate(base, rng, index)
            candidate_name = f"{family_name}_v{index:02d}"
            candidate = _write_candidate(args.output_dir, candidate_name, deck, config)
            random_smoke = smoke_native_agent_vs_random(
                main_path=Path(candidate["main_path"]),
                deck_path=Path(candidate["deck_path"]),
                games=max(2, args.games),
                seed=args.seed + index,
            )
            wins = random_smoke.wins
            finished = random_smoke.finished
            errors = list(random_smoke.errors)
            opponent_rows = []
            for opponent in opponents:
                match = smoke_native_agent_vs_agent(
                    candidate_main_path=Path(candidate["main_path"]),
                    candidate_deck_path=Path(candidate["deck_path"]),
                    opponent_main_path=Path(opponent["main_path"]),
                    opponent_deck_path=Path(opponent["deck_path"]),
                    games=args.games,
                    seed=args.seed + index,
                )
                wins += match.wins
                finished += match.finished
                errors.extend(match.errors)
                opponent_rows.append(
                    {
                        "opponent": opponent["ref"],
                        "wins": match.wins,
                        "finished": match.finished,
                        "errors": list(match.errors),
                    }
                )
            row = {
                "candidate": candidate_name,
                "family": family_name,
                "main_path": candidate["main_path"],
                "deck_path": candidate["deck_path"],
                "wins": wins,
                "finished": finished,
                "win_rate": wins / finished if finished else 0.0,
                "errors": errors,
                "opponents": opponent_rows,
                "weights": config["weights"],
                "rng_noise": config["rng_noise"],
            }
            print(json.dumps(row))
            results.append(row)
    results.sort(key=lambda row: (-row["win_rate"], len(row["errors"]), row["candidate"]))
    (args.output_dir / "tuning_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("BEST")
    for row in results[:5]:
        print(json.dumps({k: row[k] for k in ("candidate", "family", "wins", "finished", "win_rate", "main_path", "deck_path")}))


if __name__ == "__main__":
    main()
