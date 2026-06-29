# PTCG Gameplay Research and Heuristic Operating Rules

This repo is for building a stronger Pokemon TCG Kaggle agent through gameplay research, replay analysis, deck tuning, and hand-written heuristics.

## Required Context Files

- Before doing strategy, meta, replay-analysis, evaluation, candidate, or packaging work, read `docs/groupknowledge.md`.
- Treat `docs/groupknowledge.md` as append-only living group knowledge: add newest meta snapshots at the top of its meta log, put findings under the relevant section, and add an Append Log entry. Do not overwrite or collapse its historical notes.
- Keep its distinction between public visible meta and the META eval field intact. Public visible meta is a ladder/Game History prior on opponents; the META eval field is the scored frequency-weighted opponent set. Do not conflate them in reports, gates, or promotion decisions.

## 2026-06-26 Hard Pivot: Stay Away From RL

- Do not run, propose, or scale reinforcement learning for this project unless the user explicitly reverses this rule in a new request.
- Do not run PPO, policy-gradient training, neural imitation loops, random self-play counters, C random battle counters, or "real RL" pipeline work as an improvement path.
- Do not call replay labels, behavior cloning, heuristic weight sweeps, random self-play, or pseudo-trajectories "RL".
- Do not promote learned wrappers from old BC/PPO experiments. Treat them as historical diagnostics only.
- The current winning direction is evidence-backed heuristic tuning from public/legal gameplay, not learned policy training.
- Legacy RL/PPO/BC improvement paths have been purged from the active repo surface. Do not recreate them unless the user explicitly reopens that direction.

If a future agent is tempted to start a training loop, stop and convert the idea into one of these instead:

- replay/gameplay analysis
- scout reports
- matchup-specific heuristic rules
- decklist A/B candidates
- gate opponents from public/legal replays
- deterministic or repeated-batch heuristic evaluation
- package-only validation

## Current Truth

- Current leaderboard champion so far: Kaggle ref `54079056`, file `submission_lucario_web_teacher_cleaned_pathfix.tar.gz`, completed `2026-06-26 13:34:49.317000`, public score `976.7`.
- Previously submitted champion archive SHA256 for that ref: `ADFAE1179D36497119E5DCAE34141BFE6D5E366FF93E07BA905252CFEC97CD39`.
- Current rebuilt local archive: `artifacts/submission_lucario_web_teacher_cleaned_pathfix.tar.gz`.
- Current rebuilt local archive SHA256: `FAAEE1C05617F21B703E339BF8BC717DFAA3CA9FB2653903C393D017A2108CAF`.
- Requested resubmission: Kaggle ref `54093112`, completed `2026-06-27 01:42:11.360000`, public score `600.0`.
- Treat ref `54079056`, not the lower-scoring ref `54093112`, as the baseline/floor for all Lucario heuristic tuning until the score-drop is diagnosed or the user explicitly replaces it.
- Do not overwrite, rename, or demote the `54079056` champion without stronger replay/gate evidence and explicit user approval.
- The existing strongest local packages are heuristic-generated, not learned.
- This is now a heuristic and gameplay-research project.
- Replay labels are patch maps, audit data, and gate definitions. They are not training targets by default.
- Loss replay rows are not demonstrations. Use them to find heuristic flaws such as missed setup, active overattachment, attack without backup, missed trap turns, and bad recovery posture.
- Winning replay rows are not blindly cloned. Use them to identify strategic posture: setup, prize map, target selection, energy management, and preservation.
- Kaggle submission is forbidden unless the user explicitly approves submission.

## Official Rules vs Simulator Behavior

The competition simulator is designed for AI-vs-AI battles and may differ from the official Pokemon TCG rules. For this repo, treat simulator behavior as the correct competition behavior for legality, option selection, replay interpretation, gate evaluation, and package promotion.

Known differences to account for:

- Some attacks may not be selectable in the simulator even when they could be declared under the official rules if the attack effect cannot be fully resolved. Examples include putting a Basic Pokemon from the deck onto the Bench when there is no open Bench space, drawing cards when the player's deck has 0 cards remaining, or interacting with the opponent's hand when the opponent has 0 cards in hand. Treat simulator non-selectability as correct for this competition.
- For Mega Zygarde ex's `Nullifying Zero`, official rules allow the attacking player to choose the order in which damage is assigned to targets. In the simulator, target order cannot be chosen and coins are flipped automatically from left to right. Knock Out processing is simultaneous, so this difference is expected not to affect competition outcomes.
- Prize-taking order differs when both players' Pokemon are Knocked Out at the same time. Under official rules, the player whose turn is next chooses Prize cards, the opposing player chooses Prize cards, both players take Prize cards at the same time, and then the player whose turn is next puts a Pokemon into the Active Spot first. In the simulator, the player whose turn is next chooses and takes Prize cards first, then the opposing player chooses and takes Prize cards, and then the player whose turn is next puts a Pokemon into the Active Spot first. Competition results still treat both players ultimately taking all Prize cards as a draw, so use the simulator result as the outcome truth.

If additional simulator behavior announcements appear in the Discussion forum, add them here before encoding heuristics that depend on official-rule edge cases.

## Data Use Requirements

Correct data use means preserving provenance, legality, and role separation:

- Copy raw user-supplied and Kaggle replay JSON files into the run artifact directory before processing. Do not analyze only from untracked Downloads paths.
- Record the live meta snapshot used for the run: API `date`, `latestDate`, `redirected`, `totalDecks`, and `source.datasetUrl`.
- Label every gameplay row with `data_source`, replay id, source file, source hash when available, team name, owner label, actor index, opponent index, outcome, winner side, actor archetype, opponent archetype, matchup tag, and sample weight.
- Owner labels must stay explicit: `clark_kitchen` only for exact Clark Kitchen metadata, `focus_user_supplied_agent` for the user-designated repeated agent, `external_kaggle_team` for other public teams, and `unknown_kaggle_team` when metadata is missing.
- Sanitize or avoid hidden information. Do not use private kernels, competitor source, Kaggle side effects, hidden deck contents, or prize-card identities unless they are public/legal in the observation contract.
- Keep raw replays, hard labels, scout reports, heuristic patch notes, gate manifests, evaluation reports, and package artifacts as separate files.
- Do not mix local native runs, Kaggle leaderboard replays, public replay pools, and manually labeled rows without a field that identifies their source and intended research role.
- Every dataset-producing or report-producing script must write a machine-readable summary with command, input paths, replay/game counts, row counts, label counts, source metadata, and `kaggle_submission_made: false`.

## Research Loop

Use this loop before touching a candidate package:

1. Preserve raw replay files under `artifacts/`.
2. Record the current live meta API snapshot.
3. Parse replay metadata: teams, rewards, statuses, steps, actor indexes, deck ids, and SHA256s.
4. Build per-game scout reports. For important games, use two scouts: one tactical-flow scout and one strategy/deck scout.
5. Extract the repeated flaws into a patch map.
6. Translate the patch map into explicit heuristic rules.
7. Build 2-3 small, complementary candidate families.
8. Gate the candidates against public Lucario, public Dragapult/spread, current top meta, and replay-derived stress tests.
9. Package only candidates with zero legality/startup errors and clear broad-gate evidence.
10. Report package path, SHA256, gates, failures, and `Kaggle submission made: no`.

## 2026-06-26 Huge Lucario Finding

Source replay files:

- `C:/Users/Clark/Downloads/82051250.json`
- `C:/Users/Clark/Downloads/82051250-0.json`
- `C:/Users/Clark/Downloads/82056240.json`
- `C:/Users/Clark/Downloads/82056240-1.json`
- `C:/Users/Clark/Downloads/82047820.json`
- `C:/Users/Clark/Downloads/82047820-0.json`
- `C:/Users/Clark/Downloads/82059053.json`
- `C:/Users/Clark/Downloads/82059053-1.json`

Research artifact:

- `artifacts/ptcg_research/current/lucario_leaderboard_strategy_2026_06_26/`
- Main synthesis: `lucario_leaderboard_strategy_theses.md`
- Scout reports: `scout_reports/*.md`
- Label summary: `labels/summary.json`

Main finding:

- The high-scoring Lucario submission, `submission_lucario_web_teacher_cleaned_pathfix.tar.gz`, maps to the safer web-teacher deck profile: 3 Poke Pad, 2 Boss's Orders, no Judge. It appeared as `967.3` in the screenshot and later as `976.7` for Kaggle ref `54079056`.
- `submission_lucario_web_teacher_cleaned_pathfix.tar.gz` ref `54079056` is the current champion so far. Every Lucario candidate must compare against it before being treated as an improvement.
- The `740.3` Lucario submission, `submission_lucario_less_preserving_track_a_v2.tar.gz`, maps to the sharper Track A v2 profile: -2 Poke Pad, +1 Boss's Orders, +1 Judge.
- Track A v2 has real mirror/disruption upside, shown by the Lucario mirror win in `82059053`.
- Track A v2 also exposed the major ladder failure mode: less smoothing and weaker preservation can collapse into Hop/Trevenant pressure, wall/control, and bad recovery turns.
- The better broad thesis is not "attack harder". It is "attack with backup".

Do not lose this finding. The next Lucario improvement should use the high-score web-teacher champion as the broad base and borrow only the safest Track A target-control ideas.

## Current Strategic Frame

Current meta source:

- Refresh the latest daily meta from `https://ptcg-kaggle-meta.vercel.app/api/meta?page=1` before serious loop, gate, or candidate work when network is available.
- Use `docs/current-meta.md` as the cached fallback snapshot when the API is unavailable or the user explicitly pins a date.
- Record the API-returned `date`, `latestDate`, `redirected`, `totalDecks`, and `source.datasetUrl` in reports.

Current priority matchups:

- Must respect public Lucario and public Dragapult/spread.
- Must respect Hop/Trevenant, Alakazam, and Team Rocket Petrel/Transceiver as current top-five meta gates.
- Must preserve broad public-code performance.
- Should improve into Mega Starmie, Nighttime Mine/Enriching Energy, Iono/Bellibolt, Genesect/Lucky Helmet, Gravity Mountain/Hariyama, Crustle/stall, and replay-derived top meta when locally available.
- May remain weak into narrow low-frequency profiles only if that weakness does not overlap the Lucario/Dragapult/Hop failure modes.

## Candidate Tracks

Build candidates in families, not one-off boosts:

- Track A: stabilizer, setup consistency, next attacker, conservative when ahead.
- Track B: balanced target control, small Boss/gust improvement without destroying setup smoothing.
- Track C: anti-Lucario mirror specialist, only if it does not collapse into Dragapult or Hop/Trevenant.
- Track D: anti-Dragapult/spread-aware posture.
- Track E: anti-Hop/Trevenant and control-resistant board development.
- Track F: stall-safe or wall-control resistant plan for Crustle/Waitress-style games.

Do not collapse all ideas into one candidate. A/B finalists must be complementary.

For the next Lucario deck pass, prefer:

- Candidate 1: `lucario_teacher_plus`, same 967 decklist, policy/heuristic patch only.
- Candidate 2: `lucario_boss_balanced`, minimal deck delta from the 967 list: `-1 Poke Pad`, `+1 Boss's Orders`, no Judge unless proven.
- Candidate 3 only if needed: a mirror specialist based on Track A v2, clearly labeled specialist and not champion by default.

## Heuristic Patch Targets

Patch state-aware behavior, not just card weights:

- Setup: if no stable current attacker or next attacker exists, prioritize Riolu/Mega Lucario/Hariyama setup, draw/search, and Energy to the future attacker.
- Attack with backup: do not take a high-value attack with a doomed active unless a replacement attacker is already available or the attack changes the prize map enough to justify it.
- Energy discipline: penalize extra Energy to an active that already attacks, especially if it is likely to be knocked out.
- Next attacker: reward attaching to benched Riolu, Mega Lucario, Makuhita, or Hariyama when the active is already functional.
- Stop card churn: if the KO or correct prize-map attack is already available with backup, stop playing extra search/draw cards and attack.
- Boss/gust targeting: prefer evolving basics, stage bridges, support engines, or powered next attackers when removing them delays the opponent rebuild.
- Hop/Trevenant: plan for the second Trevenant swing, not only the first KO. Preserve Switch, build a second attacker, and avoid relying on one Hero's Cape Mega Lucario.
- Lucario mirror: preserve the next Mega line, deny opposing Riolu/Mega rebuilds, and do not overcommit to one active.
- Dragapult/spread: remove Dreepy/Drakloak/Dragapult bridges early, avoid unnecessary bench liabilities, and preserve damaged key Pokemon.
- Wall/control: stop repeating zero-conversion active attacks into Crustle-like walls. Shift to gust, trap, alternate target, deck/resource conservation, or denial lines.
- Low deck: reduce self-mill and unnecessary thinning.

## Replay-Derived Gates

Use the 2026-06-26 games as living heuristic gates:

- `82051250`: Alakazam setup race. Lesson: aggression works when backed by second attacker and Hariyama/Hero's Cape continuity.
- `82056240`: Hop/Trevenant double-swing pressure. Lesson: one big Mega Lucario is not enough.
- `82047820`: Crustle/Waitress wall-control. Lesson: active overcommitment and zero-conversion attacks lose badly.
- `82059053`: Lucario mirror backup race. Lesson: mirror wins come from redundancy and preserved attackers, not blind aggression.

These games are research evidence and gate seeds, not training data for RL.

## Non-Negotiable Workflow

- Use TDD for new pipeline or evaluation code.
- Keep generated artifacts under `artifacts/`; source code and tests must stay in `ptcg/`, `scripts/`, and `tests/`.
- Do not submit to Kaggle unless the user explicitly approves submission.
- Do not start RL, PPO, BC-as-improvement, neural imitation, C random battle counters, or self-play learning loops.
- Do not create new training scripts unless the user explicitly asks to reopen training work.
- For gate building, prefer an existing public generic pilot paired with a public/legal extracted deck. Do not author a custom gate pilot unless the user explicitly approves it or no generic pilot can legally run the deck.
- Do not use hidden information, private kernels, competitor source, prize-card identities unless public/legal, or Kaggle side effects.
- Do not promote on error games, legality fallback, timeout artifacts, or mismatched startup behavior.
- Every long run must write a machine-readable report with command, git status, replay count, opponent count, seed, games, win/loss/draw/error counts, package path, SHA256, and `kaggle_submission_made: false`.

## Stop Conditions

Stop and diagnose before continuing if:

- Any proposed step starts RL/PPO/BC training or random self-play as an improvement path.
- Native simulator or package startup errors are non-zero.
- A candidate beats replay clusters but remains at or near zero into public Lucario or Dragapult/spread gates.
- A candidate improves the Lucario mirror but regresses broad meta, Hop/Trevenant, Dragapult/spread, or wall/control gates.
- A result depends on legality fallback, timeout artifacts, or mismatched startup behavior.
- A result cannot be reproduced from saved command, seed, artifact paths, and package SHA256.

## Verification Commands

Use these as minimum local checks for this no-RL workflow:

```powershell
python -m pytest
python scripts\label_user_leaderboard_games.py --replays artifacts\ptcg_research\current\lucario_leaderboard_strategy_2026_06_26\raw\82051250.json artifacts\ptcg_research\current\lucario_leaderboard_strategy_2026_06_26\raw\82056240.json artifacts\ptcg_research\current\lucario_leaderboard_strategy_2026_06_26\raw\82047820.json artifacts\ptcg_research\current\lucario_leaderboard_strategy_2026_06_26\raw\82059053.json --output-dir artifacts\ptcg_research\current\lucario_leaderboard_strategy_2026_06_26\labels --focus-team "Clark Kitchen" --meta-json artifacts\ptcg_research\current\lucario_leaderboard_strategy_2026_06_26\meta_snapshot.json
python -m ptcg.kaggle_archive_validator --archive artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz
python -m ptcg.kaggle_archive_validator --archive artifacts\submission_lucario_less_preserving_track_a_v2.tar.gz
tar -tzf artifacts\submission_lucario_web_teacher_cleaned_pathfix.tar.gz
tar -tzf artifacts\submission_lucario_less_preserving_track_a_v2.tar.gz
```

Do not use verification commands that start with `train_`, `collect_native_trajectories`, `train_policy_rl`, `run_real_rl_loop`, `run_lucario_ppo_loop`, or `c_loop` unless the user explicitly asks to audit legacy training code.
