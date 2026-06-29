# Current PTCG Meta Snapshot

Source: daily Kaggle PTCG Meta app plus user-provided screenshots. The app updates as new Kaggle episode datasets land, so this file is a cached working snapshot, not a permanent source of truth.

## Refresh Source

- Dashboard: https://ptcg-kaggle-meta.vercel.app/2026-06-24
- Latest API: `https://ptcg-kaggle-meta.vercel.app/api/meta?page=1`
- Date API: `https://ptcg-kaggle-meta.vercel.app/api/meta?date=YYYY-MM-DD&page=1`
- Archetype detail API: `https://ptcg-kaggle-meta.vercel.app/api/archetype?slug={slug}&date=YYYY-MM-DD`
- Kaggle source dataset is exposed in the API as `source.datasetUrl`.
- Kaggle CLI pattern:
  - List files: `kaggle datasets files kaggle/pokemon-tcg-ai-battle-episodes-YYYY-MM-DD`
  - Download: `kaggle datasets download kaggle/pokemon-tcg-ai-battle-episodes-YYYY-MM-DD -p artifacts\meta_snapshots\YYYY-MM-DD`

Verified on 2026-06-25: requesting `date=2026-06-25` redirected to latest available `date=2026-06-24`, `totalDecks=11032`, dataset slug `pokemon-tcg-ai-battle-episodes-2026-06-24`.

Before a serious loop, refresh from the latest API and record the returned `date`, `latestDate`, `redirected`, `totalDecks`, and `source.datasetUrl`. If the API or network is unavailable, use this file as the fallback snapshot and say that it may be stale.

## Top Archetypes

| Rank | Archetype | Meta share | Decklists | Win rate | Signature cards shown |
|---:|---|---:|---:|---:|---|
| 1 | Mega Lucario ex / Riolu | 22.6% | 2,492 | 42.5% | Basic {F} Energy, Lillie's Determination, Premium Power Pro, Fighting Gong, Mega Lucario ex |
| 2 | Hop's Phantump / Hop's Trevenant | 15.4% | 1,699 | 51.7% | Lillie's Determination, Mist Energy, Hop's Choice Band, Hop's Phantump, Telepath Psychic Energy |
| 3 | Abra / Alakazam | 10.0% | 1,106 | 53.7% | Alakazam, Enhanced Hammer, Kadabra, Abra, Buddy-Buddy Poffin |
| 4 | Dragapult ex / Dreepy | 6.7% | 740 | 59.6% | Basic {R} Energy, Basic {P} Energy, Dreepy, Drakloak, Buddy-Buddy Poffin |
| 5 | Team Rocket's Petrel / Team Rocket's Transceiver | 5.9% | 647 | 51.7% | Lillie's Determination, Team Rocket's Petrel, Pokegear 3.0, Boss's Orders, Mist Energy |
| 6 | Ignition Energy / Mega Starmie ex | 4.7% | 521 | 55.9% | Wally's Compassion, Lillie's Determination, Buddy-Buddy Poffin, Pokegear 3.0, Hilda |
| 7 | Nighttime Mine / Enriching Energy | 2.4% | 263 | 53.2% | Enhanced Hammer, Buddy-Buddy Poffin, Dawn, Kadabra, Abra |
| 8 | Iono's Bellibolt ex / Iono's Voltorb | 2.3% | 257 | 39.3% | Basic {L} Energy, Lillie's Determination, Canari, Iono's Bellibolt ex, Iono's Kilowattrel |
| 9 | Genesect / Lucky Helmet | 2.0% | 220 | 39.5% | Battle Cage, Poke Pad, Buddy-Buddy Poffin, Abra, Hilda |
| 10 | Gravity Mountain / Hariyama | 1.9% | 205 | 35.6% | Basic {F} Energy, Dusk Ball, Riolu, Mega Lucario ex, Poke Pad |

## Operating Implications

- Do not freeze gate priorities to this table if the daily API has moved; refresh the meta weights first.
- The old Waitress/Cook, Cheren/Battle Cage, Ethan/Cyndaquil, and top-five Bellibolt frame is stale for planning.
- Top-five gates now mean Lucario mirror, Hop/Trevenant, Alakazam, Dragapult, and Team Rocket Petrel/Transceiver.
- Heuristic gates and replay patch maps should be weighted by these meta shares; see `docs/meta-weighted-heuristic-gate-pipeline.md`.
- Before major Lucario deck or heuristic investment, run a Lucario ceiling audit against public leaderboard/replay evidence and apply the 52% / 48% / ambiguous threshold rules in `docs/meta-weighted-heuristic-gate-pipeline.md`.
- Bellibolt is still useful as a low-frequency diagnostic, but it is not a top-five gate in this snapshot.
- Dragapult is top-five again and has the highest displayed top-five win rate at 59.6%, so spread gates must be reported explicitly.
- Hop/Trevenant is the second-largest archetype and needs a real gate before more tuning against stale Cook/Waitress profiles.
- Alakazam appears twice in the top ten through Abra/Alakazam and Nighttime Mine/Enriching Energy, so Psychic/Abra targeting remains strategically important.
- Lower-share poor-win-rate Lucario variants such as Gravity Mountain/Hariyama are useful mirror diagnostics but should not displace the primary Mega Lucario ex / Riolu gate.

## Current Priority Order

1. Run the Lucario ceiling audit before major Lucario deck or heuristic work.
2. Ensure gates exist for at least the top six archetypes in the table.
3. For any missing top-six gate, build it from public/legal decklists or actual public replay decks and pair it with an existing generic public pilot when possible.
4. Build top-player winning-side strategy labels and heuristic patch maps with matchup tags.
5. Run the current heuristic against all available top-six gates to produce the matchup table.
6. Mine losses by archetype before patching.
7. Patch exactly one matchup behavior at a time.
8. Regression-test against all available top-six gates plus random sanity.
