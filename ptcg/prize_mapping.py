from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Iterable, Iterator

from ptcg.replays import UnsafeReplayDirectoryError
from ptcg.replays import _resolve_loader_paths


@dataclass(frozen=True)
class PrizeMapDecision:
    replay_id: str
    step_index: int
    agent_index: int
    opening_turn: int
    deck_profile: str
    matchup_profile: str
    prize_delta: int
    our_prizes_left: int
    opponent_prizes_left: int
    our_attackers: int
    opponent_attackers: int
    our_energy: int
    opponent_energy: int
    our_hand_count: int
    opponent_hand_count: int
    our_deck_count: int
    opponent_deck_count: int
    option_count: int
    chosen_action: str
    option_type: str
    xg_score: float


@dataclass(frozen=True)
class RankedOpening:
    rank: int
    key: str
    games: int
    decisions: int
    avg_xg: float
    avg_prize_delta: float
    avg_energy_delta: float
    avg_attacker_delta: float
    most_common_action: str


def _card_id(card: dict | list | None) -> str:
    if isinstance(card, dict):
        return str(card.get("id", "unknown"))
    if isinstance(card, list) and card and isinstance(card[0], dict):
        return str(card[0].get("id", "unknown"))
    return "none"


def _cards(zone: object) -> list[dict]:
    if not isinstance(zone, list):
        return []
    if zone and all(isinstance(item, dict) for item in zone):
        return list(zone)
    return []


def _energy_count(cards: Iterable[dict]) -> int:
    total = 0
    for card in cards:
        energy_cards = card.get("energyCards")
        if isinstance(energy_cards, list) and energy_cards:
            total += len(energy_cards)
            continue
        energies = card.get("energies")
        if isinstance(energies, list):
            total += len(energies)
        elif isinstance(energies, (int, float)):
            total += int(energies)
    return total


def _board_cards(player: dict) -> list[dict]:
    return _cards(player.get("active")) + _cards(player.get("bench"))


def _deck_profile(player: dict) -> str:
    board = _board_cards(player)
    active = _card_id(player.get("active"))
    bench_ids = sorted(_card_id(card) for card in _cards(player.get("bench")))[:4]
    return "active:" + active + "|bench:" + ",".join(bench_ids)


def _chosen_action(select: dict, action: list[int]) -> tuple[str, str]:
    options = select.get("option") if isinstance(select, dict) else None
    if not isinstance(options, list) or not action:
        return "none", "none"
    index = action[0]
    if not isinstance(index, int) or not 0 <= index < len(options):
        return str(index), "invalid"
    option = options[index]
    if not isinstance(option, dict):
        return str(index), "unknown"
    option_type = str(option.get("type", "unknown"))
    compact = {
        key: option.get(key)
        for key in ("type", "area", "index", "playerIndex", "attack", "target")
        if key in option
    }
    return json.dumps(compact, sort_keys=True, separators=(",", ":")), option_type


def _xg_score(
    *,
    prize_delta: int,
    energy_delta: int,
    attacker_delta: int,
    hand_delta: int,
    deck_delta: int,
    option_count: int,
) -> float:
    # Expected-game proxy: prize map first, then tempo, then flexibility.
    score = 0.0
    score += prize_delta * 1.5
    score += energy_delta * 0.16
    score += attacker_delta * 0.28
    score += hand_delta * 0.035
    score += deck_delta * 0.015
    score += min(option_count, 12) * 0.025
    return round(score, 6)


def iter_prize_map_decisions(
    replay_dir: Path | None = None,
    *,
    replay_paths: Iterable[Path] | None = None,
    max_replays: int | None = None,
    opening_steps: int = 24,
    project_root: Path = Path("."),
    config_path: Path = Path("configs/current_workflow.json"),
) -> Iterator[PrizeMapDecision]:
    replay_count = 0
    for path in _resolve_loader_paths(
        replay_dir=replay_dir,
        replay_paths=replay_paths,
        project_root=project_root,
        config_path=config_path,
    ):
        try:
            episode = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(episode, dict):
            continue
        steps = episode.get("steps")
        if not isinstance(steps, list):
            continue
        replay_id = str(episode.get("info", {}).get("EpisodeId") or path.stem)
        yielded = False
        for step_index, step in enumerate(steps[:opening_steps]):
            if not isinstance(step, list):
                continue
            for agent_index, agent_step in enumerate(step):
                if not isinstance(agent_step, dict):
                    continue
                observation = agent_step.get("observation") or {}
                current = observation.get("current")
                select = observation.get("select")
                action = agent_step.get("action")
                if not isinstance(current, dict) or not isinstance(select, dict):
                    continue
                if not isinstance(action, list) or not action:
                    continue
                options = select.get("option")
                players = current.get("players")
                if not isinstance(options, list) or not isinstance(players, list) or len(players) < 2:
                    continue
                if agent_index >= len(players):
                    continue
                our = players[agent_index]
                opponent = players[1 - agent_index]
                if not isinstance(our, dict) or not isinstance(opponent, dict):
                    continue

                our_prizes_left = len(our.get("prize") or [])
                opponent_prizes_left = len(opponent.get("prize") or [])
                our_board = _board_cards(our)
                opponent_board = _board_cards(opponent)
                our_energy = _energy_count(our_board)
                opponent_energy = _energy_count(opponent_board)
                our_attackers = sum(1 for card in our_board if card.get("hp", 0) > 0)
                opponent_attackers = sum(1 for card in opponent_board if card.get("hp", 0) > 0)
                chosen_action, option_type = _chosen_action(select, action)
                prize_delta = opponent_prizes_left - our_prizes_left
                xg_score = _xg_score(
                    prize_delta=prize_delta,
                    energy_delta=our_energy - opponent_energy,
                    attacker_delta=our_attackers - opponent_attackers,
                    hand_delta=int(our.get("handCount") or 0) - int(opponent.get("handCount") or 0),
                    deck_delta=int(our.get("deckCount") or 0) - int(opponent.get("deckCount") or 0),
                    option_count=len(options),
                )
                yielded = True
                yield PrizeMapDecision(
                    replay_id=replay_id,
                    step_index=step_index,
                    agent_index=agent_index,
                    opening_turn=int(current.get("turn") or 0),
                    deck_profile=_deck_profile(our),
                    matchup_profile=_deck_profile(opponent),
                    prize_delta=prize_delta,
                    our_prizes_left=our_prizes_left,
                    opponent_prizes_left=opponent_prizes_left,
                    our_attackers=our_attackers,
                    opponent_attackers=opponent_attackers,
                    our_energy=our_energy,
                    opponent_energy=opponent_energy,
                    our_hand_count=int(our.get("handCount") or 0),
                    opponent_hand_count=int(opponent.get("handCount") or 0),
                    our_deck_count=int(our.get("deckCount") or 0),
                    opponent_deck_count=int(opponent.get("deckCount") or 0),
                    option_count=len(options),
                    chosen_action=chosen_action,
                    option_type=option_type,
                    xg_score=xg_score,
                )
        if yielded:
            replay_count += 1
            if max_replays is not None and replay_count >= max_replays:
                return


def rank_openings(decisions: Iterable[PrizeMapDecision]) -> list[RankedOpening]:
    grouped: dict[str, list[PrizeMapDecision]] = defaultdict(list)
    for decision in decisions:
        key = f"{decision.deck_profile} vs {decision.matchup_profile}"
        grouped[key].append(decision)

    ranked: list[RankedOpening] = []
    for key, rows in grouped.items():
        games = len({row.replay_id for row in rows})
        decisions_count = len(rows)
        action_counts = Counter(row.chosen_action for row in rows)
        ranked.append(
            RankedOpening(
                rank=0,
                key=key,
                games=games,
                decisions=decisions_count,
                avg_xg=sum(row.xg_score for row in rows) / decisions_count,
                avg_prize_delta=sum(row.prize_delta for row in rows) / decisions_count,
                avg_energy_delta=sum(row.our_energy - row.opponent_energy for row in rows) / decisions_count,
                avg_attacker_delta=sum(row.our_attackers - row.opponent_attackers for row in rows) / decisions_count,
                most_common_action=action_counts.most_common(1)[0][0],
            )
        )
    ranked.sort(key=lambda row: (-row.avg_xg, -row.games, -row.decisions, row.key))
    return [
        RankedOpening(
            rank=index,
            key=row.key,
            games=row.games,
            decisions=row.decisions,
            avg_xg=row.avg_xg,
            avg_prize_delta=row.avg_prize_delta,
            avg_energy_delta=row.avg_energy_delta,
            avg_attacker_delta=row.avg_attacker_delta,
            most_common_action=row.most_common_action,
        )
        for index, row in enumerate(ranked, start=1)
    ]


def write_rankings(path: Path, rankings: Iterable[RankedOpening]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "key",
                "games",
                "decisions",
                "avg_xg",
                "avg_prize_delta",
                "avg_energy_delta",
                "avg_attacker_delta",
                "most_common_action",
            ],
        )
        writer.writeheader()
        for row in rankings:
            writer.writerow(
                {
                    "rank": row.rank,
                    "key": row.key,
                    "games": row.games,
                    "decisions": row.decisions,
                    "avg_xg": f"{row.avg_xg:.6f}",
                    "avg_prize_delta": f"{row.avg_prize_delta:.6f}",
                    "avg_energy_delta": f"{row.avg_energy_delta:.6f}",
                    "avg_attacker_delta": f"{row.avg_attacker_delta:.6f}",
                    "most_common_action": row.most_common_action,
                }
            )
