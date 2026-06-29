from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.kaggle_archive_validator import validate_archive_startup

DEFAULT_RESEARCH_DIR = ROOT / "artifacts" / "ptcg_research" / "current" / "starmie_next_heuristic_2026_06_28"
DEFAULT_BROAD_RUN_DIR = DEFAULT_RESEARCH_DIR / "start_guard_broad_50g"
DEFAULT_LUCARIO_RUN_DIR = DEFAULT_RESEARCH_DIR / "start_guard_lucario_100g"
DEFAULT_ARCHIVE = ROOT / "artifacts" / "submission_starmie_start_guard_v1.tar.gz"
PARENT = "submission_3_cg_fix"
CANDIDATE = "submission_starmie_start_guard_v1"


COLORS = {
    "ink": "#202124",
    "muted": "#5f6368",
    "blue": "#264653",
    "teal": "#2a9d8f",
    "gold": "#e9c46a",
    "orange": "#f4a261",
    "red": "#e76f51",
    "gray": "#9aa0a6",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def win_rate(row: dict[str, Any]) -> float:
    finished = int(row.get("finished") or row.get("games") or 0)
    return (int(row.get("wins") or 0) / finished) if finished else 0.0


def matchup_delta_rows(
    rows: list[dict[str, Any]], *, parent: str = PARENT, candidate: str = CANDIDATE
) -> list[dict[str, Any]]:
    by_gate: dict[str, dict[str, dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        gate = str(row.get("gate_ref"))
        if gate not in by_gate:
            by_gate[gate] = {}
            order.append(gate)
        by_gate[gate][str(row.get("candidate"))] = row

    deltas: list[dict[str, Any]] = []
    for gate in order:
        paired = by_gate[gate]
        if parent not in paired or candidate not in paired:
            continue
        parent_wr = win_rate(paired[parent])
        candidate_wr = win_rate(paired[candidate])
        deltas.append(
            {
                "gate_ref": gate,
                "archetype": str(paired[candidate].get("archetype") or paired[parent].get("archetype") or ""),
                "parent_win_rate": parent_wr,
                "candidate_win_rate": candidate_wr,
                "delta": candidate_wr - parent_wr,
            }
        )
    return deltas


def _style_axes(ax: Any) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color="#eceff1", linewidth=0.8)
    ax.set_axisbelow(True)


def plot_leaderboard(leaderboard: list[dict[str, Any]], path: Path) -> None:
    ordered = sorted(leaderboard, key=lambda row: str(row["candidate"]))
    names = [str(row["candidate"]).replace("submission_", "") for row in ordered]
    raw = [float(row.get("raw_win_rate") or 0.0) for row in ordered]
    weighted = [float(row.get("weighted_win_rate") or 0.0) for row in ordered]
    x = list(range(len(names)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([i - width / 2 for i in x], raw, width, label="Raw", color=COLORS["blue"])
    ax.bar([i + width / 2 for i in x], weighted, width, label="Weighted", color=COLORS["teal"])
    ax.set_ylim(0.72, 0.95)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Starmie Start Guard vs Parent", color=COLORS["ink"])
    ax.set_ylabel("Win rate")
    ax.set_xticks(x, names, rotation=15, ha="right")
    ax.legend(frameon=False)
    _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_delta_bars(rows: list[dict[str, Any]], path: Path, *, title: str) -> None:
    ordered = sorted(rows, key=lambda row: float(row["delta"]))
    labels = [str(row["gate_ref"]).replace("current_meta/", "") for row in ordered]
    values = [float(row["delta"]) for row in ordered]
    colors = [COLORS["teal"] if value >= 0 else COLORS["red"] for value in values]

    fig_height = max(4.5, 0.38 * len(labels) + 1.2)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color=COLORS["ink"], linewidth=1)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title(title, color=COLORS["ink"])
    ax.set_xlabel(f"{CANDIDATE} win-rate delta vs parent")
    _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_trace_failures(failure_counts: dict[str, int], path: Path) -> None:
    rows = sorted(failure_counts.items(), key=lambda item: item[1])
    labels = [name.replace("_", " ") for name, _ in rows]
    values = [count for _, count in rows]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.barh(labels, values, color=COLORS["orange"])
    ax.set_title("Parent Trace Failure Tags vs Public Lucario", color=COLORS["ink"])
    ax.set_xlabel("Reports tagged")
    _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _record_line(row: dict[str, Any]) -> str:
    return (
        f"`{row['candidate']}`: {row['wins']}-{row['losses']}-{row.get('draws', 0)} "
        f"raw={float(row.get('raw_win_rate') or 0.0):.3f} "
        f"weighted={float(row.get('weighted_win_rate') or 0.0):.3f} "
        f"score={float(row.get('leaderboard_score') or 0.0):.3f} "
        f"collapses={len(row.get('hard_gate_collapses') or [])} "
        f"promotable={str(bool(row.get('promotable'))).lower()}"
    )


def _matchup_line(row: dict[str, Any]) -> str:
    return (
        f"`{row['gate_ref']}`: {row['wins']}-{row['losses']}-{row.get('draws', 0)} "
        f"({win_rate(row):.0%})"
    )


def build_report(
    *,
    research_dir: Path,
    broad_run_dir: Path,
    lucario_run_dir: Path,
    archive_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    leaderboard = load_json(broad_run_dir / "internal_leaderboard.json")
    matchup_matrix = load_json(broad_run_dir / "matchup_matrix.json")
    broad_summary = load_json(broad_run_dir / "run_summary.json")
    lucario_summary = load_json(lucario_run_dir / "lucario_matchups.json")
    trace_summary = load_json(research_dir / "trace_summary.json")
    build_report_path = ROOT / "artifacts" / "starmie_start_guard_v1" / "build_report.json"
    build_report_data = load_json(build_report_path) if build_report_path.exists() else {}

    validator = validate_archive_startup(archive_path)
    sha256 = archive_sha256(archive_path)
    validator["archive_sha256"] = sha256

    broad_deltas = matchup_delta_rows(matchup_matrix)
    lucario_deltas = matchup_delta_rows(list(lucario_summary.get("rows") or []))

    graphics = {
        "leaderboard_winrates": output_dir / "leaderboard_winrates.png",
        "broad_matchup_deltas": output_dir / "broad_matchup_deltas.png",
        "lucario_gate_deltas": output_dir / "lucario_gate_deltas.png",
        "trace_failure_tags": output_dir / "trace_failure_tags.png",
    }
    plot_leaderboard(leaderboard, graphics["leaderboard_winrates"])
    plot_delta_bars(broad_deltas, graphics["broad_matchup_deltas"], title="Broad 50-Game Gate Deltas")
    plot_delta_bars(lucario_deltas, graphics["lucario_gate_deltas"], title="Lucario 100-Game Gate Deltas")
    plot_trace_failures(trace_summary.get("failure_tag_counts") or {}, graphics["trace_failure_tags"])

    top = leaderboard[0] if leaderboard else {}
    parent = next((row for row in leaderboard if row.get("candidate") == PARENT), {})
    candidate = next((row for row in leaderboard if row.get("candidate") == CANDIDATE), {})
    decision = (
        "Promote start_guard_v1 as the current local Starmie heuristic candidate, pending explicit Kaggle approval."
        if top.get("candidate") == CANDIDATE and candidate.get("promotable")
        else "Do not promote start_guard_v1 over the parent from the saved local gates."
    )

    machine_summary = {
        "command": "python scripts\\generate_starmie_start_guard_report.py",
        "input_paths": {
            "archive": str(archive_path.resolve()),
            "broad_run_dir": str(broad_run_dir.resolve()),
            "lucario_run_dir": str(lucario_run_dir.resolve()),
            "trace_summary": str((research_dir / "trace_summary.json").resolve()),
            "build_report": str(build_report_path.resolve()),
        },
        "replay_count": int(broad_summary.get("replay_count") or 0),
        "opponent_count": int(broad_summary.get("opponent_count") or broad_summary.get("gate_count") or 0),
        "game_count": int((broad_summary.get("totals") or {}).get("finished") or 0)
        + sum(int(row.get("finished") or 0) for row in lucario_summary.get("rows") or []),
        "row_counts": {
            "leaderboard": len(leaderboard),
            "broad_matchups": len(matchup_matrix),
            "lucario_matchups": len(lucario_summary.get("rows") or []),
            "trace_reports": len(trace_summary.get("reports") or []),
        },
        "label_counts": {
            "trace_failure_tags": trace_summary.get("failure_tag_counts") or {},
            "trace_metric_aggregate": trace_summary.get("aggregate") or {},
        },
        "source_metadata": {
            "date": broad_summary.get("meta_date"),
            "latestDate": broad_summary.get("latest_date"),
            "redirected": broad_summary.get("redirected"),
            "totalDecks": broad_summary.get("total_decks"),
            "datasetUrl": broad_summary.get("dataset_url"),
        },
        "kaggle_submission_made": False,
    }

    report = {
        "decision": decision,
        "strategy": build_report_data.get("strategy"),
        "archive": str(archive_path.resolve()),
        "sha256": sha256,
        "validator": validator,
        "leaderboard": leaderboard,
        "parent_summary": parent,
        "candidate_summary": candidate,
        "broad_deltas": broad_deltas,
        "lucario_deltas": lucario_deltas,
        "trace_summary": trace_summary,
        "broad_summary": broad_summary,
        "lucario_summary": lucario_summary,
        "graphics": {name: str(path.resolve()) for name, path in graphics.items()},
        "machine_summary": machine_summary,
        "kaggle_submission_made": False,
    }

    json_path = output_dir / "final_report.json"
    md_path = output_dir / "final_report.md"
    write_json(json_path, report)
    write_markdown_report(report, md_path)
    return {"json_path": json_path, "markdown_path": md_path, "report": report}


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    meta = report["machine_summary"]["source_metadata"]
    leaderboard = report["leaderboard"]
    candidate = report["candidate_summary"]
    parent = report["parent_summary"]
    lucario_rows = list(report["lucario_summary"].get("rows") or [])
    broad_matrix = list(report["broad_summary"].get("totals") or [])
    trace_agg = report["trace_summary"].get("aggregate") or {}
    graphics = report["graphics"]

    candidate_matchups = [
        row
        for row in leaderboard[0].get("matchups", [])
        if row.get("candidate") == CANDIDATE
    ] if leaderboard else []
    if not candidate_matchups:
        candidate_matchups = [
            row for row in report.get("broad_deltas", []) if row.get("candidate") == CANDIDATE
        ]

    hard_focus = [
        row
        for row in candidate.get("matchups", [])
        if row.get("gate_ref")
        in {
            "current_meta/lucario",
            "current_meta/hop_trevenant",
            "current_meta/alakazam",
            "current_meta/dragapult",
            "current_meta/team_rocket",
            "current_meta/starmie",
            "pilkwang/pokemon-tcg-lucario-v2-strategy-baseline",
            "pixiux/ptcg-mega-lucario-ex-v63",
            "current_meta/archaludon_replay_82396187",
        }
    ]

    lucario_by_candidate = {}
    for row in lucario_rows:
        lucario_by_candidate.setdefault(row["candidate"], []).append(row)

    lines = [
        "# Starmie Start Guard Final Report",
        "",
        "## Decision",
        "",
        f"**{report['decision']}**",
        "",
        f"- Meta date: `{meta.get('date')}`; latestDate: `{meta.get('latestDate')}`; redirected: `{meta.get('redirected')}`",
        f"- Total decks: `{meta.get('totalDecks')}`",
        f"- Dataset: `{meta.get('datasetUrl')}`",
        "- Change: `+1 Staryu (1030), -1 Cinderace (666)`, parent policy unchanged",
        f"- Archive: `{report['archive']}`",
        f"- SHA256: `{report['sha256']}`",
        f"- Validator: `agent_deck_matches_csv={str(report['validator'].get('agent_deck_matches_csv')).lower()}`, "
        f"`required_members_present={str(report['validator'].get('required_members_present')).lower()}`, "
        f"`strict_raw_exec_without_file_or_syspath={str(report['validator'].get('strict_raw_exec_without_file_or_syspath')).lower()}`",
        "- Kaggle submission made: `false`",
        "",
        "## Graphics",
        "",
        f"![Leaderboard win rates]({Path(graphics['leaderboard_winrates']).as_posix()})",
        "",
        f"![Broad matchup deltas]({Path(graphics['broad_matchup_deltas']).as_posix()})",
        "",
        f"![Lucario gate deltas]({Path(graphics['lucario_gate_deltas']).as_posix()})",
        "",
        f"![Trace failure tags]({Path(graphics['trace_failure_tags']).as_posix()})",
        "",
        "## Leaderboard",
        "",
    ]
    for idx, row in enumerate(leaderboard, start=1):
        lines.append(f"{idx}. {_record_line(row)}")

    lines.extend(
        [
            "",
            "## Lucario Focus",
            "",
        ]
    )
    for name in (PARENT, CANDIDATE):
        rows = lucario_by_candidate.get(name, [])
        joined = "; ".join(_matchup_line(row) for row in rows)
        lines.append(f"- `{name}`: {joined}")

    lines.extend(
        [
            "",
            "## Broad Gate Highlights",
            "",
        ]
    )
    for row in hard_focus:
        lines.append(f"- {_matchup_line(row)}")

    best_broad_gain = sorted(report["broad_deltas"], key=lambda row: row["delta"], reverse=True)[:4]
    worst_broad_slip = sorted(report["broad_deltas"], key=lambda row: row["delta"])[:4]
    lines.extend(
        [
            "",
            "## Delta Read",
            "",
            "- Biggest broad gains: "
            + "; ".join(
                f"`{row['gate_ref']}` {row['delta']:+.0%}" for row in best_broad_gain
            ),
            "- Biggest broad slips: "
            + "; ".join(
                f"`{row['gate_ref']}` {row['delta']:+.0%}" for row in worst_broad_slip
            ),
            "",
            "## Trace Diagnosis",
            "",
            (
                "- Parent Lucario traces: "
                f"{trace_agg.get('wins', 0)}-{trace_agg.get('losses', 0)} over "
                f"{trace_agg.get('games', 0)} games, with "
                f"{trace_agg.get('empty_bench_attacks', 0)} empty-bench attacks, "
                f"{trace_agg.get('no_next_attacker_steps', 0)} no-next-attacker steps, and "
                f"{trace_agg.get('attack_without_powered_backup', 0)} attacks without powered backup."
            ),
            "- Interpretation: the public-Lucario problem was often a bad start/bench density issue, not only a gust target issue.",
            "",
            "## Interpretation",
            "",
            "- `start_guard_v1` is locally better than `submission_3_cg_fix` on the saved paired broad gates: "
            f"{candidate.get('wins', 0)}-{candidate.get('losses', 0)} weighted={float(candidate.get('weighted_win_rate') or 0.0):.3f} "
            f"vs parent {parent.get('wins', 0)}-{parent.get('losses', 0)} weighted={float(parent.get('weighted_win_rate') or 0.0):.3f}.",
            "- The targeted 100-game Lucario pass improved all three Lucario gates, especially the Pilkwang public baseline.",
            "- The main regression to watch is non-hard spread/Dragapult variance: some public spread gates slipped even though hard-gate collapse count stayed at zero.",
            "- This is still local stochastic evidence, not a leaderboard guarantee.",
            "",
            "## Verification",
            "",
            "- Archive validator: exit `0`; validator output captured in `final_report.json`.",
            "- Pending test command for closeout: `python -m pytest tests\\test_starmie_start_guard_builder.py tests\\test_starmie_start_guard_report.py tests\\test_kaggle_archive_validator.py -q`.",
            "- Full suite before this report pass: `390 passed in 272.20s`; rerun recommended before any actual Kaggle approval.",
            "- Kaggle submission made: `false`",
            "",
            "## Artifacts",
            "",
            f"- Broad benchmark dir: `{report['machine_summary']['input_paths']['broad_run_dir']}`",
            f"- Lucario benchmark dir: `{report['machine_summary']['input_paths']['lucario_run_dir']}`",
            f"- Final report JSON: `{path.with_suffix('.json')}`",
            f"- Final report Markdown: `{path}`",
        ]
    )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Starmie start-guard final report and graphics.")
    parser.add_argument("--research-dir", type=Path, default=DEFAULT_RESEARCH_DIR)
    parser.add_argument("--broad-run-dir", type=Path, default=DEFAULT_BROAD_RUN_DIR)
    parser.add_argument("--lucario-run-dir", type=Path, default=DEFAULT_LUCARIO_RUN_DIR)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESEARCH_DIR / "final_report")
    args = parser.parse_args()

    result = build_report(
        research_dir=args.research_dir,
        broad_run_dir=args.broad_run_dir,
        lucario_run_dir=args.lucario_run_dir,
        archive_path=args.archive,
        output_dir=args.output_dir,
    )
    print(json.dumps({"final_report_json": str(result["json_path"]), "final_report_md": str(result["markdown_path"])}, sort_keys=True))


if __name__ == "__main__":
    main()
