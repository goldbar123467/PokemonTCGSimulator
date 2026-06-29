from ptcg.lucario_ceiling_audit import build_audit, render_markdown
from ptcg.opponent_pool import LeaderboardEntry


def test_build_audit_flags_low_lucario_ceiling_and_matches_public_authors():
    meta_items = [
        {
            "name": "Mega Lucario ex / Riolu",
            "slug": "mega-lucario-ex-riolu-91a8b7",
            "appearances": 2492,
            "wins": 1058,
            "losses": 1429,
            "winRate": 0.4254,
            "metaShare": 0.2259,
        },
        {
            "name": "Dragapult ex / Dreepy",
            "slug": "dragapult-ex-dreepy-c1853d",
            "appearances": 740,
            "wins": 441,
            "losses": 299,
            "winRate": 0.596,
            "metaShare": 0.0671,
        },
        {
            "name": "Team Rocket's Tarountula / Team Rocket's Spidops",
            "slug": "team-rocket-s-tarountula-team-rocket-s-spidops",
            "appearances": 113,
            "wins": 74,
            "losses": 39,
            "winRate": 0.655,
            "metaShare": 0.0102,
        },
        {
            "name": "Team Rocket's Petrel / Team Rocket's Transceiver",
            "slug": "team-rocket-s-petrel-team-rocket-s-transceiver-bb8f0a",
            "appearances": 647,
            "wins": 333,
            "losses": 311,
            "winRate": 0.517,
            "metaShare": 0.0586,
        },
        {
            "name": "Ignition Energy / Mega Starmie ex",
            "slug": "ignition-energy-mega-starmie-ex-small",
            "appearances": 56,
            "wins": 30,
            "losses": 26,
            "winRate": 0.527,
            "metaShare": 0.005,
        },
        {
            "name": "Ignition Energy / Mega Starmie ex",
            "slug": "ignition-energy-mega-starmie-ex-3775d5",
            "appearances": 521,
            "wins": 291,
            "losses": 230,
            "winRate": 0.559,
            "metaShare": 0.0472,
        },
    ]
    manifest = [
        {
            "ref": "pixiux/ptcg-mega-lucario-ex-v63",
            "title": "PTCG Mega Lucario ex v63",
            "archetype": "lucario",
            "tags": ["lucario", "direct_aggression"],
            "evidence": ["contains Lucario family ids"],
            "ok": True,
            "smoke": {"finished": 1, "errors": []},
        }
    ]
    leaderboard = [
        LeaderboardEntry(
            rank=439,
            team_id="t1",
            team_name="PyJa",
            last_submission_date="2026-06-24 14:54:30",
            score=902.4,
            submission_count=2,
            members=("pixiux",),
        )
    ]
    coverage = {
        "coverage_counts": {"lucario_mirror": 10},
        "coverage_table": [
            {
                "archetype": "lucario_mirror",
                "clark_wins": 3,
                "clark_losses": 7,
            }
        ],
    }

    audit = build_audit(
        meta_items=meta_items,
        leaderboard_entries=leaderboard,
        public_manifest=manifest,
        coverage=coverage,
        meta_snapshot={
            "date": "2026-06-24",
            "latestDate": "2026-06-24",
            "redirected": False,
            "totalDecks": 11032,
            "source": {"datasetUrl": "https://example.test/dataset"},
        },
    )

    assert audit["verdict"]["track_selection"] == "flag_deck_track_pivot_before_more_tuning"
    assert audit["lucario"]["win_rate"] == 0.4254
    assert audit["public_lucario_agents"][0]["leaderboard_rank"] == 439
    assert audit["public_lucario_agents"][0]["leaderboard_score"] == 902.4
    assert audit["clark_replay_evidence"]["lucario_mirror"]["opponent_wins"] == 7
    assert "Team Rocket's Petrel / Team Rocket's Transceiver" in {
        row["name"] for row in audit["comparison_archetypes"]
    }
    assert "Team Rocket's Tarountula / Team Rocket's Spidops" not in {
        row["name"] for row in audit["comparison_archetypes"]
    }
    assert [
        row["name"] for row in audit["comparison_archetypes"]
    ].count("Ignition Energy / Mega Starmie ex") == 1

    markdown = render_markdown(audit)
    assert "Kaggle submission made: no" in markdown
    assert "PTCG Mega Lucario ex v63" in markdown
    assert "Dragapult ex / Dreepy" in markdown
