"""Tests for auto-derived known undercut labels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pitwall.causal.known_undercuts import (
    AUTO_DERIVED_NOTES_PREFIX,
    CURATED_NOTES_PREFIX,
    LapCycleInput,
    derive_known_undercuts,
    load_curated_known_undercuts_csv,
)

BASE_TS = datetime(2024, 5, 26, 13, 0, tzinfo=UTC)


def lap(
    driver_code: str,
    lap_number: int,
    position: int,
    *,
    gap_to_ahead_ms: int | None = None,
    pit_in: bool = False,
    pit_out: bool = False,
) -> LapCycleInput:
    return LapCycleInput(
        session_id="monaco_2024_R",
        driver_code=driver_code,
        lap_number=lap_number,
        position=position,
        gap_to_ahead_ms=gap_to_ahead_ms,
        is_pit_in=pit_in,
        is_pit_out=pit_out,
        ts=BASE_TS + timedelta(minutes=lap_number, seconds=position),
    )


def test_derive_successful_known_undercut_from_pit_cycle_exchange() -> None:
    rows = [
        lap("DEF", 9, 1),
        lap("ATK", 9, 2, gap_to_ahead_ms=2_000),
        lap("ATK", 10, 3, pit_in=True),
        lap("ATK", 11, 4, pit_out=True),
        lap("DEF", 12, 1, pit_in=True),
        lap("DEF", 13, 3, pit_out=True),
        lap("ATK", 14, 1),
        lap("DEF", 14, 2),
    ]

    derived = derive_known_undercuts(rows)

    assert len(derived) == 1
    assert derived[0].attacker_code == "ATK"
    assert derived[0].defender_code == "DEF"
    assert derived[0].lap_of_attempt == 10
    assert derived[0].was_successful is True
    assert derived[0].notes.startswith(AUTO_DERIVED_NOTES_PREFIX)


def test_derive_unsuccessful_known_undercut_when_attacker_remains_behind() -> None:
    rows = [
        lap("DEF", 9, 1),
        lap("ATK", 9, 2, gap_to_ahead_ms=2_000),
        lap("ATK", 10, 3, pit_in=True),
        lap("ATK", 11, 4, pit_out=True),
        lap("DEF", 12, 1, pit_in=True),
        lap("DEF", 13, 3, pit_out=True),
        lap("DEF", 14, 1),
        lap("ATK", 14, 2),
    ]

    derived = derive_known_undercuts(rows)

    assert len(derived) == 1
    assert derived[0].was_successful is False


def test_ignores_pit_stop_when_defender_does_not_respond_in_window() -> None:
    rows = [
        lap("DEF", 9, 1),
        lap("ATK", 9, 2, gap_to_ahead_ms=2_000),
        lap("ATK", 10, 3, pit_in=True),
        lap("ATK", 11, 4, pit_out=True),
        lap("DEF", 30, 1, pit_in=True),
        lap("DEF", 31, 3, pit_out=True),
    ]

    derived = derive_known_undercuts(rows)

    assert derived == []


def test_ignores_pit_stop_when_pre_pit_gap_is_too_large() -> None:
    rows = [
        lap("DEF", 9, 1),
        lap("ATK", 9, 2, gap_to_ahead_ms=35_000),
        lap("ATK", 10, 3, pit_in=True),
        lap("ATK", 11, 4, pit_out=True),
        lap("DEF", 12, 1, pit_in=True),
        lap("DEF", 13, 3, pit_out=True),
        lap("ATK", 14, 1),
        lap("DEF", 14, 2),
    ]

    derived = derive_known_undercuts(rows)

    assert derived == []


def test_load_curated_known_undercuts_csv(tmp_path: Path) -> None:
    path = tmp_path / "known_undercuts_curated.csv"
    path.write_text(
        "session_id,attacker_code,defender_code,lap_of_attempt,was_successful,"
        "reviewer,evidence,notes\n"
        "monaco_2024_R,NOR,VER,20,true,regina,video+timing,reviewed exchange\n"
    )

    rows = load_curated_known_undercuts_csv(path)

    assert len(rows) == 1
    assert rows[0].session_id == "monaco_2024_R"
    assert rows[0].attacker_code == "NOR"
    assert rows[0].defender_code == "VER"
    assert rows[0].lap_of_attempt == 20
    assert rows[0].was_successful is True
    assert rows[0].notes.startswith(CURATED_NOTES_PREFIX)
