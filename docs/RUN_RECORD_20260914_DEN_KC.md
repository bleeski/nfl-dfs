# Run record — DEN @ KC Showdown, 2026-09-14 (18 entries)

## Release truths
- `MODEL_STATUS=PRIOR_ONLY`, `RELEASE_DECISION=DO_NOT_UPLOAD`, `EVIDENCE_STATE=UNKNOWN`, `FILE_VALID=true`
- Policy enforcement: `ENFORCED_AND_INDEPENDENTLY_AUDITED`
- Shipped run `20260914T224958Z-den-kc-v6`; export SHA-256
  `4f5ab44f7003f5cd9dbad20bd0981d7ae9d08f48c06f557c48fa0b3231321204`
- Inputs: DKSalaries `e5224b69…3442204`, DKEntries `0b8c2703…111bbed`
- Weather: CLEAR, `api.weather.gov/gridpoints/EAX/47,48/forecast/hourly`,
  generatedAt 2026-09-14T22:16:24+00:00 (clear, 82-86F, S 13-14 mph, PoP 0-1%)
- Market pulled by engine: total 42.5, KC -2.5

## What was new this session
Two artifacts the 2026-09-13 retrospective asked for, both written and used here:
- `scripts/make_showdown_policy.py` — twin of `make_classic_policy.py`. Emits absolute
  paths, exact-decimal fractions, complete person map, entry IDs in template order.
  Removes the hand-guessed-schema failure that cost ~3 minutes on the prior slate.
- `scripts/qa_showdown_portfolio.py` — twin of `qa_classic_portfolio.py`. Byte diff
  restricted to the six roster cells on reserved rows, role rows, person uniqueness,
  salary cap, two teams, zero-QB, multi-kicker, multi-DST, DST-with-own-offense,
  starter-with-own-backup, official inactives, pairwise overlap, lineup uniqueness,
  entry-ID order and coverage.

## Policy variants run, with measured outcomes
| variant | combined | captain | bothQB | 4-2 | K lineups | distinct CPT | result |
|---|---|---|---|---:|---:|---:|---|
| v1 | 0.80, Nix .89 / Mah .55 / Fields .45 | 0.15 | 8/18 | 7 | 2 | 8 | 1 QB-less + 1 Mahomes+Fields lineup |
| v2 | Fields 0, K .11 | 0.15 | 8/18 | 7 | 2 | 10 | legal, 0 defects |
| v3 | as v2 | 0.11 (=1) | — | — | — | — | `CANDIDATE_BANK_EXHAUSTED_INCOMPLETE`, infeasible |
| v4 | v2 + backup QBs as policy exclusions | 0.15 | 8/18 | 7 | 2 | 10 | byte-identical to v2 |
| v5 | v2 + both kickers 0.0 | 0.15 | 11/18 | 7 | 0 | 11 | |
| **v6** | **v5 + Nix 0.95 (=17)** | **0.15** | **12/18** | **8** | **0** | **10** | **SHIPPED** |
| v7 | v6 + Franklin/Kelce CPT .17 | 0.15 | 12/18 | 8 | 0 | 9 | worse, rejected |

QB-starvation arithmetic checked before each run (retrospective §5 rule):
v6 QB slots = Nix 17 + Mahomes 16 = 33; b=12, s=6, n=0 → 2(12)+6 = 30 ≤ 33. Clears.

## Evidence base: measured showdown structure
Parsed 59,161 lineups from the DAL@NYG 2026-09-13 standings export
(`contest-standings-195526142`), plus four smaller fields.

| metric | full field | top 5% | top 1% | top 0.1% |
|---|---:|---:|---:|---:|
| rostered both starting QBs | 44.7% | 54.8% | 64.8% | 80.0% |
| 4-2 team split | 47.2% | 58.7% | 64.7% | 100% |
| 3-3 team split | 38.1% | 31.8% | 24.7% | 0% |
| contains a kicker | 43.2% | 18.9% | 0.1% | 0% |
| contains a DST | 23.2% | 8.1% | 5.3% | 0% |

Real captain ownership topped at 16.5% (Javonte Williams); `ownership.py` tops near
3.6% and is not called on this path. Chalk trap: George Pickens 45.8% rostered →
6.4% of top 1% (−39.4). Winner: Devin Singletary 4.1% rostered → 100% of top 0.1%.
Duplication: only 20.4% of the 59,161 entries were unique lineups.

## Open defects carried into the ship
1. Objective maximizes Σ DK-points-of-the-expected-stat-line. No distribution, no
   correlation. All three DK yardage bonuses are dead code this slate (max projected
   pass yds 231.2 vs 300 threshold; max rec yds 72.6 vs 100). Cannot express either
   arm of the Dual-Optimization Mandate. Engine-level, not policy-level.
2. `opportunity.py:313-314` splits KC QB attempt share Mahomes 0.5395 / Fields 0.4605.
   Mahomes is projected for 125 pass yards as the starter of a 22.5-point implied team.
   Correct share would move him 12.705 → ~19.2, pool-best. Policy exclusion of Fields
   lands in `selection.py:229-232`, AFTER `score_pool`, so it never reaches projection.
   Fix is a current-team QB allocation evidence declaration, not a cap edit.
3. Kenneth Walker III ($10,600 FLEX, most expensive player on the slate) appears 0/18.
   Diagnosed in retrospective order: captain stratum clean (`added: 3`), pool_coverage
   clean (`SELECTABLE`), objective decisive — 0.687 pts/$1k, 29th of 32. SCORING, not
   BANK. DK's price implies ~18-20 DK points; engine expects 7.3. Not laundered through
   caps.
4. One policy governs 8 contests (11 flat-prize satellite entries, 6 GPP, 1 single-entry).
   128 of 153 entry pairs are cross-contest, so 83.7% of the overlap-4 constraints buy
   nothing. Per-contest policies would recover ~2% of objective.
5. Assignment maps descending prior points onto template order, so the two weakest
   lineups always land on template rows 17-18 — here the NHL satellite, where floor is
   the whole game.

## Next
Re-run after actives are announced. `--official-status-csv` with directly-quoted
INACTIVE rows only, filtered to the DK pool (a non-pool row raises
`OFFICIAL_STATUS_INVALID` and kills the run). Josh Simmons (OT) and Chamarri Conner (S)
are out but are NOT in the Showdown pool — do not include them.
