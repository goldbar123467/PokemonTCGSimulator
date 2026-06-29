# PTCG AI — Group Knowledge

Living context file for the competition agent. **Append, don't overwrite.** Newest meta snapshots go at the top of §1. Drop new findings under the relevant section and add a line to the Append Log at the bottom.

Two distributions appear in this file and **they are not the same thing**:
- **Public visible meta (§1)** = what the top-10 ladder decks *are* (deck buckets). Source: public Leaderboard / Game History only. A prior on opponents, **not** the hidden eval distribution.
- **META eval field (§3)** = the frequency-weighted opponent set the agent is *scored against*. Different archetype names, different lens. Don't conflate.

---

## 1. Public visible meta — Meta Log (newest first)

> Source: public Leaderboard / Game History only. NOT the hidden eval distribution. Decklists and IDs stay private; buckets are abstract labels. Add new dated entries at the TOP.

### 2026-06-28 — Archaludon submit-prep snapshot

Latest API snapshot used for the Archaludon pure-heuristic submit prep: `date=2026-06-27`, `latestDate=2026-06-27`, `redirected=false`, `totalDecks=11838`, dataset `pokemon-tcg-ai-battle-episodes-2026-06-27`.

Local finding: the custom Archaludon scorer was legal but collapsed in the 10-game gate smoke. A simpler B1/first-option Archaludon shell was stronger locally (`10-30` overall as acting candidate across Lucario, current Starmie, Hop/Trevenant, Dragapult-ish gates) and became the scheduled 5:30 PM candidate. Treat this as grain-of-salt local evidence, not a leaderboard forecast.

Correction after user stop request: the scheduled 5:30 PM B1 submission was deleted and verified absent before firing. The B1 shell is not shippable: it was legal but weak, and the first rewrite round of weight-tweaked Archaludon candidates also failed badly against strong local gates. Continue from a guarded-B1 policy rewrite with explicit unsafe-retreat, live-attack, backup-attacker, and Starmie-bridge rules; do not reschedule any Archaludon submit until a package ranks first in the local gate.

### 2026-06-28 — Metal tempo becomes a new axis (full-fetch 1330/1330)

Top-10 deck-bucket composition:

| Broad archetype | Count | Δ vs prev |
|---|---|---|
| Starmie-style (water / fire / spread tempo) | 5 / 10 | — |
| Archaludon-style metal tempo | 3 / 10 | **+1** |
| Psychic / Alakazam-style control | 2 / 10 | — |
| (grass/fire/spread hybrid bucket) | — | −1 |

Evaluation priority:

| # | Axis | Count | Why it matters |
|---|---|---|---|
| 1 | Starmie-style water/fire/spread tempo | 5/10 | Largest visible group → main public stress bucket |
| 2 | Archaludon-style metal tempo | 3/10 | New major axis; **Rank 1 is here**, so Starmie-only tuning is risky |
| 3 | Psychic / Alakazam-style control | 2/10 | Core control check; fast-tempo-only agents may fail here |

Read:
- Starmie-style still the largest visible group.
- Metal tempo is now its own axis (was background noise) → **test it directly, don't fold into "Other."**
- One-axis (Starmie-only) reads are risky now that Rank 1 is metal.
- Going forward, assume **three** eval axes: **water/fire/spread · metal · psychic**.

Virtual enemies to expect: Starmie water/fire tempo · Mega Froslass + Starmie · Archaludon metal tempo · Alakazam/Psychic control.

Next actions: track Starmie-style · add a metal-tempo axis · keep the Psychic-control check · check Hop / Lucario / Iono regressions.

---

## 2. Engine reality (the interface the agent actually faces)

- One interface: `agent(obs) -> list[int]`. The engine enumerates every legal play in `obs["select"]["option"]`; you return indices into that menu. **You never construct an action — you rank and pick.** (Modeling the game as "build an attack/attach" had to be scrapped entirely.)
- Options arrive in a strong **best→worst** order. Returning `[0]` ("B1") beats random ~88–90% and is a hard local optimum. Naive type-priority reorders **lose** to B1 (3.3% vs first-index).
- **No RNG seed hook.** `BattleStart` takes only the 120 card IDs; no seed is exposed to Python. Every eval is independent-sample → large variance, **no Common Random Numbers (CRN).**
- Latency is **not** the bottleneck (~8.6 ms per MAIN decision; beam ~8.6 ms). Eval variance is.
- **2026-06-28 local round robin:** use `ptcg/round_robin.py` plus `scripts/run_round_robin.py` for local archive-vs-archive benchmarking. It drives the official SDK in `data/official/cg.game` and treats agents as option-index rankers. It can run archives that are missing bundled `cg/` by injecting the local official SDK, but those packages are flagged with `uses_external_official_cg` and are not strict Kaggle-clean. Keep strict archive validation separate from local runnable status.
- **2026-06-29 Phase 3 benchmark harness:** use `scripts/run_local_kaggle_parity.py` for one-archive raw-exec/startup/smoke checks and `scripts/run_benchmark_league.py` for fixed-registry, seed-scheduled local leagues. The seed schedule is deterministic and saved, but official `cg` still lacks exported full battle seed control, so treat schedule seeds as reproducible run labels rather than CRN proof. Local league scores are not Kaggle leaderboard scores.
- **2026-06-29 Phase 4 benchmark comparison gate:** use `scripts/compare_candidate_archives.py` to validate candidate and baseline archives, load or run fixed-registry benchmark results, add Wilson confidence intervals, compare by opponent, update `artifacts/benchmark_lab/benchmark_index.json`, and emit `PASS`, `FAIL`, or `INCONCLUSIVE` from `configs/benchmark_gate.json`. A `FAIL` on too-small samples is expected with smoke-size runs; do not interpret local comparison status as Kaggle leaderboard strength.
- **2026-06-29 Phase 5 calibration reliability layer:** champion identity is locked in `configs/champion_registry.json` by path and SHA, and historical archives are tracked in `configs/archive_registry.json`. Use `scripts/run_historical_calibration.py` for calibration reports, not promotion. Reused result directories must pass archive SHA, benchmark config hash, required matchup, schema version, and recorded opponent/seed hash checks before comparison treats them as evidence. `scripts/run_benchmark_league.py` now supports `--target-games-per-matchup` and `--resume`; it writes richer public-count diagnostics and categorized failures. This still does not make local benchmark score equal Kaggle leaderboard score.
- Current parity proof is still **partial**, not perfect 1:1: `scripts/native_official_parity_audit.py --deck deck.csv --opponent-deck deck.csv --seed 3 --max-frames 1` reports 36 passes, 0 fails, and one known gap, `frame_by_frame_engine_parity`.

---

## 3. What ships / what's best

| Agent | META WR | Status |
|---|---|---|
| StarmiePolicy on keidroid LB#1 deck | **54.0%** (σ=1.4pp, N=1,200) | **Confirmed-shippable** |
| Opp-belief-gated search hybrid (v2) | **59.7%** (+5.7pp) | **Blocked** — needs forward-search API at submission (see §6) |
| Best Alakazam (beam over heuristic) | 22.6% | Superseded (2.4× worse than Starmie) |

**Highest-value decision: copy the LB#1 deck.** Extracted keidroid's exact 60-card Mega Starmie ex list (78 winning games, same variant). *The deck was the lever, not the pilot.* keidroid's real ladder record on it: 78W / 38L = **67.2%**. The heuristic alone reaches 54%; the remaining ~13pp gap is what keidroid knows that the policy doesn't.

**META eval field weighting (competition-calibrated, sums to 100%):**
Lucario 42% · Crustle 15% · Trevenant 25% (BaseTrev 15% + PetrelTrev 10%) · Bellibolt 8% · Other 10%.

### Per-matchup (pure StarmiePolicy)

| Matchup | Field weight | WR |
|---|---|---|
| Lucario | 42% | **29.0%** ← the wall |
| Crustle | 15% | 39.0% |
| BaseTrev | 15% | 82.9% |
| PetrelTrev | 10% | 80.6% |
| Bellibolt | 8% | 68.5% |
| Other | 10% | 100% |

### Search-gating rule (the core hybrid insight)

1-ply forward search **hurts** Lucario (29 → 22, −7pp) but is **huge** on Crustle (39 → 83.5, **+44.5pp**). Gate by opponent identity (Bayesian archetype ID from observed bench cards, `agent/opp_belief.py`):

> **Default to pure StarmiePolicy. Switch to search-wrap only once the opponent is confidently non-Lucario (conf ≥ 0.60).**

Direction matters — defaulting to search and switching to pure on Lucario **fails** (57.0%): you can't recover the Lucario WR after a search-poisoned opening. Defaulting to pure fixes it (59.7%).

| Variant | META | Lucario | Crustle |
|---|---|---|---|
| pure StarmiePolicy | 54.0% | 29.0% | 39.0% |
| always 1-ply search | 57.1% | 22.0% | 83.5% |
| hybrid v1 (default search) | 57.0% | 20.1% | — |
| **hybrid v2 (default pure)** | **59.7%** | 24.5% | 86.0% |

---

## 4. The Lucario wall (TOP priority lever)

- 29% WR, and Lucario is **42% of the field** → +5pp here adds more META than any other lever.
- **Structural:** Mega Brave hits 270, enabling turn OHKOs; Starmie ex (250 HP) dies in one hit once Lucario is charged. The tempo race is extremely tight.
- Tried & failed: BC clone of keidroid (36% META, −18pp; 55% clone acc compounds into bad states) · beam (hurts Lucario specifically) · sub-weight tuning (marginal only).
- **Open ideas:** a non-ex tech attacker that changes the matchup *structurally* (the way Hariyama changes Crustle)? Mining keidroid's Lucario sub-policy from only 78 games is noisy.

---

## 5. Dead ends (don't re-run these)

- **Pre-transformer plateau (~9 methods):** 1-ply / 2-ply search, ISMCTS / AlphaZero-lite, MLP self-play, FSP pool, Demo-RL, heuristic reorders, ~10 hand-built decks — all ceiling'd at ~B1. Cause = **representation** (no card identity), not capacity (256-wide ≈ 64-wide). Lever that broke it: **card-embedding multi-head transformer** (DMODEL=64, NHEAD=4, NLAYERS=2) → 73–74% vs B1 mirror.
- **Beam value ∝ 1 / base-policy quality.** +11.3pp on weak Alakazam (10.7→22.0), −15.4pp on strong StarmiePolicy (54.0→38.6). **Wrap weak heuristics; leave strong ones alone.**
- **Imitation (BC / DAgger) plateaus below the teacher** (~41% H2H; teacher wins 59-41). Iter 4 = covariate-shift inversion (highest clone acc = worst H2H). Pure imitation can't pass the teacher → need search or RL self-play on top.
- **RL plateau is a measurement limit, not algorithmic.** Linear board probe AUC **0.82** vs value-head **0.61**; adding the hidden hand only +0.007. The RL evaluator sits below its own noise floor, so no A/B is interpretable without a paired, low-variance eval. RL stays a methodology note, not a WR lever.
- **Forensic loss-analysis trap.** LLM read 40 losses (15/40 bench-outs), surfaced 3 "obvious" fixes; shipping them cost **−7.6pp pooled (p=0.003)**. Survivorship bias — losing traces hide every game those same plays *won*. **Trust the A/B over the compelling narrative.**

---

## 6. Open blockers

- **Does the Kaggle runtime expose forward search at submission?** `cg.sim.lib` exposes `search_begin / search_step / search_release`; the 59.7% hybrid calls these. But native `cg` is **NOT** in the pip `kaggle-environments` package (entirely different card-ID universe), and our submission shim strips the search fns. → **starmie_raw (54%) is shippable; starmie_hybrid (59.7%) is blocked** until search is confirmed to run on the eval harness.
- **Variance reduction without a seed.** No CRN. Current practice in §7.
- **Kaggle raw-exec package imports.** A submission archive that imports `from cg.api ...` must bundle a top-level `cg/` runtime folder and make the package root importable even when `__file__` is absent. Prefer a compiled-code-filename fallback before `os.getcwd()` for raw `exec` compatibility.

---

## 7. Eval discipline (learned the expensive way)

- **Revalidate at ≥400 games before trusting any result.** "77%" @200 → 67% @400. 128-dim net 74% @200 → 66.8% @400.
- **Watch the noise floor.** Hill-climbing 68 weights "improved" 0.786 → 0.861 → 0.921; re-evaluating the *identical* config at 2,000 games gave 0.8665 vs 0.8802 — a **1.37pp gap from pure sampling noise** vs a 0.5pp accept threshold. Honest Alakazam WR ≈ 0.88, not 0.92.
- **No CRN** → use sequential testing (SPRT-style) for go/no-go and larger N than paired experiments would need. Working numbers: **N=1,200/arm** (σ=1.4pp per matchup).

---

## 8. Repo pointers

| Path | What it is |
|---|---|
| `engine/bench/bench_meta_weighted.py` | Frequency-weighted field eval |
| `engine/pilots/starmie_hybrid_pilot.py` | Opp-belief-gated search hybrid |
| `agent/opp_belief.py` | Bayesian archetype ID from observed board |
| `engine/pilots/ala_beam_pilot.py` | Beam over heuristic (Alakazam) |
| `engine/tools/privileged_critic_probe.py` + `data/board_critic_logistic.json` | AUC-0.82 linear board evaluator (reusable as Texel target / GAE baseline) |
| `tests/probe_value_head.py` | Overfit-one-batch value-head sanity probe |
| `engine/tools/extract_player_decisions.py` | Extract episodes / keidroid deck from public replays |

---

## Append Log

- **2026-06-28** - Recorded Archaludon pure-heuristic submit prep: custom scorer validated but failed local gates; B1 metal shell validated, dry-run submit passed, and was scheduled for the 5:30 PM guarded submit.
- **2026-06-28** - Corrected Archaludon submit prep: deleted the bad B1 5:30 PM submit automation, recorded first rewrite failure, and moved work to a guarded-B1 Archaludon policy rewrite before any future submit scheduling.
- **2026-06-28** — Added the official-SDK local round-robin runner note: `ptcg/round_robin.py` and `scripts/run_round_robin.py`; first supplied-archive 10-game directed benchmark finished 120/120 games with 0 runtime errors, but several packages remained strict-validation dirty and simulator parity remains partial.
- **2026-06-28** — Initial knowledge base assembled from project writeup + public meta snapshot (metal tempo now a separate axis).
- **2026-06-28** - Recorded `submission (3).tar.gz` packaging fix: missing `cg/` plus no-`__file__` raw-exec path bootstrap caused `ModuleNotFoundError: No module named 'cg'`.

- **2026-06-28** - Archaludon rewrite rounds 7-13 stayed non-promotable. Fixed the B1 multi-select legality bug and built Cinderace/Turbo, backup-spread, choose-second, and Fumi-second pure-heuristic variants. Best clean local Archaludon evidence remained below the gates: `round10_cinderace_spread_5g` best new spread package was 15-20 overall and 0-5 into Lucario; `round11_existing_arch_compare_5g` best old Archaludon was 14-26 and 0-5 into Lucario/Starmie; `round13_fumi_second_5g` had all Fumi-second variants 0-5 as acting candidate into Lucario/Starmie/Hop/Dragapult. No Archaludon package ranked first locally, no Kaggle submission was made, and no submit automation should be scheduled from these artifacts.
- **2026-06-28** - Archaludon rounds 14-20 stayed non-promotable after trace-driven no-RL heuristic work. Round 14 traces for `submission_archaludon_cinderace_turbo_second_judge_v1` showed single-active race, active overfeed, missed bench attachment, and no next attacker under pressure. Round 16 no-Relic + extra Metal improved the compact local shape once (17-18 overall, 1-4 Lucario, 1-4 Starmie, 2-3 Hop, 3-2 Dragapult-ish), but it was unstable across seeds. Round 20 best clean variant was `submission_archaludon_cinderace_no_relic_judge_metal_v1` at 17-18 overall with 0 errors, but still only 1-4 into Lucario and 1-4 into Starmie. Do not submit or schedule any Archaludon package from this run; no Kaggle submission was made.
- **2026-06-28** - Archaludon rounds 21-24 also stayed non-promotable. Round 21 broad no-Relic policy regressed (best new Arch 15-20); round 22 backup-lock overcorrected to 4-21; round 23 public Carmine/Judge disruption shell failed locally (best 6-24); round 24 Relicanth Memory Dive/Raging Hammer shell still finished 7-18 and failed Lucario. Live archetype detail showed public Archaludon aggregate strength (1725 appearances, 62.2% WR, strong Lucario/Starmie/Hop/Dragapult matchups), but local heuristic packages did not reproduce it. Refreshed final report: `artifacts/ptcg_research/current/archaludon_rewrite_2026_06_28/final_report/archaludon_final_report.md`. Decision remains do not submit, do not schedule; no Kaggle submission was made.
- **2026-06-28** - Archaludon rounds 25-28 stayed non-promotable after fixing duplicate Energy counting, Boss context 3 targeting, own-board Boss target guards, Memory Dive Hero Cape redirects, and damaged-Duraludon third-Energy setup. Round 25 best broad Archaludon was `submission_archaludon_cinderace_turbo_b1_v1` at 18-17 overall but 0/10 directed into Lucario; round 27 Memory Dive had the best Lucario movement at only 3/20 directed; round 28 Memory Dive regressed to 1-19 as acting candidate into Lucario. Final report: `artifacts/ptcg_research/current/archaludon_rewrite_2026_06_28/final_report/archaludon_final_report_round25_28.md`. Decision remains do not submit, do not schedule; no Kaggle submission was made.
- **2026-06-28** - After the stop request, round 29 patched Memory Dive to bench a second Duraludon line before Relicanth, but it still failed: `round29_memory_second_line_guard_5g` ranked last at 4-21 and 0-5 into `submission_3_cg_fix`, Lucario, and Hop/Trevenant. A legal Archaludon gate was then built from public replay `82396187` (`round31_archaludon_gate`). The widened internal leaderboard with 35 archives and 13 available gates ranked `submission_hop_trevenant_v2_loop5_best_spread_restraint.tar.gz` #1: 56-9, weighted WR 0.952, no hard-gate collapses, SHA256 `00FA5663722BBC1F72EDA09BB5442DF96DF6341C6A4F90A785C40AFA63BA62FE`. Guarded submit dry run passed, but no Kaggle submission was made and no submit automation was scheduled. Ready report: `artifacts/ptcg_research/current/archaludon_rewrite_2026_06_28/submit_ready_rank1/submit_ready_rank1_report.md`.
- **2026-06-29** - Added Phase 3 local Kaggle parity and benchmark league workflow: strict one-archive parity artifacts, deterministic seed-schedule persistence, fixed opponent registry, benchmark JSON/CSV outputs, light `train.py --run-benchmark` orchestration, and no gameplay-log reads inside parity/benchmark helpers. Kaggle submission made: no.
- **2026-06-29** - Added Phase 4 benchmark calibration and comparison workflow: candidate-vs-baseline comparison command, Wilson CI stats, configurable benchmark gate thresholds, regression checks, benchmark index updates, and explicit PASS/FAIL/INCONCLUSIVE decisions. Kaggle submission made: no.
- **2026-06-29** - Added Phase 5 benchmark trust layer: champion registry lockfile, archive registry, historical calibration command, result-dir compatibility checks, categorized failures, prize-count/turn diagnostics, resume/run-until-N benchmark support, and sample calibration audit. Kaggle submission made: no.
- **2026-06-29** - Condensed operating knowledge into `docs/ptcg-project-brief.md`, `docs/ptcg-evaluation-playbook.md`, and `docs/ptcg-storage-retention.md`; cleared generated replay/artifact stores for disk space. Registries remain identity locks, but local archive files may need rebuild or restore before validation.
