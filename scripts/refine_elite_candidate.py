from __future__ import annotations

import argparse
import importlib.util
import json
import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_eval import smoke_native_agent_vs_agent, smoke_native_agent_vs_random
from scripts.generate_heuristic_candidates import _write_candidate
from scripts.tune_heuristic_rng import _focused_opponents


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("elite_candidate_source", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_deck(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _base_config(main_path: Path, deck_path: Path) -> tuple[list[int], dict]:
    module = _load_module(main_path)
    return _load_deck(deck_path), {
        "strategy": f"elite refinement from {main_path.parent.name}",
        "key_cards": sorted(getattr(module, "KEY_CARDS", set())),
        "setup_cards": sorted(getattr(module, "SETUP_CARDS", set())),
        "attackers": sorted(getattr(module, "ATTACKERS", set())),
        "evolvers": sorted(getattr(module, "EVOLVERS", set())),
        "disruption": sorted(getattr(module, "DISRUPTION", set())),
        "energy_ids": sorted(getattr(module, "ENERGY_IDS", set())),
        "gate_targets": sorted(getattr(module, "GATE_TARGETS", set())),
        "rng_noise": float(getattr(module, "RNG_NOISE", 20.0)),
        "weights": dict(getattr(module, "WEIGHTS", {})),
    }


def _mutate_elite(base: dict, rng: random.Random, index: int, scale: float) -> dict:
    config = dict(base)
    config["weights"] = {
        key: round(max(0.0, float(value) * rng.uniform(1.0 - scale, 1.0 + scale)), 3)
        for key, value in base.get("weights", {}).items()
    }
    for key, default in {
        "bench_floor_card": 115,
        "bench_floor_play": 135,
        "bench_floor_select": 125,
        "bench_floor_attach": 105,
        "active_danger_attach_penalty": 120,
        "attack_active_danger_penalty": 95,
    }.items():
        if key not in config["weights"]:
            config["weights"][key] = round(default * rng.uniform(1.0 - scale, 1.0 + scale), 3)
    config["rng_noise"] = round(max(2.0, float(base.get("rng_noise", 20.0)) * rng.uniform(0.75, 1.25)), 3)
    config["strategy"] = f"{base['strategy']} elite variant {index}"
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine a strong generated PTCG candidate by local weight mutation.")
    parser.add_argument("--elite-main", type=Path, required=True)
    parser.add_argument("--elite-deck", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--opponents-manifest", type=Path, default=Path("artifacts/public_code/opponents_manifest.json"))
    parser.add_argument("--focus-opponents", type=Path, default=Path("artifacts/candidates/coverage_summary.json"))
    parser.add_argument("--variants", type=int, default=24)
    parser.add_argument("--games", type=int, default=3)
    parser.add_argument("--seed", type=int, default=13001)
    parser.add_argument("--scale", type=float, default=0.22)
    parser.add_argument("--skip-random-smoke", action="store_true")
    args = parser.parse_args()

    deck, base = _base_config(args.elite_main, args.elite_deck)
    rng = random.Random(args.seed)
    opponents = _focused_opponents(args.opponents_manifest, args.focus_opponents)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    stem = args.elite_main.parent.name
    for index in range(args.variants):
        config = _mutate_elite(base, rng, index, args.scale)
        candidate_name = f"{stem}_elite_v{index:02d}"
        candidate = _write_candidate(args.output_dir, candidate_name, deck, config)
        wins = 0
        finished = 0
        errors: list[str] = []
        if not args.skip_random_smoke:
            random_smoke = smoke_native_agent_vs_random(
                main_path=Path(candidate["main_path"]),
                deck_path=Path(candidate["deck_path"]),
                games=max(2, args.games),
                seed=args.seed + index,
            )
            wins += random_smoke.wins
            finished += random_smoke.finished
            errors.extend(random_smoke.errors)
        opponent_rows = []
        for opponent_index, opponent in enumerate(opponents):
            result = smoke_native_agent_vs_agent(
                candidate_main_path=Path(candidate["main_path"]),
                candidate_deck_path=Path(candidate["deck_path"]),
                opponent_main_path=Path(opponent["main_path"]),
                opponent_deck_path=Path(opponent["deck_path"]),
                games=args.games,
                seed=args.seed + index * 100 + opponent_index,
            )
            wins += result.wins
            finished += result.finished
            errors.extend(result.errors)
            opponent_rows.append({
                "opponent": opponent["ref"],
                "wins": result.wins,
                "finished": result.finished,
                "errors": list(result.errors),
            })
        row = {
            "candidate": candidate_name,
            "family": stem,
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
        print(json.dumps({key: row[key] for key in ("candidate", "family", "wins", "finished", "win_rate", "main_path", "deck_path")}))


if __name__ == "__main__":
    main()
