from __future__ import annotations

import tarfile
from pathlib import Path

from ptcg.kaggle_agent_runner import decode_agent_action, run_archive_agent_decision


def _write_agent_archive(root: Path, main_text: str) -> Path:
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


def _observation() -> dict:
    return {
        "current": {
            "yourIndex": 0,
            "players": [
                {"hand": [{"id": 101, "serial": 1}, {"id": 202, "serial": 2}]},
                {"hand": None},
            ],
        },
        "logs": [],
        "select": {
            "type": 0,
            "context": 0,
            "minCount": 1,
            "maxCount": 1,
            "option": [
                {"type": 14},
                {"type": 7, "area": 2, "index": 1, "cardId": 202, "playerIndex": 0},
            ],
        },
    }


def test_decode_agent_action_maps_kaggle_option_indexes() -> None:
    decoded = decode_agent_action([1], _observation())

    assert decoded["legal"] is True
    assert decoded["match_mode"] == "option_indexes"
    assert decoded["selected_option_indexes"] == [1]
    assert decoded["matched_options"] == [
        {"type": 7, "area": 2, "index": 1, "cardId": 202, "playerIndex": 0}
    ]


def test_decode_agent_action_also_accepts_direct_option_payloads() -> None:
    decoded = decode_agent_action({"type": 7, "index": 1}, _observation())

    assert decoded["legal"] is True
    assert decoded["match_mode"] == "option_payload"
    assert decoded["selected_option_indexes"] == [1]


def test_run_archive_agent_decision_executes_uploaded_agent_against_observation(tmp_path: Path) -> None:
    archive = _write_agent_archive(
        tmp_path,
        "def agent(obs, config=None):\n"
        "    if obs.get('select') is None:\n"
        "        return [9] * 60\n"
        "    return [1]\n",
    )

    result = run_archive_agent_decision(archive, _observation())

    assert result["archive"] == str(archive.resolve())
    assert result["raw_action"] == [1]
    assert result["decision"]["legal"] is True
    assert result["decision"]["matched_options"][0]["cardId"] == 202
    assert result["kaggle_submission_made"] is False
