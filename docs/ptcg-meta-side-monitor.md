# PTCG Meta Side Monitor

This monitor is a read-only side artifact for local/public replay analysis. It does not submit to Kaggle and does not change core agent policy.

## What It Produces

Run output goes to `artifacts/meta_monitor/` by default:

- `matchup_summary.csv`: archetype-vs-archetype player-game rows with xG-style expected game score and expected prizes taken.
- `prize_race_states.csv`: observable prize-race states by matchup, using prize counts and prize differential only.
- `opening_tree_rankings.csv`: opening decision sequences ranked by expected game score, then expected prizes taken.
- `deck_rankings.csv`: stable deck-fingerprint rankings by xG-style game score and expected prizes taken.
- `deck_matchup_matrix.csv`: deck-fingerprint-vs-deck-fingerprint matchup rows.
- `deck_fingerprints.csv`: replay deck fingerprints, public card-ID summaries, and conservative archetype labels.
- `latest_summary.json`: generation timestamp, counts, and output paths.
- `monitor.log`: heartbeat/progress log for a separate terminal.

## Legal Data Boundary

The script uses local public replay JSON, public pulled-code metadata already in the workspace, and observable/public replay artifacts. It does not use competitor source beyond public pulled artifacts, does not use hidden prize identity for scoring, and does not submit anything to Kaggle.

## One-Shot Run

```powershell
python scripts\ptcg_meta_side_monitor.py --replay-dir data\Pokemon-Replays-Public --output-dir artifacts\meta_monitor --max-replays 25
```

Use `--max-replays 0` or omit the flag to scan every replay JSON file.

## Continuous Side Terminal

```powershell
.\scripts\start_meta_monitor.ps1 -ReplayDir data\Pokemon-Replays-Public -OutputDir artifacts\meta_monitor -IntervalSeconds 300 -HeartbeatEvery 10
```

Leave this running in its own terminal while other work proceeds. It refreshes the report files each interval and appends progress to `artifacts/meta_monitor/monitor.log`.

## Interpretation Notes

`x_game_score` is the average player-game result from public replay rewards: win is `1.0`, loss is `0.0`, tie/unknown is `0.5`.

`x_prizes_taken` is the average final observable prizes taken, derived from prize count movement. It is not based on hidden prize card identities.

Archetype labels are conservative. Known public Lucario IDs and visible card names are named when the local artifacts prove them; otherwise decks are grouped by stable card-ID fingerprints.

Deck rankings use stable hashes of the public deck list when the replay exposes the initial deck action. The rank order uses `adjusted_x_game_score` and `adjusted_x_prizes_taken`, which shrink tiny samples toward a neutral prior so one-game decks do not automatically dominate the table. They rank observed public replay deck performance, not an exhaustive hidden-information game tree.
