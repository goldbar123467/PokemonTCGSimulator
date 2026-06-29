from __future__ import annotations

import json
from pathlib import Path

from ptcg.engine import diff_snapshots, snapshot_from_observation


REPLAY_PATH = Path(
    "artifacts/ptcg_research/current/lucario_leaderboard_strategy_2026_06_26/raw/82051250.json"
)


def _observation(step_index: int, agent_index: int) -> dict:
    episode = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    return episode["steps"][step_index][agent_index]["observation"]


def test_snapshot_preserves_agent_visible_public_state_without_hidden_card_ids() -> None:
    snapshot = snapshot_from_observation(
        _observation(4, 0),
        replay_id="82051250",
        step_index=4,
        agent_index=0,
    )

    assert snapshot.replay_id == "82051250"
    assert snapshot.step_index == 4
    assert snapshot.agent_index == 0
    assert snapshot.turn == 1
    assert snapshot.your_index == 0
    assert snapshot.legal_action_count == 5

    clark = snapshot.players[0]
    opponent = snapshot.players[1]
    assert clark.hand_count == 7
    assert clark.hand_visible is True
    assert clark.visible_hand_card_ids.count(6) == 3
    assert clark.active[0].card_id == 675
    assert clark.active[0].serial == 47

    assert opponent.hand_count == 6
    assert opponent.hand_visible is False
    assert opponent.visible_hand_card_ids == ()
    assert opponent.deck_count == 47
    assert opponent.active[0].card_id == 305


def test_diff_snapshots_tracks_real_energy_attachment_from_replay_logs() -> None:
    before = snapshot_from_observation(
        _observation(4, 0),
        replay_id="82051250",
        step_index=4,
        agent_index=0,
    )
    after = snapshot_from_observation(
        _observation(5, 0),
        replay_id="82051250",
        step_index=5,
        agent_index=0,
    )

    delta = diff_snapshots(before, after)

    assert after.players[0].hand_count == 6
    assert after.players[0].active[0].energy_card_ids == (6,)
    assert after.players[0].active[0].energy_serials == (12,)
    assert after.log_types == (11,)

    assert delta.count_delta(player_index=0, zone="hand", card_id=6) == -1
    assert delta.count_delta(player_index=0, zone="active_energy", card_id=6) == 1

    movement = delta.movement_for_serial(12)
    assert movement is not None
    assert movement.card_id == 6
    assert movement.player_index == 0
    assert movement.from_zone == "hand"
    assert movement.to_zone == "active_energy"
    assert movement.to_attached_to_serial == 47
    assert movement.log_type_hint == 11
