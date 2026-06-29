from __future__ import annotations

import tarfile
import sys
from pathlib import Path

import pytest

from ptcg.kaggle_archive_validator import ArchiveValidationError, validate_archive_startup


@pytest.fixture(autouse=True)
def _isolate_ambient_cg_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    previous_modules = {}
    for name in list(sys.modules):
        if name == "cg" or name.startswith("cg."):
            previous_modules[name] = sys.modules.pop(name)
    clean_path = []
    for entry in sys.path:
        if entry and (Path(entry) / "cg" / "api.py").exists():
            continue
        clean_path.append(entry)
    monkeypatch.setattr(sys, "path", clean_path)
    yield
    for name in list(sys.modules):
        if name == "cg" or name.startswith("cg."):
            del sys.modules[name]
    for name, module in previous_modules.items():
        sys.modules[name] = module


def _write_archive(root: Path, main_text: str) -> Path:
    package = root / "package"
    package.mkdir()
    (package / "main.py").write_text(main_text, encoding="utf-8")
    (package / "deck.csv").write_text("\n".join("9" for _ in range(60)) + "\n", encoding="utf-8")
    cg_dir = package / "cg"
    cg_dir.mkdir()
    (cg_dir / "__init__.py").write_text("", encoding="utf-8")
    (cg_dir / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = root / "agent.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))
    return archive


def test_strict_archive_validation_catches_missing_package_path_bootstrap(tmp_path: Path) -> None:
    archive = _write_archive(
        tmp_path,
        "import cg.api\n"
        "def agent(obs):\n"
        "    return [9] * 60\n",
    )

    with pytest.raises(ModuleNotFoundError):
        validate_archive_startup(archive)


def test_strict_archive_validation_accepts_inspect_bootstrap_without_file(tmp_path: Path) -> None:
    archive = _write_archive(
        tmp_path,
        "import inspect\n"
        "import os\n"
        "import sys\n"
        "_ROOT = os.path.dirname(os.path.abspath(inspect.currentframe().f_code.co_filename))\n"
        "if _ROOT not in sys.path:\n"
        "    sys.path.insert(0, _ROOT)\n"
        "import cg.api\n"
        "def agent(obs):\n"
        "    with open(os.path.join(_ROOT, 'deck.csv'), encoding='utf-8') as f:\n"
        "        return [int(line) for line in f.read().splitlines() if line.strip()]\n",
    )

    result = validate_archive_startup(archive)

    assert result["strict_raw_exec_without_file_or_syspath"] is True
    assert result["deck_len"] == 60
    assert result["deck_csv_len"] == 60
    assert result["deck_csv_sha256"] == "30D430840D033D8A93798E2A182CE7843D76E25EBD809A1250C495A41E74BF25"
    assert result["deck_csv_cards"][:4] == [9, 9, 9, 9]
    assert result["agent_deck_matches_csv"] is True


def test_strict_archive_validation_loads_split_policy_module(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "main.py").write_text(
        "import importlib.util\n"
        "import inspect\n"
        "import sys\n"
        "from pathlib import Path\n"
        "_ROOT = Path(inspect.currentframe().f_code.co_filename).resolve().parent\n"
        "def _load_policy_module():\n"
        "    root = str(_ROOT)\n"
        "    if root not in sys.path:\n"
        "        sys.path.insert(0, root)\n"
        "    spec = importlib.util.spec_from_file_location('policy_agent_under_test', _ROOT / 'policy_agent.py')\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    return module\n"
        "def agent(obs):\n"
        "    if obs.get('select') is None:\n"
        "        return [9] * 60\n"
        "    return _load_policy_module().agent(obs)\n",
        encoding="utf-8",
    )
    (package / "policy_agent.py").write_text(
        "import cg.api\n"
        "def agent(obs):\n"
        "    return []\n",
        encoding="utf-8",
    )
    (package / "deck.csv").write_text("\n".join("9" for _ in range(60)) + "\n", encoding="utf-8")
    cg_dir = package / "cg"
    cg_dir.mkdir()
    (cg_dir / "__init__.py").write_text("", encoding="utf-8")
    (cg_dir / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    archive = tmp_path / "agent.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))

    result = validate_archive_startup(archive)

    assert result["policy_module_loaded"] is True
    assert result["deck_csv_len"] == 60


def test_strict_archive_validation_requires_cg_bundle(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "main.py").write_text("def agent(obs): return [9] * 60\n", encoding="utf-8")
    (package / "deck.csv").write_text("\n".join("9" for _ in range(60)), encoding="utf-8")
    archive = tmp_path / "agent.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in package.rglob("*"):
            tf.add(path, arcname=path.relative_to(package))

    with pytest.raises(ArchiveValidationError, match="cg/api.py"):
        validate_archive_startup(archive)
