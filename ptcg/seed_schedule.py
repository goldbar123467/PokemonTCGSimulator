from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def parse_seed_list(value: str | Iterable[int] | None) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        parts = [part.strip() for part in value.split(",")]
        return [int(part) for part in parts if part]
    return [int(seed) for seed in value]


def build_seed_schedule(
    matchups: Iterable[dict[str, Any] | tuple[str, str]],
    *,
    games_per_matchup: int,
    base_seed: int | None = None,
    explicit_seeds: Iterable[int] | str | None = None,
) -> dict[str, Any]:
    if games_per_matchup <= 0:
        raise ValueError("games_per_matchup must be positive")
    seeds = parse_seed_list(explicit_seeds)
    if not seeds and base_seed is None:
        raise ValueError("base_seed or explicit_seeds is required; unseeded benchmark randomness is not allowed")
    if seeds and len(seeds) < games_per_matchup:
        raise ValueError("explicit_seeds must contain at least games_per_matchup values")

    normalized = [_normalize_matchup(matchup) for matchup in matchups]
    games: list[dict[str, Any]] = []
    for matchup_index, matchup in enumerate(normalized):
        matchup_id = _matchup_id(matchup["candidate"], matchup["opponent"])
        for game_index in range(games_per_matchup):
            seed = seeds[game_index] if seeds else _derived_seed(int(base_seed), matchup_id, game_index)
            games.append(
                {
                    "matchup_index": matchup_index,
                    "matchup_id": matchup_id,
                    "candidate": matchup["candidate"],
                    "opponent": matchup["opponent"],
                    "game_index": game_index,
                    "seed": int(seed),
                }
            )

    return {
        "base_seed": int(base_seed) if base_seed is not None else None,
        "explicit_seeds": seeds or None,
        "games_per_matchup": games_per_matchup,
        "matchup_count": len(normalized),
        "scheduled_games": len(games),
        "official_sdk_seed_control": False,
        "crn_available": False,
        "seed_policy": (
            "Seeds are deterministic schedule labels for Python-side agent/runtime RNG. "
            "The official cg SDK has no exported full battle seed hook, so games remain independent samples."
        ),
        "games": games,
    }


def save_seed_schedule(schedule: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schedule, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_matchup(matchup: dict[str, Any] | tuple[str, str]) -> dict[str, str]:
    if isinstance(matchup, tuple):
        candidate, opponent = matchup
    else:
        candidate = matchup.get("candidate")
        opponent = matchup.get("opponent")
    if not candidate or not opponent:
        raise ValueError(f"matchup must include candidate and opponent: {matchup!r}")
    return {"candidate": str(candidate), "opponent": str(opponent)}


def _matchup_id(candidate: str, opponent: str) -> str:
    return f"{_safe_slug(candidate)}__vs__{_safe_slug(opponent)}"


def _safe_slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "item"


def _derived_seed(base_seed: int, matchup_id: str, game_index: int) -> int:
    payload = f"{base_seed}:{matchup_id}:{game_index}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:12], 16) % (2**31 - 1)
