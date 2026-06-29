from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


COMPARISON_SLUG_PREFIXES = (
    "mega-lucario-ex-riolu",
    "hop-s-phantump-hop-s-trevenant",
    "abra-alakazam",
    "dragapult-ex-dreepy",
    "team-rocket-s-petrel-team-rocket-s-transceiver",
    "ignition-energy-mega-starmie-ex",
)


def _lower(value: object) -> str:
    return str(value or "").lower()


def _meta_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("archetype") or "")


def _meta_slug(item: dict[str, Any]) -> str:
    return str(item.get("slug") or "")


def _rate(item: dict[str, Any]) -> float | None:
    value = item.get("winRate")
    if isinstance(value, (int, float)):
        return float(value)
    wins = item.get("wins")
    losses = item.get("losses")
    if isinstance(wins, (int, float)) and isinstance(losses, (int, float)) and wins + losses:
        return float(wins) / float(wins + losses)
    return None


def _percent(value: float | None) -> str:
    return "unknown" if value is None else f"{value * 100:.1f}%"


def _leaderboard_dict(entry: Any) -> dict[str, Any]:
    if is_dataclass(entry):
        return asdict(entry)
    return dict(entry)


def _find_lucario_meta(meta_items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    for item in meta_items:
        name = _lower(_meta_name(item))
        slug = _lower(_meta_slug(item))
        if "lucario" in name or "lucario" in slug:
            return dict(item)
    return {}


def _comparison_rows(meta_items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_prefix: dict[str, dict[str, Any]] = {}
    for item in meta_items:
        name = _meta_name(item)
        slug = _meta_slug(item)
        lowered_slug = _lower(slug)
        prefix = next(
            (candidate for candidate in COMPARISON_SLUG_PREFIXES if lowered_slug.startswith(candidate)),
            None,
        )
        if prefix is None:
            continue
        row = {
            "name": name,
            "slug": slug,
            "appearances": int(item.get("appearances") or item.get("decklists") or 0),
            "wins": int(item.get("wins") or 0),
            "losses": int(item.get("losses") or 0),
            "win_rate": _rate(item),
            "meta_share": float(item.get("metaShare") or 0.0),
        }
        if row["appearances"] > rows_by_prefix.get(prefix, {}).get("appearances", -1):
            rows_by_prefix[prefix] = row
    rows = list(rows_by_prefix.values())
    return sorted(rows, key=lambda row: row["win_rate"] or 0.0, reverse=True)


def _leaderboard_by_member(leaderboard_entries: Iterable[Any]) -> dict[str, dict[str, Any]]:
    by_member: dict[str, dict[str, Any]] = {}
    for entry in leaderboard_entries:
        row = _leaderboard_dict(entry)
        for member in row.get("members") or ():
            by_member[_lower(member)] = row
    return by_member


def _is_lucario_public_row(row: dict[str, Any]) -> bool:
    tags = [_lower(tag) for tag in row.get("tags") or ()]
    fields = " ".join(
        [
            _lower(row.get("ref")),
            _lower(row.get("title")),
            _lower(row.get("archetype")),
            " ".join(tags),
        ]
    )
    return "lucario" in fields


def _public_lucario_agents(
    public_manifest: Iterable[dict[str, Any]],
    leaderboard_entries: Iterable[Any],
) -> list[dict[str, Any]]:
    by_member = _leaderboard_by_member(leaderboard_entries)
    agents: list[dict[str, Any]] = []
    for row in public_manifest:
        if not _is_lucario_public_row(row):
            continue
        author = str(row.get("ref") or "").split("/", 1)[0]
        leaderboard = by_member.get(_lower(author))
        smoke = row.get("smoke") if isinstance(row.get("smoke"), dict) else {}
        agent = {
            "ref": row.get("ref"),
            "title": row.get("title"),
            "author": author,
            "archetype": row.get("archetype"),
            "tags": list(row.get("tags") or []),
            "classification_evidence": list(row.get("evidence") or []),
            "public_source_url": row.get("source_url"),
            "smoke_ok": bool(row.get("ok")),
            "smoke_finished": int(smoke.get("finished") or 0),
            "smoke_errors": list(smoke.get("errors") or []),
            "leaderboard_rank": None,
            "leaderboard_score": None,
            "leaderboard_team": None,
            "leaderboard_last_submission_date": None,
            "replay_derived_win_rate": None,
            "uncertainty": (
                "Leaderboard row is matched by public notebook author. "
                "It does not prove the current leaderboard submission is exactly this public notebook."
            ),
        }
        if leaderboard:
            agent.update(
                {
                    "leaderboard_rank": int(leaderboard["rank"]),
                    "leaderboard_score": float(leaderboard["score"]),
                    "leaderboard_team": leaderboard["team_name"],
                    "leaderboard_last_submission_date": leaderboard["last_submission_date"],
                }
            )
        agents.append(agent)
    return sorted(
        agents,
        key=lambda agent: (
            agent["leaderboard_rank"] is None,
            agent["leaderboard_rank"] or 10**9,
            str(agent["ref"]),
        ),
    )


def _clark_lucario_evidence(coverage: dict[str, Any] | None) -> dict[str, Any]:
    if not coverage:
        return {}
    table = coverage.get("coverage_table") or []
    row = next((item for item in table if item.get("archetype") == "lucario_mirror"), {})
    clark_wins = int(row.get("clark_wins") or 0)
    clark_losses = int(row.get("clark_losses") or 0)
    games = int(coverage.get("coverage_counts", {}).get("lucario_mirror") or clark_wins + clark_losses)
    return {
        "lucario_mirror": {
            "games": games,
            "clark_wins": clark_wins,
            "clark_losses": clark_losses,
            "opponent_wins": clark_losses,
            "opponent_win_rate_vs_clark": (clark_losses / games) if games else None,
            "scope": "Clark Kitchen ladder replay slice only; not a public field-wide Lucario ceiling.",
        }
    }


def _verdict(lucario: dict[str, Any], public_agents: list[dict[str, Any]]) -> dict[str, Any]:
    win_rate = lucario.get("win_rate")
    appearances = int(lucario.get("appearances") or 0)
    meaningful = appearances >= 50
    best_rank = min(
        (agent["leaderboard_rank"] for agent in public_agents if agent.get("leaderboard_rank") is not None),
        default=None,
    )
    if isinstance(win_rate, float) and meaningful and win_rate > 0.52:
        track = "lucario_has_headroom_patch_first_then_scale"
        summary = "Lucario aggregate public performance is above the 52% headroom threshold."
    elif isinstance(win_rate, float) and meaningful and win_rate < 0.48:
        track = "flag_deck_track_pivot_before_more_tuning"
        summary = "Lucario aggregate public performance is below 48%; check for a deck-track pivot before more tuning."
    else:
        track = "ambiguous_patch_worst_gate_then_rerun_audit"
        summary = "Lucario ceiling evidence is ambiguous or too small."
    return {
        "track_selection": track,
        "summary": summary,
        "thresholds": {
            "above_52_percent": "patch the champion first and keep all six gates visible",
            "below_48_percent": "flag deck-track pivot before more tuning",
            "between_or_small_sample": "patch worst gate, submit only with approval, collect 50+ ladder games, rerun audit",
        },
        "best_known_public_lucario_leaderboard_rank": best_rank,
        "limitations": [
            "The daily meta API provides archetype aggregate win rate, not per-agent Lucario win rate.",
            "Public notebook author leaderboard matches are attribution evidence, not proof of the exact submitted code.",
        ],
    }


def build_audit(
    *,
    meta_items: Iterable[dict[str, Any]],
    leaderboard_entries: Iterable[Any],
    public_manifest: Iterable[dict[str, Any]],
    coverage: dict[str, Any] | None,
    meta_snapshot: dict[str, Any],
) -> dict[str, Any]:
    meta_items = [dict(item) for item in meta_items]
    lucario_meta = _find_lucario_meta(meta_items)
    lucario = {
        "name": _meta_name(lucario_meta),
        "slug": _meta_slug(lucario_meta),
        "appearances": int(lucario_meta.get("appearances") or 0),
        "wins": int(lucario_meta.get("wins") or 0),
        "losses": int(lucario_meta.get("losses") or 0),
        "win_rate": _rate(lucario_meta),
        "meta_share": float(lucario_meta.get("metaShare") or 0.0),
    }
    public_agents = _public_lucario_agents(public_manifest, leaderboard_entries)
    return {
        "meta_snapshot": meta_snapshot,
        "lucario": lucario,
        "public_lucario_agents": public_agents,
        "comparison_archetypes": _comparison_rows(meta_items),
        "clark_replay_evidence": _clark_lucario_evidence(coverage),
        "verdict": _verdict(lucario, public_agents),
        "legal_scope": "public leaderboard, public meta API, public notebooks, local public replay artifacts only",
        "kaggle_submission_made": False,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    lucario = audit["lucario"]
    snapshot = audit["meta_snapshot"]
    lines = [
        "# Lucario Ceiling Audit",
        "",
        "## Snapshot",
        "",
        f"- Meta date: {snapshot.get('date')} (latest: {snapshot.get('latestDate')}, redirected: {snapshot.get('redirected')})",
        f"- Total decks: {snapshot.get('totalDecks')}",
        f"- Dataset: {((snapshot.get('source') or {}).get('datasetUrl') or 'unknown')}",
        "",
        "## Lucario Field Evidence",
        "",
        f"- Archetype: {lucario.get('name')} ({lucario.get('slug')})",
        f"- Appearances: {lucario.get('appearances')}",
        f"- Record: {lucario.get('wins')}-{lucario.get('losses')}",
        f"- Win rate: {_percent(lucario.get('win_rate'))}",
        f"- Meta share: {_percent(lucario.get('meta_share'))}",
        "",
        "## Public Lucario Agents Found",
        "",
    ]
    agents = audit.get("public_lucario_agents") or []
    if not agents:
        lines.append("- None found in the local public manifest.")
    for agent in agents:
        rank = agent.get("leaderboard_rank") or "unknown"
        score = agent.get("leaderboard_score") or "unknown"
        lines.append(
            f"- {agent.get('title')} (`{agent.get('ref')}`): rank {rank}, score {score}, "
            f"smoke_ok={agent.get('smoke_ok')}; evidence={', '.join(agent.get('classification_evidence') or [])}"
        )
    lines.extend(["", "## Field Comparison", "", "| Archetype | Appearances | Win rate | Meta share |", "|---|---:|---:|---:|"])
    for row in audit.get("comparison_archetypes") or []:
        lines.append(
            f"| {row['name']} | {row['appearances']} | {_percent(row['win_rate'])} | {_percent(row['meta_share'])} |"
        )
    replay = (audit.get("clark_replay_evidence") or {}).get("lucario_mirror")
    lines.extend(["", "## Clark Replay Slice", ""])
    if replay:
        lines.append(
            f"- Lucario mirror games: {replay['games']}; Clark {replay['clark_wins']}-{replay['clark_losses']}; "
            f"opponent win rate vs Clark: {_percent(replay['opponent_win_rate_vs_clark'])}."
        )
        lines.append(f"- Scope: {replay['scope']}")
    else:
        lines.append("- No Clark replay slice was supplied.")
    verdict = audit["verdict"]
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            f"- Track selection: `{verdict['track_selection']}`",
            f"- Summary: {verdict['summary']}",
        ]
    )
    for limitation in verdict.get("limitations") or []:
        lines.append(f"- Limitation: {limitation}")
    lines.extend(
        [
            "",
            "## Required Statement",
            "",
            "Kaggle submission made: no",
            "",
        ]
    )
    return "\n".join(lines)
