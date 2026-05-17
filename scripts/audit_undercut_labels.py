#!/usr/bin/env python
"""Audit replay-derived undercut labels against engine-observable pairs."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy import text

from pitwall.db.engine import create_db_engine
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine import backtest
from pitwall.engine.undercut_diagnostics import (
    LabelRecord,
    UndercutDiagnosticConfig,
    audit_labels_against_decisions,
    collect_score_decompositions,
    decision_record_from_decomposition,
    label_records_from_backtest_objects,
)
from pitwall.ml.predictor import XGBoostPredictor
from pitwall.ml.train import DEFAULT_MODEL_PATH
from pitwall.pit_loss.estimation import load_pit_loss_table
from pitwall.repositories.sql import SqlSessionEventLoader, SqlSessionRepository

DEFAULT_OUTPUT = Path("reports/ml/undercut_label_audit.json")
DEFAULT_CAUSAL_META = Path("data/causal/undercut_driver_rival_lap.meta.json")
PredictorChoice = Literal["scipy", "xgboost"]

KNOWN_UNDERCUT_SQL = text(
    """
    SELECT session_id, attacker_code, defender_code, lap_of_attempt, was_successful, notes
    FROM known_undercuts
    WHERE (:session_ids_is_null OR session_id = ANY(:session_ids))
    ORDER BY session_id, lap_of_attempt, attacker_code, defender_code
    """
)


async def _session_ids(requested: list[str]) -> list[str]:
    if requested:
        return requested
    repo = SqlSessionRepository(create_db_engine())
    sessions = await repo.list_sessions()
    return [row.session_id for row in sessions]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    session_ids = await _session_ids(args.session)
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
        known_labels = _load_known_labels(connection, session_ids)

    backtest_audit_rows: list[dict[str, Any]] = []
    known_audit_rows: list[dict[str, Any]] = []
    backtest_label_count = 0
    for session_id in session_ids:
        events = await loader.load_events(session_id)
        ordered_events = sorted(events, key=backtest._event_sort_key)
        decisions = [
            decision_record_from_decomposition(row)
            for row in collect_score_decompositions(
                ordered_events,
                predictor,
                pit_loss_table,
                config=UndercutDiagnosticConfig(k=args.window_laps),
            )
            if row.alert_type == "UNDERCUT_VIABLE"
        ]
        labels = label_records_from_backtest_objects(
            backtest._derive_labels(ordered_events),
            session_id=session_id,
        )
        backtest_label_count += len(labels)
        backtest_audit_rows.extend(
            asdict(row)
            for row in audit_labels_against_decisions(
                labels,
                decisions,
                window_laps=args.window_laps,
            )
        )
        session_known = [label for label in known_labels if label.session_id == session_id]
        known_audit_rows.extend(
            asdict(row)
            for row in audit_labels_against_decisions(
                session_known,
                decisions,
                window_laps=args.window_laps,
            )
        )

    return {
        "report": "undercut_label_audit",
        "predictor": predictor_choice,
        "sessions": session_ids,
        "window_laps": args.window_laps,
        "summary": {
            "backtest_labels": backtest_label_count,
            "known_undercut_labels": len(known_labels),
            "backtest_unobservable": sum(
                1 for row in backtest_audit_rows if row["likely_unobservable_label"]
            ),
            "known_unobservable": sum(
                1 for row in known_audit_rows if row["likely_unobservable_label"]
            ),
        },
        "causal_meta": _read_causal_meta(args.causal_meta),
        "backtest_label_audit": backtest_audit_rows,
        "known_undercut_label_audit": known_audit_rows,
        "notes": [
            "backtest labels are generated from pit-in pairs plus final/latest position, so this report flags whether they were observable to the engine before the pit decision.",
            "known_undercut rows are audited separately from replay backtest labels.",
        ],
    }


def _load_known_labels(connection: Any, session_ids: list[str]) -> list[LabelRecord]:
    rows = connection.execute(
        KNOWN_UNDERCUT_SQL,
        {"session_ids": session_ids, "session_ids_is_null": not session_ids},
    )
    labels: list[LabelRecord] = []
    for row in rows:
        mapping = row._mapping
        labels.append(
            LabelRecord(
                attacker=str(mapping["attacker_code"]),
                defender=str(mapping["defender_code"]),
                lap_actual=int(mapping["lap_of_attempt"]),
                was_successful=bool(mapping["was_successful"]),
                source="known_undercuts",
                session_id=str(mapping["session_id"]),
            )
        )
    return labels


def _read_causal_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return raw if isinstance(raw, dict) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictor", choices=("scipy", "xgboost"), default="xgboost")
    parser.add_argument("--session", action="append", default=[], help="Session id to audit.")
    parser.add_argument("--window-laps", type=int, default=5)
    parser.add_argument("--xgb-model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--causal-meta", type=Path, default=DEFAULT_CAUSAL_META)
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
