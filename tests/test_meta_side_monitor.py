from pathlib import Path

from scripts.ptcg_meta_side_monitor import analyze_replay, build_reports, scan_once, configure_logging


def test_analyze_replay_extracts_deck_prize_and_opening_data():
    analysis = analyze_replay(Path("data/Pokemon-Replays-Public/81519581.json"))

    assert analysis is not None
    assert analysis.replay_id == "81519581"
    assert len(analysis.players) == 2
    assert all(player.deck_hash for player in analysis.players)
    assert any(player.opening_actions for player in analysis.players)
    assert all(player.final_prizes_taken >= 0 for player in analysis.players)


def test_build_reports_writes_deck_and_opening_rankings(tmp_path):
    analyses = [
        item
        for item in (
            analyze_replay(Path("data/Pokemon-Replays-Public/81519581.json")),
            analyze_replay(Path("data/Pokemon-Replays-Public/81126644.json")),
        )
        if item is not None
    ]

    summary = build_reports(analyses, tmp_path)

    assert summary["replays_analyzed"] == 2
    assert summary["deck_keys_ranked"] > 0
    assert summary["deck_matchups_ranked"] > 0
    deck_rankings = (tmp_path / "deck_rankings.csv").read_text(encoding="utf-8")
    assert deck_rankings.startswith("rank,deck_key,primary_archetype")
    assert "adjusted_x_game_score" in deck_rankings.splitlines()[0]
    assert (tmp_path / "deck_matchup_matrix.csv").exists()
    assert (tmp_path / "opening_tree_rankings.csv").exists()


def test_scan_once_skips_process_json_arrays(tmp_path):
    class Args:
        replay_dir = Path("data/Pokemon-Replays-Public")
        output_dir = tmp_path
        max_replays = 4
        heartbeat_every = 2

    logger = configure_logging(tmp_path)
    summary = scan_once(Args(), logger)

    assert summary["replays_analyzed"] > 0
    assert (tmp_path / "latest_summary.json").exists()
