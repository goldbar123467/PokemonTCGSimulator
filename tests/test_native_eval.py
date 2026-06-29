from pathlib import Path

from ptcg.native_eval import _load_agent, smoke_native_agent_vs_random


def test_load_agent_can_install_deterministic_time(tmp_path, monkeypatch):
    main_path = tmp_path / "main.py"
    main_path.write_text(
        "import time\n"
        "def agent(obs):\n"
        "    return [round(time.time(), 2), round(time.time(), 2)]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PTCG_DETERMINISTIC_AGENT_TIME", "1")
    monkeypatch.setenv("PTCG_DETERMINISTIC_AGENT_TIME_STEP", "0.25")

    agent = _load_agent(main_path, "deterministic_time_test")

    assert agent({}) == [0.25, 0.5]
    assert agent({}) == [0.75, 1.0]


def test_smoke_native_agent_vs_random_with_official_sample_when_available():
    sdk_path = Path("data/official")
    main_path = sdk_path / "main.py"
    deck_path = sdk_path / "deck.csv"
    if not (sdk_path / "cg" / "game.py").exists() or not main_path.exists() or not deck_path.exists():
        return

    result = smoke_native_agent_vs_random(
        main_path=main_path,
        deck_path=deck_path,
        sdk_path=sdk_path,
        games=2,
        seed=17,
    )

    assert result.games == 2
    assert result.finished == 2
    assert result.errors == ()
