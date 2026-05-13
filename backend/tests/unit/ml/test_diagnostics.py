from __future__ import annotations

import polars as pl

from pitwall.ml.dataset import TARGET_COLUMN
from pitwall.ml.diagnostics import build_shift_diagnostics


def test_shift_diagnostics_reports_targets_sources_and_zero_usable_sessions() -> None:
    frame = pl.DataFrame(
        [
            {
                "fold_id": "fold_001",
                "session_id": "bahrain_2024_R",
                "split": "train",
                "circuit_id": "bahrain",
                "compound": "HARD",
                TARGET_COLUMN: 100.0,
                "reference_source": "circuit_compound",
                "driver_offset_source": "driver_compound",
                "row_usable": True,
            },
            {
                "fold_id": "fold_001",
                "session_id": "monaco_2024_R",
                "split": "validation",
                "circuit_id": "monaco",
                "compound": "HARD",
                TARGET_COLUMN: 10_000.0,
                "reference_source": "global_compound",
                "driver_offset_source": "missing_default_zero",
                "row_usable": True,
            },
        ]
    )
    metadata = {
        "folds": [
            {
                "fold_id": "fold_001",
                "train_session_ids": ["bahrain_2024_R"],
                "validation_session_ids": ["monaco_2024_R"],
            }
        ],
        "sessions_included": ["bahrain_2024_R", "monaco_2024_R"],
    }
    ingestion_report = {
        "items": [
            {
                "year": 2024,
                "round": 21,
                "session_id": "s_o_paulo_2024_R",
                "label": "São Paulo Grand Prix",
                "status": "succeeded",
            },
            {
                "year": 2024,
                "round": 23,
                "session_id": "qatar_2024_R",
                "label": "Qatar Grand Prix",
                "status": "failed",
                "error": "Session.load",
            },
        ]
    }
    raw_rows = [
        {
            "session_id": "s_o_paulo_2024_R",
            "compound": "",
            "lap_time_ms": 90_000,
            "track_status": "GREEN",
        },
        {
            "session_id": "s_o_paulo_2024_R",
            "compound": "WET",
            "lap_time_ms": 95_000,
            "track_status": "SC",
        },
    ]

    report = build_shift_diagnostics(
        frame,
        metadata,
        ingestion_report=ingestion_report,
        raw_rows=raw_rows,
    )

    assert report["fold_target_summary"][0]["mean_ms"] == 10_000.0
    assert report["reference_source_counts"][0]["reference_source"] == "global_compound"
    assert report["zero_usable_sessions"][0]["session_id"] == "s_o_paulo_2024_R"
    assert report["zero_usable_sessions"][0]["dominant_reason"] == "unsupported_or_missing_compound"
    assert report["failed_ingestions"][0]["session_id"] == "qatar_2024_R"
