# PTCG Evaluation Playbook

Last condensed: 2026-06-29.

This file is the compact operating guide for no-submit validation, benchmarking, and calibration.

## Minimum Commands

Strict archive validation:

```powershell
python -m ptcg.kaggle_archive_validator --archive artifacts\<archive>.tar.gz
```

One-archive local parity and startup smoke:

```powershell
python scripts\run_local_kaggle_parity.py --archive artifacts\<archive>.tar.gz --output-dir artifacts\local_kaggle_parity\<run> --seed 0 --smoke-games 1
```

Fixed-opponent benchmark league:

```powershell
python scripts\run_benchmark_league.py --archive artifacts\<archive>.tar.gz --config configs\benchmark_league.json --output-dir artifacts\benchmarks\<run> --target-games-per-matchup 20 --resume
```

Candidate versus baseline comparison:

```powershell
python scripts\compare_candidate_archives.py --candidate artifacts\<candidate>.tar.gz --baseline artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz --config configs\benchmark_league.json --gate-config configs\benchmark_gate.json --output-dir artifacts\comparisons\<run>
```

Historical calibration:

```powershell
python scripts\run_historical_calibration.py --registry configs\archive_registry.json --config configs\benchmark_league.json --gate configs\benchmark_gate.json --output-dir artifacts\calibration\<run>
```

No-submit readiness wrapper:

```powershell
python train.py --archive artifacts\<archive>.tar.gz --output-dir artifacts\kaggle_readiness\<run> --registry-only
```

## Sample Size Standards

- 12 games: smoke and package health only.
- 100+ games: screening.
- 400+ games: serious calibration.
- 1200+ per arm or repeated batches: use when results are close or variance is high.

Tiny runs can detect broken packages. They cannot prove leaderboard strength.

## Calibration Question

Before strategy work, answer:

Does the local benchmark rank known stronger public/legal archives above known weaker archives?

Priority known-order pairs:

1. Lucario champion over lower Lucario Track A v2.
2. Known good Hop/Trevenant over worse Hop/Trevenant, if both are registered and strict-clean.
3. Stronger Starmie baseline over known bad Starmie retry, if both are registered and strict-clean.
4. Dragapult hard gate only if strict validation is clean or the package is repaired into a new archive with a new SHA.

If the answer is not clearly yes, stop and report `NOT CALIBRATED`, `PARTIALLY CALIBRATED ONLY`, or the relevant blocked status. Do not tune strategy from an uncalibrated benchmark.

## Validation Rules

For every archive used as evidence, record:

- path
- SHA256
- strict validation status
- startup status
- known public score or known local historical status
- whether it is eligible for calibration
- reason if excluded

If `submission_dragapult_lucario_first_web_heuristic.tar.gz` fails with `No module named 'cg'`, exclude it from clean calibration evidence or repair and revalidate it as a new archive.

## Gate Verdicts

Use exactly these verdict labels in calibration reports:

- `CALIBRATED ENOUGH FOR SCREENING`
- `PARTIALLY CALIBRATED ONLY`
- `NOT CALIBRATED`
- `BLOCKED BY DIRTY ARCHIVES`
- `BLOCKED BY INSUFFICIENT KNOWN PAIRS`
- `BLOCKED BY INSUFFICIENT SAMPLE SIZE`

Wilson intervals and sample size decide whether a pair is `PASS`, `FAIL`, or `INCONCLUSIVE`. A tiny result pointing the right way is still inconclusive.

## No-Submit Reporting

Every serious run report should include:

- exact command
- git status
- archive paths and SHA256s
- replay/game/opponent counts
- seed or seed schedule
- win/loss/draw/error counts
- invalid actions, crashes, timeouts
- per-hard-gate results
- verdict
- `kaggle_submission_made: false`

Kaggle submission remains forbidden without explicit user approval.
