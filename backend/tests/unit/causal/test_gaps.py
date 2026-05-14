"""Tests for lap-line race gap reconstruction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pitwall.causal.gaps import (
    LapGapInput,
    reconstruct_gap_updates,
    summarize_gap_updates,
)

BASE_TS = datetime(2024, 5, 26, 13, 0, tzinfo=UTC)


def lap(
    driver_code: str,
    lap_number: int,
    lap_time_ms: int | None,
    position: int | None,
    elapsed_ms: int,
) -> LapGapInput:
    return LapGapInput(
        session_id="monaco_2024_R",
        driver_code=driver_code,
        lap_number=lap_number,
        ts=BASE_TS + timedelta(milliseconds=elapsed_ms),
        lap_time_ms=lap_time_ms,
        position=position,
    )


def test_reconstruct_gap_updates_uses_lap_end_timestamp_by_position() -> None:
    updates = reconstruct_gap_updates(
        [
            lap("LEC", 1, 90_000, 1, 90_000),
            lap("PIA", 1, 91_000, 2, 91_000),
            lap("SAI", 1, 93_000, 3, 93_000),
            lap("LEC", 2, 90_000, 1, 180_000),
            lap("PIA", 2, 90_500, 2, 181_500),
            lap("SAI", 2, 92_000, 3, 185_000),
        ]
    )

    by_driver_lap = {
        (update.driver_code, update.lap_number): update for update in updates
    }
    assert by_driver_lap[("LEC", 1)].gap_to_leader_ms == 0
    assert by_driver_lap[("LEC", 1)].gap_to_ahead_ms is None
    assert by_driver_lap[("PIA", 1)].gap_to_leader_ms == 1_000
    assert by_driver_lap[("PIA", 1)].gap_to_ahead_ms == 1_000
    assert by_driver_lap[("SAI", 1)].gap_to_leader_ms == 3_000
    assert by_driver_lap[("SAI", 1)].gap_to_ahead_ms == 2_000
    assert by_driver_lap[("PIA", 2)].gap_to_leader_ms == 1_500
    assert by_driver_lap[("PIA", 2)].gap_to_ahead_ms == 1_500
    assert by_driver_lap[("SAI", 2)].gap_to_leader_ms == 5_000
    assert by_driver_lap[("SAI", 2)].gap_to_ahead_ms == 3_500


def test_missing_lap_time_does_not_block_timestamp_gap_reconstruction() -> None:
    updates = reconstruct_gap_updates(
        [
            lap("LEC", 1, 90_000, 1, 90_000),
            lap("PIA", 1, None, 2, 91_000),
            lap("LEC", 2, 90_000, 1, 180_000),
            lap("PIA", 2, 90_500, 2, 181_500),
        ]
    )

    by_driver_lap = {
        (update.driver_code, update.lap_number): update for update in updates
    }
    assert by_driver_lap[("PIA", 1)].gap_to_leader_ms == 1_000
    assert by_driver_lap[("PIA", 1)].gap_to_ahead_ms == 1_000
    assert by_driver_lap[("PIA", 2)].gap_to_leader_ms == 1_500
    assert by_driver_lap[("PIA", 2)].gap_to_ahead_ms == 1_500


def test_summary_counts_reconstructed_leader_and_ahead_rows() -> None:
    updates = reconstruct_gap_updates(
        [
            lap("LEC", 1, 90_000, 1, 90_000),
            lap("PIA", 1, 91_000, 2, 91_000),
            lap("SAI", 1, None, 3, 93_000),
        ]
    )

    summaries = summarize_gap_updates(updates)

    assert len(summaries) == 1
    assert summaries[0].session_id == "monaco_2024_R"
    assert summaries[0].rows == 3
    assert summaries[0].gap_to_leader_rows == 3
    assert summaries[0].gap_to_ahead_rows == 2
