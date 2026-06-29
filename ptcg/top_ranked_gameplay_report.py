from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


COLORS = {
    "ink": "#202124",
    "muted": "#5f6368",
    "blue": "#264653",
    "teal": "#2a9d8f",
    "gold": "#e9c46a",
    "orange": "#f4a261",
    "red": "#e76f51",
    "purple": "#6d597a",
    "gray": "#9aa0a6",
}

HIGH_SIGNAL_LABELS = {
    "setup",
    "draw/search/thin",
    "bench_develop",
    "energy_attach_active",
    "energy_attach_bench_next_attacker",
    "attack_prize_race",
    "gust_target",
    "disruption",
    "preserve_resources",
    "risk_ahead_conservative",
    "risk_behind_high_variance",
}


def load_json(path: Path) -> Any:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Could not parse JSON: {path}")


def read_episode_index_manifest(path: Path, date: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if str(row.get("date")) != date:
            continue
        total_bytes = int(float(row.get("total_bytes") or 0))
        return {
            "date": str(row.get("date") or ""),
            "daily_dataset_slug": str(row.get("daily_dataset_slug") or ""),
            "daily_dataset_url": str(row.get("daily_dataset_url") or ""),
            "episode_count": int(float(row.get("episode_count") or 0)),
            "total_bytes": total_bytes,
            "total_gb": math.ceil((total_bytes / (1024**3)) * 1000) / 1000,
            "top_avg_score": float(row.get("top_avg_score") or 0.0),
            "median_avg_score": float(row.get("median_avg_score") or 0.0),
        }
    raise ValueError(f"No episode index manifest row for {date}: {path}")


def local_full_dataset_stats(path: Path) -> dict[str, Any]:
    files = [item for item in path.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    json_files = [item for item in files if item.suffix.lower() == ".json"]
    return {
        "path": str(path),
        "local_full_dataset_files": len(files),
        "local_full_dataset_json_files": len(json_files),
        "local_full_dataset_bytes": total_bytes,
        "local_full_dataset_gb": total_bytes / (1024**3),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def _counter_rows(counter: Counter[str], *, limit: int = 12) -> list[dict[str, Any]]:
    return [{"team": name, "count": count} for name, count in counter.most_common(limit)]


def ranking_summary(rankings: dict[str, Any]) -> dict[str, Any]:
    rows = list(rankings.get("top_50") or [])
    team_counts: Counter[str] = Counter()
    winner_counts: Counter[str] = Counter()
    score_sums: list[float] = []
    winner_scores: list[float] = []
    decision_counts: list[float] = []
    active_decision_counts: list[float] = []
    steps: list[float] = []
    for row in rows:
        team_counts.update(str(team) for team in row.get("teams") or [])
        winner = row.get("winner_team")
        if winner:
            winner_counts[str(winner)] += 1
        score_sums.append(float(row.get("known_leaderboard_score_sum") or 0.0))
        winner_scores.append(float(row.get("winner_leaderboard_score") or 0.0))
        decision_counts.append(float(row.get("decision_count") or 0.0))
        active_decision_counts.append(float(row.get("active_decision_count") or 0.0))
        steps.append(float(row.get("steps") or 0.0))
    return {
        "source_dataset": rankings.get("source_dataset"),
        "scanned_count": int(rankings.get("scanned_count") or 0),
        "error_count": int(rankings.get("error_count") or 0),
        "top_count": len(rows),
        "top_team_counts": _counter_rows(team_counts),
        "winner_counts": _counter_rows(winner_counts),
        "decision_count_avg": _mean(decision_counts),
        "active_decision_count_avg": _mean(active_decision_counts),
        "steps_avg": _mean(steps),
        "steps_p90": _quantile(steps, 0.9),
        "score_sum_min": min(score_sums) if score_sums else 0.0,
        "score_sum_median": _quantile(score_sums, 0.5),
        "score_sum_max": max(score_sums) if score_sums else 0.0,
        "winner_score_avg": _mean(winner_scores),
    }


def label_share_rows(counts: dict[str, int]) -> list[dict[str, Any]]:
    total = sum(int(value) for value in counts.values())
    rows = [
        {
            "label": str(label),
            "count": int(count),
            "share": int(count) / total if total else 0.0,
            "high_signal": str(label) in HIGH_SIGNAL_LABELS,
        }
        for label, count in counts.items()
    ]
    return sorted(rows, key=lambda item: (int(item["count"]), str(item["label"])), reverse=True)


def agent_gap_rows(counts: dict[str, int]) -> list[dict[str, Any]]:
    total = max(1, sum(int(value) for value in counts.values()))
    attack = int(counts.get("attack_prize_race", 0))
    draw = int(counts.get("draw/search/thin", 0))
    setup = int(counts.get("setup", 0)) + int(counts.get("bench_develop", 0))
    active_energy = int(counts.get("energy_attach_active", 0))
    bench_energy = int(counts.get("energy_attach_bench_next_attacker", 0))
    gust_disrupt = int(counts.get("gust_target", 0)) + int(counts.get("disruption", 0))
    preserve = int(counts.get("preserve_resources", 0))
    unclear = int(counts.get("unclear_or_forced", 0))
    gaps: list[dict[str, Any]] = []
    if active_energy > max(bench_energy * 2, 8):
        gaps.append(
            {
                "gap": "next_attacker_underbuilt",
                "severity": active_energy - bench_energy,
                "evidence": f"energy_attach_active={active_energy}, energy_attach_bench_next_attacker={bench_energy}",
                "agent_action": "Increase bench-next-attacker attachment/search value before active-only damage lines.",
            }
        )
    if gust_disrupt < max(6, attack // 12):
        gaps.append(
            {
                "gap": "low_disruption_and_gust",
                "severity": max(1, attack - gust_disrupt),
                "evidence": f"attack_prize_race={attack}, gust_target+disruption={gust_disrupt}",
                "agent_action": "Add behind/gate-pressure bonuses for Boss/gust, hand reset, trap, and energy denial.",
            }
        )
    if setup < attack * 0.55:
        gaps.append(
            {
                "gap": "setup_vs_attack_imbalance",
                "severity": int(attack - setup),
                "evidence": f"setup+bench_develop={setup}, attack_prize_race={attack}",
                "agent_action": "Do not race the active unless a follow-up attacker and energy line already exist.",
            }
        )
    if preserve < max(10, total // 40):
        gaps.append(
            {
                "gap": "resource_preservation_sparse",
                "severity": max(1, max(10, total // 40) - preserve),
                "evidence": f"preserve_resources={preserve} across {total} labeled decisions",
                "agent_action": "Ahead-state policy should preserve Boss, switch, energy, and search once the turn is solved.",
            }
        )
    if unclear / total > 0.2:
        gaps.append(
            {
                "gap": "forced_or_low-context_decisions_high",
                "severity": unclear,
                "evidence": f"unclear_or_forced={unclear} ({unclear / total:.1%})",
                "agent_action": "Keep these rows for robustness, but downweight them relative to high-confidence teacher labels.",
            }
        )
    return sorted(gaps, key=lambda item: int(item["severity"]), reverse=True)


def top_meta_rows(meta: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    rows = []
    for item in list(meta.get("archetypes") or [])[:limit]:
        rows.append(
            {
                "name": str(item.get("name") or "unknown"),
                "meta_share": float(item.get("metaShare") or 0.0),
                "win_rate": float(item.get("winRate") or 0.0),
                "appearances": int(item.get("appearances") or 0),
            }
        )
    return rows


def build_report_data(
    *,
    date: str,
    full_dataset_dir: Path,
    episode_manifest_path: Path,
    rankings_path: Path,
    labels_path: Path,
    meta_snapshot_path: Path,
) -> dict[str, Any]:
    manifest_row = read_episode_index_manifest(episode_manifest_path, date)
    rankings = load_json(rankings_path)
    labels = load_json(labels_path)
    meta = load_json(meta_snapshot_path)
    dataset = {
        **manifest_row,
        **local_full_dataset_stats(full_dataset_dir),
    }
    label_counts = {str(key): int(value) for key, value in (labels.get("combined_label_counts") or {}).items()}
    return {
        "date": date,
        "dataset": dataset,
        "ranking_source_path": str(rankings_path),
        "label_source_path": str(labels_path),
        "meta_source_path": str(meta_snapshot_path),
        "ranking_summary": ranking_summary(rankings),
        "top_episodes": list(rankings.get("top_50") or []),
        "label_summary": {
            "episode_count_scanned": int(labels.get("episode_count_scanned") or 0),
            "selected_game_count": int(labels.get("selected_game_count") or len(labels.get("games") or [])),
            "phase_label_file_count": int(labels.get("phase_label_file_count") or 0),
            "total_decision_count": int(labels.get("total_decision_count") or sum(label_counts.values())),
            "total_key_decision_count": int(labels.get("total_key_decision_count") or 0),
            "combined_label_counts": label_counts,
            "label_share_rows": label_share_rows(label_counts),
            "agent_gap_rows": agent_gap_rows(label_counts),
            "teacher_rules": list(labels.get("teacher_rules") or [])[:16],
            "validation": labels.get("validation") or {},
            "kaggle_submission_made": bool(labels.get("kaggle_submission_made", False)),
        },
        "meta": {
            "date": meta.get("date"),
            "latestDate": meta.get("latestDate"),
            "redirected": meta.get("redirected"),
            "totalDecks": meta.get("totalDecks"),
            "source": meta.get("source"),
            "top_archetypes": top_meta_rows(meta, limit=10),
        },
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }


def set_plot_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 320,
            "savefig.bbox": "tight",
            "font.family": "DejaVu Sans",
            "axes.facecolor": "#fbfbfb",
            "figure.facecolor": "white",
            "axes.edgecolor": "#d9d9d9",
            "axes.labelcolor": COLORS["ink"],
            "axes.titleweight": "bold",
            "axes.titlesize": 15,
            "axes.labelsize": 11,
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
            "grid.color": "#e0e0e0",
            "grid.linewidth": 0.8,
            "legend.frameon": False,
        }
    )


def _short_label(value: str, *, max_len: int = 28) -> str:
    ascii_value = value.encode("ascii", errors="ignore").decode("ascii").strip()
    if not ascii_value:
        digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:6]
        ascii_value = f"non-ascii-{digest}"
    return ascii_value if len(ascii_value) <= max_len else ascii_value[: max_len - 1] + "."


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def figure_meta_archetypes(data: dict[str, Any], out: Path) -> None:
    rows = data["meta"]["top_archetypes"]
    names = [_short_label(row["name"]) for row in rows]
    shares = [row["meta_share"] for row in rows]
    wins = [row["win_rate"] for row in rows]
    x = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(12.5, 7), constrained_layout=True)
    bars = ax.bar(x, shares, color=COLORS["blue"], alpha=0.9, label="Meta share")
    ax2 = ax.twinx()
    ax2.plot(x, wins, color=COLORS["red"], marker="o", linewidth=2.3, label="Win rate")
    for bar, share in zip(bars, shares):
        ax.text(bar.get_x() + bar.get_width() / 2, share + 0.004, _pct(share), ha="center", fontsize=8)
    ax.set_title("Current June 24 Meta: Training Pool Must Stay Weighted")
    ax.set_ylabel("Meta share")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax2.set_ylabel("Win rate")
    ax2.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=24, ha="right")
    ax.set_ylim(0, max(shares + [0.01]) * 1.22)
    ax2.set_ylim(0, max(wins + [0.01]) * 1.18)
    ax.grid(axis="y", alpha=0.8)
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, loc="upper right")
    fig.savefig(out)
    plt.close(fig)


def figure_top_team_pressure(data: dict[str, Any], out: Path) -> None:
    rows = data["ranking_summary"]["top_team_counts"][:10]
    winner_counts = {row["team"]: row["count"] for row in data["ranking_summary"]["winner_counts"]}
    names = [_short_label(row["team"], max_len=22) for row in rows]
    appearances = [row["count"] for row in rows]
    wins = [winner_counts.get(row["team"], 0) for row in rows]
    x = list(range(len(rows)))
    width = 0.38
    fig, ax = plt.subplots(figsize=(12, 6.8), constrained_layout=True)
    ax.bar([i - width / 2 for i in x], appearances, width, label="Top-50 appearances", color=COLORS["teal"])
    ax.bar([i + width / 2 for i in x], wins, width, label="Top-50 wins", color=COLORS["gold"])
    ax.set_title("Top-Ranked Episodes Cluster Around A Small Set Of Players")
    ax.set_ylabel("Count in ranked top 50")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=24, ha="right")
    ax.grid(axis="y", alpha=0.8)
    ax.legend()
    fig.savefig(out)
    plt.close(fig)


def figure_label_profile(data: dict[str, Any], out: Path) -> None:
    rows = data["label_summary"]["label_share_rows"]
    names = [_short_label(row["label"], max_len=30) for row in rows]
    counts = [row["count"] for row in rows]
    colors = [COLORS["orange"] if row["label"] == "unclear_or_forced" else COLORS["blue"] for row in rows]
    fig, ax = plt.subplots(figsize=(11.5, 8), constrained_layout=True)
    y = list(range(len(rows)))
    ax.barh(y, counts, color=colors)
    ax.set_title("Teacher Labels From Selected Top Games: Race And Search Dominate")
    ax.set_xlabel("Labeled decisions")
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    for yi, row in enumerate(rows):
        ax.text(row["count"] + 2, yi, f"{row['count']} ({_pct(row['share'])})", va="center", fontsize=9)
    ax.grid(axis="x", alpha=0.75)
    fig.savefig(out)
    plt.close(fig)


def figure_decision_burden(data: dict[str, Any], out: Path) -> None:
    rows = data["top_episodes"]
    x = [float(row.get("known_leaderboard_score_sum") or 0.0) for row in rows]
    y = [float(row.get("decision_count") or 0.0) for row in rows]
    sizes = [max(28.0, float(row.get("active_decision_count") or 0.0) * 1.6) for row in rows]
    colors = [float(row.get("winner_leaderboard_score") or 0.0) for row in rows]
    fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
    scatter = ax.scatter(x, y, s=sizes, c=colors, cmap="viridis", alpha=0.8, edgecolor="white", linewidth=0.8)
    for row in rows[:5]:
        ax.text(
            float(row.get("known_leaderboard_score_sum") or 0.0) + 1.5,
            float(row.get("decision_count") or 0.0) + 1.5,
            str(row.get("episode_id")),
            fontsize=8,
            color=COLORS["ink"],
        )
    ax.set_title("Top-50 Games: Decision Load Varies Even At Similar Leaderboard Strength")
    ax.set_xlabel("Matched leaderboard score sum")
    ax.set_ylabel("Decision count")
    ax.grid(True, alpha=0.75)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Winner leaderboard score")
    fig.savefig(out)
    plt.close(fig)


def figure_agent_gap_signals(data: dict[str, Any], out: Path) -> None:
    rows = data["label_summary"]["agent_gap_rows"]
    if not rows:
        rows = [{"gap": "no_gap_detected", "severity": 1, "agent_action": "No strong label imbalance detected."}]
    names = [_short_label(row["gap"], max_len=40) for row in rows]
    values = [int(row["severity"]) for row in rows]
    fig, ax = plt.subplots(figsize=(10.8, 6.6), constrained_layout=True)
    y = list(range(len(rows)))
    bars = ax.barh(
        y,
        values,
        color=[COLORS["red"], COLORS["orange"], COLORS["purple"], COLORS["teal"], COLORS["blue"]][: len(rows)],
    )
    ax.set_title("Agent Training Gaps Implied By The Top-Game Labels")
    ax.set_xlabel("Relative severity from label counts")
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    for bar, value in zip(bars, values):
        ax.text(value + max(values) * 0.02, bar.get_y() + bar.get_height() / 2, str(value), va="center", fontsize=9)
    ax.grid(axis="x", alpha=0.75)
    fig.savefig(out)
    plt.close(fig)


def create_figures(data: dict[str, Any], figure_dir: Path) -> dict[str, str]:
    figure_dir.mkdir(parents=True, exist_ok=True)
    set_plot_style()
    figures = {
        "meta": figure_dir / "01_meta_share_and_win_rate.png",
        "players": figure_dir / "02_top50_player_pressure.png",
        "labels": figure_dir / "03_teacher_label_profile.png",
        "burden": figure_dir / "04_decision_burden_scatter.png",
        "gaps": figure_dir / "05_agent_gap_signals.png",
    }
    figure_meta_archetypes(data, figures["meta"])
    figure_top_team_pressure(data, figures["players"])
    figure_label_profile(data, figures["labels"])
    figure_decision_burden(data, figures["burden"])
    figure_agent_gap_signals(data, figures["gaps"])
    return {key: str(path) for key, path in figures.items()}


def _md_table(rows: list[list[Any]], headers: list[str]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def write_markdown_report(data: dict[str, Any], out: Path, figure_rel_paths: dict[str, str]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    dataset = data["dataset"]
    ranks = data["ranking_summary"]
    labels = data["label_summary"]
    meta = data["meta"]
    top_meta = meta["top_archetypes"][:6]
    top_labels = labels["label_share_rows"][:8]
    gaps = labels["agent_gap_rows"]
    top_teams = ranks["top_team_counts"][:8]
    top_winners = ranks["winner_counts"][:8]
    gap_lines = "\n".join(
        f"- `{row['gap']}`: {row['agent_action']} Evidence: {row['evidence']}" for row in gaps[:6]
    ) or "- No strong gap imbalance detected."
    teacher_rule_lines = "\n".join(f"- {rule}" for rule in labels["teacher_rules"][:10]) or "- No teacher rules captured."

    report = f"""# June 24 Top-Ranked Gameplay Agent Brief

**Thesis:** The 21 GB June 24 top-ranked gameplay dump is most useful as a strategy-gap map, not as a reason to start learned-policy loops. The full scan shows a clean high-ranked episode pool; the selected top-game labels show that elite play is heavy on attack/search decisions, while our next agent gains should come from better next-attacker setup, hard-gate disruption, and resource preservation.

## Source Boundary

- Date analyzed: `{data['date']}`.
- Daily dataset: `{dataset['daily_dataset_slug']}`.
- Dataset URL: {dataset['daily_dataset_url']}.
- Manifest size: {dataset['total_bytes']:,} bytes ({dataset['total_gb']:.2f} GiB), {dataset['episode_count']:,} episodes.
- Local full dataset path: `{dataset['path']}`.
- Local files counted: {dataset['local_full_dataset_files']:,} files, {dataset['local_full_dataset_json_files']:,} JSON files, {dataset['local_full_dataset_gb']:.2f} GiB.
- Full scan source: `{data['ranking_source_path']}`.
- Full scan result: {ranks['scanned_count']:,} scanned, {ranks['error_count']} errors, {ranks['top_count']} ranked top episodes retained.
- Teacher label source: `{data['label_source_path']}`.
- Teacher-labeled subset: {labels['selected_game_count']} selected games, {labels['total_decision_count']} labeled decisions, {labels['total_key_decision_count']} key decisions.
- Meta API date: `{meta['date']}`, latestDate `{meta['latestDate']}`, redirected `{meta['redirected']}`, totalDecks `{meta['totalDecks']}`.
- Meta dataset URL: {(meta.get('source') or {}).get('datasetUrl', 'unknown')}.
- Kaggle submission made: `no`.
- Learned-policy claim: `no`. This is replay/meta analysis and heuristic patch extraction, not a simulator policy update.

## Executive Read

- The downloaded June 24 dataset is the live current-meta day: the refreshed API also returns June 24 with {meta['totalDecks']:,} deck appearances.
- The top-six meta gates are still Lucario, Hop/Trevenant, Alakazam, Dragapult, Team Rocket Petrel/Transceiver, and Mega Starmie. Gate selection and heuristic patch priority should stay weighted to that pool.
- The ranked top-50 games were selected from {ranks['scanned_count']:,} scanned episodes with zero scan errors. Average top-game decision count was {ranks['decision_count_avg']:.1f}; average active-decision count was {ranks['active_decision_count_avg']:.1f}.
- The labeled top-game slice is decision-rich but not fully exhaustive: {labels['selected_game_count']} games produced {labels['total_decision_count']} labels. Use it as high-quality agent guidance, not as the whole patch backlog by itself.
- The largest label buckets were {', '.join(f"`{row['label']}` {row['count']}" for row in top_labels[:4])}.
- Main strategy gap: top labels lean heavily toward prize-race/search execution, while disruption/gust and bench-next-attacker preparation are comparatively sparse.

## 1. Current Meta Weight

![Current meta share and win rate]({figure_rel_paths.get('meta', '')})

{_md_table(
        [
            [
                row['name'],
                f"{row['meta_share'] * 100:.1f}%",
                f"{row['win_rate'] * 100:.1f}%",
                row['appearances'],
            ]
            for row in top_meta
        ],
        ['Archetype', 'Meta share', 'Win rate', 'Appearances'],
    )}

Agent implication: do not let a Lucario-only or Dragapult-only replay slice monopolize candidate design. The opponent pool should stay meta-share weighted, with explicit hard reports for Lucario and Dragapult/spread.

## 2. Top-Ranked Player Pressure

![Top-50 player pressure]({figure_rel_paths.get('players', '')})

Top appearances:

{_md_table([[row['team'], row['count']] for row in top_teams], ['Team', 'Top-50 appearances'])}

Top winners:

{_md_table([[row['team'], row['count']] for row in top_winners], ['Team', 'Top-50 wins'])}

Agent implication: repeated top-player pairs are useful teacher anchors, but they should be tagged by matchup and winner side. Do not collapse them into an anonymous replay blob.

## 3. Teacher Label Profile

![Teacher label profile]({figure_rel_paths.get('labels', '')})

Top labels:

{_md_table(
        [[row['label'], row['count'], f"{row['share'] * 100:.1f}%"] for row in top_labels],
        ['Label', 'Count', 'Share'],
    )}

Agent implication: the heuristic patch map should emphasize high-confidence winning-side rows and downweight `unclear_or_forced` rows. The current labels are most useful for sequencing, search/draw, and prize-race execution.

## 4. Decision Burden

![Decision burden scatter]({figure_rel_paths.get('burden', '')})

The top-50 games do not all look alike. Some high-score pairs have compact games; others force 100+ decisions. That matters for analysis because long games can overweight repeated forced choices unless we summarize per game and per phase.

Agent implication: review by game and phase, not raw row count only. Otherwise, long games can drown out short but strategically clean wins.

## 5. Agent Strategy Gaps

![Agent gap signals]({figure_rel_paths.get('gaps', '')})

{gap_lines}

Teacher rules captured from the selected top games:

{teacher_rule_lines}

## Agent-Facing Action Plan

1. Build a heuristic patch map from top-ranked visible decisions with these required fields: observation, legal actions, chosen action, matchup tag, actor archetype, opponent archetype, replay id, winner side, leaderboard score/rank when available, and sample weight.
2. Add phase tags: opening, midgame, finish. Keep per-phase summaries so long games do not dominate the backlog.
3. Tag hard gates explicitly: Lucario, Dragapult/spread, Hop/Trevenant, Alakazam, Team Rocket Petrel/Transceiver, Mega Starmie.
4. Add failure tags for losses: missed next attacker, active overattach, no gust/disruption line, poor Boss/Iono timing, resource overextension, prize-race misread.
5. Build complementary heuristic candidates, not one blended agent:
   - Track A: stabilizer, setup consistency, next attacker, conservative when ahead.
   - Track B: disruptor, higher variance when behind, gust/trap/energy denial.
   - Track C: spread-aware, anti-Dragapult.
   - Track D: anti-Lucario mirror/gate specialist.
   - Track E: anti-Hop/Trevenant and control-resistant board development.
   - Track F: anti-Team-Rocket disruption and hand-resource preservation.
6. Do not start learned-policy work from this report. Convert the evidence into explicit heuristic patches and gate tests.

## Copy-Paste Agent Directive

```text
Use the June 24 top-ranked gameplay report as scouting and heuristic-patch input, not as a promotion claim.
Build patch-map rows from winning-side public replay decisions, tagged by matchup, phase, archetype, winner side, leaderboard score, and sample weight.
Downweight unclear_or_forced decisions.
Upweight hard-gate losses with failure tags: missed next attacker, active overattach, no gust/disruption line, poor Boss/Iono timing, resource overextension, and prize-race misread.
Keep A/B finalists complementary: stabilizer versus disruptor, then add focused Dragapult/Lucario variants.
Report public Lucario and public Dragapult/spread separately before any champion comparison.
Kaggle submission made: no.
Learned-policy claim: no.
```

## Machine-Readable Companion

- Summary JSON: `summary_data.json`.
- Figures: `figures/`.
- Source scan JSON: `{data['ranking_source_path']}`.
- Source labels JSON: `{data['label_source_path']}`.
"""
    out.write_text(report, encoding="utf-8")


def write_summary_json(data: dict[str, Any], out: Path, figure_paths: dict[str, str]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": data["date"],
        "thesis": (
            "The June 24 21 GB top-ranked gameplay dump is a strategy-gap map for heuristic patches and gate design, "
            "not a standalone promotion signal."
        ),
        "dataset": data["dataset"],
        "ranking_summary": data["ranking_summary"],
        "label_summary": data["label_summary"],
        "meta": data["meta"],
        "figure_paths": figure_paths,
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_report_bundle(
    *,
    date: str,
    full_dataset_dir: Path,
    episode_manifest_path: Path,
    rankings_path: Path,
    labels_path: Path,
    meta_snapshot_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = build_report_data(
        date=date,
        full_dataset_dir=full_dataset_dir,
        episode_manifest_path=episode_manifest_path,
        rankings_path=rankings_path,
        labels_path=labels_path,
        meta_snapshot_path=meta_snapshot_path,
    )
    figure_paths = create_figures(data, output_dir / "figures")
    rel_figures = {key: str(Path(path).relative_to(output_dir)).replace("\\", "/") for key, path in figure_paths.items()}
    markdown_path = output_dir / "top_ranked_gameplay_agent_brief.md"
    summary_path = output_dir / "summary_data.json"
    write_markdown_report(data, markdown_path, rel_figures)
    write_summary_json(data, summary_path, figure_paths)
    return {
        "markdown_report": str(markdown_path),
        "summary_json": str(summary_path),
        "figures": figure_paths,
        "dataset_files": data["dataset"]["local_full_dataset_files"],
        "dataset_gb": data["dataset"]["local_full_dataset_gb"],
        "scanned_count": data["ranking_summary"]["scanned_count"],
        "error_count": data["ranking_summary"]["error_count"],
        "kaggle_submission_made": False,
        "learned_policy_claim": False,
    }
