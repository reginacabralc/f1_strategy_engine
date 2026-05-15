#!/usr/bin/env python
"""Smoke CLI: run a single causal undercut prediction and print results.

Usage examples
--------------
# Predict from the causal dataset (default: first viable row from bahrain_2024_R)
python scripts/predict_causal_undercut.py

# Supply a specific row from the causal dataset parquet
python scripts/predict_causal_undercut.py \\
  --session bahrain_2024_R --lap 35 --attacker NOR --defender VER

# Supply inputs entirely via flags (no DB or dataset needed)
python scripts/predict_causal_undercut.py \\
  --circuit monaco --lap 40 --total-laps 78 \\
  --attacker LEC --attacker-compound MEDIUM --attacker-tyre-age 18 \\
  --defender VER --defender-compound HARD --defender-tyre-age 22 \\
  --gap-ms 4800 --pit-loss-ms 22000

The same ``evaluate_causal_live()`` function is used here and in the live
engine loop, so this smoke test exercises the actual production code path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _print_result(result: object) -> None:  # type: ignore[type-arg]
    """Pretty-print a CausalLiveResult to stdout."""
    from pitwall.causal.live_inference import CausalLiveResult

    r: CausalLiveResult = result  # type: ignore[assignment]
    obs = r.observation
    width = 60

    print("=" * width)
    print("Causal Undercut Prediction")
    print("=" * width)
    print(f"  session        : {obs.session_id}")
    print(f"  circuit        : {obs.circuit_id}")
    print(f"  lap            : {obs.lap_number} / {obs.total_laps or '?'}")
    print(f"  attacker       : {obs.attacker_code}  (pos {obs.current_position})")
    print(f"  defender       : {obs.defender_code}  (pos {obs.rival_position})")
    print(f"  attacker tyre  : {obs.attacker_compound}, age {obs.attacker_tyre_age} laps")
    print(f"  defender tyre  : {obs.defender_compound}, age {obs.defender_tyre_age} laps")
    print(f"  tyre_age_delta : {obs.tyre_age_delta} laps")
    print(f"  gap_to_rival   : {obs.gap_to_rival_ms} ms")
    print(f"  pit_loss_est   : {obs.pit_loss_estimate_ms} ms")
    print(f"  track_status   : {obs.track_status}")
    print()
    print("Decision")
    print("-" * width)
    viable_label = "YES ✓" if r.undercut_viable else "NO  ✗"
    print(f"  undercut_viable        : {viable_label}")
    print(f"  support_level          : {r.support_level}")
    print(f"  confidence             : {r.confidence:.3f}")
    print(f"  required_gain_ms       : {r.required_gain_ms}")
    print(f"  projected_gain_ms      : {r.projected_gain_ms}")
    print(f"  projected_gap_after_pit: {r.projected_gap_after_pit_ms}")
    print(f"  traffic_after_pit      : {r.traffic_after_pit}")
    print(f"  top_factors            : {', '.join(r.top_factors)}")
    print()
    print("Explanation")
    print("-" * width)
    for line in r.explanations:
        if not line.startswith("  "):
            print(f"  {line}")
        else:
            print(line)
    print()
    print("Counterfactuals")
    print("-" * width)
    header = f"  {'scenario':<30} {'viable':<8} {'req_ms':>8} {'proj_ms':>8} {'gap_ms':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for cf in r.counterfactuals:
        v = "YES" if cf.undercut_viable else "no "
        req = str(cf.required_gain_ms) if cf.required_gain_ms is not None else "—"
        proj = str(cf.projected_gain_ms) if cf.projected_gain_ms is not None else "—"
        gap = str(cf.projected_gap_after_pit_ms) if cf.projected_gap_after_pit_ms is not None else "—"
        print(f"  {cf.scenario_name:<30} {v:<8} {req:>8} {proj:>8} {gap:>8}")
    print("=" * width)


def _load_predictor() -> object:
    """Load ScipyPredictor from DB if available, fall back to empty."""
    from pitwall.degradation.predictor import ScipyPredictor

    try:
        from pitwall.db.engine import create_db_engine

        pred = ScipyPredictor.from_engine(create_db_engine())
        if pred._coefficients:
            return pred
    except Exception:
        pass
    return ScipyPredictor([])


def _predict_from_flags(args: argparse.Namespace) -> int:
    """Build DriverState / RaceState from CLI flags and predict."""
    from pitwall.causal.live_inference import evaluate_causal_live
    from pitwall.engine.state import DriverState, RaceState

    predictor = _load_predictor()
    state = RaceState(
        session_id=f"{args.circuit}_manual",
        circuit_id=args.circuit,
        total_laps=args.total_laps,
        current_lap=args.lap,
        track_status="GREEN",
        track_temp_c=None,
        air_temp_c=None,
        rainfall=False,
    )
    attacker = DriverState(
        driver_code=args.attacker,
        position=2,
        gap_to_ahead_ms=args.gap_ms,
        compound=args.attacker_compound,
        tyre_age=args.attacker_tyre_age,
        laps_in_stint=args.attacker_tyre_age,
    )
    defender = DriverState(
        driver_code=args.defender,
        position=1,
        compound=args.defender_compound,
        tyre_age=args.defender_tyre_age,
        laps_in_stint=args.defender_tyre_age,
    )
    result = evaluate_causal_live(
        state, attacker, defender, predictor, pit_loss_ms=args.pit_loss_ms
    )
    _print_result(result)
    return 0


def _predict_from_dataset(args: argparse.Namespace) -> int:
    """Load one row from the causal parquet and predict from it."""
    import polars as pl

    from pitwall.causal.live_inference import evaluate_causal_live
    from pitwall.engine.state import DriverState, RaceState

    path = Path(args.dataset_path)
    if not path.exists():
        print(f"ERROR: causal dataset not found at {path}", file=sys.stderr)
        print("Run `make build-causal-dataset` first.", file=sys.stderr)
        return 1

    df = pl.read_parquet(path)
    mask = pl.lit(True)
    if args.session:
        mask = mask & (pl.col("session_id") == args.session)
    if args.attacker:
        mask = mask & (pl.col("attacker_code") == args.attacker)
    if args.defender:
        mask = mask & (pl.col("defender_code") == args.defender)
    if args.lap is not None:
        mask = mask & (pl.col("lap_number") == args.lap)

    filtered = df.filter(mask & pl.col("row_usable").eq(True)).sort("lap_number")
    if filtered.is_empty():
        print(
            "ERROR: no matching rows found. Try broader filters or use --circuit flags.",
            file=sys.stderr,
        )
        return 1

    row = filtered.row(0, named=True)
    predictor = ScipyPredictor([])
    state = RaceState(
        session_id=str(row["session_id"]),
        circuit_id=str(row["circuit_id"]),
        total_laps=row.get("total_laps"),
        current_lap=int(row["lap_number"]),
        track_status=str(row.get("track_status") or "GREEN"),
        track_temp_c=row.get("track_temp_c"),
        air_temp_c=row.get("air_temp_c"),
        rainfall=bool(row.get("rainfall", False)),
    )
    attacker = DriverState(
        driver_code=str(row["attacker_code"]),
        position=row.get("current_position"),
        gap_to_ahead_ms=row.get("gap_to_rival_ms"),
        compound=row.get("attacker_compound"),
        tyre_age=int(row.get("attacker_tyre_age") or 0),
        laps_in_stint=int(row.get("attacker_laps_in_stint") or row.get("attacker_tyre_age") or 0),
    )
    defender = DriverState(
        driver_code=str(row["defender_code"]),
        position=row.get("rival_position"),
        compound=row.get("defender_compound"),
        tyre_age=int(row.get("defender_tyre_age") or 0),
        laps_in_stint=int(row.get("defender_laps_in_stint") or row.get("defender_tyre_age") or 0),
    )
    pit_loss_ms = int(row.get("pit_loss_estimate_ms") or 21_000)
    predictor = _load_predictor()
    result = evaluate_causal_live(state, attacker, defender, predictor, pit_loss_ms=pit_loss_ms)
    _print_result(result)
    return 0


def main() -> int:
    args = parse_args()
    # If circuit is given (manual mode), use flag-based path
    if args.circuit:
        return _predict_from_flags(args)
    return _predict_from_dataset(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    # Dataset mode
    ds = parser.add_argument_group("dataset mode (default)")
    ds.add_argument("--session", default=None, help="session_id filter, e.g. bahrain_2024_R")
    ds.add_argument("--attacker", default=None, help="attacker driver code filter, e.g. NOR")
    ds.add_argument("--defender", default=None, help="defender driver code filter, e.g. VER")
    ds.add_argument(
        "--dataset-path",
        default="data/causal/undercut_driver_rival_lap.parquet",
        help="path to the causal parquet dataset",
    )

    # Manual/flags mode
    m = parser.add_argument_group("manual flags mode (requires --circuit)")
    m.add_argument("--circuit", default=None, help="circuit_id, e.g. monaco")
    m.add_argument("--total-laps", type=int, default=78)
    m.add_argument("--attacker-compound", default="MEDIUM")
    m.add_argument("--attacker-tyre-age", type=int, default=20)
    m.add_argument("--defender-compound", default="HARD")
    m.add_argument("--defender-tyre-age", type=int, default=30)
    m.add_argument("--gap-ms", type=int, default=5_000, help="gap to rival in ms")
    m.add_argument("--pit-loss-ms", type=int, default=21_000)

    # Shared
    parser.add_argument("--lap", type=int, default=None, help="lap number")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
