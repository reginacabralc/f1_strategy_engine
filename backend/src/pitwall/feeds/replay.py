"""``ReplayFeed`` — emit a sequence of events at a configurable
wall-clock acceleration.

V1 (this skeleton): events come from an in-memory ``Iterable[Event]``
passed to the constructor — used by tests, by ``scripts/replay_cli.py``
on small fixtures, and by the FastAPI ``/api/v1/replay/start`` route
when Stream A's DB-backed event source lands on Day 3.

V2 (Stream A Day 3): the only change will be the source of the
sequence (a streaming DB cursor instead of a list). The pacing
algorithm and the public API stay the same.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from time import monotonic

from pitwall.feeds.base import Event


class ReplayFeed:
    """Replay a sequence of events at ``speed_factor``.

    The emit schedule is anchored to the timestamp of the first event
    so that a slow consumer cannot drift the entire timeline (see
    ``docs/quanta/05-replay-engine.md``). Concretely, for the
    ``i``-th event::

        sim_dt   = (event_i.ts - t0) / speed_factor
        delay    = sim_dt - elapsed_wall_clock_since_start
        if delay > 0: sleep(delay)

    Calling :meth:`stop` aborts any in-flight sleep and causes
    :meth:`events` to terminate without yielding further items.
    """

    def __init__(
        self,
        events: Iterable[Event],
        speed_factor: float = 30.0,
    ) -> None:
        if speed_factor <= 0:
            raise ValueError(f"speed_factor must be > 0, got {speed_factor}")

        # Materialise the iterable up-front so the sort below is safe
        # to do once and so ``event_count`` is meaningful for tests.
        self._events: list[Event] = sorted(events, key=lambda e: e["ts"])
        self._speed_factor = float(speed_factor)
        self._stop_event = asyncio.Event()

    @property
    def speed_factor(self) -> float:
        return self._speed_factor

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    async def events(self) -> AsyncIterator[Event]:
        """Yield events in timestamp order, paced by ``speed_factor``."""
        if not self._events:
            return

        t0 = self._events[0]["ts"]
        sim_t0 = monotonic()

        for ev in self._events:
            if self._stop_event.is_set():
                return

            sim_dt = (ev["ts"] - t0).total_seconds() / self._speed_factor
            delay = sim_dt - (monotonic() - sim_t0)

            if delay > 0:
                # Wait either for the natural delay or for stop().
                # asyncio.wait_for raises TimeoutError on the natural
                # path (no stop), which is exactly what we want.
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=delay,
                    )
                except TimeoutError:
                    pass
                else:
                    return  # stop() was called during the sleep

            yield ev

    async def stop(self) -> None:
        """Idempotent. Future calls to :meth:`events` will be empty."""
        self._stop_event.set()
