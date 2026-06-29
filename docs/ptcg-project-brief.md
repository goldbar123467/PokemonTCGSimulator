# PTCG Project Brief

Last condensed: 2026-06-29.

This repo is a no-RL Pokemon TCG Kaggle agent workspace. The active direction is public/legal gameplay research, replay audit, archive validation, local benchmark calibration, and hand-written heuristic work. Kaggle submission is forbidden unless the user explicitly approves it.

## Hard Rules

- Do not run PPO, policy gradients, behavior cloning as an improvement path, random self-play counters, or new training loops.
- Do not use hidden information, private kernels, opponent source code, hidden prize-card identities, or Kaggle side effects.
- Do not promote from smoke tests. Treat 12 games as package health only.
- Do not call local win-rate movement meaningful unless historical calibration supports the benchmark.
- Do not overwrite or demote the locked Lucario champion without explicit approval.

## Locked Champion

- Name: `lucario_web_teacher_champion`
- Archive path when present: `artifacts/submission_lucario_web_teacher_cleaned_pathfix.tar.gz`
- Kaggle ref: `54079056`
- Public score: `976.7`
- SHA256: `FAAEE1C05617F21B703E339BF8BC717DFAA3CA9FB2653903C393D017A2108CAF`
- Registry: `configs/champion_registry.json`

After the 2026-06-29 storage cleanup, generated artifact folders may be absent locally. The registry is the identity lock; the archive must be restored or rebuilt before validation, calibration, or comparison work.

## Meta Distinction

Do not conflate these:

- Public visible meta: public ladder and Game History deck buckets. Use it as a prior on likely opponents.
- META eval field: the scored frequency-weighted opponent set. It is a different lens and must stay separate in reports, gates, and promotion decisions.

Refresh the daily meta API before serious gate or candidate work:

```powershell
Invoke-RestMethod 'https://ptcg-kaggle-meta.vercel.app/api/meta?page=1'
```

Record `date`, `latestDate`, `redirected`, `totalDecks`, and `source.datasetUrl` in every serious run report.

## Current Working Truth

- Local benchmark score is not Kaggle leaderboard score.
- The official `cg` SDK has no full battle seed hook. Seed schedules are reproducible labels, not Common Random Numbers proof.
- The simulator option interface is `agent(obs) -> list[int]`; the agent ranks legal option indices, it does not construct actions.
- First-option/B1 is a strong baseline. Naive reordering often loses to it.
- Strict archive validation and local runnable status are separate concepts.
- Reused result directories are evidence only when archive SHA, benchmark config hash, matchup requirements, schema version, opponent registry, and seed schedule match.

## Strategic Priorities

- Must report public Lucario and public Dragapult/spread gates explicitly.
- Current priority gates: Lucario, Dragapult/spread, Hop/Trevenant, Alakazam/Psychic, Team Rocket Petrel/Transceiver, Starmie-style tempo, and metal/Archaludon tempo when available.
- Lucario work uses the SHA-locked web-teacher champion as the floor.
- Lucario candidate direction, if calibration permits: patch policy/heuristic posture first, then minimal Boss balance only with evidence.
- Starmie retry truth: broad online repair remained bad into Lucario; only `starmie_lucario_farm_v1` moved Lucario off zero, and it was still not promotion-ready.
- Archaludon truth: many no-RL rewrite rounds stayed non-promotable despite some local movement; do not schedule or submit those artifacts.

## Dead Ends

- RL/PPO/BC/search-hybrid work is historical diagnostic material only unless the user explicitly reopens it.
- Replay loss narratives are not proof. Loss rows find flaws; they are not demonstrations.
- Winning rows are not cloning targets. Extract posture, prize map, target selection, sequencing, and resource discipline.
- Do not keep stacking card weights when the failure is state posture: no next attacker, wrong target, active overattachment, poor supporter timing, or no low-deck restraint.

## Canonical Starting Point

Before strategy, replay analysis, evaluation, candidate, or packaging work:

1. Read `AGENTS.md`.
2. Read `docs/groupknowledge.md`.
3. Read this brief.
4. Check whether generated artifacts/replays needed for the task still exist locally.
5. If artifacts were cleared, rebuild or restore only the specific inputs needed for the run.
