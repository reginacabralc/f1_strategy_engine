"""Tests for RaceState, DriverState, and compute_relevant_pairs.

Each test is synthetic — no DB, no feed, no network.  Scenarios are
built from small Event dicts and asserted against the resulting
DriverState / RaceState fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pitwall.engine.state import (
    GAP_RELEVANCE_MS,
    DriverState,
    RaceState,
    compute_relevant_pairs,
)


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------

_TS = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)


def _session_start(
    session_id: str = "monaco_2024_R",
    circuit_id: str = "monaco",
    total_laps: int = 78,
    drivers: list[str] | None = None,
) -> dict:
    return {
        "type": "session_start",
        "session_id": session_id,
        "ts": _TS,
        "payload": {
            "circuit_id": circuit_id,
            "total_laps": total_laps,
            "drivers": drivers or ["VER", "LEC", "NOR"],
        },
    }


def _lap_complete(
    driver_code: str = "VER",
    lap_number: int = 1,
    lap_time_ms: int | None = 74_000,
    compound: str = "MEDIUM",
    tyre_age: int = 10,
    position: int | None = 1,
    gap_to_leader_ms: int | None = 0,
    gap_to_ahead_ms: int | None = None,
    is_pit_in: bool = False,
    is_pit_out: bool = False,
    is_valid: bool = True,
    track_status: str | None = None,
    session_id: str = "monaco_2024_R",
) -> dict:
    payload: dict = {
        "driver_code": driver_code,
        "lap_number": lap_number,
        "lap_time_ms": lap_time_ms,
        "compound": compound,
        "tyre_age": tyre_age,
        "is_pit_in": is_pit_in,
        "is_pit_out": is_pit_out,
        "is_valid": is_valid,
    }
    if position is not None:
        payload["position"] = position
    if gap_to_leader_ms is not None:
        payload["gap_to_leader_ms"] = gap_to_leader_ms
    if gap_to_ahead_ms is not None:
        payload["gap_to_ahead_ms"] = gap_to_ahead_ms
    if track_status is not None:
        payload["track_status"] = track_status
    return {"type": "lap_complete", "session_id": session_id, "ts": _TS, "payload": payload}


def _pit_in(driver_code: str = "VER", lap_number: int = 20) -> dict:
    return {
        "type": "pit_in",
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {"driver_code": driver_code, "lap_number": lap_number},
    }


def _pit_out(
    driver_code: str = "VER",
    lap_number: int = 21,
    new_compound: str = "HARD",
    new_tyre_age: int = 0,
    new_stint_number: int = 2,
) -> dict:
    return {
        "type": "pit_out",
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {
            "driver_code": driver_code,
            "lap_number": lap_number,
            "duration_ms": 21_000,
            "new_compound": new_compound,
            "new_tyre_age": new_tyre_age,
            "new_stint_number": new_stint_number,
        },
    }


def _track_status_change(status: str = "SC", previous: str = "GREEN") -> dict:
    return {
        "type": "track_status_change",
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {"lap_number": 30, "status": status, "previous_status": previous},
    }


def _weather_update(
    track_temp: float = 42.0,
    air_temp: float = 28.0,
    humidity_pct: float = 35.0,
    rainfall: bool = False,
) -> dict:
    return {
        "type": "weather_update",
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {
            "track_temp_c": track_temp,
            "air_temp_c": air_temp,
            "humidity_pct": humidity_pct,
            "rainfall": rainfall,
        },
    }


def _data_stale(driver_code: str = "VER", stale_since_lap: int = 10) -> dict:
    return {
        "type": "data_stale",
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {
            "driver_code": driver_code,
            "stale_since_lap": stale_since_lap,
            "reason": "missing",
        },
    }


def _session_end(classification: list[dict] | None = None) -> dict:
    return {
        "type": "session_end",
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {"final_classification": classification or []},
    }


# ---------------------------------------------------------------------------
# session_start
# ---------------------------------------------------------------------------


def test_apply_session_start_initializes_drivers() -> None:
    state = RaceState()
    state.apply(_session_start(drivers=["VER", "LEC", "NOR"]))

    assert state.circuit_id == "monaco"
    assert state.total_laps == 78
    assert set(state.drivers) == {"VER", "LEC", "NOR"}
    assert all(not d.is_in_pit for d in state.drivers.values())


def test_apply_session_start_sets_session_id() -> None:
    state = RaceState()
    state.apply(_session_start(session_id="hungary_2024_R"))
    assert state.session_id == "hungary_2024_R"


def test_apply_session_start_idempotent_for_existing_drivers() -> None:
    state = RaceState()
    state.drivers["VER"] = DriverState(driver_code="VER", position=1, compound="MEDIUM")
    state.apply(_session_start(drivers=["VER", "LEC"]))
    # Existing driver state must be preserved
    assert state.drivers["VER"].position == 1
    assert state.drivers["VER"].compound == "MEDIUM"


# ---------------------------------------------------------------------------
# lap_complete — basic updates
# ---------------------------------------------------------------------------


def test_apply_lap_complete_updates_position_and_gaps() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", lap_number=5, position=1, gap_to_leader_ms=0, gap_to_ahead_ms=None))

    ver = state.drivers["VER"]
    assert ver.position == 1
    assert ver.gap_to_leader_ms == 0


def test_apply_lap_complete_updates_tyre_data() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("LEC", compound="SOFT", tyre_age=8))

    lec = state.drivers["LEC"]
    assert lec.compound == "SOFT"
    assert lec.tyre_age == 8


def test_apply_lap_complete_advances_current_lap() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", lap_number=12))
    state.apply(_lap_complete("LEC", lap_number=11))

    assert state.current_lap == 12


def test_apply_lap_complete_only_updates_last_lap_when_valid() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", lap_time_ms=74_000, is_valid=True))
    state.apply(_lap_complete("VER", lap_time_ms=99_000, is_valid=False))

    assert state.drivers["VER"].last_lap_ms == 74_000  # invalid lap not applied


def test_apply_lap_complete_updates_track_status() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", track_status="SC"))

    assert state.track_status == "SC"


def test_apply_lap_complete_creates_driver_if_not_in_session_start() -> None:
    state = RaceState()
    state.apply(_session_start(drivers=["VER"]))
    state.apply(_lap_complete("SAI", position=5))  # SAI not in session_start

    assert "SAI" in state.drivers
    assert state.drivers["SAI"].position == 5


# ---------------------------------------------------------------------------
# lap_complete — pit handling
# ---------------------------------------------------------------------------


def test_apply_lap_complete_pit_in_marks_driver_in_pit_and_records_lap() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", lap_number=20, is_pit_in=True))

    ver = state.drivers["VER"]
    assert ver.is_in_pit is True
    assert ver.last_pit_lap == 20


def test_apply_lap_complete_pit_out_clears_pit_and_resets_stint_count() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", is_pit_in=True))         # in pit
    state.apply(_lap_complete("VER", is_pit_out=True, compound="HARD", tyre_age=0))

    ver = state.drivers["VER"]
    assert ver.is_in_pit is False
    assert ver.laps_in_stint == 1


def test_apply_lap_complete_increments_laps_in_stint_on_normal_lap() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER"))
    state.apply(_lap_complete("VER"))
    state.apply(_lap_complete("VER"))

    assert state.drivers["VER"].laps_in_stint == 3


# ---------------------------------------------------------------------------
# lap_complete — stale flag
# ---------------------------------------------------------------------------


def test_apply_lap_complete_clears_stale_flag() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_data_stale("VER", stale_since_lap=9))
    assert state.drivers["VER"].data_stale is True

    state.apply(_lap_complete("VER", lap_number=10))
    assert state.drivers["VER"].data_stale is False
    assert state.drivers["VER"].stale_since_lap is None


# ---------------------------------------------------------------------------
# pit_in / pit_out events (separate from lap_complete)
# ---------------------------------------------------------------------------


def test_apply_pit_in_event_marks_driver_in_pit() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_pit_in("LEC", lap_number=25))

    lec = state.drivers["LEC"]
    assert lec.is_in_pit is True
    assert lec.last_pit_lap == 25


def test_apply_pit_out_event_updates_compound_and_clears_pit() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_pit_in("LEC", lap_number=25))
    state.apply(_pit_out("LEC", new_compound="HARD", new_tyre_age=0, new_stint_number=2))

    lec = state.drivers["LEC"]
    assert lec.is_in_pit is False
    assert lec.compound == "HARD"
    assert lec.tyre_age == 0
    assert lec.stint_number == 2
    assert lec.laps_in_stint == 0   # will become 1 on next lap_complete


# ---------------------------------------------------------------------------
# track_status_change
# ---------------------------------------------------------------------------


def test_apply_track_status_change_updates_status() -> None:
    state = RaceState()
    state.apply(_session_start())
    assert state.track_status == "GREEN"

    state.apply(_track_status_change(status="SC", previous="GREEN"))
    assert state.track_status == "SC"

    state.apply(_track_status_change(status="GREEN", previous="SC"))
    assert state.track_status == "GREEN"


# ---------------------------------------------------------------------------
# weather_update
# ---------------------------------------------------------------------------


def test_apply_weather_update_sets_all_fields() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_weather_update(track_temp=50.0, air_temp=30.0, humidity_pct=20.0, rainfall=False))

    assert state.track_temp_c == 50.0
    assert state.air_temp_c == 30.0
    assert state.humidity_pct == 20.0
    assert state.rainfall is False


def test_apply_weather_update_rainfall_true() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_weather_update(rainfall=True))
    assert state.rainfall is True


# ---------------------------------------------------------------------------
# data_stale
# ---------------------------------------------------------------------------


def test_apply_data_stale_marks_driver_stale() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_data_stale("NOR", stale_since_lap=14))

    nor = state.drivers["NOR"]
    assert nor.data_stale is True
    assert nor.stale_since_lap == 14


# ---------------------------------------------------------------------------
# session_end
# ---------------------------------------------------------------------------


def test_apply_session_end_updates_final_positions() -> None:
    state = RaceState()
    state.apply(_session_start(drivers=["VER", "LEC"]))
    state.apply(
        _session_end(
            classification=[
                {"driver_code": "VER", "position": 1},
                {"driver_code": "LEC", "position": 2},
            ]
        )
    )

    assert state.drivers["VER"].position == 1
    assert state.drivers["LEC"].position == 2


# ---------------------------------------------------------------------------
# Unknown event type
# ---------------------------------------------------------------------------


def test_apply_unknown_event_type_is_silently_ignored() -> None:
    state = RaceState()
    state.apply(_session_start())
    initial_lap = state.current_lap

    state.apply({
        "type": "mystery_event",   # type: ignore[typeddict-item]
        "session_id": "monaco_2024_R",
        "ts": _TS,
        "payload": {},
    })

    assert state.current_lap == initial_lap   # nothing changed


# ---------------------------------------------------------------------------
# Gap smoothing
# ---------------------------------------------------------------------------


def test_gap_smoothing_with_single_sample() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=5_000))

    assert state.drivers["NOR"].gap_to_ahead_ms == 5_000


def test_gap_smoothing_rolling_average_over_three_laps() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=5_000))
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=7_000))
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=6_000))

    # Mean of [5000, 7000, 6000] = 6000
    assert state.drivers["NOR"].gap_to_ahead_ms == 6_000


def test_gap_smoothing_drops_oldest_sample_after_three() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=5_000))
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=7_000))
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=6_000))
    state.apply(_lap_complete("NOR", gap_to_ahead_ms=9_000))  # drops 5000

    # Mean of [7000, 6000, 9000] = 7333
    assert state.drivers["NOR"].gap_to_ahead_ms == 7_333


def test_gap_clears_on_pit_out_event() -> None:
    state = RaceState()
    state.apply(_session_start())
    state.apply(_lap_complete("VER", gap_to_ahead_ms=3_000))
    state.apply(_lap_complete("VER", gap_to_ahead_ms=4_000))
    state.apply(_pit_out("VER", new_compound="HARD", new_tyre_age=0, new_stint_number=2))

    # After pit-out the gap history is reset; next lap_complete starts fresh
    state.apply(_lap_complete("VER", gap_to_ahead_ms=20_000, is_pit_out=True))
    assert state.drivers["VER"].gap_to_ahead_ms == 20_000


# ---------------------------------------------------------------------------
# compute_relevant_pairs
# ---------------------------------------------------------------------------


def _state_with_positions(
    *drivers: tuple[str, int, int | None],  # (code, position, gap_ms)
    in_pit: set[str] | None = None,
    stale: set[str] | None = None,
    lapped: set[str] | None = None,
) -> RaceState:
    """Helper: build a RaceState from (driver_code, position, gap_to_ahead) tuples."""
    state = RaceState()
    for code, pos, gap in drivers:
        d = DriverState(driver_code=code, position=pos, gap_to_ahead_ms=gap)
        if in_pit and code in in_pit:
            d.is_in_pit = True
        if stale and code in stale:
            d.data_stale = True
        if lapped and code in lapped:
            d.is_lapped = True
        state.drivers[code] = d
    return state


def test_compute_relevant_pairs_with_empty_state() -> None:
    assert compute_relevant_pairs(RaceState()) == []


def test_compute_relevant_pairs_with_single_driver() -> None:
    state = _state_with_positions(("VER", 1, None))
    assert compute_relevant_pairs(state) == []


def test_compute_relevant_pairs_returns_pair_within_gap() -> None:
    state = _state_with_positions(
        ("VER", 1, None),
        ("LEC", 2, 10_000),   # 10 s behind VER — relevant
    )
    pairs = compute_relevant_pairs(state)
    assert len(pairs) == 1
    atk, def_ = pairs[0]
    assert atk.driver_code == "LEC"
    assert def_.driver_code == "VER"


def test_compute_relevant_pairs_excludes_gap_over_30s() -> None:
    state = _state_with_positions(
        ("VER", 1, None),
        ("LEC", 2, GAP_RELEVANCE_MS),      # exactly 30 s — NOT included
        ("NOR", 3, 5_000),                 # 5 s — included
    )
    pairs = compute_relevant_pairs(state)
    codes = [(a.driver_code, d.driver_code) for a, d in pairs]
    assert ("LEC", "VER") not in codes
    assert ("NOR", "LEC") in codes


def test_compute_relevant_pairs_excludes_pit_drivers() -> None:
    state = _state_with_positions(
        ("VER", 1, None),
        ("LEC", 2, 5_000),
        ("NOR", 3, 8_000),
        in_pit={"LEC"},
    )
    pairs = compute_relevant_pairs(state)
    codes = {a.driver_code for a, _ in pairs} | {d.driver_code for _, d in pairs}
    assert "LEC" not in codes


def test_compute_relevant_pairs_excludes_stale_drivers() -> None:
    state = _state_with_positions(
        ("VER", 1, None),
        ("LEC", 2, 5_000),
        stale={"LEC"},
    )
    assert compute_relevant_pairs(state) == []


def test_compute_relevant_pairs_excludes_lapped_drivers() -> None:
    state = _state_with_positions(
        ("VER", 1, None),
        ("LEC", 2, 5_000),
        lapped={"LEC"},
    )
    assert compute_relevant_pairs(state) == []


def test_compute_relevant_pairs_excludes_drivers_with_no_position() -> None:
    state = RaceState()
    state.drivers["VER"] = DriverState(driver_code="VER", position=None)
    state.drivers["LEC"] = DriverState(driver_code="LEC", position=None, gap_to_ahead_ms=5_000)
    assert compute_relevant_pairs(state) == []


def test_compute_relevant_pairs_multiple_pairs_ordered_by_position() -> None:
    state = _state_with_positions(
        ("VER", 1, None),
        ("LEC", 2, 8_000),    # P2 → P1: 8 s
        ("NOR", 3, 12_000),   # P3 → P2: 12 s
        ("SAI", 4, 35_000),   # P4 → P3: 35 s — too far
    )
    pairs = compute_relevant_pairs(state)
    assert len(pairs) == 2
    assert pairs[0][0].driver_code == "LEC"
    assert pairs[0][1].driver_code == "VER"
    assert pairs[1][0].driver_code == "NOR"
    assert pairs[1][1].driver_code == "LEC"
