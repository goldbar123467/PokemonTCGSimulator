# PTCG Artifact Flow

Canonical current research output lives under:

`artifacts/ptcg_research/current/`

Current high-signal subfolders include:

- `kaggle_loss_mining/`: Kaggle API submission episodes, downloaded public replays, sanitized decision labels, heuristic patch maps, and trend reports.
- `lucario_leaderboard_strategy_2026_06_26/`: user-supplied Lucario leaderboard replays, two-scout reports per game, label summaries, and strategy theses.
- `archaludon_rewrite_2026_06_28/`: no-RL Archaludon heuristic rewrite reports, gate outputs, and non-promotable candidate evidence.

Other artifact roots:

- `artifacts/kaggle_readiness/`: archive registry reports and optional no-submit round-robin runs from `python train.py`.
- `artifacts/public_meta/`: public notebook/deck/pilot pulls and legal opponent-gate material.
- `artifacts/meta_snapshots/`: saved daily meta API or Kaggle dataset snapshots.
- `artifacts/submit_validation/`: manual submit guard logs. These should exist only after explicit user-approved submission work.
- `artifacts/quarantine/`: generated debug or scratch outputs removed from the active artifact root after reference checks.
- top-level `artifacts/*.tar.gz`: candidate packages and rebuilt local archives.
- `data_manifest/`: replay manifest and current replay allowlist.
- `logs/archived/` and `logs/quarantine/`: replay/log material removed from the active data path.

Archive/scratch output should move under:

`artifacts/_old/<date-or-topic>/`

Keep these outside `_old` unless deliberately superseded:

- Packaged agents and submission candidates.
- Current meta gates and opponent manifests.
- Source public-meta opponent bundles and source ledgers.

Rerunnable commands:

```powershell
python train.py --archive <candidate.tar.gz> --output-dir artifacts\kaggle_readiness\<run> --registry-only
python train.py --archive-glob "artifacts\submission_*.tar.gz" --output-dir artifacts\kaggle_readiness\<run> --games-per-pair 1 --seed 0
python -m ptcg.kaggle_archive_validator --archive <candidate.tar.gz>
python scripts\validate_gameplay_logs.py --output data_manifest\gameplay_logs.json
python scripts\filter_current_gameplay_logs.py --manifest data_manifest\gameplay_logs.json --output data_manifest\current_gameplay_logs.txt
python scripts\mine_kaggle_submission_losses.py --submission-limit 14 --episodes-per-submission 0
python scripts\analyze_kaggle_loss_trends_ml.py
python scripts\label_user_leaderboard_games.py --replays <public-replay-jsons> --output-dir artifacts\ptcg_research\current\<run>\labels
```

Kaggle submission made: no.

Training/data-loading guardrail:

- `train.py` must pass `ptcg.gameplay_log_guard.assert_training_gameplay_logs_allowed` before it prepares archives or runs round-robin readiness.
- Reusable replay loaders in `ptcg/replays.py` and `ptcg/prize_mapping.py` do not broad-glob replay directories. They require explicit replay paths or use the configured current allowlist.
- Legacy/manual scripts that still accept `--replay-dir` are not canonical training entrypoints and must not be used as a data source without first generating the current manifest and allowlist.
