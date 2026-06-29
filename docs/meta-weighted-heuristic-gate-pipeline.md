# Meta-Weighted Heuristic Gate Pipeline

Source: user strategy correction on 2026-06-25 plus daily Kaggle PTCG Meta app. Use this file for heuristic patching, gate selection, and replay research. It is not a learned-policy training plan.

## Core Claim

The field is moving. A candidate that only beats one sparring partner or one stale replay cluster is not strategically meaningful. Heuristic work must stay tied to the current meta:

1. A meta-share-weighted public opponent and replay gate pool.
2. Top-ranked public replay evidence used as strategy examples, not cloning targets.
3. Matchup-tagged decision and flaw labels.
4. Small, explicit heuristic patches evaluated against the same weighted gate pool.

Do not call a run strategically meaningful if it skips the opponent distribution or collapses the current champion into one broad untested tweak.

## Current Gate Weights

Refresh raw meta share from `https://ptcg-kaggle-meta.vercel.app/api/meta?page=1` before serious gate, replay, or candidate work. Use `docs/current-meta.md` only as the cached fallback snapshot. Normalize weights only at runtime.

The meta API returns the Kaggle source dataset in `source.datasetUrl`. Save that URL in every opponent-pool, gate, replay-labeling, and candidate report so the distribution can be reproduced.

If raw data is needed, derive the Kaggle dataset slug from that URL and use:

```powershell
kaggle datasets files kaggle/pokemon-tcg-ai-battle-episodes-YYYY-MM-DD
kaggle datasets download kaggle/pokemon-tcg-ai-battle-episodes-YYYY-MM-DD -p artifacts\meta_snapshots\YYYY-MM-DD
```

| Archetype | Raw weight |
|---|---:|
| Mega Lucario ex / Riolu | 22.6 |
| Hop's Phantump / Hop's Trevenant | 15.4 |
| Abra / Alakazam | 10.0 |
| Dragapult ex / Dreepy | 6.7 |
| Team Rocket's Petrel / Team Rocket's Transceiver | 5.9 |
| Ignition Energy / Mega Starmie ex | 4.7 |
| Nighttime Mine / Enriching Energy | 2.4 |
| Iono's Bellibolt ex / Iono's Voltorb | 2.3 |
| Genesect / Lucky Helmet | 2.0 |
| Gravity Mountain / Hariyama | 1.9 |

Every opponent-pool manifest entry should record archetype, raw meta weight, deck source, pilot source, legal/public source status, snapshot date, Kaggle dataset URL, smoke-test result, and any API redirect status.

## Lucario Ceiling Audit

Before major Lucario deck or heuristic investment, answer whether Lucario has enough public-performance headroom.

Required question:

What is the public-performance ceiling of the best leaderboard agents that are actually running Lucario?

Minimum report:

- Highest-ranked or highest-score public Lucario agents found.
- Evidence used to classify each as Lucario.
- Their leaderboard rank/score when available.
- Replay-derived win rate when available.
- Best Lucario result compared with the field and with non-Lucario top archetypes.
- Verdict:
  - If top Lucario agents are above about 52% win rate at meaningful game count, Lucario has enough pilot headroom. Patch the champion heuristic first.
  - If no Lucario agent is above about 48% win rate at meaningful game count, suspect a structural deck ceiling and flag a deck-track pivot before more Lucario tuning.
  - If the ceiling is ambiguous, around 48-52% or based on a small sample, patch the worst gate matchup first, prepare a candidate only with explicit submission approval, collect 50+ fresh ladder games, then rerun the ceiling check.

Do not use this audit to justify BC/PPO. It is a deck and heuristic investment gate only.

## Replay Evidence

Replay labels are a patch map and strategy audit, not a training target by default.

Preferred source:

- Top 20-30 public replays from highest-rated public leaderboard agents.
- Extract public/legal visible decisions, with winner side and matchup tags.
- Include strong non-Lucario games; they show what good play does into the same matchups our agent faces.

Each example must contain:

- `observation`
- `legal_actions`
- `chosen_action`
- `matchup_tag`
- `actor_archetype`
- `opponent_archetype`
- `replay_id`
- `winner_side`
- `leaderboard_rank` or `leaderboard_score` when available
- `sample_weight`

Weight evidence summaries by opponent meta share so the patch backlog reflects the ladder distribution, not just replay-count convenience. The current champion is the baseline/floor, not a cloning target.

## Heuristic Gate Pool

Gate sampling:

- Sample archetypes according to the current raw meta weights.
- Within an archetype, sample among available legal decks/pilots.
- Report per-matchup win rate, startup/legality errors, timeouts, and major replay-derived flaw tags.

A single sparring partner does not prove a heuristic patch is robust.

## Practical Priority Order

1. Run the Lucario ceiling audit against public leaderboard/replay evidence.
2. Refresh the latest daily meta API and record the returned date plus Kaggle dataset URL.
3. Pull the top 20-30 public replays from highest-rated public agents and build matchup-tagged strategy/flaw labels.
4. Build gate opponents for at least the top six archetypes using extracted public/replay decks plus existing public generic pilots.
5. Run the current heuristic against all top-six gates and write a matchup table.
6. Only then choose between tracks:
   - Above about 52% Lucario ceiling: heuristic patch the champion first.
   - No Lucario above about 48% at meaningful game count: deck-track pivot before more tuning.
   - Ambiguous 48-52% or small sample: patch worst gate, submit only with explicit user approval, collect 50+ ladder games, and rerun the ceiling check.

Kaggle submission remains forbidden unless the user explicitly approves it.
