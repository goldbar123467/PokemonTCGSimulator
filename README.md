# PTCG Kaggle Agent Research

This repo is a no-RL Pokemon TCG Kaggle agent research workspace. The active
workflow is gameplay research, public/legal replay analysis, deterministic
package validation where possible, repeated-batch heuristic gates, and
Kaggle-style `.tar.gz` readiness reports.

Before strategy, replay-analysis, evaluation, candidate, packaging, or report
work, read:

- `AGENTS.md`
- `docs/groupknowledge.md`
- `docs/ptcg-project-brief.md`
- `docs/ptcg-evaluation-playbook.md`
- `docs/ptcg-storage-retention.md`

Current hard rule: do not run PPO, RL, behavior-cloning-as-improvement,
random self-play counters, or neural imitation loops unless the user explicitly
reopens that direction. Kaggle submission is forbidden unless the user
explicitly approves it.

## No-RL Kaggle Readiness Workflow

Use `train.py` as the top-level readiness wrapper. Despite the historical file
name, it does not train a model. It validates local archives, records package
provenance, and optionally runs the official-SDK round robin. Every report
writes `kaggle_submission_made: false`.

Registry/provenance only:

```powershell
python train.py --archive artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz --output-dir artifacts\kaggle_readiness\lucario_champion --registry-only
```

Round robin:

```powershell
python train.py --archive-glob "artifacts\submission_*.tar.gz" --output-dir artifacts\kaggle_readiness\round_robin --games-per-pair 1 --seed 0
```

Local Kaggle parity check for one candidate:

```powershell
python scripts\run_local_kaggle_parity.py --archive artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz --output-dir artifacts\local_kaggle_parity\lucario_champion --seed 0 --smoke-games 1
```

Benchmark league:

```powershell
python scripts\run_benchmark_league.py --archive artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz --config configs\benchmark_league.json --output-dir artifacts\benchmarks\lucario_champion --seeds 0,1,2,3,4
```

Candidate-vs-baseline benchmark comparison:

```powershell
python scripts\compare_candidate_archives.py --candidate artifacts\<candidate>.tar.gz --baseline artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz --config configs\benchmark_league.json --gate-config configs\benchmark_gate.json --output-dir artifacts\comparisons\<run>
```

Historical calibration report:

```powershell
python scripts\run_historical_calibration.py --registry configs\archive_registry.json --config configs\benchmark_league.json --gate configs\benchmark_gate.json --output-dir artifacts\calibration\<run>
```

Resume or extend a benchmark until each matchup reaches a target count:

```powershell
python scripts\run_benchmark_league.py --archive artifacts\<candidate>.tar.gz --config configs\benchmark_league.json --output-dir artifacts\benchmarks\<run> --target-games-per-matchup 20 --resume
```

Train/readiness wrapper with benchmark orchestration:

```powershell
python train.py --archive artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz --output-dir artifacts\kaggle_readiness\lucario_benchmark --run-benchmark --benchmark-config configs\benchmark_league.json --seeds 0,1,2,3,4
```

Strict raw-exec archive validation:

```powershell
python -m ptcg.kaggle_archive_validator --archive artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz
```

Gameplay-log hygiene is enforced by `train.py`. Run these commands before any
readiness or evaluation command:

```powershell
python scripts\validate_gameplay_logs.py --output data_manifest\gameplay_logs.json
python scripts\filter_current_gameplay_logs.py --manifest data_manifest\gameplay_logs.json --output data_manifest\current_gameplay_logs.txt
```

Focused verification for this workflow:

```powershell
python -m pytest tests\test_gameplay_log_hygiene.py tests\test_training_log_guardrails.py tests\test_replays.py tests\test_replay_parser.py tests\test_prize_mapping.py tests\test_train_kaggle_readiness_cli.py tests\test_kaggle_archive_validator.py tests\test_round_robin.py tests\test_seed_schedule.py tests\test_local_kaggle_parity.py tests\test_benchmark_league.py tests\test_benchmark_comparison.py -q
```

### Benchmark Artifacts And Seed Policy

`scripts\run_local_kaggle_parity.py` writes:

- `parity_summary.json`
- `parity_events.jsonl`
- `failures.json`
- `run_config.json`

`scripts\run_benchmark_league.py` writes:

- `results_by_game.csv`
- `results_by_matchup.csv`
- `summary.json`
- `failures.json`
- `seed_schedule.json`
- `opponent_registry.json`

`scripts\compare_candidate_archives.py` writes:

- `candidate_summary.json`
- `baseline_summary.json`
- `comparison_by_matchup.csv`
- `comparison_summary.json`
- `decision.json`

`scripts\run_historical_calibration.py` writes:

- `calibration_pairs.csv`
- `calibration_summary.json`
- `archive_registry_resolved.json`
- `failures.json`
- `result_reuse_report.json`

The benchmark seed schedule is deterministic and persisted. Reusing the same
candidate, opponent registry, game count, and seed config produces the same
schedule file. The official `cg` SDK still does not expose full battle seed
control, so these seeds are schedule/runtime labels for reproducible local
runs, not proof of Common Random Numbers. Local benchmark score is not a Kaggle
leaderboard score.

`configs/benchmark_league.json` is a fixed opponent registry. It supports
explicit local archives and the built-in `random` baseline. It intentionally
rejects broad archive/replay globs; unavailable archives are listed in
`opponent_registry.json` and `summary.json` instead of being silently invented.

Phase 5 adds registry and compatibility guardrails:

- `configs/champion_registry.json` locks the current champion archive by path,
  SHA256, known submission id, known public score, archetype label, validation
  status, and notes. It is never updated automatically.
- `configs/archive_registry.json` records historical, baseline, hard-gate, bad
  variant, and unknown archives. Unknown scores stay `null`; the calibration
  runner marks those pairs `INCONCLUSIVE` instead of inventing labels.
- Reused benchmark result directories must match archive SHA256, benchmark
  config hash, required matchups, current benchmark schema version, and any
  recorded opponent-registry or seed-schedule hashes.
- Benchmark summaries include richer diagnostics where available: average
  prizes taken/allowed, prize differential, average turns, early losses,
  no-progress games, long-game flags, and invalid-action counts by action type.
  Prize diagnostics use public prize counts only, not prize-card identities.

### Benchmark Gate Policy

`configs/benchmark_gate.json` controls comparison thresholds. It includes:

- minimum total games
- minimum games per required hard-gate matchup
- maximum invalid action, timeout, and crash rates
- minimum aggregate win-rate delta versus baseline
- minimum candidate lower confidence bound
- required hard-gate opponents
- maximum allowed hard-gate regression

Decision meanings:

- `PASS`: candidate met every configured threshold versus the baseline.
- `FAIL`: candidate had enough evidence and violated at least one threshold.
- `INCONCLUSIVE`: a required opponent or required evidence surface was missing.

The current best archive should be named explicitly in commands. For Lucario
work, use `artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz`
as the baseline unless the user explicitly replaces the champion. Do not mutate
or demote a current best archive automatically. The same identity is locked in
`configs/champion_registry.json`; if its SHA does not match, comparison refuses
to treat that archive as the champion.

Before trusting a candidate, run enough games for the configured gate. The
default gate expects at least `100` total games and `20` games per required
hard-gate matchup. For serious promotion decisions, `docs/groupknowledge.md`
still recommends much larger repeated-batch evidence because local variance is
large and there is no full official-SDK seed hook.

Current evidence standards:

- smoke: `12` games
- screening: `100+` games
- serious comparison: `400+` games
- promotion candidate: configured gate pass plus historical-calibration sanity

## Canonical Commands

There is no active model-training command in this repo. Legacy RL/PPO/BC
training is intentionally disabled by project rule. The canonical top-level
command is the no-submit Kaggle readiness wrapper:

```powershell
python train.py --archive <candidate.tar.gz> --output-dir artifacts\kaggle_readiness\<run> --registry-only
```

The canonical replay-data gate is:

```powershell
python scripts\validate_gameplay_logs.py --output data_manifest\gameplay_logs.json
python scripts\filter_current_gameplay_logs.py --manifest data_manifest\gameplay_logs.json --output data_manifest\current_gameplay_logs.txt
```

Any future training, validation, or replay analysis script must read from
`data_manifest/current_gameplay_logs.txt` or reproduce the same validation
rules before consuming gameplay logs. Raw replay-folder globbing is forbidden
for training/data-loading paths. `train.py` exits before archive prep if the
manifest, allowlist, schema version, file count, file size, allowlist SHA256,
listed files, or blocked path checks fail.

Stale, archived, quarantined, duplicate, old, debug, or changed gameplay logs
must never enter training or readiness runs. The parity and benchmark commands
do not read gameplay logs; `train.py` still enforces the gameplay-log guard
before it invokes either registry, round-robin, or benchmark helpers.

Blocked allowlist path segments include `archive`, `archived`, `quarantine`,
`duplicate`, `old`, `stale_debug`, and `failed_experiment`.

## Project Map

- `ptcg/`: reusable Python package code for archive validation, native eval,
  replay parsing, public-meta handling, reports, and round-robin evaluation.
- `scripts/`: command-line entrypoints and research utilities. Prefer adding
  reusable logic to `ptcg/` and keeping scripts thin.
- `tests/`: pytest coverage for package behavior, validators, reports, and
  selected candidate packages.
- `docs/`: current group knowledge, artifact flow, public-source ledger, and
  workflow notes.
- `configs/current_workflow.json`: central seed, current replay schema cutoff,
  data/manifest paths, artifact roots, and Kaggle input/output locations.
- `data_manifest/`: generated manifests and allowlists for current compatible
  gameplay logs.
- `logs/`: archived and quarantined gameplay-log folders that must not be
  consumed by default.
- `artifacts/`: generated packages, reports, gates, meta snapshots, and run
  outputs. Keep generated outputs here rather than in source directories.

The web practice beta has been moved out of this repo to the sibling project:

`C:\Users\Clark\Documents\ptcg-website`
