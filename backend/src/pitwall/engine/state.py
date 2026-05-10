"""In-memory race state for the undercut engine.

``RaceState`` is the engine's single source of truth during a replay.
It is updated by ``RaceState.apply(event)`` as events arrive from the
``ReplayFeed`` and queried by ``compute_relevant_pairs()`` to find driver
pairs that are close enough for an undercut to be viable.

Design constraints (from the master plan, §6):
- "The engine must be readable on a whiteboard."
- Pair filter: gap < 30 s, both in-race, neither in pit, neither stale.
- Gap is smoothed over a 3-lap rolling window to reduce timing noise.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pitwall.feeds.base import Event

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAP_RELEVANCE_MS: int = 30_000   # 30 s in milliseconds — master plan §6.1
GAP_SMOOTH_WINDOW: int = 3       # rolling-average window — master plan §6.2


# ---------------------------------------------------------------------------
# DriverState
# ---------------------------------------------------------------------------


@dataclass
class DriverState:
    """In-memory state for one driver during an active race session."""

    driver_code: str
    team_code: str | None = None

    # Position and gap (updated from lap_complete events)
    position: int | None = None
    gap_to_leader_ms: int | None = None
    gap_to_ahead_ms: int | None = None   # smoothed rolling average
    last_lap_ms: int | None = None       # most recent *valid* lap time

    # Tyre state
    compound: str | None = None
    tyre_age: int = 0
    stint_number: int = 1
    laps_in_stint: int = 0  # laps completed on current tyres; reset on pit-out

    # Pit / race status
    is_in_pit: bool = False
    is_lapped: bool = False   # V1: always False; lapping detection is Day 8
    last_pit_lap: int | None = None

    # Data quality
    data_stale: bool = False
    stale_since_lap: int | None = None

    # Undercut score [0, 1] towards the driver immediately ahead.
    # Set by the engine loop after each lap_complete; None when no relevant pair.
    undercut_score: float | None = None

    # Raw gap samples for the rolling-average smoothing. Excluded from
    # repr and equality so tests can compare DriverState instances cleanly.
    _gap_samples: deque[int] = field(
        default_factory=lambda: deque(maxlen=GAP_SMOOTH_WINDOW),
        init=False,
        repr=False,
        compare=False,
    )


# ---------------------------------------------------------------------------
# RaceState
# ---------------------------------------------------------------------------


@dataclass
class RaceState:
    """Full in-memory state of the race being replayed.

    Mutate it by calling :meth:`apply` for each event from the feed::

        state = RaceState()
        async for event in feed.events():
            state.apply(event)
            for atk, def_ in compute_relevant_pairs(state):
                ...
    """

    session_id: str = ""
    circuit_id: str = ""
    total_laps: int | None = None
    current_lap: int = 0

    # Track conditions
    track_status: str = "GREEN"
    track_temp_c: float | None = None
    air_temp_c: float | None = None
    humidity_pct: float | None = None
    rainfall: bool = False

    drivers: dict[str, DriverState] = field(default_factory=dict)
    last_event_ts: datetime | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def apply(self, event: Event) -> None:
        """Update state from the next event in the feed."""
        if not self.session_id:
            self.session_id = event["session_id"]
        self.last_event_ts = event["ts"]

        payload: dict[str, Any] = event.get("payload") or {}
        event_type = event["type"]

        if event_type == "session_start":
            self._apply_session_start(payload)
        elif event_type == "session_end":
            self._apply_session_end(payload)
        elif event_type == "lap_complete":
            self._apply_lap_complete(payload)
        elif event_type == "pit_in":
            self._apply_pit_in(payload)
        elif event_type == "pit_out":
            self._apply_pit_out(payload)
        elif event_type == "track_status_change":
            self._apply_track_status_change(payload)
        elif event_type == "weather_update":
            self._apply_weather_update(payload)
        elif event_type == "data_stale":
            self._apply_data_stale(payload)
        # Unknown event types are silently ignored.

    # ------------------------------------------------------------------
    # Per-type handlers (private)
    # ------------------------------------------------------------------

    def _apply_session_start(self, payload: dict[str, Any]) -> None:
        if circuit_id := payload.get("circuit_id"):
            self.circuit_id = str(circuit_id)
        if (total := payload.get("total_laps")) is not None:
            self.total_laps = int(total)
        for code in payload.get("drivers") or []:
            self.drivers.setdefault(str(code), DriverState(driver_code=str(code)))

    def _apply_session_end(self, payload: dict[str, Any]) -> None:
        for entry in payload.get("final_classification") or []:
            code = str(entry.get("driver_code") or "")
            if code and code in self.drivers:
                if (pos := entry.get("position")) is not None:
                    self.drivers[code].position = int(pos)

    def _apply_lap_complete(self, payload: dict[str, Any]) -> None:
        code = str(payload.get("driver_code") or "")
        if not code:
            return
        d = self.drivers.setdefault(code, DriverState(driver_code=code))

        # Position and leader gap
        if (pos := payload.get("position")) is not None:
            d.position = int(pos)
        if (gl := payload.get("gap_to_leader_ms")) is not None:
            d.gap_to_leader_ms = int(gl)

        # Gap to driver ahead — smoothed with rolling window (§6.2)
        if (ga := payload.get("gap_to_ahead_ms")) is not None:
            d._gap_samples.append(int(ga))
            d.gap_to_ahead_ms = sum(d._gap_samples) // len(d._gap_samples)

        # Lap time — only update for valid laps
        if payload.get("is_valid", True) and (lt := payload.get("lap_time_ms")) is not None:
            d.last_lap_ms = int(lt)

        # Tyre data
        if (compound := payload.get("compound")) is not None:
            d.compound = str(compound)
        if (age := payload.get("tyre_age")) is not None:
            d.tyre_age = int(age)

        # Stint tracking
        is_pit_out = bool(payload.get("is_pit_out", False))
        is_pit_in = bool(payload.get("is_pit_in", False))

        if is_pit_out:
            d.is_in_pit = False
            d.laps_in_stint = 1         # first lap on new rubber
        else:
            d.laps_in_stint += 1

        if is_pit_in:
            d.is_in_pit = True
            if (lap := payload.get("lap_number")) is not None:
                d.last_pit_lap = int(lap)

        # Receiving data clears the stale flag
        d.data_stale = False
        d.stale_since_lap = None

        # Race-level updates
        if (ts := payload.get("track_status")) is not None:
            self.track_status = str(ts)
        if (lap := payload.get("lap_number")) is not None:
            self.current_lap = max(self.current_lap, int(lap))

    def _apply_pit_in(self, payload: dict[str, Any]) -> None:
        code = str(payload.get("driver_code") or "")
        if not code:
            return
        d = self.drivers.setdefault(code, DriverState(driver_code=code))
        d.is_in_pit = True
        if (lap := payload.get("lap_number")) is not None:
            d.last_pit_lap = int(lap)

    def _apply_pit_out(self, payload: dict[str, Any]) -> None:
        code = str(payload.get("driver_code") or "")
        if not code:
            return
        d = self.drivers.setdefault(code, DriverState(driver_code=code))
        d.is_in_pit = False
        if (compound := payload.get("new_compound")) is not None:
            d.compound = str(compound)
        if (age := payload.get("new_tyre_age")) is not None:
            d.tyre_age = int(age)
        if (stint := payload.get("new_stint_number")) is not None:
            d.stint_number = int(stint)
        d.laps_in_stint = 0          # incremented to 1 on next lap_complete
        d._gap_samples.clear()       # gap history is invalid during a pit stop

    def _apply_track_status_change(self, payload: dict[str, Any]) -> None:
        if (status := payload.get("status")) is not None:
            self.track_status = str(status)

    def _apply_weather_update(self, payload: dict[str, Any]) -> None:
        if (temp := payload.get("track_temp_c")) is not None:
            self.track_temp_c = float(temp)
        if (air := payload.get("air_temp_c")) is not None:
            self.air_temp_c = float(air)
        if (hum := payload.get("humidity_pct")) is not None:
            self.humidity_pct = float(hum)
        if (rain := payload.get("rainfall")) is not None:
            self.rainfall = bool(rain)

    def _apply_data_stale(self, payload: dict[str, Any]) -> None:
        code = str(payload.get("driver_code") or "")
        if not code:
            return
        d = self.drivers.setdefault(code, DriverState(driver_code=code))
        d.data_stale = True
        if (lap := payload.get("stale_since_lap")) is not None:
            d.stale_since_lap = int(lap)


# ---------------------------------------------------------------------------
# compute_relevant_pairs
# ---------------------------------------------------------------------------


def compute_relevant_pairs(
    state: RaceState,
) -> list[tuple[DriverState, DriverState]]:
    """Return ``(attacker, defender)`` pairs eligible for undercut evaluation.

    Filtering criteria — master plan §6.1:

    - Both drivers have a known position.
    - Neither driver is in the pit lane.
    - Neither driver is lapped.
    - Neither driver has stale data.
    - Gap from attacker to the driver immediately ahead < 30 s.

    The *attacker* is the driver behind (higher position number); the
    *defender* is the driver immediately ahead (lower position number).
    Pairs are ordered by position: (P2 vs P1), (P3 vs P2), …
    """
    in_race = [
        d for d in state.drivers.values()
        if d.position is not None
        and not d.is_in_pit
        and not d.is_lapped
        and not d.data_stale
    ]
    in_race.sort(key=lambda d: d.position)  # type: ignore[arg-type, return-value]

    pairs: list[tuple[DriverState, DriverState]] = []
    for i in range(len(in_race) - 1):
        defender = in_race[i]       # ahead (lower position number)
        attacker = in_race[i + 1]   # behind (higher position number)

        if (
            attacker.gap_to_ahead_ms is not None
            and attacker.gap_to_ahead_ms < GAP_RELEVANCE_MS
        ):
            pairs.append((attacker, defender))

    return pairs
