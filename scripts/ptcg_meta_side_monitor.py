from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any


KNOWN_ARCHETYPE_TERMS = (
    "Lucario",
    "Riolu",
    "Dragapult",
    "Dreepy",
    "Drakloak",
    "Starmie",
    "Froslass",
    "Trevenant",
    "Charizard",
    "Alakazam",
)

LUCARIO_IDS = {673, 674, 675, 676, 677, 678}
OPENING_DECISION_LIMIT = 12
DECK_RANKING_PRIOR_GAMES = 6


@dataclass
class PlayerTrack:
    name: str
    deck: tuple[int, ...] = ()
    card_names: dict[int, str] = field(default_factory=dict)
    observed_ids: Counter[int] = field(default_factory=Counter)
    prize_states: list[tuple[int, int, int]] = field(default_factory=list)
    opening_actions: list[str] = field(default_factory=list)
    final_prizes_taken: int = 0
    game_score: float = 0.5
    archetype: str = "unknown"
    deck_hash: str = ""


@dataclass
class ReplayAnalysis:
    replay_id: str
    source: str
    players: tuple[PlayerTrack, PlayerTrack]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def deck_hash(deck: tuple[int, ...]) -> str:
    if not deck:
        return "no-deck"
    body = ",".join(str(card_id) for card_id in deck)
    return hashlib.blake2b(body.encode("ascii"), digest_size=6).hexdigest()


def card_id(value: Any) -> int | None:
    if isinstance(value, dict) and isinstance(value.get("id"), int):
        return value["id"]
    return None


def remember_card_names(track: PlayerTrack, cards: Any) -> None:
    if not isinstance(cards, list):
        return
    for item in cards:
        if not isinstance(item, dict):
            continue
        cid = card_id(item)
        name = item.get("name")
        if cid is not None and isinstance(name, str) and name:
            track.card_names[cid] = name


def board_cards(player: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for area in ("active", "bench", "discard"):
        area_cards = player.get(area)
        if isinstance(area_cards, list):
            cards.extend(item for item in area_cards if isinstance(item, dict))
    return cards


def visible_prize_count(player: dict[str, Any]) -> int:
    prize = player.get("prize")
    return len(prize) if isinstance(prize, list) else 0


def extract_initial_decks(steps: Any) -> dict[int, tuple[int, ...]]:
    decks: dict[int, tuple[int, ...]] = {}
    if not isinstance(steps, list):
        return decks
    for step in steps[:5]:
        if not isinstance(step, list):
            continue
        for agent_index, agent_step in enumerate(step):
            if not isinstance(agent_step, dict):
                continue
            action = agent_step.get("action")
            if (
                isinstance(action, list)
                and len(action) >= 40
                and all(isinstance(item, int) for item in action)
            ):
                decks[agent_index] = tuple(action)
    return decks


def select_option_label(select: dict[str, Any], action: Any, players: list[dict[str, Any]], your_index: int) -> str:
    options = select.get("option")
    if not isinstance(options, list) or not isinstance(action, list):
        return "unavailable"

    labels: list[str] = []
    for raw_index in action[:3]:
        if not isinstance(raw_index, int) or raw_index < 0 or raw_index >= len(options):
            continue
        option = options[raw_index]
        if not isinstance(option, dict):
            labels.append(f"option:{raw_index}")
            continue
        parts = [f"opt_type={option.get('type', '?')}"]
        for key in ("attackId", "number"):
            if key in option:
                parts.append(f"{key}={option[key]}")
        resolved = resolve_option_card(option, players, your_index)
        if resolved is not None:
            parts.append(f"card={resolved}")
        labels.append("/".join(parts))
    if not labels:
        return "empty-action"
    context = select.get("context", "?")
    select_type = select.get("type", "?")
    return f"context={context};select={select_type};" + "|".join(labels)


def resolve_option_card(option: dict[str, Any], players: list[dict[str, Any]], your_index: int) -> int | None:
    area = option.get("area")
    index = option.get("index")
    player_index = option.get("playerIndex", your_index)
    if not isinstance(index, int) or not isinstance(player_index, int):
        return None
    if player_index < 0 or player_index >= len(players):
        return None
    player = players[player_index]
    area_name = {2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    if area_name is None:
        return None
    cards = player.get(area_name)
    if not isinstance(cards, list) or index < 0 or index >= len(cards):
        return None
    return card_id(cards[index])


def archetype_label(track: PlayerTrack) -> str:
    ids = Counter(track.deck) if track.deck else track.observed_ids
    names = " ".join(track.card_names.values())
    for term in KNOWN_ARCHETYPE_TERMS:
        if term.lower() in names.lower():
            if term in {"Riolu"}:
                return "Mega Lucario"
            if term in {"Dreepy", "Drakloak"}:
                return "Dragapult"
            return term
    if sum(ids.get(card_id_, 0) for card_id_ in LUCARIO_IDS) >= 10:
        return "Mega Lucario"
    top_pokemon = [
        str(card_id_)
        for card_id_, count in ids.most_common()
        if count >= 2 and card_id_ > 20
    ][:4]
    return "Deck " + "-".join(top_pokemon) if top_pokemon else "unknown"


def analyze_replay(path: Path) -> ReplayAnalysis | None:
    episode = read_json(path)
    if episode is None or not isinstance(episode.get("steps"), list):
        return None

    info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
    names = info.get("TeamNames") if isinstance(info.get("TeamNames"), list) else []
    replay_id = str(info.get("EpisodeId") or episode.get("id") or path.stem)
    tracks = (
        PlayerTrack(str(names[0]) if len(names) > 0 else "player_0"),
        PlayerTrack(str(names[1]) if len(names) > 1 else "player_1"),
    )

    for agent_index, deck in extract_initial_decks(episode["steps"]).items():
        if 0 <= agent_index <= 1:
            tracks[agent_index].deck = deck
            tracks[agent_index].deck_hash = deck_hash(deck)
            tracks[agent_index].observed_ids.update(deck)

    last_prizes: tuple[int, int] | None = None
    seen_opening = [0, 0]
    for step_index, step in enumerate(episode["steps"]):
        if not isinstance(step, list):
            continue
        step_state_recorded = False
        for agent_index, agent_step in enumerate(step):
            if not isinstance(agent_step, dict):
                continue
            observation = agent_step.get("observation")
            if not isinstance(observation, dict):
                continue
            current = observation.get("current")
            if not isinstance(current, dict):
                continue
            players = current.get("players")
            if not isinstance(players, list) or len(players) < 2:
                continue

            for player_index in (0, 1):
                if not isinstance(players[player_index], dict):
                    continue
                player = players[player_index]
                remember_card_names(tracks[player_index], player.get("hand"))
                remember_card_names(tracks[player_index], player.get("deck"))
                remember_card_names(tracks[player_index], player.get("discard"))
                remember_card_names(tracks[player_index], player.get("active"))
                remember_card_names(tracks[player_index], player.get("bench"))
                for card in board_cards(player):
                    cid = card_id(card)
                    if cid is not None:
                        tracks[player_index].observed_ids[cid] += 1

            prizes = (
                visible_prize_count(players[0]),
                visible_prize_count(players[1]),
            )
            if not step_state_recorded and prizes != last_prizes and max(prizes) <= 6:
                turn = int(current.get("turn") or 0)
                for player_index, prize_left in enumerate(prizes):
                    taken = max(0, 6 - prize_left)
                    diff = taken - max(0, 6 - prizes[1 - player_index])
                    tracks[player_index].prize_states.append((turn, taken, diff))
                    tracks[player_index].final_prizes_taken = taken
                last_prizes = prizes
                step_state_recorded = True

            your_index = current.get("yourIndex")
            if (
                isinstance(your_index, int)
                and 0 <= your_index <= 1
                and seen_opening[your_index] < OPENING_DECISION_LIMIT
                and int(current.get("turn") or 0) <= 4
            ):
                select = observation.get("select")
                action = agent_step.get("action")
                if isinstance(select, dict):
                    label = select_option_label(select, action, players, your_index)
                    tracks[your_index].opening_actions.append(label)
                    seen_opening[your_index] += 1

    rewards = episode.get("rewards")
    if isinstance(rewards, list) and len(rewards) >= 2:
        for player_index, reward in enumerate(rewards[:2]):
            if isinstance(reward, (int, float)):
                tracks[player_index].game_score = 1.0 if reward > 0 else 0.0 if reward < 0 else 0.5

    for track in tracks:
        if not track.deck_hash:
            track.deck_hash = deck_hash(track.deck)
        track.archetype = archetype_label(track)

    return ReplayAnalysis(replay_id=replay_id, source=str(path), players=tracks)


def opening_key(track: PlayerTrack) -> str:
    if not track.opening_actions:
        return "no-opening-actions"
    return " > ".join(track.opening_actions[:OPENING_DECISION_LIMIT])


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def adjusted_mean(values: list[float], *, prior_mean: float, prior_games: int) -> float:
    return (sum(values) + prior_mean * prior_games) / (len(values) + prior_games) if values else prior_mean


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_reports(analyses: list[ReplayAnalysis], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    matchup: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"games": 0, "score": [], "prizes": [], "race_states": Counter()}
    )
    deck_matchup: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"games": 0, "score": [], "prizes": [], "archetypes": Counter()}
    )
    deck_strength: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"games": 0, "score": [], "prizes": [], "archetypes": Counter(), "opponents": Counter()}
    )
    opening: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"games": 0, "score": [], "prizes": [], "examples": []}
    )
    deck_rows: list[dict[str, Any]] = []

    for replay in analyses:
        for player_index, track in enumerate(replay.players):
            opponent = replay.players[1 - player_index]
            key = (track.archetype, opponent.archetype)
            item = matchup[key]
            item["games"] += 1
            item["score"].append(track.game_score)
            item["prizes"].append(float(track.final_prizes_taken))
            for turn, taken, diff in track.prize_states:
                item["race_states"][(turn, taken, diff)] += 1

            deck_key = f"{track.deck_hash}:{track.archetype}"
            opponent_deck_key = f"{opponent.deck_hash}:{opponent.archetype}"
            deck_item = deck_matchup[(deck_key, opponent_deck_key)]
            deck_item["games"] += 1
            deck_item["score"].append(track.game_score)
            deck_item["prizes"].append(float(track.final_prizes_taken))
            deck_item["archetypes"][track.archetype] += 1

            strength = deck_strength[deck_key]
            strength["games"] += 1
            strength["score"].append(track.game_score)
            strength["prizes"].append(float(track.final_prizes_taken))
            strength["archetypes"][track.archetype] += 1
            strength["opponents"][opponent_deck_key] += 1

            open_key = (track.archetype, opponent.archetype, opening_key(track))
            opened = opening[open_key]
            opened["games"] += 1
            opened["score"].append(track.game_score)
            opened["prizes"].append(float(track.final_prizes_taken))
            if len(opened["examples"]) < 3:
                opened["examples"].append(replay.replay_id)

            deck_rows.append(
                {
                    "replay_id": replay.replay_id,
                    "player_index": player_index,
                    "player_name": track.name,
                    "archetype": track.archetype,
                    "deck_hash": track.deck_hash,
                    "top_ids": " ".join(f"{cid}:{count}" for cid, count in Counter(track.deck or ()).most_common(8)),
                    "known_names": " | ".join(sorted(set(track.card_names.values()))[:12]),
                }
            )

    deck_matchup_rows: list[dict[str, Any]] = []
    for (deck_key, opponent_deck_key), item in deck_matchup.items():
        deck_matchup_rows.append(
            {
                "deck_key": deck_key,
                "opponent_deck_key": opponent_deck_key,
                "player_games": item["games"],
                "x_game_score": f"{mean(item['score']):.4f}",
                "x_prizes_taken": f"{mean(item['prizes']):.4f}",
            }
        )
    deck_matchup_rows.sort(
        key=lambda row: (
            -float(row["x_game_score"]),
            -float(row["x_prizes_taken"]),
            -int(row["player_games"]),
            row["deck_key"],
        )
    )

    deck_strength_rows: list[dict[str, Any]] = []
    for deck_key, item in deck_strength.items():
        games = int(item["games"])
        raw_game_score = mean(item["score"])
        raw_prizes = mean(item["prizes"])
        adjusted_game_score = adjusted_mean(
            item["score"],
            prior_mean=0.5,
            prior_games=DECK_RANKING_PRIOR_GAMES,
        )
        adjusted_prizes = adjusted_mean(
            item["prizes"],
            prior_mean=3.0,
            prior_games=DECK_RANKING_PRIOR_GAMES,
        )
        deck_strength_rows.append(
            {
                "deck_key": deck_key,
                "primary_archetype": item["archetypes"].most_common(1)[0][0],
                "player_games": games,
                "opponent_decks_seen": len(item["opponents"]),
                "x_game_score": f"{raw_game_score:.4f}",
                "x_prizes_taken": f"{raw_prizes:.4f}",
                "adjusted_x_game_score": f"{adjusted_game_score:.4f}",
                "adjusted_x_prizes_taken": f"{adjusted_prizes:.4f}",
                "confidence_games": min(games, 25),
            }
        )
    deck_strength_rows.sort(
        key=lambda row: (
            -float(row["adjusted_x_game_score"]),
            -float(row["adjusted_x_prizes_taken"]),
            -int(row["confidence_games"]),
            row["deck_key"],
        )
    )
    for rank, row in enumerate(deck_strength_rows, start=1):
        row["rank"] = rank

    matchup_rows: list[dict[str, Any]] = []
    race_rows: list[dict[str, Any]] = []
    for (archetype, opponent), item in sorted(matchup.items()):
        matchup_rows.append(
            {
                "archetype": archetype,
                "opponent_archetype": opponent,
                "player_games": item["games"],
                "x_game_score": f"{mean(item['score']):.4f}",
                "x_prizes_taken": f"{mean(item['prizes']):.4f}",
            }
        )
        for (turn, taken, diff), count in item["race_states"].most_common():
            race_rows.append(
                {
                    "archetype": archetype,
                    "opponent_archetype": opponent,
                    "turn": turn,
                    "prizes_taken": taken,
                    "prize_diff": diff,
                    "state_count": count,
                }
            )

    opening_rows: list[dict[str, Any]] = []
    for (archetype, opponent, tree), item in opening.items():
        games = item["games"]
        opening_rows.append(
            {
                "archetype": archetype,
                "opponent_archetype": opponent,
                "opening_tree": tree,
                "player_games": games,
                "x_game_score": f"{mean(item['score']):.4f}",
                "x_prizes_taken": f"{mean(item['prizes']):.4f}",
                "examples": " ".join(item["examples"]),
            }
        )
    opening_rows.sort(
        key=lambda row: (
            -float(row["x_game_score"]),
            -float(row["x_prizes_taken"]),
            -int(row["player_games"]),
            row["archetype"],
        )
    )

    write_csv(
        output_dir / "matchup_summary.csv",
        ["archetype", "opponent_archetype", "player_games", "x_game_score", "x_prizes_taken"],
        matchup_rows,
    )
    write_csv(
        output_dir / "prize_race_states.csv",
        ["archetype", "opponent_archetype", "turn", "prizes_taken", "prize_diff", "state_count"],
        race_rows,
    )
    write_csv(
        output_dir / "opening_tree_rankings.csv",
        [
            "archetype",
            "opponent_archetype",
            "opening_tree",
            "player_games",
            "x_game_score",
            "x_prizes_taken",
            "examples",
        ],
        opening_rows,
    )
    write_csv(
        output_dir / "deck_matchup_matrix.csv",
        ["deck_key", "opponent_deck_key", "player_games", "x_game_score", "x_prizes_taken"],
        deck_matchup_rows,
    )
    write_csv(
        output_dir / "deck_rankings.csv",
        [
            "rank",
            "deck_key",
            "primary_archetype",
            "player_games",
            "opponent_decks_seen",
            "x_game_score",
            "x_prizes_taken",
            "adjusted_x_game_score",
            "adjusted_x_prizes_taken",
            "confidence_games",
        ],
        deck_strength_rows,
    )
    write_csv(
        output_dir / "deck_fingerprints.csv",
        ["replay_id", "player_index", "player_name", "archetype", "deck_hash", "top_ids", "known_names"],
        deck_rows,
    )

    summary = {
        "generated_at": utc_now(),
        "replays_analyzed": len(analyses),
        "player_games": len(analyses) * 2,
        "outputs": {
            "matchup_summary": str(output_dir / "matchup_summary.csv"),
            "prize_race_states": str(output_dir / "prize_race_states.csv"),
            "opening_tree_rankings": str(output_dir / "opening_tree_rankings.csv"),
            "deck_matchup_matrix": str(output_dir / "deck_matchup_matrix.csv"),
            "deck_rankings": str(output_dir / "deck_rankings.csv"),
            "deck_fingerprints": str(output_dir / "deck_fingerprints.csv"),
        },
        "deck_keys_ranked": len(deck_strength_rows),
        "deck_matchups_ranked": len(deck_matchup_rows),
        "legal_scope": "public replay JSON, public pulled code metadata, local artifacts only; no Kaggle submission",
    }
    (output_dir / "latest_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def scan_once(args: argparse.Namespace, logger: logging.Logger) -> dict[str, Any]:
    replay_paths = sorted(args.replay_dir.glob("*.json"))
    if args.max_replays:
        replay_paths = replay_paths[: args.max_replays]

    analyses: list[ReplayAnalysis] = []
    logger.info("scan_start replays=%s replay_dir=%s", len(replay_paths), args.replay_dir)
    for index, path in enumerate(replay_paths, start=1):
        analysis = analyze_replay(path)
        if analysis is not None:
            analyses.append(analysis)
        if index == 1 or index % args.heartbeat_every == 0 or index == len(replay_paths):
            logger.info("heartbeat scanned=%s/%s usable=%s last=%s", index, len(replay_paths), len(analyses), path.name)

    summary = build_reports(analyses, args.output_dir)
    logger.info("scan_done replays_analyzed=%s output_dir=%s", summary["replays_analyzed"], args.output_dir)
    return summary


def configure_logging(output_dir: Path) -> logging.Logger:
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ptcg_meta_side_monitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(output_dir / "monitor.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Side monitor for public PTCG replay prize-race states and opening-tree xG rankings."
    )
    parser.add_argument("--replay-dir", type=Path, default=Path("data/Pokemon-Replays-Public"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/meta_monitor"))
    parser.add_argument("--max-replays", type=int, default=0, help="0 means all replay JSON files.")
    parser.add_argument("--interval-seconds", type=float, default=0.0, help="Run continuously when greater than 0.")
    parser.add_argument("--heartbeat-every", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.heartbeat_every <= 0:
        args.heartbeat_every = 10
    logger = configure_logging(args.output_dir)
    logger.info("monitor_start interval_seconds=%s legal_scope=public_observable_local_only", args.interval_seconds)

    while True:
        scan_once(args, logger)
        if args.interval_seconds <= 0:
            break
        logger.info("sleep seconds=%s", args.interval_seconds)
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
