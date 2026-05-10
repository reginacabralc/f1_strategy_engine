"""Tests for ``ReplayFeed``.

Day-2 deliverable for Stream B. The bullet in the plan is "ReplayFeed
emits events in order at factor 1000×"; we cover that plus the
correctness corners that matter for the engine on Day 5: ``stop()``
during a sleep, empty input, invalid speed factor, and the protocol
adherence smoke.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic

import pytest

from pitwall.feeds.base import Event, RaceFeed
from pitwall.feeds.replay import ReplayFeed

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _lap_event(driver: str, lap: int, t: datetime) -> Event:
    """Build a minimal `lap_complete` event with timestamp `t`."""
    return Event(
        type="lap_complete",
        session_id="monaco_2024_R",
        ts=t,
        payload={
            "driver_code": driver,
            "lap_number": lap,
            "lap_time_ms": 75_000,
            "is_pit_in": False,
            "is_pit_out": False,
            "is_valid": True,
        },
    )


def _build_session(n_laps: int, n_drivers: int = 2) -> list[Event]:
    """N laps × M drivers, one second between successive laps."""
    t0 = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)
    events: list[Event] = []
    for lap in range(1, n_laps + 1):
        for d in range(n_drivers):
            ts = t0 + timedelta(seconds=lap * 60 + d)
            events.append(_lap_event(f"D{d:02d}", lap, ts))
    return events


async def _drain(feed: RaceFeed) -> list[Event]:
    return [ev async for ev in feed.events()]


# --------------------------------------------------------------------------
# Construction validation
# --------------------------------------------------------------------------


def test_rejects_zero_speed_factor() -> None:
    with pytest.raises(ValueError, match="speed_factor must be > 0"):
        ReplayFeed(events=[], speed_factor=0)


def test_rejects_negative_speed_factor() -> None:
    with pytest.raises(ValueError, match="speed_factor must be > 0"):
        ReplayFeed(events=[], speed_factor=-1.0)


def test_satisfies_protocol() -> None:
    feed = ReplayFeed(events=[], speed_factor=1.0)
    assert isinstance(feed, RaceFeed)


# --------------------------------------------------------------------------
# Empty input
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_feed_yields_nothing() -> None:
    feed = ReplayFeed(events=[], speed_factor=1.0)
    assert feed.event_count == 0
    assert await _drain(feed) == []


# --------------------------------------------------------------------------
# Ordering — the headline Day-2 requirement
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_are_yielded_in_timestamp_order_at_factor_1000() -> None:
    """Build a session and shuffle the input list; ReplayFeed must
    still yield events in monotonic timestamp order."""
    events = _build_session(n_laps=10, n_drivers=4)
    # Reverse to make sure the feed sorts internally rather than relying
    # on the caller to pre-sort.
    feed = ReplayFeed(events=list(reversed(events)), speed_factor=1000.0)
    assert feed.event_count == len(events)

    yielded = await _drain(feed)
    assert len(yielded) == len(events)
    # Strict monotonic timestamps.
    timestamps = [ev["ts"] for ev in yielded]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_factor_1000_finishes_quickly() -> None:
    """A 1-hour session at factor 1000 must complete in well under
    1 hour. We assert "well under 5 s" to keep the test resilient on
    slow CI."""
    events = _build_session(n_laps=60, n_drivers=20)  # ~1200 events
    feed = ReplayFeed(events=events, speed_factor=1000.0)

    start = monotonic()
    yielded = await _drain(feed)
    elapsed = monotonic() - start

    assert len(yielded) == len(events)
    assert elapsed < 5.0, f"factor=1000 took {elapsed:.2f}s, expected < 5s"


# --------------------------------------------------------------------------
# Pacing actually paces (smoke at low factor)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pacing_actually_waits_at_low_factor() -> None:
    """At a deliberately low factor the feed must take measurable
    wall-clock time. Two events 1 simulated minute apart at factor 600
    means the wall-clock delta must be approximately 0.1 s."""
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    events = [
        _lap_event("VER", 1, t0),
        _lap_event("VER", 2, t0 + timedelta(seconds=60)),
    ]
    feed = ReplayFeed(events=events, speed_factor=600.0)

    start = monotonic()
    yielded = await _drain(feed)
    elapsed = monotonic() - start

    assert len(yielded) == 2
    # 60 s / 600 = 0.1 s — but be generous on both sides for CI.
    assert 0.05 < elapsed < 1.0, f"unexpected elapsed {elapsed:.3f}s"


# --------------------------------------------------------------------------
# Cancellation via stop()
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_during_sleep_terminates_promptly() -> None:
    """Two events 10 simulated minutes apart at factor 1 (real time).
    The natural delay is 600 s; stop() must terminate the iterator in
    well under 1 s rather than waiting out the sleep."""
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    events = [
        _lap_event("VER", 1, t0),
        _lap_event("VER", 2, t0 + timedelta(seconds=600)),
    ]
    feed = ReplayFeed(events=events, speed_factor=1.0)

    received: list[Event] = []

    async def consume() -> None:
        async for ev in feed.events():
            received.append(ev)

    consumer = asyncio.create_task(consume())
    # Give the consumer time to yield the first event and enter the sleep.
    await asyncio.sleep(0.05)

    start = monotonic()
    await feed.stop()
    await asyncio.wait_for(consumer, timeout=1.0)
    elapsed = monotonic() - start

    assert received == [events[0]], "second event should not have been yielded"
    assert elapsed < 0.5, f"stop() took {elapsed:.3f}s to take effect"
    assert feed.is_stopped is True


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    feed = ReplayFeed(events=[], speed_factor=1.0)
    await feed.stop()
    await feed.stop()  # second call must not raise
    assert feed.is_stopped is True


@pytest.mark.asyncio
async def test_iterator_after_stop_yields_nothing() -> None:
    events = _build_session(n_laps=5)
    feed = ReplayFeed(events=events, speed_factor=1000.0)
    await feed.stop()
    assert await _drain(feed) == []
