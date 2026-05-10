"""Unit tests for ReplayManager.

The key Day-3 acceptance test: a replay of 10 lap_complete events
produces exactly 10 events in ``topics.events``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from pitwall.core.topics import Topics
from pitwall.engine.replay_manager import ReplayManager
from pitwall.feeds.base import Event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lap_events(n: int, session_id: str = "test_session_R") -> list[Event]:
    """Return *n* lap_complete events spaced 90 s apart."""
    t0 = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)
    events: list[Event] = []
    for i in range(n):
        events.append(
            {
                "type": "lap_complete",
                "session_id": session_id,
                "ts": t0 + timedelta(seconds=90 * i),
                "payload": {
                    "driver_code": "VER",
                    "lap_number": i + 1,
                    "lap_time_ms": 74_000 + i * 50,
                    "compound": "MEDIUM",
                    "tyre_age": i,
                    "is_valid": True,
                },
            }
        )
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_start_returns_uuid_and_marks_running() -> None:
    topics = Topics()
    manager = ReplayManager(topics)

    run_id = await manager.start("test_R", speed_factor=1000.0, events=_make_lap_events(3))
    assert manager.is_running
    assert manager.current_session_id == "test_R"
    assert manager.current_run_id == run_id
    await manager.stop()


async def test_start_while_already_running_raises() -> None:
    topics = Topics()
    manager = ReplayManager(topics)

    await manager.start("monaco_2024_R", speed_factor=1000.0, events=_make_lap_events(3))
    with pytest.raises(ValueError, match="already running"):
        await manager.start("hungary_2024_R", speed_factor=1000.0, events=_make_lap_events(1))
    await manager.stop()


async def test_stop_returns_run_id_and_clears_state() -> None:
    topics = Topics()
    manager = ReplayManager(topics)

    run_id = await manager.start("monaco_2024_R", speed_factor=1000.0, events=_make_lap_events(2))
    stopped_id = await manager.stop()

    assert stopped_id == run_id
    assert not manager.is_running
    assert manager.current_session_id is None
    assert manager.current_run_id is None


async def test_stop_when_not_running_returns_none() -> None:
    topics = Topics()
    manager = ReplayManager(topics)

    result = await manager.stop()
    assert result is None


async def test_stop_is_idempotent() -> None:
    topics = Topics()
    manager = ReplayManager(topics)

    await manager.start("monaco_2024_R", speed_factor=1000.0, events=_make_lap_events(2))
    await manager.stop()
    # Second stop must not raise
    result = await manager.stop()
    assert result is None


async def test_10_laps_produce_10_events_in_topic() -> None:
    """Day-3 acceptance test: replay feeds every event into topics.events."""
    topics = Topics()
    manager = ReplayManager(topics)
    events = _make_lap_events(10)

    await manager.start("monaco_2024_R", speed_factor=1000.0, events=events)

    collected: list[Event] = []
    for _ in range(10):
        ev = await asyncio.wait_for(topics.events.get(), timeout=2.0)
        collected.append(ev)

    assert len(collected) == 10
    assert all(e["type"] == "lap_complete" for e in collected)
    assert [e["payload"]["lap_number"] for e in collected] == list(range(1, 11))
    await manager.stop()


async def test_events_arrive_in_timestamp_order() -> None:
    """Events provided out of order must still arrive ordered by ts."""
    t0 = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)
    events: list[Event] = [
        {
            "type": "lap_complete",
            "session_id": "test_R",
            "ts": t0 + timedelta(seconds=90 * i),
            "payload": {"lap_number": i + 1},
        }
        for i in range(5)
    ]
    # Shuffle before passing
    shuffled = [events[2], events[0], events[4], events[1], events[3]]

    topics = Topics()
    manager = ReplayManager(topics)
    await manager.start("test_R", speed_factor=1000.0, events=shuffled)

    collected: list[Event] = []
    for _ in range(5):
        collected.append(await asyncio.wait_for(topics.events.get(), timeout=2.0))

    lap_numbers = [e["payload"]["lap_number"] for e in collected]
    assert lap_numbers == [1, 2, 3, 4, 5]
    await manager.stop()


async def test_started_at_and_speed_factor_reflect_active_run() -> None:
    topics = Topics()
    manager = ReplayManager(topics)

    await manager.start("monaco_2024_R", speed_factor=42.0, events=_make_lap_events(2))
    assert manager.started_at is not None
    assert manager.current_speed_factor == pytest.approx(42.0)
    await manager.stop()

    # After stop, properties return None
    assert manager.started_at is None
    assert manager.current_speed_factor is None
