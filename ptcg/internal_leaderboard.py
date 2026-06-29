from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from ptcg.kaggle_archive_validator import validate_archive_startup
from ptcg.meta_archetypes import classify_deck
from ptcg.native_eval import smoke_native_agent_vs_agent


CURRENT_META_URL = "https://ptcg-kaggle-meta.vercel.app/api/meta?page=1"
DEFAULT_CHAMPION_REF = "54079056"

CANONICAL_ALIASES = {
    "dragapult": "dragapult_spread",
    "starmie": "mega_starmie",
    "team_rocket": "team_rocket_petrel",
}

HARD_GATE_ARCHETYPES = {
    "alakazam",
    "archaludon",
    "dragapult_spread",
    "hop_trevenant",
    "lucario",
    "mega_starmie",
    "team_rocket_petrel",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_deck_csv(path: Path) -> list[int]:
    deck: list[int] = []
    for token in path.read_text(encoding="utf-8").replace(",", "\n").splitlines():
        token = token.strip()
        if token:
            deck.append(int(token))
    return deck


def archive_name(path: Path) -> str:
    name = path.name
    return name[:-7] if name.endswith(".tar.gz") else path.stem


def safe_slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "item"


def normalize_archetype(value: str | None) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    return CANONICAL_ALIASES.get(key, key or "unknown")


def canonical_archetype_from_meta_row(row: dict[str, Any]) -> str:
    name = str(row.get("name") or row.get("title") or row.get("slug") or "").lower()
    signature_ids = [
        int(card["id"])
        for card in row.get("signatureCards", []) or []
        if isinstance(card, dict) and isinstance(card.get("id"), int)
    ]
    if "lucario" in name or "riolu" in name:
        return "lucario"
    if "dragapult" in name or "drakloak" in name or "dreepy" in name:
        return "dragapult_spread"
    if "phantump" in name or "trevenant" in name:
        return "hop_trevenant"
    if "alakazam" in name or "kadabra" in name or "abra" in name:
        return "alakazam"
    if "petrel" in name or "team rocket" in name:
        return "team_rocket_petrel"
    if "starmie" in name or "mega signal" in name:
        return "mega_starmie"
    if "archaludon" in name or "duraludon" in name:
        return "archaludon"
    if signature_ids:
        return classify_deck(signature_ids).primary
    return "unknown"


def fetch_json_url(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_json_path_or_url(value: str | Path) -> dict[str, Any]:
    text = str(value)
    if text.startswith("http://") or text.startswith("https://"):
        return fetch_json_url(text)
    return json.loads(Path(value).read_text(encoding="utf-8"))


def meta_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows = snapshot.get("archetypes")
    if not isinstance(rows, list):
        rows = snapshot.get("rows")
    if not isinstance(rows, list):
        rows = snapshot.get("data")
    if not isinstance(rows, list):
        rows = snapshot.get("decks")
    return [row for row in rows or [] if isinstance(row, dict)]


def _raw_meta_weight(row: dict[str, Any], total_decks: int | None) -> float:
    if row.get("metaShare") is not None:
        return float(row["metaShare"]) * 100.0
    if row.get("appearances") is not None and total_decks:
        return float(row["appearances"]) / float(total_decks) * 100.0
    if row.get("deckCount") is not None and total_decks:
        return float(row["deckCount"]) / float(total_decks) * 100.0
    return float(row.get("raw_weight", 0.0) or 0.0)


def meta_weights_from_snapshot(snapshot: dict[str, Any], *, top_n: int | None = None) -> dict[str, dict[str, Any]]:
    total_decks = snapshot.get("totalDecks")
    total_decks = int(total_decks) if isinstance(total_decks, int) else None
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    weights: dict[str, dict[str, Any]] = {}
    rows = meta_rows(snapshot)
    if top_n is not None:
        rows = rows[:top_n]
    for row in rows:
        archetype = canonical_archetype_from_meta_row(row)
        if archetype == "unknown":
            continue
        raw_weight = _raw_meta_weight(row, total_decks)
        if raw_weight <= 0:
            continue
        entry = weights.setdefault(
            archetype,
            {
                "archetype": archetype,
                "raw_weight": 0.0,
                "date": snapshot.get("date"),
                "latest_date": snapshot.get("latestDate"),
                "redirected": snapshot.get("redirected"),
                "total_decks": snapshot.get("totalDecks"),
                "dataset_url": source.get("datasetUrl"),
                "labels": [],
            },
        )
        entry["raw_weight"] += raw_weight
        entry["labels"].append(str(row.get("name") or row.get("title") or row.get("slug") or archetype))
    return weights


def _safe_extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            member_name = member.name.replace("\\", "/").lstrip("./")
            if not member_name or member_name.startswith("../") or ":" in member_name.split("/", 1)[0]:
                raise ValueError(f"unsafe archive member: {member.name}")
            target = (base / member_name).resolve()
            try:
                target.relative_to(base)
            except ValueError as exc:
                raise ValueError(f"unsafe archive member: {member.name}") from exc
            member.name = member_name
            tf.extract(member, base)


def strategy_label_from_name(name: str, archetype: str, policy_module_loaded: bool) -> str:
    lower = name.lower()
    if "web_teacher" in lower and "pathfix" in lower:
        return "lucario_web_teacher_champion_floor"
    if "web_teacher" in lower:
        return "lucario_web_teacher"
    if "next_attacker" in lower:
        return "next_attacker_broad"
    if "less_preserving" in lower or "track_a" in lower:
        return "track_a_target_control"
    if "hop_trevenant" in lower:
        return "hop_trevenant_resilience"
    if "dragapult" in lower:
        return "dragapult_spread_response"
    if "champion" in lower:
        return "legacy_champion_archive"
    if not policy_module_loaded:
        return f"{archetype}_single_file_or_inline"
    return archetype


def build_candidate_registry(archives: Iterable[Path], *, extract_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    extract_root.mkdir(parents=True, exist_ok=True)
    for archive in sorted(Path(path) for path in archives):
        archive = archive.resolve()
        name = archive_name(archive)
        row: dict[str, Any] = {
            "name": name,
            "archive": str(archive),
            "sha256": sha256_file(archive) if archive.exists() else None,
            "validator_ok": False,
            "validation_error": None,
            "eligible_for_benchmark": False,
            "warnings": [],
            "main_path": None,
            "deck_path": None,
            "archetype": "unknown",
            "strategy_label": "unknown",
        }
        try:
            validation = validate_archive_startup(archive)
            row.update(validation)
            row["validator_ok"] = True
            destination = extract_root / f"{safe_slug(name)}_{str(row['sha256'])[:12]}"
            if destination.exists():
                shutil.rmtree(destination)
            _safe_extract_archive(archive, destination)
            main_path = destination / "main.py"
            deck_path = destination / "deck.csv"
            deck = read_deck_csv(deck_path)
            archetype = classify_deck(deck).primary
            row.update(
                {
                    "main_path": str(main_path),
                    "deck_path": str(deck_path),
                    "deck_len": len(deck),
                    "archetype": archetype,
                    "strategy_label": strategy_label_from_name(
                        name,
                        archetype,
                        bool(row.get("policy_module_loaded")),
                    ),
                }
            )
            if not row.get("policy_module_loaded"):
                row["warnings"].append("policy_module_not_loaded")
            row["eligible_for_benchmark"] = (
                bool(row.get("validator_ok"))
                and bool(row.get("required_members_present"))
                and int(row.get("deck_len") or 0) == 60
                and main_path.exists()
                and deck_path.exists()
            )
        except Exception as exc:
            row["validation_error"] = f"{type(exc).__name__}:{exc}"
        rows.append(row)
    return rows


def _manifest_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    return []


def build_gate_rows(
    manifest_paths: Iterable[Path],
    *,
    meta_snapshot: dict[str, Any] | None = None,
    include_unavailable_meta: bool = True,
) -> list[dict[str, Any]]:
    weights = meta_weights_from_snapshot(meta_snapshot) if meta_snapshot else {}
    available: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        path = Path(manifest_path)
        if not path.exists():
            continue
        for row in _manifest_rows(path):
            source_archetype = str(row.get("archetype") or row.get("classification") or "")
            archetype = normalize_archetype(source_archetype)
            available.append(
                {
                    "ref": str(row.get("ref") or f"{path.stem}/{archetype}"),
                    "title": row.get("title"),
                    "source_manifest": str(path),
                    "source_archetype": source_archetype,
                    "archetype": archetype,
                    "main_path": row.get("main_path") or row.get("pilot_path"),
                    "deck_path": row.get("deck_path"),
                    "ok": bool(row.get("ok")),
                    "available": bool(row.get("ok")) and bool(row.get("main_path") or row.get("pilot_path")) and bool(row.get("deck_path")),
                    "errors": list(row.get("errors") or []),
                    "raw_weight": float(row.get("raw_weight") or 0.0),
                    "gate_weight": 0.0,
                    "hard_gate": archetype in HARD_GATE_ARCHETYPES,
                    "tags": list(row.get("tags") or []),
                    "source_url": row.get("source_url"),
                    "snapshot_date": row.get("snapshot_date"),
                    "kaggle_dataset_url": row.get("kaggle_dataset_url"),
                }
            )

    available_counts: dict[str, int] = {}
    for row in available:
        if row["available"]:
            available_counts[row["archetype"]] = available_counts.get(row["archetype"], 0) + 1

    for row in available:
        weight_entry = weights.get(row["archetype"])
        if weight_entry:
            row["raw_weight"] = float(weight_entry["raw_weight"])
            row["snapshot_date"] = weight_entry.get("date")
            row["latest_date"] = weight_entry.get("latest_date")
            row["redirected"] = weight_entry.get("redirected")
            row["total_decks"] = weight_entry.get("total_decks")
            row["kaggle_dataset_url"] = weight_entry.get("dataset_url")
        divisor = available_counts.get(row["archetype"], 1)
        row["gate_weight"] = float(row["raw_weight"] or 1.0) / float(divisor)

    if include_unavailable_meta:
        present = {row["archetype"] for row in available if row["available"]}
        for archetype, weight_entry in sorted(weights.items()):
            if archetype in present or archetype not in HARD_GATE_ARCHETYPES:
                continue
            available.append(
                {
                    "ref": f"current_meta/{archetype}",
                    "title": " / ".join(weight_entry.get("labels") or [archetype]),
                    "source_manifest": None,
                    "source_archetype": archetype,
                    "archetype": archetype,
                    "main_path": None,
                    "deck_path": None,
                    "ok": False,
                    "available": False,
                    "errors": ["no available local gate for live meta archetype"],
                    "raw_weight": float(weight_entry["raw_weight"]),
                    "gate_weight": float(weight_entry["raw_weight"]),
                    "hard_gate": True,
                    "tags": [archetype],
                    "source_url": None,
                    "snapshot_date": weight_entry.get("date"),
                    "latest_date": weight_entry.get("latest_date"),
                    "redirected": weight_entry.get("redirected"),
                    "total_decks": weight_entry.get("total_decks"),
                    "kaggle_dataset_url": weight_entry.get("dataset_url"),
                }
            )
    return available


def _candidate_key(row: dict[str, Any]) -> str:
    return str(row.get("candidate") or row.get("name") or row.get("candidate_id") or "")


def _win_rate(row: dict[str, Any]) -> float:
    finished = int(row.get("finished") or 0)
    return float(row.get("wins") or 0) / finished if finished else 0.0


def rank_candidates(
    candidates: Iterable[dict[str, Any]],
    matchup_rows: Iterable[dict[str, Any]],
    *,
    hard_gate_floor: float = 0.35,
) -> list[dict[str, Any]]:
    candidate_rows = {str(row.get("name") or row.get("candidate")): row for row in candidates}
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in candidate_rows}
    for row in matchup_rows:
        grouped.setdefault(str(row.get("candidate")), []).append(row)

    leaderboard: list[dict[str, Any]] = []
    for candidate, source_row in candidate_rows.items():
        rows = grouped.get(candidate, [])
        total_finished = sum(int(row.get("finished") or 0) for row in rows)
        total_wins = sum(int(row.get("wins") or 0) for row in rows)
        total_losses = sum(int(row.get("losses") or 0) for row in rows)
        total_draws = sum(int(row.get("draws") or 0) for row in rows)
        error_count = sum(len(row.get("errors") or []) for row in rows)
        weighted_total = sum(float(row.get("gate_weight") or 1.0) for row in rows if int(row.get("finished") or 0) > 0)
        weighted_rate = (
            sum(_win_rate(row) * float(row.get("gate_weight") or 1.0) for row in rows if int(row.get("finished") or 0) > 0)
            / weighted_total
            if weighted_total
            else 0.0
        )
        raw_rate = total_wins / total_finished if total_finished else 0.0
        collapses = [
            {
                "gate_ref": row.get("gate_ref") or row.get("opponent"),
                "archetype": normalize_archetype(str(row.get("archetype") or "")),
                "win_rate": _win_rate(row),
                "finished": int(row.get("finished") or 0),
                "floor": hard_gate_floor,
            }
            for row in rows
            if bool(row.get("hard_gate"))
            and int(row.get("finished") or 0) > 0
            and _win_rate(row) < hard_gate_floor
        ]
        floor_penalty = 0.0
        if weighted_total:
            for row in rows:
                if not bool(row.get("hard_gate")) or int(row.get("finished") or 0) <= 0:
                    continue
                rate = _win_rate(row)
                if rate < hard_gate_floor:
                    floor_penalty += (hard_gate_floor - rate) * float(row.get("gate_weight") or 1.0) / weighted_total
        error_penalty = min(0.25, error_count * 0.03)
        eligible = bool(source_row.get("eligible_for_benchmark", True))
        promotable = eligible and total_finished > 0 and error_count == 0 and not collapses
        leaderboard.append(
            {
                "candidate": candidate,
                "archive": source_row.get("archive"),
                "sha256": source_row.get("sha256"),
                "archetype": source_row.get("archetype"),
                "strategy_label": source_row.get("strategy_label"),
                "eligible_for_benchmark": eligible,
                "wins": total_wins,
                "losses": total_losses,
                "draws": total_draws,
                "finished": total_finished,
                "raw_win_rate": raw_rate,
                "weighted_win_rate": weighted_rate,
                "hard_gate_floor": hard_gate_floor,
                "hard_gate_collapses": collapses,
                "errors": error_count,
                "leaderboard_score": weighted_rate - floor_penalty - error_penalty,
                "promotable": promotable,
                "matchups": rows,
            }
        )
    leaderboard.sort(
        key=lambda row: (
            -float(row["leaderboard_score"]),
            len(row["hard_gate_collapses"]),
            int(row["errors"]),
            -float(row["weighted_win_rate"]),
            str(row["candidate"]),
        )
    )
    return leaderboard


def benchmark_candidates(
    candidates: Iterable[dict[str, Any]],
    gates: Iterable[dict[str, Any]],
    *,
    games: int,
    seed: int,
    sdk_path: Path = Path("data/official"),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    runnable_gates = [gate for gate in gates if gate.get("available") and gate.get("ok")]
    for candidate_index, candidate in enumerate(candidates):
        if not candidate.get("eligible_for_benchmark"):
            continue
        for gate_index, gate in enumerate(runnable_gates):
            result = smoke_native_agent_vs_agent(
                candidate_main_path=Path(str(candidate["main_path"])),
                candidate_deck_path=Path(str(candidate["deck_path"])),
                opponent_main_path=Path(str(gate["main_path"])),
                opponent_deck_path=Path(str(gate["deck_path"])),
                sdk_path=sdk_path,
                games=games,
                seed=seed + candidate_index * 1000 + gate_index,
            )
            rows.append(
                {
                    "candidate": candidate["name"],
                    "gate_ref": gate["ref"],
                    "archetype": gate["archetype"],
                    "wins": result.wins,
                    "losses": result.losses,
                    "draws": result.draws,
                    "finished": result.finished,
                    "games": result.games,
                    "errors": list(result.errors),
                    "gate_weight": gate.get("gate_weight") or gate.get("raw_weight") or 1.0,
                    "hard_gate": bool(gate.get("hard_gate")),
                }
            )
    return rows


def build_submit_offer(
    leaderboard: list[dict[str, Any]],
    *,
    champion_ref: str = DEFAULT_CHAMPION_REF,
    blocking_gate_gaps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    blocking_gate_gaps = blocking_gate_gaps or []
    top = leaderboard[0] if leaderboard else None
    recommend = bool(top and top.get("promotable") and not blocking_gate_gaps)
    reason = "no benchmarked candidate"
    if top and not top.get("promotable"):
        reason = "top candidate is not promotable under hard-gate/error checks"
    elif top and blocking_gate_gaps:
        reason = "live meta has hard-gate coverage gaps"
    elif top and recommend:
        reason = "top candidate passed local hard-gate/error checks; user approval still required"
    return {
        "kaggle_submission_made": False,
        "requires_user_approval": True,
        "champion_floor_ref": champion_ref,
        "recommend_submit": recommend,
        "recommended_candidate": top["candidate"] if recommend and top else None,
        "top_candidate": top,
        "blocking_gate_gaps": blocking_gate_gaps,
        "reason": reason,
    }


def render_markdown_report(
    *,
    meta_snapshot: dict[str, Any] | None,
    candidate_registry: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
    leaderboard: list[dict[str, Any]],
    submit_offer: dict[str, Any],
    command: str,
    git_status: str,
    games: int,
    seed: int,
) -> str:
    lines = [
        "# Internal Leaderboard",
        "",
        f"- Command: `{command}`",
        f"- Git status: `{git_status.strip() or 'clean'}`",
        f"- Meta date: `{(meta_snapshot or {}).get('date')}`",
        f"- Latest meta date: `{(meta_snapshot or {}).get('latestDate')}`",
        f"- Total decks: `{(meta_snapshot or {}).get('totalDecks')}`",
        f"- Dataset: `{((meta_snapshot or {}).get('source') or {}).get('datasetUrl')}`",
        f"- Candidate archives: `{len(candidate_registry)}`",
        f"- Gates: `{len(gate_rows)}`",
        f"- Available gates: `{sum(1 for row in gate_rows if row.get('available'))}`",
        f"- Games per matchup: `{games}`",
        f"- Seed: `{seed}`",
        "- Kaggle submission made: `false`",
        "",
        "## Ranking",
        "",
    ]
    for index, row in enumerate(leaderboard[:20], start=1):
        lines.append(
            f"{index}. `{row['candidate']}` score={row['leaderboard_score']:.3f} "
            f"weighted_wr={row['weighted_win_rate']:.3f} raw_wr={row['raw_win_rate']:.3f} "
            f"errors={row['errors']} collapses={len(row['hard_gate_collapses'])} "
            f"promotable={str(row['promotable']).lower()}"
        )
    lines.extend(["", "## Submit Offer", "", f"- Recommend submit: `{str(submit_offer['recommend_submit']).lower()}`"])
    lines.append(f"- Reason: {submit_offer['reason']}")
    if submit_offer.get("recommended_candidate"):
        lines.append(f"- Candidate: `{submit_offer['recommended_candidate']}`")
    gaps = submit_offer.get("blocking_gate_gaps") or []
    if gaps:
        lines.extend(["", "## Blocking Gate Gaps", ""])
        for gap in gaps:
            lines.append(f"- `{gap['archetype']}` weight={gap['gate_weight']:.3f}: {', '.join(gap['errors'])}")
    return "\n".join(lines) + "\n"
