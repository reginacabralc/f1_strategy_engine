#!/usr/bin/env python
"""Write undercut score decomposition diagnostics for replay sessions."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from pitwall.db.engine import create_db_engine
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine.undercut_diagnostics import (
    UndercutDiagnosticConfig,
    collect_score_decompositions,
)
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.train import DEFAULT_MODEL_PATH
from pitwall.pit_loss.estimation import load_pit_loss_table
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

DEFAULT_JSON_OUTPUT = Path("reports/ml/undercut_score_decomposition.json")
DEFAULT_CSV_OUTPUT = Path("reports/ml/undercut_score_decomposition.csv")
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

    config = UndercutDiagnosticConfig(
        k=args.k,
        margin_ms=args.margin_ms,
        pit_loss_scale=args.pit_loss_scale,
        score_threshold=args.score_threshold,
        confidence_threshold=args.confidence_threshold,
        cold_tyre_mode=args.cold_tyre_mode,
    )
    all_rows: list[dict[str, Any]] = []
    for session_id in await _session_ids(args.session):
        events = await loader.load_events(session_id)
        rows = collect_score_decompositions(
            events,
            predictor,
            pit_loss_table,
            config=config,
            snapshot_mode=args.snapshot_mode,
        )
        all_rows.extend(asdict(row) for row in rows)

    return {
        "report": "undercut_score_decomposition",
        "predictor": predictor_choice,
        "snapshot_mode": args.snapshot_mode,
        "config": asdict(config),
        "row_count": len(all_rows),
        "summary": _summary(all_rows),
        "rows": all_rows,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(row["score"]) for row in rows]
    raw_score_ms = [
        int(row["raw_score_ms"]) for row in rows if row.get("raw_score_ms") is not None
    ]
    return {
        "evaluated_pairs": len(rows),
        "alerts": sum(1 for row in rows if row["should_alert"]),
        "positive_scores": sum(1 for row in rows if float(row["score"]) > 0.0),
        "zero_scores": sum(1 for row in rows if float(row["score"]) == 0.0),
        "confidence_suppressed": sum(1 for row in rows if row["suppressed_by_confidence"]),
        "score_suppressed": sum(1 for row in rows if row["suppressed_by_score"]),
        "mean_score": sum(scores) / len(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "mean_raw_score_ms": sum(raw_score_ms) / len(raw_score_ms) if raw_score_ms else None,
        "max_raw_score_ms": max(raw_score_ms) if raw_score_ms else None,
        "by_pit_loss_source": _counts(rows, "pit_loss_source"),
        "by_alert_type": _counts(rows, "alert_type"),
    }


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    scalar_rows = [
        {key: value for key, value in row.items() if not isinstance(value, list)}
        for row in rows
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scalar_rows[0].keys()))
        writer.writeheader()
        writer.writerows(scalar_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictor", choices=("scipy", "xgboost"), default="xgboost")
    parser.add_argument("--session", action="append", default=[], help="Session id to inspect.")
    parser.add_argument("--xgb-model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--snapshot-mode", choices=("event_order", "lap_boundary"), default="event_order")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--margin-ms", type=int, default=500)
    parser.add_argument("--pit-loss-scale", type=float, default=1.0)
    parser.add_argument("--score-threshold", type=float, default=0.4)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    parser.add_argument("--cold-tyre-mode", choices=("current", "none", "half"), default="current")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = asyncio.run(_run(args))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_csv(args.output_csv, cast(list[dict[str, Any]], report["rows"]))
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_csv}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
