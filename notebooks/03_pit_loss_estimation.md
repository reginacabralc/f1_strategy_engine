# 03 — Pit Loss Estimation

## Goal

Day 6 estimates pit loss from the three ingested demo races and persists it in
`pit_loss_estimates` so Stream B can call:

```python
lookup_pit_loss(circuit_id, team_code, pit_loss_table)
```

without using the constant 21,000 ms fallback when DB estimates exist.

## Reproduce

```bash
cp .env.example .env
make down-v
make migrate
make ingest-demo
make fit-degradation
make fit-pit-loss
make validate-demo
make validate-degradation
make validate-pit-loss
```

## Method

The fitter reads `pit_stops`, `laps`, `sessions`, `events`, and `drivers`.

1. Prefer `pit_stops.pit_loss_ms` when FastF1 provides it.
2. Otherwise estimate:

```text
pit_loss_ms = pit_in_lap_ms + pit_out_lap_ms - 2 * median_nearby_clean_lap_ms
```

The nearby clean baseline is computed from the same driver and session within
six laps of the pit-out lap. Clean laps must be valid, non-pit laps, green-track
when status is available, and between 60,000 and 180,000 ms.

Samples outside 10,000-40,000 ms are rejected before taking medians.

## Robust Aggregation

Runtime `pit_loss_ms` remains median-based:

- medians are stable for the current demo data, where several team groups have
  only 1-5 samples,
- one slow or suspicious stop should not move the runtime estimate,
- the undercut engine should be conservative until more historical data exists.

The fitter now also computes trimmed and winsorized means for diagnostics when a
group has enough samples. They are not used as the runtime estimate in V1.

Outliers are classified before aggregation:

- `valid_normal`: usable sample,
- `mild_outlier`: usable but lowers confidence/quality,
- `extreme_outlier_quarantined`: excluded from the median.

Impossible values outside 10,000-40,000 ms are always quarantined. Plausible but
extreme values are also quarantined when they are far from the group median.
Outliers affect `quality`, `iqr_ms`, `std_ms`, and diagnostic counts instead of
being allowed to dominate the estimate.

## Persisted Shape

`pit_loss_estimates` stores team rows and one circuit fallback row:

```text
circuit_id | team_code | pit_loss_ms | n_samples
-----------+-----------+-------------+----------
monaco     | mercedes  | 20115       | 1
monaco     | NULL      | 20414       | 6
```

`team_code IS NULL` is the circuit-level fallback consumed by
`engine.pit_loss.lookup_pit_loss`.

The DB schema was not widened for diagnostics. `fit_pit_loss.py` and
`validate_pit_loss.py` recompute/report diagnostic metadata from the same source
samples:

- `iqr_ms`, `std_ms`, `min_ms`, `max_ms`,
- `aggregation_method`,
- `source` (`direct_pit_loss_ms`, `estimated_from_laps`, or `mixed`),
- `quality` (`good`, `weak`, `fallback`),
- outlier counts.

## Fallback Hierarchy

Runtime lookup order is:

1. circuit + team estimate,
2. circuit median estimate,
3. global conservative fallback,
4. hardcoded `DEFAULT_PIT_LOSS_MS = 21_000`.

The global fallback is represented in the existing `PitLossTable` shape as:

```python
{"__global__": {None: global_pit_loss_ms}}
```

It is derived from all usable pit-loss samples and made conservative with:

```text
global_pit_loss_ms = max(global_median_ms, 21_000)
```

Known circuit/team estimates are not replaced by the global fallback.

## Current Demo Results

Last clean local run read 87 realistic samples, quarantined one plausible
extreme Monaco outlier, and wrote 28 persisted estimate rows:

| circuit_id | row | pit_loss_ms | n_samples | iqr_ms | quality |
|------------|-----|-------------|-----------|--------|---------|
| bahrain | CIRCUIT_MEDIAN | 25,071 | 40 | 1,718 | weak |
| hungary | CIRCUIT_MEDIAN | 20,393 | 40 | 3,005 | weak |
| monaco | CIRCUIT_MEDIAN | 20,414 | 6 | 3,650 | weak |
| `__global__` | GLOBAL_FALLBACK | 23,274 | 86 | 4,688 | fallback |

Team-level rows are still persisted and printed by `make validate-pit-loss`,
but most have fewer than eight samples and should be treated as weak.

## Assumptions And Caveats

- The V1 estimator is intentionally conservative and median-based.
- Monaco has only 7 realistic samples in the current demo set, so team rows with
  one or two samples are diagnostic rather than robust.
- Low-sample team rows are persisted so Stream B can inspect them, but quality
  labels should be treated as a warning before using team differences as strong
  evidence.
- Safety-car-specific pit-loss modeling is not implemented yet.
- The current table is enough for Stream B to use circuit/team lookups during
  replay, but larger historical ingestion is needed before treating team
  differences as stable.
- This does not start XGBoost, driver/team pace offsets, curated undercuts, or
  backtest comparison.

## Validation

`make validate-pit-loss` checks:

- at least one persisted row exists,
- every circuit has a `team_code IS NULL` fallback,
- values are positive and inside 10,000-40,000 ms,
- diagnostic rows include uncertainty, source, quality, and status,
- `load_pit_loss_table()` returns the Stream B table shape,
- `lookup_pit_loss()` resolves circuit and global fallbacks.

## Next Step

Continue with the remaining Day 6/E9 item only when requested: curate known
undercuts for backtest. Do not start XGBoost until the dataset/split strategy is
explicitly agreed.
