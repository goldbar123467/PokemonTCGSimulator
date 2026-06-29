import json

import pytest

from ptcg.replays import UnsafeReplayDirectoryError, load_replay_decisions


def test_load_replay_decisions_can_include_legal_empty_optional_actions(tmp_path):
    replay = tmp_path / "episode.json"
    replay.write_text(
        json.dumps(
            {
                "info": {"EpisodeId": "episode"},
                "steps": [
                    [
                        {
                            "observation": {
                                "current": {"players": [{}, {}], "yourIndex": 0},
                                "select": {
                                    "minCount": 0,
                                    "maxCount": 1,
                                    "context": 2,
                                    "type": 1,
                                    "option": [{"type": 3, "area": 2, "index": 0}],
                                },
                            },
                            "action": [],
                        }
                    ]
                ],
            }
        ),
        encoding="utf-8",
    )

    skipped = load_replay_decisions(replay_paths=[replay], include_optional_pass=False)
    included = load_replay_decisions(replay_paths=[replay], include_optional_pass=True)

    assert skipped == []
    assert len(included) == 1
    assert included[0].action_indices == ()


def test_load_replay_decisions_refuses_raw_directory_globbing(tmp_path):
    with pytest.raises(UnsafeReplayDirectoryError):
        load_replay_decisions(tmp_path)
