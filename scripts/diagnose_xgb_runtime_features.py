#!/usr/bin/env python
"""Audit runtime XGBoost feature support over replay decision contexts."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pitwall.db.engine import create_db_engine
from pitwall.engine.state import RaceState, compute_relevant_pairs
from pitwall.engine.undercut import _context_for_driver
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.runtime_diagnostics import diagnose_xgboost_runtime_features
from pitwall.ml.train import DEFAULT_MODEL_PATH
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

DEFAULT_OUTPUT = Path("reports/ml/xgb_runtime_feature_parity.json")

_NEXT_COMPOUND: dict[str, str] = {
    "SOFT": "MEDIUM",
    "MEDIUM": "HARD",
    "HARD": "MEDIUM",
    "INTER": "INTER",
    "WET": "WET",
}
_DEFAULT_NEXT_COMPOUND = "MEDIUM"


async def _session_ids(requested: list[str]) -> list[str]:
    if requested:
        return requested
    repo = SqlSessionRepository(create_db_engine())
    sessions = await repo.list_sessions()
    return [row.session_id for row in sessions]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    engine = create_db_engine()
    loader = SqlSessionEventLoader(engine)
    predictor = XGBoostPredictor.from_file(args.xgb_model)
    rows: list[dict[str, Any]] = []
    for session_id in await _session_ids(args.session):
        events = sorted(await loader.load_events(session_id), key=_event_sort_key)
        state = RaceState()
        for event in events:
            state.apply(event)
            if event["type"] != "lap_complete" or state.track_status in {"SC", "VSC"}:
                continue
            for attacker, defender in compute_relevant_pairs(state):
                def_compound = defender.compound or _DEFAULT_NEXT_COMPOUND
                next_compound = _NEXT_COMPOUND.get(
                    (attacker.compound or "").upper(),
                    _DEFAULT_NEXT_COMPOUND,
                )
                contexts = {
                    "defender": _context_for_driver(
                        state,
                        defender,
                        def_compound,
                        max(1, defender.tyre_age),
                    ),
                    "attacker_fresh": _context_for_driver(
                        state,
                        attacker,
                        next_compound,
                        1,
                        start_lap_in_stint=1,
                        stint_number=attacker.stint_number + 1,
                    ),
                }
                for role, context in contexts.items():
                    report = diagnose_xgboost_runtime_features(predictor, context)
                    rows.append(
                        {
                            "session_id": session_id,
                            "lap_number": state.current_lap,
                            "role": role,
                            "driver_code": context.driver_code,
                            "compound": context.compound,
                            "reference_available": report.reference_lap_time_available,
                            "reference_feature_present": report.reference_lap_time_feature_present,
                            "predicts_delta": report.predicts_delta,
                            "driver_pace_offset_missing": report.driver_pace_offset_missing,
                            "missing_numeric_features": list(report.missing_numeric_features),
                            "unknown_categorical_features": report.unknown_categorical_features,
                        }
                    )
    return {
        "report": "xgb_runtime_feature_parity",
        "xgb_model_path": str(args.xgb_model),
        "row_count": len(rows),
        "summary": _summary(rows),
        "rows": rows,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing_numeric = Counter[str]()
    unknown_categorical = Counter[str]()
    missing_reference_by_session_compound = Counter[str]()
    for row in rows:
        missing_numeric.update(str(value) for value in row["missing_numeric_features"])
        unknown_categorical.update(str(key) for key in row["unknown_categorical_features"])
        if row["predicts_delta"] and not row["reference_available"]:
            missing_reference_by_session_compound.update(
                [f"{row['session_id']}|{row['role']}|{row['compound']}"]
            )
    return {
        "contexts": len(rows),
        "delta_prediction_contexts": sum(1 for row in rows if row["predicts_delta"]),
        "missing_reference_contexts": sum(
            1 for row in rows if row["predicts_delta"] and not row["reference_available"]
        ),
        "reference_feature_present_contexts": sum(
            1 for row in rows if row["reference_feature_present"]
        ),
        "driver_pace_offset_missing_contexts": sum(
            1 for row in rows if row["driver_pace_offset_missing"]
        ),
        "missing_numeric_features": dict(missing_numeric.most_common()),
        "unknown_categorical_features": dict(unknown_categorical.most_common()),
        "missing_reference_by_session_role_compound": dict(
            missing_reference_by_session_compound.most_common()
        ),
    }


def _event_sort_key(event: dict[str, Any]) -> tuple[Any, int, int, str]:
    payload = event.get("payload") or {}
    return (
        event.get("ts"),
        int(payload.get("lap_number") or 0),
        int(payload.get("position") or 99),
        str(payload.get("driver_code") or ""),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", action="append", default=[], help="Session id to audit.")
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
