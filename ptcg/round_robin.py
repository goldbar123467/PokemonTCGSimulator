from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable, Any

from ptcg.kaggle_archive_validator import validate_archive_startup
from ptcg.native_eval import smoke_native_agent_vs_agent


@dataclass(frozen=True)
class PreparedSubmission:
    name: str
    source_path: str
    source_format: str
    source_sha256: str
    package_dir: str
    main_path: str
    deck_path: str
    deck_len: int
    deck_sha256: str
    bundled_cg: bool
    strict_validation_ok: bool
    validation_error: str | None
    eligible_for_round_robin: bool
    warnings: tuple[str, ...]


def prepare_submission_packages(
    sources: Iterable[Path | str],
    *,
    extract_root: Path,
) -> list[PreparedSubmission]:
    extract_root.mkdir(parents=True, exist_ok=True)
    packages: list[PreparedSubmission] = []
    for source in sources:
        source_path = Path(source).resolve()
        packages.append(_prepare_one_submission(source_path, extract_root=extract_root))
    return packages


def run_round_robin(
    packages: Iterable[PreparedSubmission],
    *,
    output_dir: Path,
    games_per_pair: int,
    seed: int,
    sdk_path: Path = Path("data/official"),
    max_steps: int = 1000,
    command: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    package_rows = [package for package in packages if package.eligible_for_round_robin]
    matrix: list[dict[str, Any]] = []

    for candidate_index, candidate in enumerate(package_rows):
        for opponent_index, opponent in enumerate(package_rows):
            if candidate.name == opponent.name:
                continue
            matchup_seed = seed + candidate_index * 10000 + opponent_index * 101
            result = smoke_native_agent_vs_agent(
                candidate_main_path=Path(candidate.main_path),
                candidate_deck_path=Path(candidate.deck_path),
                opponent_main_path=Path(opponent.main_path),
                opponent_deck_path=Path(opponent.deck_path),
                sdk_path=sdk_path,
                games=games_per_pair,
                seed=matchup_seed,
                max_steps=max_steps,
            )
            matrix.append(
                {
                    "candidate": candidate.name,
                    "opponent": opponent.name,
                    "candidate_source": candidate.source_path,
                    "opponent_source": opponent.source_path,
                    "candidate_sha256": candidate.source_sha256,
                    "opponent_sha256": opponent.source_sha256,
                    "seed": matchup_seed,
                    "games": result.games,
                    "finished": result.finished,
                    "wins": result.wins,
                    "losses": result.losses,
                    "draws": result.draws,
                    "errors": list(result.errors),
                    "win_rate": _rate(result.wins, result.finished),
                    "loss_rate": _rate(result.losses, result.finished),
                    "draw_rate": _rate(result.draws, result.finished),
                }
            )

    totals = {
        "scheduled_games": sum(int(row["games"]) for row in matrix),
        "finished": sum(int(row["finished"]) for row in matrix),
        "wins": sum(int(row["wins"]) for row in matrix),
        "losses": sum(int(row["losses"]) for row in matrix),
        "draws": sum(int(row["draws"]) for row in matrix),
        "errors": sum(len(row["errors"]) for row in matrix),
    }
    leaderboard = _leaderboard(package_rows, matrix)
    summary = {
        "engine": "official_cg_sdk",
        "engine_path": str(sdk_path.resolve()),
        "engine_parity_status": "uses official cg.game; clean-room native parity is tracked separately",
        "package_count": len(package_rows),
        "opponent_count": len(package_rows),
        "replay_count": 0,
        "games_per_pair": games_per_pair,
        "seed": seed,
        "max_steps": max_steps,
        "command": command,
        "git_status": _git_status(),
        "python": sys.version,
        "totals": totals,
        "packages": [asdict(package) for package in package_rows],
        "package_paths": [package.source_path for package in package_rows],
        "sha256s": {package.name: package.source_sha256 for package in package_rows},
        "leaderboard": leaderboard,
        "kaggle_submission_made": False,
    }

    package_registry_path = output_dir / "submission_registry.json"
    matrix_path = output_dir / "matchup_matrix.json"
    leaderboard_path = output_dir / "leaderboard.json"
    summary_path = output_dir / "summary.json"
    markdown_path = output_dir / "round_robin.md"

    _write_json(package_registry_path, [asdict(package) for package in package_rows])
    _write_json(matrix_path, matrix)
    _write_json(leaderboard_path, leaderboard)
    _write_json(summary_path, summary)
    markdown_path.write_text(
        _render_markdown(summary=summary, matrix=matrix, leaderboard=leaderboard),
        encoding="utf-8",
    )

    return {
        "summary": summary,
        "matchup_matrix": matrix,
        "leaderboard": leaderboard,
        "report_paths": {
            "summary": str(summary_path.resolve()),
            "matchup_matrix": str(matrix_path.resolve()),
            "leaderboard": str(leaderboard_path.resolve()),
            "submission_registry": str(package_registry_path.resolve()),
            "markdown": str(markdown_path.resolve()),
        },
        "kaggle_submission_made": False,
    }


def _prepare_one_submission(source_path: Path, *, extract_root: Path) -> PreparedSubmission:
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    source_format = _source_format(source_path)
    source_sha256 = _sha256_file(source_path)
    name = _submission_name(source_path)
    destination = extract_root / f"{_safe_slug(name)}_{source_sha256[:12]}"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    validation_target: Path | None = None
    if source_format == "zip":
        _safe_extract_zip(source_path, destination)
        nested = _find_nested_submission_tar(destination)
        validation_target = nested
    elif source_format == "tar.gz":
        validation_target = source_path
        _safe_extract_tar(source_path, destination)
    else:
        raise ValueError(f"unsupported submission format: {source_path}")

    package_dir = _find_package_dir(destination)
    if package_dir is None:
        raise ValueError(f"submission does not contain main.py and deck.csv: {source_path}")

    strict_ok, validation_error = _strict_validation(validation_target, package_dir=package_dir)
    deck_path = package_dir / "deck.csv"
    main_path = package_dir / "main.py"
    deck_cards = _read_deck(deck_path)
    bundled_cg = (package_dir / "cg" / "api.py").exists()
    warnings: list[str] = []
    if not strict_ok:
        warnings.append("strict_validation_failed")
    if not bundled_cg:
        warnings.append("uses_external_official_cg")
    eligible = main_path.exists() and deck_path.exists() and len(deck_cards) == 60
    return PreparedSubmission(
        name=name,
        source_path=str(source_path),
        source_format=source_format,
        source_sha256=source_sha256,
        package_dir=str(package_dir.resolve()),
        main_path=str(main_path.resolve()),
        deck_path=str(deck_path.resolve()),
        deck_len=len(deck_cards),
        deck_sha256=_deck_sha256(deck_cards),
        bundled_cg=bundled_cg,
        strict_validation_ok=strict_ok,
        validation_error=validation_error,
        eligible_for_round_robin=eligible,
        warnings=tuple(warnings),
    )


def _source_format(path: Path) -> str:
    lower = path.name.lower()
    if lower.endswith(".tar.gz"):
        return "tar.gz"
    if lower.endswith(".zip"):
        return "zip"
    return path.suffix.lower().lstrip(".") or "unknown"


def _submission_name(path: Path) -> str:
    name = path.name
    if name.lower().endswith(".tar.gz"):
        name = name[:-7]
    elif name.lower().endswith(".zip"):
        name = name[:-4]
    return _safe_slug(name)


def _safe_slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "submission"


def _safe_extract_tar(path: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(path, "r:gz") as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"archive contains unsupported link member: {member.name}")
            member_name = member.name.replace("\\", "/").lstrip("./")
            if not member_name:
                continue
            target = (root / member_name).resolve()
            target.relative_to(root)
            member.name = member_name
            tf.extract(member, root)


def _safe_extract_zip(path: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            member_name = info.filename.replace("\\", "/").lstrip("./")
            if not member_name:
                continue
            target = (root / member_name).resolve()
            target.relative_to(root)
            zf.extract(info, root)


def _find_package_dir(root: Path) -> Path | None:
    candidates = [
        path
        for path in [root, *root.rglob("*")]
        if path.is_dir() and (path / "main.py").exists() and (path / "deck.csv").exists()
    ]
    if not candidates:
        nested = _find_nested_submission_tar(root)
        if nested is None:
            return None
        nested_dir = root / f"{nested.stem}_expanded"
        _safe_extract_tar(nested, nested_dir)
        return _find_package_dir(nested_dir)
    candidates.sort(key=lambda path: (len(path.relative_to(root).parts), str(path)))
    return candidates[0]


def _find_nested_submission_tar(root: Path) -> Path | None:
    matches = sorted(root.rglob("*.tar.gz"))
    return matches[0] if matches else None


def _strict_validation(path: Path | None, *, package_dir: Path) -> tuple[bool, str | None]:
    if path is None:
        return False, "no tar.gz archive available for strict validation"
    try:
        validate_archive_startup(path)
        return True, None
    except Exception as exc:
        if isinstance(exc, ModuleNotFoundError) and (package_dir / "cg" / "api.py").exists():
            try:
                _validate_extracted_startup(package_dir)
                return True, None
            except Exception as fallback_exc:
                return False, f"{type(fallback_exc).__name__}:{fallback_exc}"
        return False, f"{type(exc).__name__}:{exc}"


def _validate_extracted_startup(package_dir: Path) -> None:
    old_path = sys.path[:]
    old_modules = set(sys.modules)
    env = {"__builtins__": __builtins__}
    try:
        package_root = str(package_dir.resolve())
        if package_root not in sys.path:
            sys.path.insert(0, package_root)
        main_path = package_dir / "main.py"
        exec(compile(main_path.read_text(encoding="utf-8"), str(main_path), "exec"), env)
        agent = env.get("agent")
        if not callable(agent):
            raise ValueError("main.py did not define callable agent")
        action = agent(
            {
                "current": None,
                "logs": [],
                "remainingOverageTime": 600,
                "search_begin_input": None,
                "select": None,
                "step": 0,
            }
        )
        deck = _read_deck(package_dir / "deck.csv")
        if list(action) != deck:
            raise ValueError("step-0 agent deck does not match deck.csv")
    finally:
        sys.path[:] = old_path
        for name in set(sys.modules) - old_modules:
            if name == "cg" or name.startswith("cg."):
                sys.modules.pop(name, None)


def _read_deck(path: Path) -> list[int]:
    cards: list[int] = []
    for token in path.read_text(encoding="utf-8").replace(",", "\n").splitlines():
        token = token.strip()
        if token:
            cards.append(int(token))
    return cards


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _deck_sha256(cards: list[int]) -> str:
    canonical = "".join(f"{card_id}\n" for card_id in cards).encode("ascii")
    return hashlib.sha256(canonical).hexdigest().upper()


def _rate(count: int, total: int) -> float:
    return float(count) / float(total) if total else 0.0


def _leaderboard(packages: list[PreparedSubmission], matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for package in packages:
        played = [row for row in matrix if row["candidate"] == package.name]
        finished = sum(int(row["finished"]) for row in played)
        wins = sum(int(row["wins"]) for row in played)
        losses = sum(int(row["losses"]) for row in played)
        draws = sum(int(row["draws"]) for row in played)
        errors = sum(len(row["errors"]) for row in played)
        rows.append(
            {
                "name": package.name,
                "source_path": package.source_path,
                "source_sha256": package.source_sha256,
                "finished": finished,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "errors": errors,
                "win_rate": _rate(wins, finished),
                "non_loss_rate": _rate(wins + draws, finished),
                "strict_validation_ok": package.strict_validation_ok,
                "warnings": list(package.warnings),
            }
        )
    rows.sort(key=lambda row: (-float(row["win_rate"]), int(row["errors"]), str(row["name"])))
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else result.stderr


def _render_markdown(
    *,
    summary: dict[str, Any],
    matrix: list[dict[str, Any]],
    leaderboard: list[dict[str, Any]],
) -> str:
    lines = [
        "# PTCG Round Robin",
        "",
        f"- Engine: `{summary['engine']}`",
        f"- Engine path: `{summary['engine_path']}`",
        f"- Packages: `{summary['package_count']}`",
        f"- Games per directed matchup: `{summary['games_per_pair']}`",
        f"- Seed label: `{summary['seed']}`",
        f"- Scheduled games: `{summary['totals']['scheduled_games']}`",
        f"- Finished games: `{summary['totals']['finished']}`",
        f"- Errors: `{summary['totals']['errors']}`",
        "- Kaggle submission made: `false`",
        "",
        "## Leaderboard",
        "",
    ]
    for index, row in enumerate(leaderboard, start=1):
        lines.append(
            f"{index}. `{row['name']}` win_rate={row['win_rate']:.3f} "
            f"finished={row['finished']} errors={row['errors']} warnings={','.join(row['warnings']) or 'none'}"
        )
    lines.extend(["", "## Matchups", ""])
    for row in matrix:
        lines.append(
            f"- `{row['candidate']}` vs `{row['opponent']}`: "
            f"{row['wins']}-{row['losses']}-{row['draws']} "
            f"finished={row['finished']} errors={len(row['errors'])}"
        )
    return "\n".join(lines) + "\n"
