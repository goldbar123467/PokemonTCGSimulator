from pathlib import Path

from ptcg.replays import ReplaySample, iter_replay_samples, load_replay_observations, load_replay_samples


def test_iter_replay_samples_extracts_active_decisions_from_real_replay():
    replay = Path("data/Pokemon-Replays-Public/81519581.json")

    sample = next(iter_replay_samples(replay))

    assert isinstance(sample, ReplaySample)
    assert sample.replay_id == "81519581"
    assert sample.agent_index in {0, 1}
    assert sample.step_index > 0
    assert sample.option_count >= 1
    assert sample.action_indices
    assert all(0 <= idx < sample.option_count for idx in sample.action_indices)
    assert sample.search_begin_input


def test_load_replay_samples_skips_process_log_files_and_respects_limit():
    samples = load_replay_samples(
        replay_paths=[
            Path("data/Pokemon-Replays-Public/81519581.json"),
            Path("data/Pokemon-Replays-Public/81126644.json"),
            Path("data/Pokemon-Replays-Public/81559694.json"),
        ],
        max_replays=3,
        max_samples=25,
    )

    assert len(samples) == 25
    assert all(sample.replay_id for sample in samples)
    assert all(sample.option_count > 0 for sample in samples)


def test_load_replay_observations_returns_full_observation_dicts():
    observations = load_replay_observations(
        replay_paths=[Path("data/Pokemon-Replays-Public/81519581.json")],
        max_observations=3,
    )

    assert len(observations) == 3
    assert observations[0]["current"]["players"]
    assert "stadium" in observations[0]["current"]
    assert observations[0]["select"]["option"]
