"""In-process pub-sub channels (ADR 0007: no message broker in V1).

Three asyncio.Queue instances cover the three data flows inside the
process:

- ``events``    Replay feed → engine. One Event envelope per queue item.
- ``alerts``    Engine → WebSocket broadcaster. AlertPayload items (Day 5).
- ``snapshots`` Engine → WebSocket broadcaster. RaceSnapshot items (Day 5).

Queues are created when the :class:`Topics` instance is constructed.
In Python 3.10+ asyncio.Queue does not require a running event loop at
construction time; it binds to the running loop on first await.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pitwall.feeds.base import Event


@dataclass
class Topics:
    """Shared in-process message channels for V1 (no Kafka, no Redis)."""

    events: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(maxsize=1_000))
    alerts: asyncio.Queue[Any] = field(default_factory=lambda: asyncio.Queue(maxsize=500))
    snapshots: asyncio.Queue[Any] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
