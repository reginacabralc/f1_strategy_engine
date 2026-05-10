# Replay event format v1

> **Owner**: Stream B. **Producers**: `ReplayFeed` in V1, `OpenF1Feed` in
> V2 (stub today). **Consumers**: the undercut engine
> (`pitwall.engine`) and the WebSocket broadcaster.
> **Status**: v1 finalised at Day 1 kickoff. Field names match
> `db_schema_v1.sql` and `websocket_messages.md`.

## Why a feed abstraction

`pitwall.engine.consume_feed` reads from a `RaceFeed` async iterator —
not from the database directly, not from OpenF1 directly. The reasons
are:

1. **Reproducibility**. `ReplayFeed` is deterministic for a given
   `(session_id, speed_factor)`. Tests run end-to-end at 1000× without
   flakes.
2. **Live independence**. The V1 demo replays historical sessions.
   When V2 needs to consume OpenF1 live, only the feed implementation
   changes — the engine does not.
3. **Symmetric back-tests**. The same code path serves a normal demo
   and the back-test harness (which replays a session and compares
   alerts to the curated `known_undercuts` list).

See [ADR 0002](../adr/0002-replay-first.md) and
[quanta 05](../quanta/05-replay-engine.md).

## Python type

```python
from datetime import datetime
from typing import AsyncIterator, Literal, TypedDict

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
    type: EventType
    session_id: str
    ts: datetime          # tz-aware UTC; comparable across events
    payload: dict         # shape depends on `type` (see below)

class RaceFeed(Protocol):
    async def events(self) -> AsyncIterator[Event]: ...
    async def stop(self) -> None: ...
```

Concrete dataclass models live in `backend/src/pitwall/feeds/events.py`
(Stream B Day 2). This document is the authoritative shape.

## Wire format (when serialised)

When events are persisted (back-test fixtures, debugging) they are
serialised as JSON Lines. Each line is one event:

```json
{"type":"lap_complete","session_id":"monaco_2024_R","ts":"2024-05-26T13:42:18.503Z","payload":{...}}
```

The serialised form is consumed by Stream A's back-test fixtures
(`backend/tests/fixtures/`) and by `scripts/replay_cli.py`.

## Event types

### `session_start`

First event of every session. The engine resets state on receipt.

```json
{
  "type": "session_start",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:00:00.000Z",
  "payload": {
    "circuit_id": "monaco",
    "total_laps": 78,
    "drivers": ["VER", "LEC", "NOR", "PIA", "..."]
  }
}
```

### `session_end`

Last event of every session. The engine flushes any buffered alerts
and stops processing.

```json
{
  "type": "session_end",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T15:08:32.000Z",
  "payload": {
    "final_classification": [
      { "position": 1, "driver_code": "LEC", "total_laps": 78, "total_time_ms": 8423000 }
    ]
  }
}
```

### `lap_complete`

The most frequent event. Emitted whenever a driver crosses the finish
line. Field names are 1-to-1 with the `laps` table in
`db_schema_v1.sql`.

```json
{
  "type": "lap_complete",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:42:18.503Z",
  "payload": {
    "driver_code": "VER",
    "lap_number": 18,
    "lap_time_ms": 74521,
    "sector_1_ms": 24100,
    "sector_2_ms": 25200,
    "sector_3_ms": 25221,
    "compound": "MEDIUM",
    "tyre_age": 18,
    "is_pit_in": false,
    "is_pit_out": false,
    "is_valid": true,
    "track_status": "GREEN",
    "position": 2,
    "gap_to_leader_ms": 1820,
    "gap_to_ahead_ms": 1820
  }
}
```

`compound` ∈ `Compound` enum. `track_status` ∈ `TrackStatus` enum
(see `openapi_v1.yaml`).

### `pit_in`

Fires when a driver crosses the pit-entry detection loop.

```json
{
  "type": "pit_in",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:55:10.000Z",
  "payload": {
    "driver_code": "HAM",
    "lap_number": 24
  }
}
```

### `pit_out`

Fires when the same driver crosses the pit-exit detection loop. The
two events are emitted as a pair, in order (`pit_in` first), and both
carry the same `lap_number`.

```json
{
  "type": "pit_out",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:55:32.000Z",
  "payload": {
    "driver_code": "HAM",
    "lap_number": 24,
    "duration_ms": 2400,
    "new_compound": "HARD",
    "new_tyre_age": 0,
    "new_stint_number": 2
  }
}
```

`duration_ms` is the stationary time in the box (~2-3 s for a clean
stop). `new_compound` ∈ `Compound`. `new_tyre_age` is always `0` in
V1 (FastF1 does not surface used-tyre starts pre-2026).

### `track_status_change`

Emitted when the FIA track status changes (SC deployed/withdrawn,
VSC, yellow flags, red flag). Always carries the current `status` and
the `previous_status`. The engine uses this to suspend/resume
alerts (see quanta 04 § edge cases).

```json
{
  "type": "track_status_change",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:30:15.000Z",
  "payload": {
    "lap_number": 12,
    "status": "SC",
    "previous_status": "GREEN"
  }
}
```

### `weather_update`

Reported irregularly (FastF1 captures roughly one record per minute,
not synced with laps). Field names match the `weather` table.

```json
{
  "type": "weather_update",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:50:00.000Z",
  "payload": {
    "track_temp_c": 38.5,
    "air_temp_c": 24.0,
    "humidity_pct": 62.0,
    "rainfall": false
  }
}
```

`humidity_pct` is in the FastF1 percent scale (0-100).

### `data_stale`

Emitted when the feed has not produced a `lap_complete` for a driver
within an expected interval — e.g. they retired, were classified DNF,
or their data dropped from the feed. The engine drops the driver
from relevant pairs until a fresh `lap_complete` arrives.

```json
{
  "type": "data_stale",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:48:00.000Z",
  "payload": {
    "driver_code": "BOT",
    "stale_since_lap": 23,
    "reason": "missing"
  }
}
```

`reason` ∈ `missing | dnf | retired`.

## Ordering guarantees

| Guarantee | V1 |
|---|---|
| `session_start` precedes every other event in that session | ✅ |
| `pit_in` precedes the matching `pit_out` for the same driver | ✅ |
| `lap_complete` for driver `D` is monotonic in `lap_number` | ✅ |
| Wall-clock order across drivers | ❌ (best-effort) |
| `track_status_change` precedes the laps it affects | ❌ (timestamps tell the truth) |

The engine is required to be tolerant of out-of-order events between
drivers — two `lap_complete` events with identical `ts` may arrive in
any order. The engine sorts by `ts` and resolves ties deterministically
(`lap_number` then `driver_code`).

## How `ReplayFeed` paces itself

```python
async def events(self) -> AsyncIterator[Event]:
    cursor = open_session_cursor(self.session_id)
    t0 = next(cursor).ts        # first event's ts
    sim_t0 = monotonic()
    yield first_event
    for ev in cursor:
        sim_dt = (ev.ts - t0).total_seconds() / self.speed_factor
        delay  = sim_dt - (monotonic() - sim_t0)
        if delay > 0:
            await asyncio.sleep(delay)
        yield ev
```

The schedule is anchored to `t0`, not to the previous event, so a slow
consumer cannot drift the entire timeline. At `speed_factor=1000` the
sleeps collapse to zero and the feed runs as fast as the engine can
consume — which is what the back-test and CI use.

## Differences between `ReplayFeed` and `OpenF1Feed` (V2)

| Aspect | `ReplayFeed` (V1) | `OpenF1Feed` (V2) |
|---|---|---|
| Source | DB rows previously ingested by FastF1 | OpenF1 HTTP / SSE |
| Determinism | Total — same input, same events, same order | Subject to lag, retries, and provider-side reordering |
| Wall-clock | Configurable via `speed_factor` | `1×` only |
| Missing data | Known up front; `data_stale` emitted preemptively | Discovered on-the-fly via heartbeat absence |
| Reset on reconnect | N/A | Yes — re-emits a synthetic `session_start` |

The engine does not distinguish the two. That is the whole point.

## Versioning summary

- **V1 path**: this document.
- Adding a new event type: backward-compatible (engine handles unknown
  types as a no-op, log warning).
- Adding a new field to a payload: backward-compatible.
- Removing or renaming a field, or changing semantics: breaking → bump
  to v2.

## Where it lives in code

- Interface (`RaceFeed`): `backend/src/pitwall/feeds/base.py` (Stream B Day 2).
- Replay implementation: `backend/src/pitwall/feeds/replay.py` (Stream B Day 3).
- OpenF1 stub: `backend/src/pitwall/feeds/openf1.py` (V1 stub, V2 real).
- Engine consumer: `backend/src/pitwall/engine/__init__.py::consume_feed`.
- Back-test harness: `backend/src/pitwall/engine/backtest.py` (Stream A+B Day 9).
