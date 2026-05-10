"""``RaceFeed`` Protocol and event payload shapes.

The wire shapes here are the runtime mirror of
``docs/interfaces/replay_event_format.md``. Any change to either side
must be reflected on the other.

The engine consumes ``RaceFeed`` rather than knowing whether the events
come from a deterministic replay (V1) or live OpenF1 (V2). See
ADR 0002 for the reasoning behind the abstraction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

# --------------------------------------------------------------------------
# Event envelope and the discriminator type.
# --------------------------------------------------------------------------

EventType = Literal[
    "session_start",
    "session_end",
    "lap_complete",
    "pit_in",
    "pit_out",
    "track_status_change",
    "weather_update",
    "data_stale",
]


class Event(TypedDict):
    """The wire envelope shared by every event.

    ``ts`` is a tz-aware UTC ``datetime`` so events from different
    sources can be compared directly. ``payload`` shape is selected by
    ``type``; the per-type ``TypedDict`` definitions below are the
    authoritative shapes.
    """

    type: EventType
    session_id: str
    ts: datetime
    payload: dict[str, Any]


# --------------------------------------------------------------------------
# Per-event payload shapes (mirror of `replay_event_format.md`).
# --------------------------------------------------------------------------


class SessionStartPayload(TypedDict):
    circuit_id: str
    total_laps: int
    drivers: list[str]


class SessionEndPayload(TypedDict, total=False):
    final_classification: list[dict[str, Any]]


class LapCompletePayload(TypedDict, total=False):
    driver_code: str
    lap_number: int
    lap_time_ms: int | None
    sector_1_ms: int | None
    sector_2_ms: int | None
    sector_3_ms: int | None
    compound: str | None
    tyre_age: int | None
    is_pit_in: bool
    is_pit_out: bool
    is_valid: bool
    track_status: str | None
    position: int | None
    gap_to_leader_ms: int | None
    gap_to_ahead_ms: int | None


class PitInPayload(TypedDict):
    driver_code: str
    lap_number: int


class PitOutPayload(TypedDict):
    driver_code: str
    lap_number: int
    duration_ms: int
    new_compound: str
    new_tyre_age: int
    new_stint_number: int


class TrackStatusChangePayload(TypedDict):
    lap_number: int | None
    status: str
    previous_status: str


class WeatherUpdatePayload(TypedDict, total=False):
    track_temp_c: float | None
    air_temp_c: float | None
    humidity_pct: float | None
    rainfall: bool | None


class DataStalePayload(TypedDict):
    driver_code: str
    stale_since_lap: int
    reason: Literal["missing", "dnf", "retired"]


# --------------------------------------------------------------------------
# RaceFeed Protocol.
# --------------------------------------------------------------------------


@runtime_checkable
class RaceFeed(Protocol):
    """The engine's only window onto the world.

    Implementations must satisfy:

    - ``events()`` returns an async iterator that yields ``Event``
      objects in causal order (per the guarantees in
      ``replay_event_format.md`` § ordering). It is cancellable: when
      ``stop()`` is awaited, the iterator must terminate cleanly
      without yielding further events.
    - ``stop()`` is idempotent and may be called from any task.
    """

    def events(self) -> AsyncIterator[Event]: ...

    async def stop(self) -> None: ...
