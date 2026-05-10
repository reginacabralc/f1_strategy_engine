"""ReplayManager — drives a single active ReplayFeed into the event topic.

Lifecycle
---------
1. ``start(session_id, speed_factor, events)`` — creates a :class:`ReplayFeed`,
   spawns a background :mod:`asyncio` task that drains the feed into
   ``topics.events``, and returns the generated run UUID.
2. ``stop()`` — signals the feed to halt, waits up to 2 s for the task
   to finish, then cancels it if still running.  Idempotent.

Only one replay may run at a time in V1.  ``is_running`` reflects whether
a live background task exists.  Callers check it before calling ``start``
and return HTTP 409 if a replay is already active.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pitwall.core.topics import Topics
from pitwall.feeds.base import Event
from pitwall.feeds.replay import ReplayFeed

logger = logging.getLogger(__name__)


class ReplayManager:
    """Manages one active replay at a time (single event loop, no thread safety needed)."""

    def __init__(self, topics: Topics) -> None:
        self._topics = topics
        self._feed: ReplayFeed | None = None
        self._task: asyncio.Task[None] | None = None
        self._run_id: UUID | None = None
        self._session_id: str | None = None
        self._speed_factor: float | None = None
        self._started_at: datetime | None = None

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def current_session_id(self) -> str | None:
        return self._session_id if self.is_running else None

    @property
    def current_run_id(self) -> UUID | None:
        return self._run_id if self.is_running else None

    @property
    def current_speed_factor(self) -> float | None:
        return self._speed_factor if self.is_running else None

    @property
    def started_at(self) -> datetime | None:
        return self._started_at if self.is_running else None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def start(
        self,
        session_id: str,
        speed_factor: float,
        events: list[Event],
    ) -> UUID:
        """Start a replay.  Raises :exc:`ValueError` if already running."""
        if self.is_running:
            raise ValueError(
                f"A replay is already running for session {self._session_id!r}. "
                "Call stop() first."
            )
        self._run_id = uuid4()
        self._session_id = session_id
        self._speed_factor = speed_factor
        self._started_at = datetime.now(UTC)
        self._feed = ReplayFeed(events, speed_factor=speed_factor)
        self._task = asyncio.create_task(self._run(), name=f"replay-{session_id}")
        return self._run_id

    async def stop(self) -> UUID | None:
        """Stop the active replay.  Returns the run_id that was stopped, or None."""
        run_id = self._run_id
        if self._feed is not None:
            await self._feed.stop()
        if self._task is not None and not self._task.done():
            done, _ = await asyncio.wait({self._task}, timeout=2.0)
            if not done:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
        self._feed = None
        self._task = None
        self._run_id = None
        self._session_id = None
        self._speed_factor = None
        self._started_at = None
        return run_id

    # ------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        assert self._feed is not None
        try:
            async for event in self._feed.events():
                await self._topics.events.put(event)
        except Exception:
            logger.exception("Replay task failed for session %r", self._session_id)
