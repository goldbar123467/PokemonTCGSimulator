from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import json


GENERIC_FLAWS = {"unconverted_decision"}

CARD_NAMES = {
    3: "Water Energy",
    11: "Mist Energy",
    17: "Ignition Energy",
    19: "Telepath Psychic Energy",
    304: "Hop's Snorlax",
    311: "Hop's Cramorant",
    344: "Dreepy",
    345: "Drakloak",
    666: "Cinderace",
    878: "Hop's Phantump",
    879: "Hop's Trevenant",
    1030: "Staryu",
    1031: "Mega Starmie ex",
    1086: "Buddy-Buddy Poffin",
    1092: "Secret Box",
    1097: "Night Stretcher",
    1115: "Hop's Bag",
    1120: "Crushing Hammer",
    1121: "Ultra Ball",
    1122: "Pokegear 3.0",
    1134: "Team Rocket's Transceiver",
    1145: "Mega Signal",
    1152: "Poke Pad",
    1159: "Hero's Cape",
    1171: "Hop's Choice Band",
    1182: "Boss's Orders",
    1189: "Salvatore",
    1197: "Xerosic's Machinations",
    1219: "Team Rocket's Petrel",
    1223: "Harlequin",
    1225: "Hilda",
    1227: "Lillie's Determination",
    1229: "Wally",
    1255: "Postwick",
}

OPTION_TYPES = {
    1: "choose",
    3: "choose card",
    7: "play",
    8: "attach",
    9: "evolve",
    10: "target",
    12: "retreat",
    13: "attack",
    14: "end turn",
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _card_name(card: dict[str, Any] | None) -> str:
    if not isinstance(card, dict):
        return "unknown"
    name = card.get("name") or card.get("Name")
    if name:
        return str(name)
    card_id = card.get("id")
    try:
        return CARD_NAMES.get(int(card_id), f"card {int(card_id)}")
    except (TypeError, ValueError):
        return "unknown"


def _card_short(card: dict[str, Any] | None) -> str:
    if not isinstance(card, dict):
        return "none"
    hp = card.get("hp")
    max_hp = card.get("maxHp")
    hp_text = f" {hp}/{max_hp}HP" if hp is not None and max_hp is not None else ""
    energy_cards = card.get("energyCards")
    if isinstance(energy_cards, list) and energy_cards:
        energies = len(energy_cards)
    else:
        raw_energies = card.get("energies")
        if isinstance(raw_energies, list):
            energies = len(raw_energies)
        elif isinstance(raw_energies, (int, float)):
            energies = int(raw_energies)
        else:
            energies = 0
    energy_text = f" E{energies}" if energies else ""
    tools = card.get("tools") or []
    tool_text = ""
    if isinstance(tools, list) and tools:
        tool_text = " tools=" + ",".join(_card_name(tool) for tool in tools if isinstance(tool, dict))
    return f"{_card_name(card)}{hp_text}{energy_text}{tool_text}"


def _cards(player: dict[str, Any], zone: str) -> list[dict[str, Any]]:
    value = player.get(zone)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _player_snapshot(player: dict[str, Any]) -> str:
    active = ", ".join(_card_short(card) for card in _cards(player, "active")) or "none"
    bench = ", ".join(_card_short(card) for card in _cards(player, "bench")) or "none"
    prize_count = player.get("prize_count", player.get("prizeCount", "?"))
    hand_count = player.get("handCount", len(player.get("hand") or []) if isinstance(player.get("hand"), list) else "?")
    deck_count = player.get("deckCount", player.get("deck_count", "?"))
    return f"active: {active}; bench: {bench}; prizes left: {prize_count}; hand: {hand_count}; deck: {deck_count}"


def _latest_observation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in sorted(rows, key=lambda item: int(item.get("step_index") or -1), reverse=True):
        observation = row.get("observation")
        if isinstance(observation, dict) and isinstance(observation.get("current"), dict):
            return observation
    return {}


def _board_lines(actor: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    observation = _latest_observation(rows)
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    actor_index = int(actor.get("actor_index") or 0)
    opponent_index = int(actor.get("opponent_index") or (1 - actor_index))
    lines = [f"- Step/turn: `{max((int(row.get('step_index') or 0) for row in rows), default=0)}` / `{current.get('turn', '?')}`"]
    if actor_index < len(players) and isinstance(players[actor_index], dict):
        lines.append(f"- Clark Kitchen: {_player_snapshot(players[actor_index])}")
    if opponent_index < len(players) and isinstance(players[opponent_index], dict):
        lines.append(f"- Opponent: {_player_snapshot(players[opponent_index])}")
    return lines


def _option_card(observation: dict[str, Any], option: dict[str, Any]) -> dict[str, Any] | None:
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    area = option.get("area")
    zone = {1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench", 12: "looking"}.get(area)
    player_index = int(option.get("playerIndex", current.get("yourIndex", 0)) or 0)
    index = int(option.get("index") or 0)
    if zone is None or not (0 <= player_index < len(players)):
        return None
    cards = _cards(players[player_index], zone)
    return cards[index] if 0 <= index < len(cards) else None


def _target_card(observation: dict[str, Any], option: dict[str, Any]) -> dict[str, Any] | None:
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    zone = {4: "active", 5: "bench"}.get(option.get("inPlayArea"))
    player_index = int(option.get("playerIndex", current.get("yourIndex", 0)) or 0)
    index = int(option.get("inPlayIndex") or 0)
    if zone is None or not (0 <= player_index < len(players)):
        return None
    cards = _cards(players[player_index], zone)
    return cards[index] if 0 <= index < len(cards) else None


def _describe_option(observation: dict[str, Any], option: dict[str, Any]) -> str:
    option_type = int(option.get("type") or -1)
    verb = OPTION_TYPES.get(option_type, f"type {option_type}")
    if option_type in {7, 9}:
        return f"{verb} {_card_name(_option_card(observation, option))}"
    if option_type == 8:
        return f"attach {_card_name(_option_card(observation, option))} to {_card_short(_target_card(observation, option))}"
    if option_type == 13:
        return f"attack {option.get('attackName') or option.get('attackId', 'unknown')}"
    return verb


def _describe_action(row: dict[str, Any], action: list[Any] | None) -> str:
    observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
    options = row.get("legal_actions") if isinstance(row.get("legal_actions"), list) else []
    if not action:
        return "none"
    described: list[str] = []
    for raw_index in action:
        try:
            option = options[int(raw_index)]
        except (TypeError, ValueError, IndexError):
            described.append(str(raw_index))
            continue
        if isinstance(option, dict):
            described.append(_describe_option(observation, option))
        else:
            described.append(str(raw_index))
    return "; ".join(described)


def _episode_cause(actor: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    matchup = str(actor.get("opponent_archetype") or "unknown")
    actor_arch = str(actor.get("actor_archetype") or "unknown")
    flaws = Counter(tag for row in rows for tag in row.get("flaw_tags", []) if tag not in GENERIC_FLAWS)
    labels = Counter(label for row in rows for label in row.get("pipeline_labels", []))
    setup_text = "setup/bench-development labels were high" if labels.get("setup", 0) + labels.get("bench_develop", 0) else "the labeled windows were low-signal"
    backup_text = "attack-without-backup appeared" if flaws.get("attack_without_backup", 0) else "backup posture was still the central risk"

    if actor_arch == "mega_starmie":
        if matchup == "dragapult_spread":
            return (
                "Dragapult/spread punished the Starmie baseline before it converted Staryu/Mega Starmie setup "
                f"into a protected second attacker; {setup_text}, and {backup_text}."
            )
        if matchup == "mega_starmie":
            return (
                "The mirror loss was a tempo and redundancy failure: the baseline spent too many turns on generic "
                "setup/card selection while the opposing Starmie line converted first or rebuilt cleaner."
            )
        if matchup == "alakazam":
            return (
                "Alakazam reached its control board before Starmie forced a clear prize map; the loss labels point "
                "to setup churn without enough Boss/bridge-removal pressure."
            )
        return (
            "The unknown matchup still showed the baseline Starmie problem: many decisions converted into setup "
            "or card selection, but not into a stable attacker chain and prize-pressure plan."
        )

    if actor_arch == "hop_trevenant":
        if matchup == "dragapult_spread":
            return (
                "Dragapult/spread set up too safely while Hop/Trevenant spent early turns on generic setup/churn "
                "instead of forcing a trap, gust, or KO window on the evolving line."
            )
        if matchup == "lucario":
            return (
                "Lucario punished the deck before the second Trevenant/Snorlax pressure plan stabilized; the fix "
                "needs disruption plus a real backup attacker, not only more setup."
            )
        if matchup == "alakazam":
            return (
                "Alakazam got the Stage-2/control board online while Hop/Trevenant failed to turn trap/control "
                "cards into immediate prize pressure."
            )
    return (
        f"The loss was mostly a conversion failure into `{matchup}`: {setup_text}, "
        "but the selected actions did not turn that work into enough tempo or prizes."
    )


def _top_rows(rows: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    def score(row: dict[str, Any]) -> tuple[int, int]:
        flaws = set(row.get("flaw_tags") or [])
        weight = 0
        if "teacher_preferred_alternative" in flaws:
            weight += 5
        if "attack_without_backup" in flaws:
            weight += 4
        if "active_overattach" in flaws:
            weight += 4
        weight += len(row.get("pipeline_labels") or [])
        return weight, int(row.get("step_index") or 0)

    candidates = [row for row in rows if set(row.get("flaw_tags") or []) - GENERIC_FLAWS or row.get("teacher_agrees") is False]
    if not candidates:
        candidates = rows
    return sorted(candidates, key=score, reverse=True)[:limit]


def _write_episode_scout(output_dir: Path, actor: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    episode_id = int(actor["episode_id"])
    flaw_counts = Counter(tag for row in rows for tag in row.get("flaw_tags", []) if tag not in GENERIC_FLAWS)
    label_counts = Counter(label for row in rows for label in row.get("pipeline_labels", []))
    cause = _episode_cause(actor, rows)
    path = output_dir / f"episode_{episode_id}_scout.md"

    lines = [
        f"# Episode {episode_id} Scout",
        "",
        f"- Created: `{actor.get('create_time', 'unknown')}`",
        (
            f"- Matchup: Clark Kitchen {actor.get('actor_archetype', 'unknown')} vs "
            f"`{actor.get('opponent_team_name', 'unknown')}` (`{actor.get('opponent_archetype', 'unknown')}`)"
        ),
        f"- Result: {actor.get('outcome')} reward `{actor.get('reward')}` to `{actor.get('opponent_reward')}`",
        f"- Replay: `{actor.get('replay_path', 'unknown')}`",
        f"- Decision rows: {len(rows)}",
        "- Highest-signal flaw tags: "
        + (", ".join(f"{key}={value}" for key, value in flaw_counts.most_common()) or "none beyond generic loss tags"),
        "- Main decision labels: " + (", ".join(f"{key}={value}" for key, value in label_counts.most_common()) or "none"),
        "",
        "## Scout Read",
        "",
        cause,
        "",
        "## Final Visible Board Snapshot",
        "",
        *_board_lines(actor, rows),
        "",
        "## Key Decision Windows",
        "",
    ]

    for row in _top_rows(rows):
        observation = row.get("observation") if isinstance(row.get("observation"), dict) else {}
        turn = (observation.get("current") or {}).get("turn", "?") if isinstance(observation.get("current"), dict) else "?"
        lines.extend(
            [
                f"- Step `{row.get('step_index')}`, turn `{turn}`:",
                f"  chosen: {_describe_action(row, row.get('chosen_action'))}",
                f"  teacher/read: {_describe_action(row, row.get('teacher_action'))}",
                (
                    "  labels: "
                    f"selected={row.get('selected_labels', [])}, teacher={row.get('teacher_labels', [])}, "
                    f"penalties={row.get('selected_penalties', [])}, flaws={row.get('flaw_tags', [])}"
                ),
            ]
        )

    lines.extend(["", "Kaggle submission made: no", ""])
    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    episode_summary = {
        "episode_id": episode_id,
        "create_time": actor.get("create_time"),
        "actor_index": actor.get("actor_index"),
        "opponent": actor.get("opponent_team_name"),
        "opponent_archetype": actor.get("opponent_archetype"),
        "decision_rows": len(rows),
        "teacher_preferred": flaw_counts.get("teacher_preferred_alternative", 0),
        "attack_without_backup": flaw_counts.get("attack_without_backup", 0),
        "active_overattach": flaw_counts.get("active_overattach", 0),
        "setup_labels": label_counts.get("setup", 0),
        "bench_develop_labels": label_counts.get("bench_develop", 0),
        "cause": cause,
        "scout_path": str(path.resolve()),
    }
    return path, episode_summary


def _read_loss_trends(dataset_dir: Path) -> dict[str, Any]:
    path = dataset_dir / "loss_trends.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_submission_loss_scouts(
    *,
    dataset_dir: Path,
    output_dir: Path,
    submission_id: int,
    scope: str,
    command: str,
) -> dict[str, Any]:
    actors = _load_jsonl(dataset_dir / "episode_actors.jsonl")
    rows = _load_jsonl(dataset_dir / "decision_labels.jsonl")
    trends = _read_loss_trends(dataset_dir)
    loss_actors = [
        actor
        for actor in actors
        if int(actor.get("submission_id") or 0) == int(submission_id) and actor.get("outcome") == "loss"
    ]
    loss_actors.sort(key=lambda item: str(item.get("create_time") or ""), reverse=True)
    loss_actor_keys = {(int(actor["episode_id"]), int(actor.get("actor_index") or 0)) for actor in loss_actors}
    loss_keys_by_episode: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for key in loss_actor_keys:
        loss_keys_by_episode[key[0]].append(key)

    rows_by_loss_key: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    selected_submission_rows: list[dict[str, Any]] = []
    for row in rows:
        episode_id = int(row.get("episode_id") or 0)
        row_submission = int(row.get("submission_id") or 0)
        if row_submission == int(submission_id):
            selected_submission_rows.append(row)
        if "actor_index" in row or "agent_index" in row:
            actor_index = int(row.get("actor_index", row.get("agent_index")) or 0)
            key = (episode_id, actor_index)
            if key in loss_actor_keys:
                rows_by_loss_key[key].append(row)
        elif episode_id in loss_keys_by_episode:
            for key in loss_keys_by_episode[episode_id]:
                rows_by_loss_key[key].append(row)
                if row not in selected_submission_rows:
                    selected_submission_rows.append(row)

    aggregate_flaws = Counter(
        tag
        for actor in loss_actors
        for row in rows_by_loss_key.get((int(actor.get("episode_id")), int(actor.get("actor_index") or 0)), [])
        for tag in row.get("flaw_tags", [])
        if tag not in GENERIC_FLAWS
    )
    aggregate_labels = Counter(
        label
        for actor in loss_actors
        for row in rows_by_loss_key.get((int(actor.get("episode_id")), int(actor.get("actor_index") or 0)), [])
        for label in row.get("pipeline_labels", [])
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    episode_summaries: list[dict[str, Any]] = []
    for actor in loss_actors:
        episode_id = int(actor["episode_id"])
        key = (episode_id, int(actor.get("actor_index") or 0))
        _path, episode_summary = _write_episode_scout(output_dir, actor, rows_by_loss_key.get(key, []))
        episode_summaries.append(episode_summary)

    public_score = next((actor.get("submission_public_score") for actor in actors if int(actor.get("submission_id") or 0) == int(submission_id)), None)
    summary = {
        "command": command,
        "dataset_dir": str(dataset_dir),
        "input_paths": {
            "episode_actors_jsonl": str(dataset_dir / "episode_actors.jsonl"),
            "decision_labels_jsonl": str(dataset_dir / "decision_labels.jsonl"),
            "loss_trends_json": str(dataset_dir / "loss_trends.json"),
        },
        "scope": scope,
        "submission_id": int(submission_id),
        "public_score": public_score,
        "actor_records": len([actor for actor in actors if int(actor.get("submission_id") or 0) == int(submission_id)]),
        "loss_game_count": len(loss_actors),
        "decision_rows": len(selected_submission_rows),
        "loss_decision_rows": sum(
            len(rows_by_loss_key.get((int(actor.get("episode_id")), int(actor.get("actor_index") or 0)), []))
            for actor in loss_actors
        ),
        "aggregate_flaws": dict(aggregate_flaws),
        "aggregate_labels": dict(aggregate_labels),
        "loss_trends": trends,
        "episodes": episode_summaries,
        "kaggle_submission_made": False,
    }

    summary_json = output_dir / "loss_scout_summary.json"
    _write_json(summary_json, summary)

    lines = [
        f"# Submission {submission_id} Loss Scout Summary",
        "",
        f"- Submission: `{submission_id}`",
        f"- Public score from pulled submission metadata: `{public_score}`",
        f"- Scope: {scope}",
        "- Source: downloaded Kaggle public episode replays plus sanitized decision labels.",
        "- Kaggle submission made: no",
        "",
        "## Losses",
        "",
    ]
    for episode in episode_summaries:
        lines.append(
            f"- `{episode['episode_id']}` {episode.get('create_time')}: loss vs "
            f"{episode.get('opponent')} (`{episode.get('opponent_archetype')}`), actor index {episode.get('actor_index')}"
        )
    lines.extend(
        [
            "",
            "## Pattern Read",
            "",
            _summary_pattern(loss_actors, aggregate_flaws, aggregate_labels),
            "",
            "## Per-Game Causes",
            "",
        ]
    )
    for episode in episode_summaries:
        lines.append(
            f"- `{episode['episode_id']}` vs {episode.get('opponent')} (`{episode.get('opponent_archetype')}`): {episode['cause']}"
        )
    lines.extend(
        [
            "",
            "## Aggregate Signals",
            "",
            "- Flaws excluding generic loss tag: "
            + (", ".join(f"{key}={value}" for key, value in aggregate_flaws.most_common()) or "none"),
            "- Labels: " + (", ".join(f"{key}={value}" for key, value in aggregate_labels.most_common()) or "none"),
            "- Kaggle submission made: no",
            "",
        ]
    )
    (output_dir / "loss_scout_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def _summary_pattern(
    loss_actors: list[dict[str, Any]],
    aggregate_flaws: Counter[str],
    aggregate_labels: Counter[str],
) -> str:
    if not loss_actors:
        return "No losses were present in the selected submission pull."
    actor_arch = str(loss_actors[0].get("actor_archetype") or "unknown")
    matchups = Counter(str(actor.get("opponent_archetype") or "unknown") for actor in loss_actors)
    matchup_text = ", ".join(f"{matchup}={count}" for matchup, count in matchups.most_common())
    if actor_arch == "mega_starmie":
        return (
            f"The latest Starmie pull lost across {matchup_text}. The common signal is not that Starmie never sets up; "
            f"setup/bench labels total {aggregate_labels.get('setup', 0) + aggregate_labels.get('bench_develop', 0)}. "
            "The problem is conversion: it needs a sturdier 4-4 Starmie chain, more rebuild insurance, and clearer "
            "Boss/bridge-removal turns before Dragapult, Alakazam, or mirror opponents stabilize."
        )
    if actor_arch == "hop_trevenant":
        return (
            f"The Hop/Trevenant losses covered {matchup_text}. The repeated failure was setup without enough immediate "
            "disruption or prize pressure, which is why the Petrel/Secret Box rewrite should benchmark hand-control "
            "tempo instead of only adding more generic setup."
        )
    return (
        f"The losses covered {matchup_text}. The repeated signal was conversion failure after setup, with "
        f"teacher alternatives counted {aggregate_flaws.get('teacher_preferred_alternative', 0)} times."
    )
