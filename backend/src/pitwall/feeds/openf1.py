"""``OpenF1Feed`` — V2 stub.

V1 uses :class:`~pitwall.feeds.replay.ReplayFeed` exclusively (see
ADR 0002). This stub exists so the engine can be wired with the same
interface today while we wait to implement the live OpenF1 client in
V2.

Instantiation raises immediately. This is deliberate: an accidental
wiring of the live feed in a V1 deployment fails loudly rather than
silently producing zero events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from pitwall.feeds.base import Event


class OpenF1FeedNotImplementedError(NotImplementedError):
    """Raised when V1 code tries to use the V2-only OpenF1 feed."""


class OpenF1Feed:
    """Live OpenF1 feed — not implemented in V1."""

    def __init__(self) -> None:
        raise OpenF1FeedNotImplementedError(
            "OpenF1Feed is a V2 stub. V1 uses ReplayFeed; see ADR 0002."
        )

    def events(self) -> AsyncIterator[Event]:  # pragma: no cover
        raise OpenF1FeedNotImplementedError

    async def stop(self) -> None:  # pragma: no cover
        raise OpenF1FeedNotImplementedError
