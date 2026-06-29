from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_eval import smoke_native_agent_vs_agent
from ptcg.internal_leaderboard import CURRENT_META_URL, load_json_path_or_url, meta_weights_from_snapshot


TARGETS = {
    "lucario": {
        "coverage_keys": ("lucario_mirror",),
        "label": "Mega Lucario ex / Riolu",
        "raw_weight": 22.6,
        "tags": ["lucario", "direct_aggression"],
    },
    "hop_trevenant": {
        "coverage_keys": ("hop_trevenant",),
        "label": "Hop's Phantump / Hop's Trevenant",
        "raw_weight": 15.4,
        "tags": ["hop_trevenant", "hop", "trevenant", "control"],
    },
    "alakazam": {
        "coverage_keys": ("alakazam_psychic", "alakazam"),
        "label": "Abra / Alakazam",
        "raw_weight": 10.0,
        "tags": ["alakazam", "psychic", "control"],
    },
    "dragapult": {
        "coverage_keys": ("dragapult_spread",),
        "label": "Dragapult ex / Dreepy",
        "raw_weight": 6.7,
        "tags": ["dragapult", "spread"],
    },
    "team_rocket": {
        "coverage_keys": ("team_rocket", "team_rocket_petrel"),
        "label": "Team Rocket's Petrel / Team Rocket's Transceiver",
        "raw_weight": 5.9,
        "tags": ["team_rocket", "petrel", "disruption"],
    },
    "starmie": {
        "coverage_keys": ("starmie", "mega_starmie"),
        "label": "Ignition Energy / Mega Starmie ex",
        "raw_weight": 4.7,
        "tags": ["starmie", "spread", "water"],
    },
}

TARGET_META_ALIASES = {
    "dragapult": "dragapult_spread",
    "starmie": "mega_starmie",
    "team_rocket": "team_rocket_petrel",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _initial_decks(replay: dict[str, Any]) -> dict[int, list[int]]:
    decks: dict[int, list[int]] = {}
    steps = replay.get("steps")
    if not isinstance(steps, list):
        return decks
    for step in steps[:5]:
        if not isinstance(step, list):
            continue
        for player_index, player_step in enumerate(step):
            if not isinstance(player_step, dict):
                continue
            action = player_step.get("action")
            if (
                isinstance(action, list)
                and len(action) == 60
                and all(isinstance(card_id, int) for card_id in action)
            ):
                decks[player_index] = [int(card_id) for card_id in action]
    return decks


def _write_deck(path: Path, deck: list[int]) -> None:
    path.write_text("\n".join(str(card_id) for card_id in deck) + "\n", encoding="utf-8")


def _matching_rows(coverage: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    keys = set(target["coverage_keys"])
    return [
        row
        for row in coverage.get("rows", [])
        if isinstance(row, dict) and str(row.get("classification")) in keys
    ]


def _candidate_source_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("file") and row.get("opponent_index") is not None:
            return row
    return rows[0] if rows else None


def _safe_ref(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_")


def _targets_for_snapshot(meta_snapshot: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    targets = {
        archetype: {
            **target,
            "coverage_keys": tuple(target["coverage_keys"]),
            "tags": list(target["tags"]),
        }
        for archetype, target in TARGETS.items()
    }
    if not meta_snapshot:
        return targets, {}

    weights = meta_weights_from_snapshot(meta_snapshot)
    for archetype, target in targets.items():
        canonical = TARGET_META_ALIASES.get(archetype, archetype)
        weight = weights.get(canonical)
        if weight:
            target["raw_weight"] = float(weight["raw_weight"])
            target["meta_labels"] = list(weight.get("labels") or [])
    source = meta_snapshot.get("source") if isinstance(meta_snapshot.get("source"), dict) else {}
    return targets, {
        "snapshot_date": meta_snapshot.get("date"),
        "latest_date": meta_snapshot.get("latestDate"),
        "redirected": meta_snapshot.get("redirected"),
        "total_decks": meta_snapshot.get("totalDecks"),
        "dataset_url": source.get("datasetUrl"),
    }


def _smoke_gate(
    *,
    candidate_main: Path,
    candidate_deck: Path,
    opponent_main: Path,
    opponent_deck: Path,
    games: int,
    seed: int,
) -> dict[str, Any]:
    if games <= 0:
        return {
            "games": 0,
            "finished": 0,
            "candidate_wins": 0,
            "candidate_losses": 0,
            "draws": 0,
            "errors": [],
            "skipped": True,
        }
    result = smoke_native_agent_vs_agent(
        candidate_main_path=candidate_main,
        candidate_deck_path=candidate_deck,
        opponent_main_path=opponent_main,
        opponent_deck_path=opponent_deck,
        games=games,
        seed=seed,
    )
    return {
        "games": result.games,
        "finished": result.finished,
        "candidate_wins": result.wins,
        "candidate_losses": result.losses,
        "draws": result.draws,
        "errors": list(result.errors),
        "skipped": False,
    }


def build_current_meta_replay_gates(
    *,
    coverage_path: Path,
    replay_dir: Path,
    gate_root: Path,
    mining_dir: Path,
    output_manifest: Path,
    pilot_main: Path,
    candidate_main: Path,
    candidate_deck: Path,
    smoke_games: int,
    seed: int,
    snapshot_date: str = "2026-06-24",
    dataset_url: str = "https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-2026-06-24",
    meta_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    coverage = _read_json(coverage_path)
    rows: list[dict[str, Any]] = []
    gate_root.mkdir(parents=True, exist_ok=True)
    mining_dir.mkdir(parents=True, exist_ok=True)
    targets, meta_metadata = _targets_for_snapshot(meta_snapshot)
    effective_snapshot_date = str(meta_metadata.get("snapshot_date") or snapshot_date)
    effective_dataset_url = str(meta_metadata.get("dataset_url") or dataset_url)

    for target_index, (archetype, target) in enumerate(targets.items()):
        errors: list[str] = []
        matching_rows = _matching_rows(coverage, target)
        source_row = _candidate_source_row(matching_rows)
        gate_dir = gate_root / _safe_ref(archetype)
        gate_dir.mkdir(parents=True, exist_ok=True)
        main_path = gate_dir / "main.py"
        deck_path = gate_dir / "deck.csv"
        evidence_games = [
            {
                "episode_id": str(row.get("episode_id")),
                "file": row.get("file"),
                "outcome": row.get("outcome"),
                "key_turn_numbers": [],
            }
            for row in matching_rows
        ]
        deck_source = None

        if source_row is None:
            errors.append("no labeled replay row for archetype")
        else:
            replay_file = replay_dir / str(source_row.get("file"))
            opponent_index = int(source_row.get("opponent_index", 1))
            if not replay_file.exists():
                errors.append(f"missing replay file: {replay_file}")
            else:
                decks = _initial_decks(_read_json(replay_file))
                deck = decks.get(opponent_index)
                if deck is None:
                    errors.append(f"no initial deck for player {opponent_index} in {replay_file.name}")
                else:
                    shutil.copyfile(pilot_main, main_path)
                    _write_deck(deck_path, deck)
                    deck_source = f"public_local_replay:{replay_file.name}:player{opponent_index}"

        smoke = _smoke_gate(
            candidate_main=candidate_main,
            candidate_deck=candidate_deck,
            opponent_main=main_path,
            opponent_deck=deck_path,
            games=smoke_games,
            seed=seed + target_index,
        ) if not errors else {
            "games": smoke_games,
            "finished": 0,
            "candidate_wins": 0,
            "candidate_losses": 0,
            "draws": 0,
            "errors": list(errors),
            "skipped": True,
        }
        errors.extend(str(error) for error in smoke.get("errors", []))
        smoke_ok = not errors and (smoke_games <= 0 or int(smoke.get("finished", 0)) > 0)
        row = {
            "ref": f"current_meta/{archetype}",
            "title": str(target["label"]),
            "archetype": archetype,
            "raw_weight": float(target["raw_weight"]),
            "deck_path": str(deck_path) if deck_path.exists() else None,
            "main_path": str(main_path) if main_path.exists() else None,
            "pilot_path": str(main_path) if main_path.exists() else None,
            "deck_source": deck_source,
            "pilot_source": str(pilot_main),
            "snapshot_date": effective_snapshot_date,
            "latest_date": meta_metadata.get("latest_date"),
            "redirected": meta_metadata.get("redirected"),
            "total_decks": meta_metadata.get("total_decks"),
            "kaggle_dataset_url": effective_dataset_url,
            "smoke_ok": smoke_ok,
            "smoke": smoke,
            "ok": smoke_ok,
            "errors": errors,
            "tags": list(target["tags"]),
            "source_url": deck_source,
            "legal_scope": "public/local replay deck paired with official generic sample pilot; no hidden information",
        }
        rows.append(row)
        evidence = {
            "archetype": archetype,
            "label": target["label"],
            "games": evidence_games,
            "outcomes": {
                "clark_wins": sum(1 for game in evidence_games if game.get("outcome") == "win"),
                "clark_losses": sum(1 for game in evidence_games if game.get("outcome") == "loss"),
            },
            "failure_mode_summary": (
                "Coverage gate created from labeled replay deck. Losses still need trace-level decision labels "
                "before a matchup-specific heuristic patch."
            ),
            "gate_manifest_ref": row["ref"],
            "smoke": smoke,
        }
        (mining_dir / f"{archetype}_evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build current top-six meta replay gate manifest.")
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/mining/bootstrap_archetype_coverage.json"),
    )
    parser.add_argument(
        "--replay-dir",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/replays"),
    )
    parser.add_argument(
        "--gate-root",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/gates/current_meta"),
    )
    parser.add_argument(
        "--mining-dir",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/mining"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/gates/current_meta_manifest.json"),
    )
    parser.add_argument("--pilot-main", type=Path, default=Path("data/official/main.py"))
    parser.add_argument(
        "--candidate-main",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/package/main.py"),
    )
    parser.add_argument(
        "--candidate-deck",
        type=Path,
        default=Path("artifacts/kaggle_submission_54024037_strategy/package/deck.csv"),
    )
    parser.add_argument("--smoke-games", type=int, default=10)
    parser.add_argument("--seed", type=int, default=9101)
    parser.add_argument("--meta-json", type=Path)
    parser.add_argument("--meta-url", default=CURRENT_META_URL)
    parser.add_argument("--no-meta-fetch", action="store_true")
    args = parser.parse_args()
    meta_snapshot = None
    if args.meta_json:
        meta_snapshot = load_json_path_or_url(args.meta_json)
    elif not args.no_meta_fetch and args.meta_url:
        meta_snapshot = load_json_path_or_url(args.meta_url)

    rows = build_current_meta_replay_gates(
        coverage_path=args.coverage,
        replay_dir=args.replay_dir,
        gate_root=args.gate_root,
        mining_dir=args.mining_dir,
        output_manifest=args.output,
        pilot_main=args.pilot_main,
        candidate_main=args.candidate_main,
        candidate_deck=args.candidate_deck,
        smoke_games=args.smoke_games,
        seed=args.seed,
        meta_snapshot=meta_snapshot,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
                "ok": sum(1 for row in rows if row.get("ok")),
                "errors": {row["archetype"]: row["errors"] for row in rows if row.get("errors")},
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
