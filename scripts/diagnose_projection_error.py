#!/usr/bin/env python
"""Write as-raced pair projection-error diagnostics for undercut windows."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from pitwall.db.engine import create_db_engine
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine.undercut_diagnostics import (
    UndercutDiagnosticConfig,
    collect_score_decompositions,
    projection_errors_from_decompositions,
)
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.train import DEFAULT_MODEL_PATH
from pitwall.pit_loss.estimation import load_pit_loss_table
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

DEFAULT_OUTPUT = Path("reports/ml/undercut_projection_error.json")
PredictorChoice = Literal["scipy", "xgboost"]


async def _session_ids(requested: list[str]) -> list[str]:
    if requested:
        return requested
    repo = SqlSessionRepository(create_db_engine())
    sessions = await repo.list_sessions()
    return [row.session_id for row in sessions]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    engine = create_db_engine()
    loader = SqlSessionEventLoader(engine)
    predictor_choice = cast(PredictorChoice, args.predictor)
    predictor = (
        ScipyPredictor.from_engine(engine)
        if predictor_choice == "scipy"
        else XGBoostPredictor.from_file(args.xgb_model)
    )
    with engine.connect() as connection:
        pit_loss_table = load_pit_loss_table(connection)

    horizons = tuple(args.horizon or [1, 2, 3, 5, 8])
    all_rows: list[dict[str, Any]] = []
    for session_id in await _session_ids(args.session):
        events = await loader.load_events(session_id)
        for horizon in horizons:
            rows = collect_score_decompositions(
                events,
                predictor,
                pit_loss_table,
                config=UndercutDiagnosticConfig(k=horizon),
                snapshot_mode=args.snapshot_mode,
            )
            all_rows.extend(
                asdict(row)
                for row in projection_errors_from_decompositions(rows, events)
            )

    return {
        "report": "undercut_projection_error",
        "predictor": predictor_choice,
        "snapshot_mode": args.snapshot_mode,
        "horizons": list(horizons),
        "row_count": len(all_rows),
        "summary": _summary(all_rows),
        "rows": all_rows,
        "notes": [
            "realized_as_raced_gap_delta_ms is observational, not a true counterfactual fresh-tyre undercut outcome.",
            "Use this report to locate high-error pair windows, not to claim causal success.",
        ],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_horizon: dict[str, dict[str, Any]] = {}
    for horizon in sorted({int(row["k"]) for row in rows}):
        values = [int(row["abs_error_ms"]) for row in rows if int(row["k"]) == horizon]
        signed = [int(row["error_ms"]) for row in rows if int(row["k"]) == horizon]
        by_horizon[str(horizon)] = {
            "rows": len(values),
            "mae_ms": round(sum(values) / len(values)) if values else None,
            "mean_signed_error_ms": round(sum(signed) / len(signed)) if signed else None,
            "max_abs_error_ms": max(values) if values else None,
        }
    return {"by_horizon": by_horizon}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictor", choices=("scipy", "xgboost"), default="xgboost")
    parser.add_argument("--session", action="append", default=[], help="Session id to inspect.")
    parser.add_argument("--horizon", type=int, action="append", default=[])
    parser.add_argument("--snapshot-mode", choices=("event_order", "lap_boundary"), default="event_order")
    parser.add_argument("--xgb-model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = asyncio.run(_run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {args.output}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
