from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ptcg.kaggle_episode_ingest import build_ingest_manifest
from ptcg.kaggle_episode_ingest import own_agent_indices
from ptcg.kaggle_episode_ingest import parse_submission_episode_ref
from ptcg.kaggle_episode_ingest import parse_submission_episode_refs


def _submission(ref: int, *, score: str = "956.0", file_name: str = "agent.tar.gz") -> SimpleNamespace:
    return SimpleNamespace(
        ref=ref,
        file_name=file_name,
        status="SubmissionStatus.COMPLETE",
        public_score=score,
        private_score=None,
        error_description=None,
        description="leaderboard package",
        team_name="Clark Kitchen",
        submitted_by="clarkkitchen",
        total_bytes=99,
        date="2026-06-25 17:22:41",
    )


def _episode(episode_id: int, submission_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=episode_id,
        create_time="2026-06-25 18:00:00",
        end_time="2026-06-25 18:04:00",
        state="EpisodeState.COMPLETED",
        type="EpisodeType.EPISODE_TYPE_PUBLIC",
        agents=[
            SimpleNamespace(
                submission_id=submission_id,
                index=0,
                reward=1,
                state="EpisodeAgentState.ACTIVE",
                team_name="Clark Kitchen",
                team_id=16395686,
            ),
            SimpleNamespace(
                submission_id=99999999,
                index=1,
                reward=-1,
                state="EpisodeAgentState.DONE",
                team_name="Opponent",
                team_id=123,
            ),
        ],
    )


def test_parse_submission_episode_ref_from_kaggle_url() -> None:
    ref = parse_submission_episode_ref(
        "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/submissions?"
        "submissionId=54049099&episodeId=81883221#"
    )

    assert ref.submission_id == 54049099
    assert ref.episode_id == 81883221
    assert ref.source_url.endswith("episodeId=81883221#")


def test_parse_submission_episode_refs_accepts_newline_urls() -> None:
    refs = parse_submission_episode_refs(
        [
            "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/submissions?submissionId=54049099&episodeId=81883221#\n"
            "https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/submissions?submissionId=54048478&episodeId=81883240#"
        ]
    )

    assert [(ref.submission_id, ref.episode_id) for ref in refs] == [
        (54049099, 81883221),
        (54048478, 81883240),
    ]


def test_build_ingest_manifest_records_replays_logs_scores_and_meta(tmp_path: Path) -> None:
    refs = [parse_submission_episode_ref("submissionId=54049099&episodeId=81883221")]
    replay_path = tmp_path / "raw" / "54049099" / "episode-81883221-replay.json"
    log_paths = [tmp_path / "raw" / "54049099" / "episode-81883221-agent-0.log"]
    manifest = build_ingest_manifest(
        refs=refs,
        submissions={54049099: _submission(54049099)},
        episodes={81883221: _episode(81883221, 54049099)},
        replay_paths={81883221: replay_path},
        agent_log_paths={81883221: log_paths},
        output_dir=tmp_path,
        meta_snapshot={
            "date": "2026-06-25",
            "latestDate": "2026-06-25",
            "redirected": False,
            "totalDecks": 123,
            "source": {"datasetUrl": "https://example.invalid/meta.json"},
        },
        command="pytest",
    )

    assert manifest["command"] == "pytest"
    assert manifest["episode_count"] == 1
    assert manifest["submission_records"][0]["submission_id"] == 54049099
    assert manifest["submission_records"][0]["public_score"] == 956.0
    assert manifest["episode_records"][0]["episode_id"] == 81883221
    assert manifest["episode_records"][0]["replay_path"] == str(replay_path)
    assert manifest["episode_records"][0]["agent_log_paths"] == [str(log_paths[0])]
    assert manifest["meta"]["date"] == "2026-06-25"
    assert manifest["meta"]["source"]["datasetUrl"] == "https://example.invalid/meta.json"
    assert manifest["kaggle_submission_made"] is False


def test_own_agent_indices_returns_only_agents_for_requested_submission() -> None:
    episode = _episode(81883221, 54049099)

    assert own_agent_indices(episode, 54049099) == [0]
