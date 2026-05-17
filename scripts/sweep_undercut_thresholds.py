#!/usr/bin/env python
"""Run expanded undercut threshold and physics sweeps."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import Any, Literal, cast

from pitwall.db.engine import create_db_engine
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine import backtest
from pitwall.engine.undercut_diagnostics import (
    COLD_TYRE_PENALTIES_MS,
    ColdTyreMode,
    DecisionRecord,
    ScoreDecomposition,
    ThresholdConfig,
    UndercutDiagnosticConfig,
    collect_score_decompositions,
    label_records_from_backtest_objects,
    sweep_thresholds,
    threshold_configs,
)
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.train import DEFAULT_MODEL_PATH
from pitwall.pit_loss.estimation import load_pit_loss_table
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

DEFAULT_OUTPUT = Path("reports/ml/undercut_threshold_sweep_expanded.json")
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

    configs = _configs_from_args(args)
    all_rows: list[dict[str, Any]] = []
    all_decomposition_summaries: list[dict[str, Any]] = []
    for session_id in await _session_ids(args.session):
        events = await loader.load_events(session_id)
        ordered_events = sorted(events, key=backtest._event_sort_key)
        labels = label_records_from_backtest_objects(
            backtest._derive_labels(ordered_events),
            session_id=session_id,
        )
        base_decompositions_by_horizon = {
            horizon: collect_score_decompositions(
                ordered_events,
                predictor,
                pit_loss_table,
                config=UndercutDiagnosticConfig(k=horizon, cold_tyre_mode="current"),
            )
            for horizon in sorted({config.k for config in configs})
        }
        for physics_key, grouped_configs_iter in groupby(
            sorted(
                configs,
                key=attrgetter("k", "margin_ms", "pit_loss_scale", "cold_tyre_mode"),
            ),
            key=attrgetter("k", "margin_ms", "pit_loss_scale", "cold_tyre_mode"),
        ):
            k, margin_ms, pit_loss_scale, cold_tyre_mode = physics_key
            grouped_configs = list(grouped_configs_iter)
            base_decompositions = base_decompositions_by_horizon[k]
            decisions = [
                _decision_for_config(row, k, margin_ms, pit_loss_scale, cold_tyre_mode)
                for row in base_decompositions
                if row.alert_type == "UNDERCUT_VIABLE"
                and len(row.defender_projected_laps_ms) >= k
                and len(row.attacker_projected_laps_ms) >= k
            ]
            all_decomposition_summaries.append(
                {
                    "session_id": session_id,
                    "k": k,
                    "margin_ms": margin_ms,
                    "pit_loss_scale": pit_loss_scale,
                    "cold_tyre_mode": cold_tyre_mode,
                    "evaluated_pairs": len(decisions),
                    "positive_scores": sum(1 for decision in decisions if decision.score > 0.0),
                    "max_score": max((decision.score for decision in decisions), default=None),
                }
            )
            rows = sweep_thresholds(
                labels,
                decisions,
                configs=grouped_configs,
                window_laps=k,
            )
            all_rows.extend({"session_id": session_id, **asdict(row)} for row in rows)

    return {
        "report": "undercut_threshold_sweep_expanded",
        "predictor": predictor_choice,
        "row_count": len(all_rows),
        "summary": _summary(all_rows),
        "decomposition_summary": all_decomposition_summaries,
        "rows": all_rows,
    }


def _decision_for_config(
    row: ScoreDecomposition,
    k: int,
    margin_ms: int,
    pit_loss_scale: float,
    cold_tyre_mode: ColdTyreMode,
) -> DecisionRecord:
    gap_recuperable = sum(
        defender_ms - attacker_ms
        for defender_ms, attacker_ms in zip(
            row.defender_projected_laps_ms[:k],
            row.attacker_projected_laps_ms[:k],
            strict=True,
        )
    )
    gap_recuperable += _cold_tyre_gain_adjustment(k, cold_tyre_mode)
    pit_loss_ms = round(row.original_pit_loss_ms * pit_loss_scale)
    gap_actual_ms = row.gap_actual_ms or 0
    raw_score = (gap_recuperable - pit_loss_ms - gap_actual_ms - margin_ms) / max(
        1,
        pit_loss_ms,
    )
    return DecisionRecord(
        attacker=row.attacker,
        defender=row.defender,
        lap_number=row.lap_number,
        score=max(0.0, min(1.0, raw_score)),
        confidence=row.confidence,
        estimated_gain_ms=gap_recuperable - pit_loss_ms,
    )


def _cold_tyre_gain_adjustment(k: int, mode: ColdTyreMode) -> int:
    current_penalty = sum(COLD_TYRE_PENALTIES_MS[:k])
    if mode == "current":
        return 0
    if mode == "none":
        return current_penalty
    return current_penalty - sum(round(value / 2) for value in COLD_TYRE_PENALTIES_MS[:k])


def _configs_from_args(args: argparse.Namespace) -> list[ThresholdConfig]:
    return threshold_configs(
        score_thresholds=tuple(args.score_threshold or [0.0, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0]),
        confidence_thresholds=tuple(args.confidence_threshold or [0.0, 0.15, 0.35, 0.5, 0.7, 1.0]),
        margins_ms=tuple(args.margin_ms or [0, 250, 500, 1_000]),
        horizons=tuple(args.k or [2, 3, 5, 8]),
        pit_loss_scales=tuple(args.pit_loss_scale or [0.8, 1.0, 1.2]),
        cold_tyre_modes=tuple(args.cold_tyre_mode or ["current", "none", "half"]),
    )


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"best_f1": None, "nonzero_recall_rows": 0}
    best = max(rows, key=lambda row: (float(row["f1"]), float(row["recall"]), float(row["precision"])))
    return {
        "best_f1": best,
        "nonzero_recall_rows": sum(1 for row in rows if float(row["recall"]) > 0.0),
        "nonzero_alert_rows": sum(1 for row in rows if int(row["alerts"]) > 0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictor", choices=("scipy", "xgboost"), default="xgboost")
    parser.add_argument("--session", action="append", default=[], help="Session id to sweep.")
    parser.add_argument("--xgb-model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--k", type=int, action="append", default=None)
    parser.add_argument("--margin-ms", type=int, action="append", default=None)
    parser.add_argument("--pit-loss-scale", type=float, action="append", default=None)
    parser.add_argument("--cold-tyre-mode", choices=("current", "none", "half"), action="append", default=None)
    parser.add_argument("--score-threshold", type=float, action="append", default=None)
    parser.add_argument("--confidence-threshold", type=float, action="append", default=None)
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
