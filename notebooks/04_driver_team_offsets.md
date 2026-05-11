# 04 — Driver/Team Pace Offsets

**Stream A · Day 6.5**

---

## What is a driver pace offset?

A driver pace offset is a single number (in milliseconds) that captures how much faster or slower a given driver tends to be compared to the field average at a specific circuit on a specific tyre compound.

A negative offset means the driver is faster than the group median reference (e.g. VER at Monaco HARD: −3782 ms).
A positive offset means the driver is slower (e.g. SAR at Monaco HARD: +1852 ms).

The offset is *relative*, not absolute.  It does not say "VER is 3.8 seconds per lap faster than everyone" — it says "on the historical clean-air laps we have for Monaco on HARD tyres, VER ran a median 3782 ms faster than the overall group median for that circuit+compound."

---

## Why compute this before XGBoost?

When XGBoost eventually predicts lap-time pace, it will do so from numeric features like tyre age, compound, circuit ID, and weather.  Without a driver-level correction, the model is forced to explain all of the cross-driver variation through those features — but driver talent and car performance account for a large fraction of lap-time variance that is *not* explained by tyre age or compound.

Concretely:

1. **Better reference pace in `ScipyPredictor`.** The degradation curves currently fit one curve per (circuit, compound) across all drivers.  If you feed that curve a VER context it will over-predict his lap times; if you feed it a SAR context it will under-predict.  Adding `offset_ms` as an additive correction term before comparing attacker vs. defender projections reduces systematic bias.

2. **Clean XGBoost features.** When we build the Day 7 XGBoost dataset, `offset_ms` becomes a numeric feature: `driver_pace_offset_ms` and optionally `defender_pace_offset_ms`.  This gives the model a stable, pre-computed summary of relative pace without leaking future race data into the training set.

3. **Interpretability.** A table of offsets is human-readable.  If something looks wrong in an undercut alert, you can immediately check whether the pace offsets are reasonable.

---

## Method

### Step 1 — Select clean-air laps

We use the `clean_air_lap_times` materialized view with `fitting_eligible = TRUE`.  This filter requires:

- `is_valid = TRUE`
- `is_pit_in = FALSE`, `is_pit_out = FALSE`
- `track_status = 'GREEN'`
- `lap_time_ms BETWEEN 60000 AND 180000`
- `compound IN ('SOFT', 'MEDIUM', 'HARD')`
- `tyre_age >= 1`

### Step 2 — Compute reference pace per (circuit_id, compound)

For each (circuit_id, compound) group, the reference pace is the **median lap time across all drivers and all eligible laps in that group**.

Median is used instead of mean because:

- A handful of slow outlier laps (VSC tail, traffic that slipped past the `track_status` filter) would pull the mean up and shift all offsets.
- Median is resistant to up to 50% outlier contamination.

### Step 3 — Compute driver offsets

For each (driver_code, circuit_id, compound) sub-group:

```
offset_ms = median(driver_lap_time_ms - reference_lap_time_ms)
```

Taking the median of *differences* (rather than computing `median(driver) - reference`) makes the estimate robust to individual bad laps, and keeps the semantics clear: how much does this driver systematically deviate from the group reference?

### Step 4 — Minimum sample threshold

We persist an offset only if `n_samples >= 5`.  With fewer than 5 laps the median can be dominated by a single extreme lap, making the offset noisy enough to do more harm than good.

Groups with fewer than 5 laps are reported as `skipped_insufficient_data` and excluded from the DB.

### Step 5 — Idempotent upsert

```sql
INSERT INTO driver_skill_offsets (driver_code, circuit_id, compound, offset_ms, n_samples, computed_at)
VALUES (...)
ON CONFLICT (driver_code, circuit_id, compound) DO UPDATE SET
    offset_ms   = EXCLUDED.offset_ms,
    n_samples   = EXCLUDED.n_samples,
    computed_at = EXCLUDED.computed_at
```

Running `make fit-driver-offsets` twice produces the same result.

---

## Results on 3 demo races (2026-05-11)

### Summary

- Clean-air laps loaded: **3503**
- Offsets fitted: **103**
- Groups skipped (< 5 laps): **4**
- Circuits covered: bahrain, hungary, monaco

### Notable observations

| Driver | Circuit | Compound | offset_ms | n_laps |
|--------|---------|----------|-----------|--------|
| VER    | monaco  | HARD     | −3782     | 25     |
| HAM    | monaco  | HARD     | −3685     | 26     |
| SAR    | monaco  | HARD     | +1852     | 54     |
| RIC    | monaco  | HARD     | +1520     | 74     |
| VER    | bahrain | SOFT     | −2527     | 35     |
| PER    | bahrain | SOFT     | −2527     | 31     |

VER and HAM at Monaco show the strongest negative offsets on HARD tyres — consistent with well-known qualifying pace at Monaco.  The large magnitude (~3.7 s) is partly a circuit effect: Monaco heavily amplifies inter-driver differences because traffic affects clean-air availability.

---

## Limitations with only 3 demo races

1. **Few MEDIUM/SOFT groups at some circuits.**  Monaco 2024 was almost entirely a HARD-tyre race after the first lap; most drivers do not have ≥5 MEDIUM or SOFT clean-air laps.  Offsets for MEDIUM/SOFT at Monaco are therefore sparse.

2. **Small samples inflate IQR.**  With 5–10 laps, the IQR can exceed 3000 ms (e.g. OCO Hungary MEDIUM: IQR 5330 ms).  These offsets are usable but noisy.

3. **No team-level offset.**  The current implementation is driver-level only.  A team-level offset (e.g. pace of the car independent of the driver) would require more sessions to disentangle car vs. driver contribution.

4. **No year-over-year normalisation.**  With one year of data, we cannot distinguish "this driver was consistently fast in 2024" from "this car was consistently fast in 2024".  As more seasons are ingested, grouping by `(circuit_id, compound, regulation_era)` will be more meaningful.

---

## How this feeds into XGBoost (Day 7)

The XGBoost dataset builder will join `driver_skill_offsets` on `(driver_code, circuit_id, compound)` and add:

- `attacker_pace_offset_ms` — offset of the driver attempting the undercut
- `defender_pace_offset_ms` — offset of the driver being undercut
- `relative_pace_offset_ms = attacker_pace_offset_ms - defender_pace_offset_ms`

These three features give the model a compact, interpretable summary of the pace differential between the two drivers at that circuit on those tyres, without requiring the model to learn it from raw lap-time patterns in the training set.

The offset can also be used at runtime in `ScipyPredictor` as an additive correction:

```python
predicted_lap_ms = degradation_curve(tyre_age) + driver_pace_offset_ms
```

This is a simple but principled improvement over the current baseline that uses the same curve for all drivers.

---

## Files added

| File | Purpose |
|------|---------|
| `backend/src/pitwall/pace_offsets/models.py` | `DriverOffsetResult` dataclass, constants |
| `backend/src/pitwall/pace_offsets/estimation.py` | Reference pace + driver offset calculation |
| `backend/src/pitwall/pace_offsets/writer.py` | Idempotent upsert to `driver_skill_offsets` |
| `scripts/fit_driver_offsets.py` | CLI — fits and persists offsets |
| `scripts/validate_driver_offsets.py` | CLI — validates persisted offsets |
| `backend/tests/unit/pace_offsets/test_estimation.py` | 19 unit tests, synthetic data only |
| `backend/tests/unit/pace_offsets/test_writer.py` | 6 writer tests, mock connection |

No schema migration was needed — `driver_skill_offsets` already existed in `0001_initial_schema.py`.
