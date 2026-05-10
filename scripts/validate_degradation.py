#!/usr/bin/env python
"""Validate Day 4 degradation fitting outputs in the local DB."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text

from pitwall.db.engine import create_db_engine
from pitwall.degradation.dataset import DEMO_SESSION_IDS
from pitwall.degradation.predictor import ScipyPredictor
from pitwall.engine.projection import PaceContext

SUMMARY_SQL = text(
    """
    SELECT
        (SELECT COUNT(*) FROM laps WHERE session_id = ANY(:session_ids)) AS demo_laps,
        (SELECT COUNT(*) FROM clean_air_lap_times
         WHERE session_id = ANY(:session_ids) AND fitting_eligible = TRUE) AS eligible_laps,
        (SELECT COUNT(*) FROM degradation_coefficients) AS coefficient_rows,
        (SELECT COUNT(*) FROM degradation_coefficients
         WHERE a IS NOT NULL
           AND b IS NOT NULL
           AND c IS NOT NULL
           AND r_squared IS NOT NULL
           AND rmse_ms IS NOT NULL) AS fitted_metric_rows,
        (SELECT COUNT(*) FROM degradation_coefficients
         WHERE circuit_id = 'monaco'
            OR (source_sessions IS NOT NULL AND :monaco_session = ANY(source_sessions))
        ) AS monaco_coefficients
    """
)

COEFFICIENT_SQL = text(
    """
    SELECT
        circuit_id,
        compound,
        n_laps,
        ROUND(r_squared::numeric, 3) AS r2,
        ROUND(rmse_ms::numeric, 0) AS rmse_ms,
        source_sessions
    FROM degradation_coefficients
    ORDER BY circuit_id, compound
    """
)


def main() -> int:
    engine = create_db_engine()
    with engine.connect() as connection:
        summary = dict(
            connection.execute(
                SUMMARY_SQL,
                {
                    "session_ids": list(DEMO_SESSION_IDS),
                    "monaco_session": "monaco_2024_R",
                },
            )
            .one()
            ._mapping
        )
        coefficients = [
            dict(row._mapping) for row in connection.execute(COEFFICIENT_SQL)
        ]
        predictor = ScipyPredictor.from_connection(connection)

    print("Degradation validation summary")
    print_table([summary], list(summary))
    print("\nCoefficient rows")
    print_table(
        coefficients,
        ["circuit_id", "compound", "n_laps", "r2", "rmse_ms", "source_sessions"],
    )
    if predictor.is_available("monaco", "MEDIUM"):
        prediction = predictor.predict(
            PaceContext(
                driver_code="LEC",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
            )
        )
        print(
            "\nScipyPredictor smoke: "
            f"monaco MEDIUM age 10 -> {prediction.predicted_lap_time_ms} ms "
            f"(confidence {prediction.confidence:.3f})"
        )

    if int(summary["demo_laps"] or 0) <= 0:
        raise SystemExit("No demo lap data found")
    if int(summary["eligible_laps"] or 0) <= 0:
        raise SystemExit("No eligible clean-air fitting rows found")
    if int(summary["coefficient_rows"] or 0) <= 0:
        raise SystemExit("No degradation coefficients found; run make fit-degradation")
    if int(summary["monaco_coefficients"] or 0) <= 0:
        raise SystemExit("No Monaco degradation coefficient found")
    if int(summary["fitted_metric_rows"] or 0) <= 0:
        raise SystemExit("No fitted coefficients have populated R2/RMSE metrics")
    return 0


def print_table(rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    rows = list(rows)
    widths = {
        column: max([len(column), *(len(str(row.get(column, ""))) for row in rows)])
        for column in columns
    }
    print(" | ".join(column.ljust(widths[column]) for column in columns))
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(
            " | ".join(
                str(row.get(column, "")).ljust(widths[column]) for column in columns
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
