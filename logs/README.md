# Log Archive And Quarantine

This folder holds gameplay-log material removed from the active data path.

Archived:

- `logs/archived/old_public_replays/2026-06-25_first_two`: older public replay
  ingest moved out of `data/kaggle_public_leaderboard` because it predates the
  current manifest cutoff.

Quarantined:

- `logs/quarantine/duplicate_replays/2026-06-27_submission_54120813_score916_full`
- `logs/quarantine/duplicate_replays/2026-06-28_last_two_hop_strategy`
- `logs/quarantine/duplicate_replays/hop_54127067_10game_agent`

These folders are preserved for auditability, but they must not be read by
default training, validation, or replay-analysis commands. To re-admit a log,
copy it into the active data root and rerun the manifest validation.
