import json
import zipfile
from pathlib import Path

from ptcg.opponent_pool import (
    OpponentAgent,
    smoke_test_bundle,
    ExtractedBundle,
    extract_kernel_sources,
    write_deck_from_python_source,
    parse_leaderboard_zip,
    rank_kernel_candidates,
)


def test_parse_leaderboard_zip_reads_ranked_rows(tmp_path):
    archive = tmp_path / "leaderboard.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "leaderboard.csv",
            "\ufeffRank,TeamId,TeamName,LastSubmissionDate,Score,SubmissionCount,TeamMemberUserNames\n"
            "1,1,Alpha,\"2026-06-21 05:39:02\",1366.5,2,alpha_user\n"
            "2,2,Beta,\"2026-06-21 06:39:02\",1288.6,1,beta_user\n",
        )

    entries = parse_leaderboard_zip(archive)

    assert [entry.rank for entry in entries] == [1, 2]
    assert entries[0].team_name == "Alpha"
    assert entries[0].score == 1366.5
    assert entries[1].members == ("beta_user",)


def test_rank_kernel_candidates_prefers_agent_like_titles():
    kernels = [
        {"ref": "u/eda", "title": "Deck EDA", "author": "u", "votes": 50},
        {"ref": "u/lucario", "title": "Mega Lucario Agent Baseline", "author": "u", "votes": 5},
        {"ref": "u/search", "title": "MCTS heuristic sample code", "author": "u", "votes": 20},
    ]

    ranked = rank_kernel_candidates(kernels)

    assert [item.ref for item in ranked][:2] == ["u/lucario", "u/search"]


def test_extract_kernel_sources_writes_main_and_deck_from_notebook(tmp_path):
    kernel_dir = tmp_path / "kernel"
    kernel_dir.mkdir()
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "source": [
                    "%%writefile main.py\n",
                    "def agent(obs_dict):\n",
                    "    return [0]\n",
                ],
            },
            {
                "cell_type": "code",
                "source": [
                    "%%writefile deck.csv\n",
                    "1\n",
                    "1\n",
                ],
            },
        ]
    }
    (kernel_dir / "agent.ipynb").write_text(json.dumps(notebook), encoding="utf-8")

    bundle = extract_kernel_sources(kernel_dir)

    assert bundle.main_path.read_text(encoding="utf-8").startswith("def agent")
    assert bundle.deck_path is not None
    assert bundle.deck_path.read_text(encoding="utf-8").splitlines() == ["1", "1"]


def test_extract_kernel_sources_reads_deck_assignment_from_notebook_cell(tmp_path):
    kernel_dir = tmp_path / "kernel"
    kernel_dir.mkdir()
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "source": [
                    "DECK = [4, 5, 6]\n",
                    "from pathlib import Path\n",
                    "Path('deck.csv').write_text('\\n'.join(map(str, DECK)))\n",
                ],
            },
            {
                "cell_type": "code",
                "source": [
                    "%%writefile main.py\n",
                    "def agent(obs_dict):\n",
                    "    return [0]\n",
                ],
            },
        ]
    }
    (kernel_dir / "agent.ipynb").write_text(json.dumps(notebook), encoding="utf-8")

    bundle = extract_kernel_sources(kernel_dir)

    assert bundle.deck_path is not None
    assert bundle.deck_path.read_text(encoding="utf-8").splitlines() == ["4", "5", "6"]


def test_opponent_agent_selects_with_fake_cg_api(tmp_path):
    main_path = tmp_path / "main.py"
    main_path.write_text(
        "from cg.api import to_observation_class\n"
        "def agent(obs_dict):\n"
        "    obs = to_observation_class(obs_dict)\n"
        "    if obs.select is None:\n"
        "        return [1] * 60\n"
        "    return [len(obs.select.option) - 1]\n",
        encoding="utf-8",
    )

    agent = OpponentAgent(main_path)

    assert agent.select({"select": {"option": [{}, {}, {}]}}) == [2]
    assert len(agent.select({"select": None})) == 60


def test_write_deck_from_python_source_extracts_assignment(tmp_path):
    main_path = tmp_path / "main.py"
    main_path.write_text(
        "my_deck = [\n"
        "    7, 8, 9,\n"
        "]\n",
        encoding="utf-8",
    )

    deck_path = write_deck_from_python_source(main_path, tmp_path / "deck.csv")

    assert deck_path.read_text(encoding="utf-8").splitlines() == ["7", "8", "9"]


def test_smoke_test_bundle_reports_deck_length_and_action(tmp_path):
    main_path = tmp_path / "main.py"
    deck_path = tmp_path / "deck.csv"
    main_path.write_text(
        "def agent(obs_dict):\n"
        "    return [0]\n",
        encoding="utf-8",
    )
    deck_path.write_text("\n".join(["1"] * 60) + "\n", encoding="utf-8")
    bundle = ExtractedBundle(tmp_path, tmp_path, main_path, deck_path)
    obs = {"select": {"option": [{"type": 1}]}}

    result = smoke_test_bundle(bundle, obs)

    assert result["ok"] is True
    assert result["deck_count"] == 60
    assert result["action"] == [0]
