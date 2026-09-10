# Q1 metric and promotion registration

Authoritative machine-readable artifact:
`config/metric_registry_q1_v1.json`

Status: `PREDECLARED` at `2026-09-10T17:37:30Z`, before Q2-Q7 challenger or
holdout evaluation. The thresholds are engineering and practical-significance
limits; they were not fitted to challenger, REFEREE, or holdout results. This
registration promotes no model.

## Registered measurement families

- Player outcomes: median-points MAE, distribution CRPS, and central-80%
  coverage error.
- Participation: Brier score and recall for settled nonparticipation.
- Ownership: field-weighted MAE and adaptive-bin calibration error.
- Complete-lineup duplication: `log1p` count MAE and unique-lineup Brier score.
- Rank and payout tails: rank-percentile CRPS, top-1% Brier score, and
  fee-normalized 95th-percentile payout error.
- Portfolio: fee-normalized expected-utility and lower-tail 5% CVaR errors.
- Operations: full-evaluation wall time and peak resident memory.

Every metric fixes direction, unit, uncertainty interval, effective-sample-size
reporting, minimum sample, promotion delta, noninferiority margin, demotion
threshold, rollback threshold, and rationale. Missing metrics, insufficient
samples, low effective sample size, or an incomplete contest-objective stratum
result in `DO_NOT_PROMOTE`.

## Split and decision policy

Splits are grouped by whole slate and ordered by UTC lock time. The minimums are
40 training, 10 validation, and 20 untouched holdout slates, with four rolling-
origin folds and a two-day embargo. Challenger choice uses training and
validation only; the holdout stays untouched until the final promotion
decision. One-sided 95% slate-cluster intervals must clear improvement and
noninferiority rules, with Holm correction inside each metric family. Every
family must pass.

Two consecutive demotion windows trigger demotion. One registered rollback
breach, or any integrity failure, triggers rollback; integrity rollback is
immediate. REFEREE cannot tune or select a challenger, but a registered safety
or sign disagreement blocks promotion.

## Operational limits

- Full registered evaluation: at most 600 seconds.
- Peak memory: at most 4 GiB.
- Exact reference field: at most 200,000 entries and 1,000,000 declared work
  units, with the request also declaring a runtime deadline.

An exceeded limit is a refusal or failed gate, never permission to approximate
silently. The canonical artifact hash is recorded in every Q1 settlement
bundle. `learn` validates and hashes the registry and rejects a registration
timestamp that does not precede challenger evaluation. Until Q6 supplies the
actual registered metric-result artifact, `learn` reports
`REGISTERED_METRIC_RESULTS_REQUIRED_Q6`, keeps the tier `COLD`, influence zero,
and `promote=false` even when its legacy boolean diagnostics are all true.
