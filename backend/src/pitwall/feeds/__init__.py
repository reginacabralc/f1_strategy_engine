"""Race feeds — sources of events for the engine.

V1 ships ``ReplayFeed`` (deterministic playback from an in-memory
sequence or, on Day 3, from the database). ``OpenF1Feed`` is a stub
in V1 and will become a real client in V2 (see ADR 0002).
"""

from pitwall.feeds.base import (
    DataStalePayload,
    Event,
    EventType,
    LapCompletePayload,
    PitInPayload,
    PitOutPayload,
    RaceFeed,
    SessionEndPayload,
    SessionStartPayload,
    TrackStatusChangePayload,
    WeatherUpdatePayload,
)
from pitwall.feeds.openf1 import OpenF1Feed, OpenF1FeedNotImplementedError
from pitwall.feeds.replay import ReplayFeed

__all__ = [
    "DataStalePayload",
    "Event",
    "EventType",
    "LapCompletePayload",
    "OpenF1Feed",
    "OpenF1FeedNotImplementedError",
    "PitInPayload",
    "PitOutPayload",
    "RaceFeed",
    "ReplayFeed",
    "SessionEndPayload",
    "SessionStartPayload",
    "TrackStatusChangePayload",
    "WeatherUpdatePayload",
]
