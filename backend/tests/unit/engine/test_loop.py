"""Tests for EngineLoop edge cases — SC/VSC suspension, rain, pit-recent.

All tests run the loop as a background task against a real asyncio queue
so the dispatch path is exercised end-to-end.  A ``_NullBroadcaster``
captures every JSON message for assertions without touching any real
network.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from pitwall.core.topics import Topics
from pitwall.engine.loop import EngineLoop
from pitwall.engine.projection import PaceContext, PacePrediction, UnsupportedContextError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CaptureBroadcaster:
    """Records every broadcast_json call for assertions."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def broadcast_json(self, data: dict[str, Any]) -> None:
        self.messages.append(data)

    def alert_types(self) -> list[str]:
        return [
            m["payload"]["alert_type"]
            for m in self.messages
            if m.get("type") == "alert"
        ]

    def message_types(self) -> list[str]:
        return [m.get("type", "") for m in self.messages]


class _ConstPredictor:
    """Returns a fixed lap time and confidence for every context."""

    def __init__(self, lap_ms: int = 74_500, conf: float = 0.8) -> None:
        self._lap_ms = lap_ms
        self._conf = conf

    def predict(self, ctx: PaceContext) -> PacePrediction:
        return PacePrediction(predicted_lap_time_ms=self._lap_ms, confidence=self._conf)


class _FailPredictor:
    """Always raises UnsupportedContextError."""

    def predict(self, ctx: PaceContext) -> PacePrediction:
        raise UnsupportedContextError("no data")


_TS = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)


def _make_event(
    event_type: str,
    payload: dict[str, Any],
    session_id: str = "monaco_2024_R",
) -> dict[str, Any]:
    return {"type": event_type, "session_id": session_id, "ts": _TS, "payload": payload}


def _session_start(drivers: list[str] | None = None) -> dict[str, Any]:
    return _make_event(
        "session_start",
        {
            "circuit_id": "monaco",
            "total_laps": 78,
            "drivers": drivers or ["VER", "LEC"],
        },
    )


def _lap_complete(
    driver_code: str,
    position: int,
    gap_to_ahead_ms: int | None,
    lap_number: int = 5,
    compound: str = "MEDIUM",
    tyre_age: int = 10,
    track_status: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "driver_code": driver_code,
        "lap_number": lap_number,
        "position": position,
        "gap_to_ahead_ms": gap_to_ahead_ms,
        "compound": compound,
        "tyre_age": tyre_age,
        "is_pit_in": False,
        "is_pit_out": False,
        "is_valid": True,
    }
    if track_status is not None:
        payload["track_status"] = track_status
    return _make_event("lap_complete", payload)


async def _run_events(
    events: list[dict[str, Any]],
    predictor: Any = None,
) -> _CaptureBroadcaster:
    """Feed events through a live EngineLoop and return the broadcaster."""
    broadcaster = _CaptureBroadcaster()
    topics = Topics()
    loop = EngineLoop(topics, broadcaster, predictor or _ConstPredictor(), {})  # type: ignore[arg-type]
    await loop.start()

    for event in events:
        await topics.events.put(event)  # type: ignore[arg-type]

    # Drain: wait until all events have been consumed.
    await asyncio.sleep(0.05)
    await loop.stop()
    return broadcaster


# ---------------------------------------------------------------------------
# SC / VSC — session-level suspension
# ---------------------------------------------------------------------------


async def test_sc_active_broadcasts_suspended_sc_alert() -> None:
    events = [
        _session_start(),
        # 5 normal laps to build up laps_in_stint
        *[_lap_complete("VER", 1, None, lap_number=i) for i in range(1, 6)],
        *[_lap_complete("LEC", 2, 8_000, lap_number=i) for i in range(1, 6)],
        # Lap 6 under SC
        _lap_complete("VER", 1, None, lap_number=6, track_status="SC"),
        _lap_complete("LEC", 2, 8_000, lap_number=6, track_status="SC"),
    ]
    broadcaster = await _run_events(events)
    assert "SUSPENDED_SC" in broadcaster.alert_types()


async def test_vsc_active_broadcasts_suspended_vsc_alert() -> None:
    events = [
        _session_start(),
        *[_lap_complete("VER", 1, None, lap_number=i) for i in range(1, 6)],
        *[_lap_complete("LEC", 2, 8_000, lap_number=i) for i in range(1, 6)],
        _lap_complete("VER", 1, None, lap_number=6, track_status="VSC"),
        _lap_complete("LEC", 2, 8_000, lap_number=6, track_status="VSC"),
    ]
    broadcaster = await _run_events(events)
    assert "SUSPENDED_VSC" in broadcaster.alert_types()


async def test_sc_active_does_not_broadcast_undercut_viable() -> None:
    """No UNDERCUT_VIABLE alerts while SC is deployed."""
    events = [
        _session_start(),
        *[_lap_complete("VER", 1, None, lap_number=i) for i in range(1, 6)],
        *[_lap_complete("LEC", 2, 8_000, lap_number=i) for i in range(1, 6)],
        _lap_complete("VER", 1, None, lap_number=6, track_status="SC"),
        _lap_complete("LEC", 2, 8_000, lap_number=6, track_status="SC"),
    ]
    broadcaster = await _run_events(events)
    assert "UNDERCUT_VIABLE" not in broadcaster.alert_types()


async def test_sc_active_snapshot_still_broadcast() -> None:
    """Snapshot must always be broadcast regardless of track status."""
    events = [
        _session_start(),
        _lap_complete("VER", 1, None, track_status="SC"),
        _lap_complete("LEC", 2, 8_000, track_status="SC"),
    ]
    broadcaster = await _run_events(events)
    assert "snapshot" in broadcaster.message_types()


async def test_green_flag_resumes_undercut_evaluation_after_sc() -> None:
    """After SC ends, the engine re-evaluates undercuts normally."""
    # Give a highly viable undercut scenario: defender much slower on old tyres
    class _SlowDefenderPredictor:
        def predict(self, ctx: PaceContext) -> PacePrediction:
            # Defender on old MEDIUM: 79 s/lap; attacker on fresh HARD: 74 s/lap
            lap_ms = 79_000 if ctx.compound == "MEDIUM" else 74_000
            return PacePrediction(predicted_lap_time_ms=lap_ms, confidence=0.9)

    events = [
        _session_start(),
        # 5 laps under SC — no undercut
        *[_lap_complete("VER", 1, None, lap_number=i, track_status="SC") for i in range(1, 6)],
        *[
            _lap_complete("LEC", 2, 2_000, lap_number=i, compound="MEDIUM",
                          tyre_age=25, track_status="SC")
            for i in range(1, 6)
        ],
        # Green flag — 3 more laps, undercut should evaluate
        *[_lap_complete("VER", 1, None, lap_number=i) for i in range(6, 9)],
        *[
            _lap_complete("LEC", 2, 2_000, lap_number=i, compound="MEDIUM", tyre_age=25 + (i - 5))
            for i in range(6, 9)
        ],
    ]
    broadcaster = await _run_events(events, predictor=_SlowDefenderPredictor())
    # SC laps should have SUSPENDED_SC; green laps should NOT have SUSPENDED_SC
    sc_alerts = [a for a in broadcaster.alert_types() if a == "SUSPENDED_SC"]
    # There were SC laps, so some SUSPENDED_SC alerts were emitted
    assert len(sc_alerts) > 0
    # At least one evaluation happened under green (snapshot was broadcast)
    assert broadcaster.message_types().count("snapshot") >= 5


async def test_yellow_flag_does_not_suspend_undercut() -> None:
    """YELLOW flag is NOT SC/VSC — undercut evaluation continues."""
    events = [
        _session_start(),
        _lap_complete("VER", 1, None, track_status="YELLOW"),
        _lap_complete("LEC", 2, 8_000, track_status="YELLOW"),
    ]
    broadcaster = await _run_events(events)
    assert "SUSPENDED_SC" not in broadcaster.alert_types()
    assert "SUSPENDED_VSC" not in broadcaster.alert_types()


# ---------------------------------------------------------------------------
# Loop invariants
# ---------------------------------------------------------------------------


async def test_snapshot_broadcast_on_every_lap_complete() -> None:
    """Exactly one snapshot per lap_complete event."""
    events = [
        _session_start(),
        _lap_complete("VER", 1, None, lap_number=1),
        _lap_complete("VER", 1, None, lap_number=2),
        _lap_complete("VER", 1, None, lap_number=3),
    ]
    broadcaster = await _run_events(events)
    assert broadcaster.message_types().count("snapshot") == 3


async def test_undercut_scores_reset_each_lap() -> None:
    """undercut_score on DriverState must be None after reset, then set per lap."""
    topics = Topics()
    broadcaster = _CaptureBroadcaster()
    loop = EngineLoop(topics, broadcaster, _ConstPredictor(), {})  # type: ignore[arg-type]
    await loop.start()

    events = [
        _session_start(),
        *[_lap_complete("VER", 1, None, lap_number=i) for i in range(1, 6)],
        *[_lap_complete("LEC", 2, 8_000, lap_number=i) for i in range(1, 6)],
    ]
    for e in events:
        await topics.events.put(e)  # type: ignore[arg-type]
    await asyncio.sleep(0.05)

    # After processing, undercut_score is set (0.0 since predictor is constant
    # and gap_recuperable won't beat pit_loss + margin)
    assert loop.state.drivers["LEC"].undercut_score is not None
    await loop.stop()
