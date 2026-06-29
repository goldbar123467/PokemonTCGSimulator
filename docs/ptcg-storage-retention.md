# PTCG Storage And Replay Retention

Last condensed: 2026-06-29.

This repo keeps source, tests, configs, compact manifests, and canonical docs in Git. Generated replay dumps, benchmark outputs, package archives, logs, screenshots, and calibration runs are local scratch and should be regenerated or restored only when needed.

## Git-Tracked By Default

- `ptcg/`
- `scripts/`
- `tests/`
- `configs/`
- `docs/`
- `data/official/`
- `data/official_kaggle/`
- `data/kaggle_sample/`
- `data_manifest/`
- `deck.csv`
- `train.py`
- `README.md`
- `AGENTS.md`

## Ignored Generated Stores

These paths are intentionally ignored and safe to clear when space is needed:

- `artifacts/`
- `data/kaggle_public_leaderboard/`
- `data/Pokemon-Replays-Public/`
- `logs/archived/`
- `logs/quarantine/`
- `.pytest_cache/`
- `__pycache__/`
- `.venv/`
- `.venv-cuda/`

Do not delete `data/official/`, `data/official_kaggle/`, or `data/kaggle_sample/` during replay cleanup. They are small, tracked SDK/sample inputs.

## 2026-06-29 Cleanup

The following local generated stores were cleared to make room for future replay ingestion:

| Path | Files | Approx size |
|---|---:|---:|
| `artifacts/` | 49,597 | 47.39 GB |
| `data/kaggle_public_leaderboard/` | 552 | 0.51 GB |
| `data/Pokemon-Replays-Public/` | 92 | 0.21 GB |
| `logs/archived/` | 7 | 0.01 GB |
| `logs/quarantine/` | 143 | 0.15 GB |

Approximate total cleared: 48.27 GB.

Important consequence: local archive paths in `configs/archive_registry.json` and `configs/champion_registry.json` may point to files that no longer exist. The registry identity still matters, but archives must be restored, rebuilt, or re-downloaded before validation or calibration.

## Future Replay Intake

Put newly downloaded public replays under `data/kaggle_public_leaderboard/<dated_run>/` only while actively processing them. Before any training/readiness path consumes gameplay logs, rebuild the manifest:

```powershell
python scripts\validate_gameplay_logs.py --output data_manifest\gameplay_logs.json
python scripts\filter_current_gameplay_logs.py --manifest data_manifest\gameplay_logs.json --output data_manifest\current_gameplay_logs.txt
```

After extracting labels, reports, and compact summaries, clear or quarantine raw replays again. Keep only machine-readable summaries and markdown findings in Git when they are small and reusable.

## What To Preserve Before Clearing

Before deleting a generated run, preserve one compact markdown or JSON summary with:

- command
- source snapshot metadata
- archive path and SHA at the time of the run
- replay/game/opponent counts
- key per-matchup results
- failures and exclusions
- verdict
- `kaggle_submission_made: false`

If a package becomes a real candidate, preserve its SHA in a registry or markdown note before deleting the tarball.
