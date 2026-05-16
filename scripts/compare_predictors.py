#!/usr/bin/env python
"""Run replay backtests for Scipy and XGBoost and write a comparison report."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pitwall.db.engine import create_db_engine
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine.backtest import BacktestResultData, run_backtest
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.train import DEFAULT_MODEL_PATH
from pitwall.pit_loss.estimation import load_pit_loss_table
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

DEFAULT_OUTPUT_PATH = Path("reports/ml/scipy_xgboost_backtest_report.json")


async def _session_ids(requested: list[str]) -> list[str]:
    if requested:
        return requested
    repo = SqlSessionRepository(create_db_engine())
    sessions = await repo.list_sessions()
    return [row.session_id for row in sessions]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    engine = create_db_engine()
    loader = SqlSessionEventLoader(engine)
    scipy = ScipyPredictor.from_engine(engine)
    xgboost = XGBoostPredictor.from_file(args.xgb_model)
    with engine.connect() as connection:
        pit_loss_table = load_pit_loss_table(connection)

    report_rows: list[dict[str, Any]] = []
    for session_id in await _session_ids(args.session):
        events = await loader.load_events(session_id)
        for predictor_name, predictor in (("scipy", scipy), ("xgboost", xgboost)):
            result = run_backtest(
                session_id,
                events,
                predictor,
                predictor_name=predictor_name,
                pit_loss_table=pit_loss_table,
            )
            report_rows.append(asdict(result))
    return {
        "report": "scipy_xgboost_backtest",
        "xgb_model_path": str(args.xgb_model),
        "sessions": sorted({row["session_id"] for row in report_rows}),
        "results": report_rows,
        "decision": _decision(report_rows),
    }


def _decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_predictor: dict[str, list[dict[str, Any]]] = {"scipy": [], "xgboost": []}
    for row in rows:
        by_predictor.setdefault(str(row["predictor"]), []).append(row)

    scipy_mae = _mean_metric(by_predictor["scipy"], "mae_k3_ms")
    xgb_mae = _mean_metric(by_predictor["xgboost"], "mae_k3_ms")
    scipy_f1 = _mean_metric(by_predictor["scipy"], "f1")
    xgb_f1 = _mean_metric(by_predictor["xgboost"], "f1")
    if scipy_mae is None or xgb_mae is None:
        default = "scipy"
        reason = "MAE@k3 comparison unavailable for one or both predictors"
    else:
        xgb_improvement = (scipy_mae - xgb_mae) / max(1.0, scipy_mae)
        f1_not_materially_worse = xgb_f1 is None or scipy_f1 is None or xgb_f1 >= scipy_f1 - 0.05
        default = "xgboost" if xgb_improvement >= 0.10 and f1_not_materially_worse else "scipy"
        reason = (
            "XGBoost clears ADR 0009 default threshold"
            if default == "xgboost"
            else "XGBoost does not clear ADR 0009 default threshold"
        )
    return {
        "recommended_default": default,
        "reason": reason,
        "mean_scipy_mae_k3_ms": scipy_mae,
        "mean_xgboost_mae_k3_ms": xgb_mae,
        "mean_scipy_f1": scipy_f1,
        "mean_xgboost_f1": xgb_f1,
    }


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", action="append", default=[], help="Session id to compare.")
    parser.add_argument("--xgb-model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    try:
        report = asyncio.run(_run(args))
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Wrote predictor comparison report to {args.output}")
    print(f"recommended_default: {report['decision']['recommended_default']}")
    print(f"reason: {report['decision']['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
