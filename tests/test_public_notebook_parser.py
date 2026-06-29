from pathlib import Path

from ptcg.public_notebook_parser import extract_notebook_artifacts


def test_extract_notebook_artifacts_finds_dragapult_deck_and_main_from_skarin_probe():
    root = Path("artifacts/public_meta/kernels/skarin__phantom_dive_or_go_home_a_dragapult_ex_deck")
    if not root.exists():
        root = Path("artifacts/web_research_probe/skarin_dragapult")
    notebook = next(root.glob("*.ipynb"))

    artifacts = extract_notebook_artifacts(notebook)

    assert artifacts.deck_ids is not None
    assert len(artifacts.deck_ids) == 60
    assert artifacts.deck_ids.count(119) == 4
    assert artifacts.deck_ids.count(120) == 4
    assert artifacts.deck_ids.count(121) == 3
    assert artifacts.main_py is not None
    assert "def agent" in artifacts.main_py
    assert "Dragapult" in artifacts.strategy_text


def test_extract_notebook_artifacts_finds_count_dict_lucario_deck_from_pixiux():
    root = Path("artifacts/public_meta/kernels/pixiux__ptcg_mega_lucario_ex_v63")
    notebook = next(root.glob("*.ipynb"))

    artifacts = extract_notebook_artifacts(notebook)

    assert artifacts.deck_ids is not None
    assert len(artifacts.deck_ids) == 60
    assert artifacts.deck_ids.count(677) == 4
    assert artifacts.deck_ids.count(678) == 4
    assert artifacts.deck_ids.count(1213) == 1
    assert artifacts.main_py is not None
    assert "def agent" in artifacts.main_py


def test_extract_notebook_artifacts_reconstructs_generated_lucario_agent_from_pilkwang():
    root = Path("artifacts/public_meta/kernels/pilkwang__pokemon_tcg_lucario_v2_strategy_baseline")
    notebook = next(root.glob("*.ipynb"))

    artifacts = extract_notebook_artifacts(notebook)

    assert artifacts.deck_ids is not None
    assert len(artifacts.deck_ids) == 60
    assert artifacts.deck_ids.count(677) == 4
    assert artifacts.deck_ids.count(678) == 4
    assert artifacts.deck_ids.count(1182) == 3
    assert artifacts.main_py is not None
    assert "def agent" in artifacts.main_py
    assert "EMBEDDED_DECK = [673, 673" in artifacts.main_py
