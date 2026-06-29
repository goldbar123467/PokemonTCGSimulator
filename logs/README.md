# Log Archive And Quarantine

This folder may hold gameplay-log material removed from the active data path.
Large archived and quarantined replay/log folders are ignored by Git and may be
cleared when disk space is needed.

Archived:

- `logs/archived/old_public_replays/2026-06-25_first_two`: older public replay
  ingest moved out of `data/kaggle_public_leaderboard` because it predates the
  current manifest cutoff.

Quarantined:

- `logs/quarantine/duplicate_replays/2026-06-27_submission_54120813_score916_full`
- `logs/quarantine/duplicate_replays/2026-06-28_last_two_hop_strategy`
- `logs/quarantine/duplicate_replays/hop_54127067_10game_agent`

These folders are not canonical evidence. If they exist, they must not be read
by default training, validation, or replay-analysis commands. To re-admit a log,
copy it into the active data root and rerun manifest validation. If they have
been cleared, rely on compact summaries in `docs/` and rebuild from public/legal
sources only when needed.
