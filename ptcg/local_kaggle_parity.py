from __future__ import annotations

import json
import hashlib
import re
import tarfile
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ptcg.failure_taxonomy import classify_failure
from ptcg.kaggle_archive_validator import validate_archive_startup
from ptcg.native_eval import smoke_native_agent_vs_agent
from ptcg.round_robin import prepare_submission_packages


class LocalKaggleParityError(RuntimeError):
    pass


HIDDEN_PATH_RE = re.compile(
    r"([A-Za-z]:[\\/](?:Users|Documents|Downloads)[\\/]|C:[\\/]Users[\\/]|/Users/|/home/)",
    re.IGNORECASE,
)


def run_local_kaggle_parity(
    *,
    archive: Path | str,
    output_dir: Path | str,
    smoke_games: int = 1,
    seed: int = 0,
    sdk_path: Path | str = Path("data/official"),
    max_steps: int = 1000,
    command: str | None = None,
) -> dict[str, Any]:
    archive_path = Path(archive).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "parity_events.jsonl"
    if events_path.exists():
        events_path.unlink()

    failures: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "workflow": "local_kaggle_parity",
        "status": "running",
        "archive": str(archive_path),
        "archive_sha256": _sha256_file(archive_path) if archive_path.exists() else None,
        "output_dir": str(output.resolve()),
        "archive_validation": None,
        "required_files": {},
        "hidden_local_path_markers": [],
        "smoke": None,
        "gameplay_logs_read": 0,
        "used_archived_or_quarantined_logs": False,
        "source_folders_written": False,
        "official_sdk_seed_control": False,
        "crn_available": False,
        "kaggle_submission_made": False,
    }
    run_config = {
        "archive": str(archive_path),
        "archive_sha256": summary["archive_sha256"],
        "output_dir": str(output.resolve()),
        "smoke_games": int(smoke_games),
        "seed": int(seed),
        "sdk_path": str(Path(sdk_path).resolve()),
        "max_steps": int(max_steps),
        "command": command,
        "kaggle_submission_made": False,
    }
    _write_json(output / "run_config.json", run_config)
    _event(events_path, "start", "ok", archive=str(archive_path), command=command)

    try:
        validation = validate_archive_startup(archive_path)
        summary["archive_validation"] = validation
        _event(events_path, "archive_validation", "ok", deck_len=validation.get("deck_len"))
    except Exception as exc:
        failure = _failure("archive_validation", exc)
        failures.append(failure)
        summary["status"] = "failed"
        _event(events_path, "archive_validation", "failed", message=failure["message"])
        _write_outputs(output, summary, failures)
        raise LocalKaggleParityError(f"validation failed: {exc}") from exc

    extract_dir = output / "extracted_candidate"
    try:
        if extract_dir.exists():
            _remove_tree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_tar(archive_path, extract_dir)
        package_dir = _find_package_dir(extract_dir)
        if package_dir is None:
            raise LocalKaggleParityError("archive extraction did not produce main.py and deck.csv")
        required = {
            "main.py": (package_dir / "main.py").exists(),
            "deck.csv": (package_dir / "deck.csv").exists(),
            "cg/api.py": (package_dir / "cg" / "api.py").exists(),
        }
        summary["required_files"] = required
        missing = [name for name, exists in required.items() if not exists]
        if missing:
            raise LocalKaggleParityError(f"missing required files after extraction: {missing}")
        markers = _scan_hidden_local_paths(package_dir)
        summary["hidden_local_path_markers"] = markers
        if markers:
            raise LocalKaggleParityError(f"hidden local path markers found: {markers}")
        _event(events_path, "extract_and_scan", "ok", package_dir=str(package_dir.resolve()))
    except Exception as exc:
        failure = _failure("extract_and_scan", exc)
        failures.append(failure)
        summary["status"] = "failed"
        _event(events_path, "extract_and_scan", "failed", message=failure["message"])
        _write_outputs(output, summary, failures)
        if "hidden local path" in str(exc):
            raise LocalKaggleParityError(f"hidden local path check failed: {exc}") from exc
        raise LocalKaggleParityError(f"extraction failed: {exc}") from exc

    smoke_payload = {
        "enabled": int(smoke_games) > 0,
        "games": int(smoke_games),
        "seed": int(seed),
        "max_steps": int(max_steps),
        "result": None,
    }
    if smoke_games > 0:
        try:
            packages = prepare_submission_packages([archive_path], extract_root=output / "prepared")
            package = packages[0]
            smoke_result = smoke_native_agent_vs_agent(
                candidate_main_path=Path(package.main_path),
                candidate_deck_path=Path(package.deck_path),
                opponent_main_path=Path(package.main_path),
                opponent_deck_path=Path(package.deck_path),
                sdk_path=Path(sdk_path),
                games=int(smoke_games),
                seed=int(seed),
                max_steps=int(max_steps),
            )
            smoke_payload["result"] = asdict(smoke_result)
            if smoke_result.errors:
                failures.append(
                    {
                        "stage": "smoke_evaluation",
                        "category": "runtime_exception",
                        "archive": str(archive_path),
                        "matchup": "self_smoke",
                        "seed": int(seed),
                        "game_index": None,
                        "type": "SmokeEvaluationError",
                        "message": "; ".join(smoke_result.errors),
                        "traceback": "",
                    }
                )
            _event(events_path, "smoke_evaluation", "ok", errors=len(smoke_result.errors))
        except Exception as exc:
            failure = _failure("smoke_evaluation", exc)
            failures.append(failure)
            _event(events_path, "smoke_evaluation", "failed", message=failure["message"])
    else:
        _event(events_path, "smoke_evaluation", "skipped", games=0)

    summary["smoke"] = smoke_payload
    summary["status"] = "failed" if failures else "passed"
    _event(events_path, "complete", summary["status"], failures=len(failures))
    _write_outputs(output, summary, failures)
    if failures:
        raise LocalKaggleParityError(f"local parity failed: {failures[0]['message']}")
    return {
        "summary": summary,
        "failures": failures,
        "report_paths": {
            "summary": str((output / "parity_summary.json").resolve()),
            "events": str(events_path.resolve()),
            "failures": str((output / "failures.json").resolve()),
            "run_config": str((output / "run_config.json").resolve()),
        },
        "kaggle_submission_made": False,
    }


def _write_outputs(output: Path, summary: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    _write_json(output / "parity_summary.json", summary)
    _write_json(output / "failures.json", failures)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _event(path: Path, stage: str, status: str, **fields: Any) -> None:
    row = {"stage": stage, "status": status, **fields}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _failure(stage: str, exc: Exception) -> dict[str, Any]:
    return {
        "stage": stage,
        "category": classify_failure(stage, type(exc).__name__, str(exc)),
        "archive": None,
        "matchup": None,
        "seed": None,
        "game_index": None,
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(limit=5),
    }


def _safe_extract_tar(path: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk():
                raise LocalKaggleParityError(f"archive contains unsupported link member: {member.name}")
            member_name = member.name.replace("\\", "/").lstrip("./")
            if not member_name:
                continue
            target = (root / member_name).resolve()
            target.relative_to(root)
            member.name = member_name
            tf.extract(member, root)


def _find_package_dir(root: Path) -> Path | None:
    candidates = [
        path
        for path in [root, *root.rglob("*")]
        if path.is_dir() and (path / "main.py").exists() and (path / "deck.csv").exists()
    ]
    candidates.sort(key=lambda path: (len(path.relative_to(root).parts), str(path)))
    return candidates[0] if candidates else None


def _scan_hidden_local_paths(package_dir: Path) -> list[dict[str, str]]:
    markers: list[dict[str, str]] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".py", ".csv", ".json", ".txt", ".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in HIDDEN_PATH_RE.finditer(text):
            markers.append(
                {
                    "path": str(path.resolve()),
                    "marker": match.group(0),
                }
            )
    return markers


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
