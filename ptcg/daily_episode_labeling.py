from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

LABEL_TAXONOMY = (
    "setup",
    "draw/search/thin",
    "bench_develop",
    "energy_attach_active",
    "energy_attach_bench_next_attacker",
    "attack_prize_race",
    "gust_target",
    "disruption",
    "retreat_switch",
    "preserve_resources",
    "stall_or_denial",
    "risk_ahead_conservative",
    "risk_behind_high_variance",
    "unclear_or_forced",
)


def read_episode(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a Kaggle episode object")
    return value


def load_leaderboard_scores(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    scores: dict[str, float] = {}
    for row in rows:
        name = str(row.get("teamName") or row.get("TeamName") or row.get("team_name") or "").strip()
        raw_score = row.get("score") or row.get("Score") or row.get("publicScore")
        if not name or raw_score in (None, ""):
            continue
        try:
            scores[name] = float(raw_score)
        except ValueError:
            continue
    return scores


def _winner_team(teams: list[str], rewards: list[Any]) -> str | None:
    numeric = [value for value in rewards if isinstance(value, (int, float))]
    if len(numeric) != len(rewards) or not numeric:
        return None
    best = max(numeric)
    if numeric.count(best) != 1:
        return None
    index = numeric.index(best)
    return teams[index] if index < len(teams) else None


def _iter_decision_steps(episode: dict[str, Any]):
    for step_index, step in enumerate(episode.get("steps") or []):
        if not isinstance(step, list):
            continue
        for agent_index, agent_step in enumerate(step):
            if not isinstance(agent_step, dict):
                continue
            observation = agent_step.get("observation")
            select = observation.get("select") if isinstance(observation, dict) else None
            options = select.get("option") if isinstance(select, dict) else None
            action = agent_step.get("action")
            if not isinstance(observation, dict) or not isinstance(select, dict):
                continue
            if not isinstance(options, list) or not isinstance(action, list):
                continue
            if not options or not action:
                continue
            if not all(isinstance(item, int) and 0 <= item < len(options) for item in action):
                continue
            yield step_index, agent_index, agent_step


def summarize_episode(path: Path, leaderboard_scores: dict[str, float]) -> dict[str, Any]:
    episode = read_episode(path)
    info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
    teams = [str(name) for name in info.get("TeamNames") or []]
    rewards = list(episode.get("rewards") or [])
    scores = [leaderboard_scores.get(team) for team in teams]
    known_scores = [score for score in scores if score is not None]
    winner = _winner_team(teams, rewards)
    decisions = list(_iter_decision_steps(episode))
    active_decision_count = sum(1 for _, _, agent_step in decisions if agent_step.get("status") == "ACTIVE")
    return {
        "file": path.name,
        "path": str(path),
        "episode_id": info.get("EpisodeId") or path.stem,
        "teams": teams,
        "rewards": rewards,
        "winner_team": winner,
        "leaderboard_scores": scores,
        "known_leaderboard_score_sum": sum(known_scores),
        "winner_leaderboard_score": leaderboard_scores.get(winner) if winner else None,
        "steps": len(episode.get("steps") or []),
        "decision_count": len(decisions),
        "active_decision_count": active_decision_count,
        "seed": (episode.get("configuration") or {}).get("seed")
        if isinstance(episode.get("configuration"), dict)
        else None,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def rank_episode_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        summaries,
        key=lambda item: (
            len([score for score in item.get("leaderboard_scores", []) if score is not None]),
            float(item.get("known_leaderboard_score_sum") or 0.0),
            float(item.get("winner_leaderboard_score") or -1.0),
            int(item.get("active_decision_count") or 0),
            int(item.get("steps") or 0),
        ),
        reverse=True,
    )


def _card_label(card: Any) -> str | None:
    if not isinstance(card, dict):
        return None
    card_id = card.get("id")
    name = card.get("name") or card.get("Name")
    if name and isinstance(card_id, int):
        return f"{name}#{card_id}"
    if name:
        return str(name)
    if isinstance(card_id, int):
        return f"card#{card_id}"
    return None


def _area_cards(player: dict[str, Any], area: str, *, limit: int) -> list[str]:
    cards = player.get(area)
    if not isinstance(cards, list):
        return []
    labels = [label for card in cards[:limit] if (label := _card_label(card))]
    if len(cards) > limit:
        labels.append(f"...+{len(cards) - limit}")
    return labels


def _resolve_option_card(option: dict[str, Any], players: list[Any], your_index: int) -> str | None:
    area = option.get("area")
    index = option.get("index")
    player_index = option.get("playerIndex", your_index)
    area_name = {2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    if area_name is None or not isinstance(index, int) or not isinstance(player_index, int):
        return None
    if player_index < 0 or player_index >= len(players) or not isinstance(players[player_index], dict):
        return None
    cards = players[player_index].get(area_name)
    if not isinstance(cards, list) or index < 0 or index >= len(cards):
        return None
    return _card_label(cards[index])


def _option_desc(option: Any, players: list[Any], your_index: int) -> dict[str, Any]:
    if not isinstance(option, dict):
        return {"raw": repr(option)[:200]}
    desc = {
        key: option.get(key)
        for key in ("type", "area", "index", "playerIndex", "number", "attackId", "effect", "damage")
        if key in option
    }
    resolved = _resolve_option_card(option, players, your_index)
    if resolved is not None:
        desc["resolved_card"] = resolved
    return desc


def _board_summary(current: dict[str, Any], teams: list[str]) -> dict[str, Any]:
    players = current.get("players")
    if not isinstance(players, list):
        return {"players": []}
    output = []
    for player_index, player in enumerate(players[:2]):
        if not isinstance(player, dict):
            output.append({})
            continue
        output.append(
            {
                "player_index": player_index,
                "team": teams[player_index] if player_index < len(teams) else f"player_{player_index}",
                "active": _area_cards(player, "active", limit=2),
                "bench": _area_cards(player, "bench", limit=6),
                "hand_count": len(player.get("hand") or []) if isinstance(player.get("hand"), list) else None,
                "deck_count": len(player.get("deck") or []) if isinstance(player.get("deck"), list) else None,
                "discard": _area_cards(player, "discard", limit=8),
                "discard_count": len(player.get("discard") or []) if isinstance(player.get("discard"), list) else None,
                "prize_remaining": len(player.get("prize") or []) if isinstance(player.get("prize"), list) else None,
            }
        )
    return {"players": output}


def _compact_decision(
    *,
    step_index: int,
    agent_index: int,
    agent_step: dict[str, Any],
    teams: list[str],
    rewards: list[Any],
) -> dict[str, Any]:
    observation = agent_step["observation"]
    select = observation["select"]
    options = select.get("option") or []
    action = agent_step.get("action") or []
    current = observation.get("current") if isinstance(observation.get("current"), dict) else {}
    players = current.get("players") if isinstance(current.get("players"), list) else []
    your_index = current.get("yourIndex") if isinstance(current.get("yourIndex"), int) else agent_index
    candidates = []
    for option_index, option in enumerate(options[:12]):
        item = _option_desc(option, players, your_index)
        item["option_index"] = option_index
        item["selected"] = option_index in action
        candidates.append(item)
    return {
        "step_index": step_index,
        "agent_index": agent_index,
        "team": teams[agent_index] if agent_index < len(teams) else f"player_{agent_index}",
        "winner": bool(agent_index < len(rewards) and isinstance(rewards[agent_index], (int, float)) and rewards[agent_index] > 0),
        "turn": current.get("turn"),
        "your_index": your_index,
        "status": agent_step.get("status"),
        "reward": agent_step.get("reward"),
        "select_context": select.get("context"),
        "select_type": select.get("type"),
        "min_count": select.get("minCount"),
        "max_count": select.get("maxCount"),
        "option_count": len(options),
        "action": action,
        "selected_options": [_option_desc(options[index], players, your_index) for index in action],
        "candidate_options_first_12": candidates,
        "board": _board_summary(current, teams),
        "log_tail": (observation.get("logs") or [])[-5:] if isinstance(observation.get("logs"), list) else [],
    }


def write_phase_packets(episode_path: Path, output_dir: Path) -> dict[str, Any]:
    episode = read_episode(episode_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
    teams = [str(name) for name in info.get("TeamNames") or []]
    rewards = list(episode.get("rewards") or [])
    decisions = [
        _compact_decision(
            step_index=step_index,
            agent_index=agent_index,
            agent_step=agent_step,
            teams=teams,
            rewards=rewards,
        )
        for step_index, agent_index, agent_step in _iter_decision_steps(episode)
    ]
    chunks = {
        "opening": decisions[: (len(decisions) + 2) // 3],
        "midgame": decisions[(len(decisions) + 2) // 3 : (2 * len(decisions) + 2) // 3],
        "finish": decisions[(2 * len(decisions) + 2) // 3 :],
    }
    manifest = {
        "source_replay": str(episode_path),
        "episode_id": info.get("EpisodeId") or episode_path.stem,
        "teams": teams,
        "rewards": rewards,
        "winner": _winner_team(teams, rewards),
        "seed": (episode.get("configuration") or {}).get("seed")
        if isinstance(episode.get("configuration"), dict)
        else None,
        "sha256": hashlib.sha256(episode_path.read_bytes()).hexdigest(),
        "decision_count": len(decisions),
        "phase_packets": {},
        "label_taxonomy": list(LABEL_TAXONOMY),
    }
    for phase, items in chunks.items():
        packet = {
            "phase": phase,
            "source_replay": str(episode_path),
            "episode_id": manifest["episode_id"],
            "teams": teams,
            "rewards": rewards,
            "winner": manifest["winner"],
            "decision_count": len(items),
            "decisions": items,
            "label_taxonomy": list(LABEL_TAXONOMY),
        }
        packet_path = output_dir / f"{episode_path.stem}_{phase}.json"
        packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        manifest["phase_packets"][phase] = str(packet_path)
    manifest_path = output_dir / f"{episode_path.stem}_manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def consolidate_label_files(
    *,
    packet_manifest: dict[str, Any],
    label_files: dict[str, Path],
    output_path: Path,
) -> dict[str, Any]:
    taxonomy = set(packet_manifest.get("label_taxonomy") or LABEL_TAXONOMY)
    required = {"step_index", "agent_index", "team", "intent_label", "why", "teacher_rule", "confidence"}
    errors: list[str] = []
    phase_reports = []
    key_decisions = []
    teacher_rules = []
    combined = Counter()
    for phase, label_path in label_files.items():
        labels = json.loads(Path(label_path).read_text(encoding="utf-8"))
        packet_path = packet_manifest.get("phase_packets", {}).get(phase)
        packet = json.loads(Path(packet_path).read_text(encoding="utf-8")) if packet_path else {}
        counts = labels.get("label_counts") or {}
        if not isinstance(counts, dict):
            errors.append(f"{phase}: label_counts is not an object")
            counts = {}
        for label in counts:
            if label not in taxonomy:
                errors.append(f"{phase}: unknown count label {label}")
        total = sum(int(value) for value in counts.values() if isinstance(value, int))
        expected = int(packet.get("decision_count") or 0)
        if expected and total != expected:
            errors.append(f"{phase}: label_counts total {total} != packet decision_count {expected}")
        for index, item in enumerate(labels.get("key_decisions") or []):
            missing = required - set(item)
            if missing:
                errors.append(f"{phase}: key_decisions[{index}] missing {sorted(missing)}")
            if item.get("intent_label") not in taxonomy:
                errors.append(f"{phase}: key_decisions[{index}] unknown intent_label {item.get('intent_label')}")
            confidence = item.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                errors.append(f"{phase}: key_decisions[{index}] invalid confidence {confidence}")
            merged = dict(item)
            merged["phase"] = phase
            key_decisions.append(merged)
        for rule in labels.get("teacher_rules") or []:
            if isinstance(rule, str) and rule not in teacher_rules:
                teacher_rules.append(rule)
        combined.update({label: int(value) for label, value in counts.items() if isinstance(value, int)})
        phase_reports.append(
            {
                "phase": phase,
                "label_file": str(label_path),
                "source_packet": packet_path,
                "decision_count": expected,
                "key_decision_count": len(labels.get("key_decisions") or []),
                "label_counts": counts,
                "summary": labels.get("summary", ""),
                "sha256": hashlib.sha256(Path(label_path).read_bytes()).hexdigest(),
            }
        )
    if errors:
        raise ValueError("; ".join(errors))
    report = {
        "source_replay": packet_manifest.get("source_replay"),
        "episode_id": packet_manifest.get("episode_id"),
        "teams": packet_manifest.get("teams"),
        "winner": packet_manifest.get("winner"),
        "packet_manifest": packet_manifest.get("manifest_path"),
        "phase_reports": phase_reports,
        "combined_label_counts": dict(sorted(combined.items())),
        "key_decision_count": len(key_decisions),
        "key_decisions": sorted(key_decisions, key=lambda item: (int(item.get("step_index", 0)), int(item.get("agent_index", 0)))),
        "teacher_rules": teacher_rules,
        "validation": {
            "passed": True,
            "errors": [],
            "required_key_decision_fields": sorted(required),
            "taxonomy": sorted(taxonomy),
        },
        "kaggle_submission_made": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return report
