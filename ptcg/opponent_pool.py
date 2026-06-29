from __future__ import annotations

from dataclasses import dataclass
import ast
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types
import zipfile


COMPETITION = "pokemon-tcg-ai-battle"


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    team_id: str
    team_name: str
    last_submission_date: str
    score: float
    submission_count: int
    members: tuple[str, ...]


@dataclass(frozen=True)
class KernelCandidate:
    ref: str
    title: str
    author: str
    votes: int
    score: int


@dataclass(frozen=True)
class ExtractedBundle:
    source_dir: Path
    work_dir: Path
    main_path: Path
    deck_path: Path | None


@dataclass(frozen=True)
class OpponentPoolEntry:
    ref: str
    title: str
    author: str
    votes: int
    source_dir: str
    main_path: str | None
    deck_path: str | None
    ok: bool
    errors: tuple[str, ...]


def parse_leaderboard_zip(path: Path) -> list[LeaderboardEntry]:
    with zipfile.ZipFile(path) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"no CSV file found in {path}")
        with zf.open(csv_names[0]) as handle:
            text = handle.read().decode("utf-8-sig")

    rows = csv.DictReader(text.splitlines())
    entries: list[LeaderboardEntry] = []
    for row in rows:
        members = tuple(
            member.strip()
            for member in (row.get("TeamMemberUserNames") or "").split(",")
            if member.strip()
        )
        entries.append(
            LeaderboardEntry(
                rank=int(row["Rank"]),
                team_id=row["TeamId"],
                team_name=row["TeamName"],
                last_submission_date=row["LastSubmissionDate"],
                score=float(row["Score"]),
                submission_count=int(row["SubmissionCount"]),
                members=members,
            )
        )
    return sorted(entries, key=lambda entry: entry.rank)


def _agent_keyword_score(title: str) -> int:
    lowered = title.lower()
    score = 0
    for keyword, weight in [
        ("agent", 10),
        ("baseline", 8),
        ("lucario", 8),
        ("alakazam", 6),
        ("mcts", 6),
        ("search", 5),
        ("heuristic", 5),
        ("submission", 4),
        ("eda", -8),
        ("viewer", -8),
        ("visualizer", -8),
    ]:
        if keyword in lowered:
            score += weight
    return score


def rank_kernel_candidates(kernels: list[dict]) -> list[KernelCandidate]:
    candidates: list[KernelCandidate] = []
    for kernel in kernels:
        title = str(kernel.get("title") or "")
        ref = str(kernel.get("ref") or "")
        author = str(kernel.get("author") or "")
        votes = int(kernel.get("votes") or 0)
        keyword_score = _agent_keyword_score(title)
        if keyword_score <= -8:
            continue
        candidates.append(
            KernelCandidate(
                ref=ref,
                title=title,
                author=author,
                votes=votes,
                score=keyword_score * 1000 + votes,
            )
        )
    return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.ref))


def _clean_writefile_source(source: str) -> tuple[str | None, str]:
    lines = source.splitlines()
    if not lines:
        return None, source
    first = lines[0].strip()
    if not first.startswith("%%writefile"):
        return None, source
    parts = first.split(maxsplit=1)
    if len(parts) != 2:
        return None, "\n".join(lines[1:]) + "\n"
    return parts[1].strip(), "\n".join(lines[1:]) + "\n"


def extract_kernel_sources(kernel_dir: Path, *, output_root: Path | None = None) -> ExtractedBundle:
    output_root = output_root or kernel_dir / "extracted_agent"
    output_root.mkdir(parents=True, exist_ok=True)
    notebook_sources: list[str] = []

    for py_path in kernel_dir.glob("*.py"):
        if py_path.name == "main.py":
            deck_path = kernel_dir / "deck.csv"
            return ExtractedBundle(kernel_dir, kernel_dir, py_path, deck_path if deck_path.exists() else None)

    for notebook_path in kernel_dir.glob("*.ipynb"):
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        for cell in notebook.get("cells", []):
            source_value = cell.get("source", "")
            source = "".join(source_value) if isinstance(source_value, list) else str(source_value)
            notebook_sources.append(source)
            filename, body = _clean_writefile_source(source)
            if filename is None:
                continue
            destination = output_root / Path(filename).name
            destination.write_text(body, encoding="utf-8")

    main_path = output_root / "main.py"
    if not main_path.exists():
        raise FileNotFoundError(f"no main.py found or extracted from {kernel_dir}")
    deck_path = output_root / "deck.csv"
    if not deck_path.exists():
        deck_path = write_deck_from_python_source(main_path, deck_path)
    if not deck_path.exists():
        for source in notebook_sources:
            deck_path = write_deck_from_python_text(source, deck_path)
            if deck_path.exists():
                break
    return ExtractedBundle(kernel_dir, output_root, main_path, deck_path if deck_path.exists() else None)


def write_deck_from_python_source(main_path: Path, deck_path: Path) -> Path:
    return write_deck_from_python_text(main_path.read_text(encoding="utf-8"), deck_path)


def write_deck_from_python_text(source: str, deck_path: Path) -> Path:
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("%"))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return deck_path
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not any(name in {"my_deck", "HARD_CODED_DECK", "deck", "DECK"} for name in names):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, list) and value and all(isinstance(item, int) for item in value):
            deck_path.write_text("\n".join(str(item) for item in value) + "\n", encoding="utf-8")
            return deck_path
    return deck_path


def _to_namespace(value):
    if isinstance(value, dict):
        return types.SimpleNamespace(**{key: _to_namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


class _EnumFallback:
    _KNOWN = {
        "DECK": 1,
        "HAND": 2,
        "DISCARD": 3,
        "ACTIVE": 4,
        "BENCH": 5,
        "PRIZE": 6,
        "STADIUM": 7,
        "ENERGY": 8,
        "TOOL": 9,
        "PRE_EVOLUTION": 10,
        "PLAYER": 11,
        "LOOKING": 12,
        "MAIN": 0,
        "CARD": 3,
        "ATTACHED_CARD": 2,
        "CARD_OR_ATTACHED_CARD": 3,
        "SKILL": 15,
        "ATTACK": 13,
        "EVOLVE": 9,
        "COUNT": 8,
        "YES_NO": 9,
        "SPECIAL_CONDITION": 16,
        "NUMBER": 0,
        "YES": 1,
        "NO": 2,
        "TOOL_CARD": 4,
        "ENERGY_CARD": 5,
        "PLAY": 7,
        "ATTACH": 8,
        "ABILITY": 10,
        "RETREAT": 12,
        "END": 14,
    }

    def __getattr__(self, name: str) -> int:
        value = self._KNOWN.get(name, abs(hash(name)) % 10000)
        setattr(self, name, value)
        return value


def _install_fake_cg_api() -> dict[str, types.ModuleType | None]:
    previous = {
        "cg": sys.modules.get("cg"),
        "cg.api": sys.modules.get("cg.api"),
    }
    cg_module = types.ModuleType("cg")
    api_module = types.ModuleType("cg.api")
    api_module.to_observation_class = _to_namespace
    api_module.all_card_data = lambda: []
    api_module.all_attack = lambda: []
    api_module.AreaType = _EnumFallback()
    api_module.CardType = _EnumFallback()
    api_module.EnergyType = _EnumFallback()
    api_module.OptionType = _EnumFallback()
    api_module.SelectContext = _EnumFallback()
    api_module.SelectType = _EnumFallback()
    api_module.Card = types.SimpleNamespace
    api_module.Pokemon = types.SimpleNamespace
    api_module.Observation = types.SimpleNamespace
    api_module.PlayerState = types.SimpleNamespace
    api_module.State = types.SimpleNamespace
    api_module.Option = types.SimpleNamespace
    api_module.SelectData = types.SimpleNamespace
    api_module.Log = types.SimpleNamespace
    api_module.CardData = types.SimpleNamespace
    api_module.Attack = types.SimpleNamespace
    sys.modules["cg"] = cg_module
    sys.modules["cg.api"] = api_module
    return previous


def _restore_modules(previous: dict[str, types.ModuleType | None]) -> None:
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class OpponentAgent:
    def __init__(self, main_path: Path, *, install_fake_api: bool = True) -> None:
        self.main_path = main_path
        self.install_fake_api = install_fake_api
        self._module = None

    def _load(self):
        if self._module is not None:
            return self._module
        previous = _install_fake_cg_api() if self.install_fake_api else {}
        try:
            module_name = f"ptcg_public_agent_{abs(hash(self.main_path))}"
            spec = importlib.util.spec_from_file_location(module_name, self.main_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot import {self.main_path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, "agent"):
                raise AttributeError(f"{self.main_path} does not define agent(obs_dict)")
            self._module = module
            return module
        finally:
            if not self.install_fake_api:
                _restore_modules(previous)

    def select(self, obs_dict: dict) -> list[int]:
        module = self._load()
        result = module.agent(obs_dict)
        if not isinstance(result, list) or not all(isinstance(item, int) for item in result):
            raise ValueError(f"{self.main_path} returned invalid action {result!r}")
        return result


def _deck_count(deck_path: Path | None) -> int | None:
    if deck_path is None or not deck_path.exists():
        return None
    return len([line for line in deck_path.read_text(encoding="utf-8").splitlines() if line.strip()])


def smoke_test_bundle(bundle: ExtractedBundle, obs_dict: dict) -> dict:
    errors: list[str] = []
    deck_count = _deck_count(bundle.deck_path)
    if deck_count != 60:
        errors.append(f"deck_count={deck_count}, expected 60")
    action: list[int] | None = None
    try:
        action = OpponentAgent(bundle.main_path).select(obs_dict)
        options = (((obs_dict.get("select") or {}).get("option")) or [])
        if not action:
            errors.append("agent returned no action")
        elif options and any(item < 0 or item >= len(options) for item in action):
            errors.append(f"agent returned action outside legal option range: {action}")
    except Exception as exc:
        errors.append(f"agent smoke error: {type(exc).__name__}: {exc}")
    return {
        "ok": not errors,
        "errors": errors,
        "deck_count": deck_count,
        "action": action,
    }


def build_public_opponent_pool(
    *,
    output_dir: Path = Path("artifacts/public_code"),
    limit: int = 20,
    smoke_obs: dict | None = None,
) -> list[OpponentPoolEntry]:
    kernels = rank_kernel_candidates(discover_public_code(max(limit * 2, 20)))
    entries: list[OpponentPoolEntry] = []
    for candidate in kernels[:limit]:
        errors: list[str] = []
        source_dir = output_dir / candidate.ref.replace("/", "__")
        main_path: Path | None = None
        deck_path: Path | None = None
        ok = False
        try:
            pulled_dir = pull_kernel(candidate.ref, output_dir)
            bundle = extract_kernel_sources(pulled_dir)
            main_path = bundle.main_path
            deck_path = bundle.deck_path
            if smoke_obs is not None:
                smoke = smoke_test_bundle(bundle, smoke_obs)
                errors.extend(smoke["errors"])
                ok = bool(smoke["ok"])
            else:
                ok = deck_path is not None and _deck_count(deck_path) == 60
                if not ok:
                    errors.append(f"deck_count={_deck_count(deck_path)}, expected 60")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        entries.append(
            OpponentPoolEntry(
                ref=candidate.ref,
                title=candidate.title,
                author=candidate.author,
                votes=candidate.votes,
                source_dir=str(source_dir),
                main_path=str(main_path) if main_path else None,
                deck_path=str(deck_path) if deck_path else None,
                ok=ok,
                errors=tuple(errors),
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = [
        {
            "ref": entry.ref,
            "title": entry.title,
            "author": entry.author,
            "votes": entry.votes,
            "source_dir": entry.source_dir,
            "main_path": entry.main_path,
            "deck_path": entry.deck_path,
            "ok": entry.ok,
            "errors": list(entry.errors),
        }
        for entry in entries
    ]
    (output_dir / "opponents_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return entries


def download_leaderboard(output_dir: Path = Path("artifacts/kaggle")) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "kaggle",
            "competitions",
            "leaderboard",
            COMPETITION,
            "--download",
            "--path",
            str(output_dir),
        ],
        check=True,
    )
    return output_dir / f"{COMPETITION}.zip"


def discover_public_code(page_size: int = 20) -> list[dict]:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    kernels = api.kernels_list(competition=COMPETITION, page_size=page_size) or []
    result: list[dict] = []
    for kernel in kernels:
        result.append(
            {
                "ref": getattr(kernel, "ref", ""),
                "title": getattr(kernel, "title", ""),
                "author": getattr(kernel, "author", ""),
                "votes": getattr(kernel, "total_votes", 0),
            }
        )
    return result


def pull_kernel(ref: str, output_dir: Path) -> Path:
    destination = output_dir / ref.replace("/", "__")
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(["kaggle", "kernels", "pull", ref, "-p", str(destination)], check=True)
    return destination
