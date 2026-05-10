# WebSocket — message format v1

> **Owner**: Stream B. **Consumed by**: Stream C (`useRaceFeed` hook).
> **Status**: v1 finalised at Day 1 kickoff. All `type`, enum and field
> names are consistent with `openapi_v1.yaml` and `db_schema_v1.sql`.

WebSockets are not first-class in OpenAPI 3.0, so this document is the
canonical reference for the push channel. Any change here must be
mirrored in the JSON encoders/decoders on both ends and is a breaking
change unless additive.

## Endpoint

```
ws://localhost:8000/ws/v1/live
```

The protocol is versioned in the URL (`/ws/v1/...`). Any change that
breaks an existing client must bump to `/ws/v2/...` and run side-by-side
during a deprecation window.

## Reconnection policy

The server will close idle or misbehaving connections. The client must
reconnect with **exponential back-off**: `1 s → 2 s → 4 s → 8 s → 16 s`,
then 16 s steady. After reconnecting, the client receives a fresh
`snapshot` message containing the full race state — there is no replay
of past events.

Heartbeat: server emits `ping` every 15 s; client must reply `pong`
within 10 s or the connection is closed with code `1011`.

## Envelope

Every message — both directions — has the shape:

```json
{
  "type":    "<one of the values listed below>",
  "ts":      "2024-05-26T13:45:21.503Z",
  "payload": { ... }
}
```

`ts` is the server-side wall-clock at the moment the event was emitted,
in UTC ISO-8601 with millisecond precision. `payload` is type-specific.

## Server → client messages

### `snapshot`

Emitted on connect, after every reconnect, and at most once per second
during steady-state operation. Idempotent: receiving a newer snapshot
fully overrides the client's local state.

```json
{
  "type": "snapshot",
  "ts": "2024-05-26T13:45:21.503Z",
  "payload": {
    "session_id": "monaco_2024_R",
    "current_lap": 23,
    "track_status": "GREEN",
    "track_temp_c": 38.2,
    "air_temp_c": 24.0,
    "humidity_pct": 62.0,
    "active_predictor": "xgboost",
    "drivers": [
      {
        "driver_code": "VER",
        "team_code": "RBR",
        "position": 1,
        "gap_to_leader_ms": 0,
        "gap_to_ahead_ms": null,
        "last_lap_ms": 74521,
        "compound": "MEDIUM",
        "tyre_age": 18,
        "is_in_pit": false,
        "is_lapped": false,
        "last_pit_lap": null,
        "stint_number": 1,
        "undercut_score": null
      }
    ]
  }
}
```

The `payload` schema is `RaceSnapshot` from `openapi_v1.yaml`.

### `lap_update`

Emitted when any driver crosses the finish line. Smaller and cheaper
than `snapshot`; clients can apply it directly to their cached state.

```json
{
  "type": "lap_update",
  "ts": "2024-05-26T13:42:18.503Z",
  "payload": {
    "session_id": "monaco_2024_R",
    "lap_number": 18,
    "driver_code": "VER",
    "lap_time_ms": 74521,
    "position": 1,
    "gap_to_leader_ms": 0,
    "gap_to_ahead_ms": null,
    "compound": "MEDIUM",
    "tyre_age": 18,
    "is_pit_in": false,
    "is_pit_out": false,
    "track_status": "GREEN"
  }
}
```

### `pit_stop`

Emitted on both pit entry and pit exit; distinguished by `phase`. The
exit message also carries `duration_ms` (stationary time) and
`new_compound`.

```json
{
  "type": "pit_stop",
  "ts": "2024-05-26T13:55:32.000Z",
  "payload": {
    "session_id": "monaco_2024_R",
    "lap_number": 24,
    "driver_code": "HAM",
    "phase": "out",
    "duration_ms": 2400,
    "new_compound": "HARD"
  }
}
```

`phase` is one of `"in"` or `"out"`. On `phase="in"`, `duration_ms`
and `new_compound` are absent.

### `alert`

The reason this product exists. Emitted by the undercut engine when a
relevant pair satisfies the alert conditions (see quanta 04). Critical
event — never dropped.

```json
{
  "type": "alert",
  "ts": "2024-05-26T13:46:10.000Z",
  "payload": {
    "alert_id": "a3e2c9c4-8b3a-4cd1-9dc4-89e1d4a5fa17",
    "session_id": "monaco_2024_R",
    "lap_number": 23,
    "alert_type": "UNDERCUT_VIABLE",
    "attacker_code": "NOR",
    "defender_code": "VER",
    "estimated_gain_ms": 1800,
    "pit_loss_ms": 22000,
    "gap_actual_ms": 2500,
    "score": 0.62,
    "confidence": 0.71,
    "ventana_laps": 4,
    "predictor_used": "xgboost"
  }
}
```

`alert_type` ∈ `AlertType` enum from `openapi_v1.yaml`:

| Value | Meaning |
|---|---|
| `UNDERCUT_VIABLE` | Score and confidence both above thresholds; pit now is recommended. |
| `UNDERCUT_RISK` | Marginal. Score above threshold but confidence is low. |
| `UNDERCUT_DISABLED_RAIN` | Wet-weather compounds detected; engine refuses to project. |
| `SUSPENDED_SC` | Safety car deployed; alerts paused for the duration. |
| `SUSPENDED_VSC` | Virtual safety car. |
| `INSUFFICIENT_DATA` | Stint too short or `data_stale` for one of the drivers. |

### `track_status`

```json
{
  "type": "track_status",
  "ts": "2024-05-26T13:30:15.000Z",
  "payload": {
    "session_id": "monaco_2024_R",
    "lap_number": 12,
    "status": "SC",
    "previous_status": "GREEN",
    "started": true
  }
}
```

`status` ∈ `TrackStatus` enum (`GREEN | SC | VSC | YELLOW | RED`).
`started=true` for begin-of-period; `started=false` for end-of-period
(in which case `status` carries the period that ended).

### `replay_state`

Emitted on replay lifecycle transitions.

```json
{
  "type": "replay_state",
  "ts": "2024-05-26T13:00:00.000Z",
  "payload": {
    "run_id": "f7a01b58-e9c0-4d2e-8e2c-2cb7ad1a4e21",
    "session_id": "monaco_2024_R",
    "state": "started",
    "speed_factor": 30,
    "pace_predictor": "xgboost"
  }
}
```

`state` ∈ `started | stopped | finished`.

### `error`

Surfaces a backend-side issue the client should display. Never used for
schema-validation errors against the client (those close the
connection).

```json
{
  "type": "error",
  "ts": "...",
  "payload": {
    "code": "FEED_DISCONNECTED",
    "message": "Lost connection to feed; will retry."
  }
}
```

`code` enum (extensible): `FEED_DISCONNECTED`, `DB_UNAVAILABLE`,
`MODEL_NOT_LOADED`, `INTERNAL`. Clients must tolerate unknown codes.

### `ping` / `pong`

```json
{ "type": "ping", "ts": "..." }
{ "type": "pong", "ts": "..." }
```

Empty payload (or absent). Sent every 15 s by the server. The client
must echo a `pong` within 10 s.

## Client → server messages

### `pong`

Heartbeat reply (see above).

### `subscribe` (reserved, V2)

Reserved for selective subscriptions in V2. V1 servers ignore unknown
client messages; V1 clients must not send anything other than `pong`.

## Backpressure & delivery

| Concern | V1 behaviour |
|---|---|
| Slow client | Each `send` has a 1 s timeout; on timeout the connection is closed with `1011 server overloaded`. |
| Outgoing buffer | Per-client cap of 100 queued messages; over the cap → close `1011`. |
| Snapshot coalescing | Newer snapshots replace older queued snapshots; `alert` and `pit_stop` are **never** coalesced or dropped. |
| Order | Best-effort per session; the engine emits in causal order, but the broadcaster may interleave events from different streams. |
| Persistence | None. Reconnecting clients receive a fresh `snapshot` only. |

Multi-process backends are out of scope for V1. Today, all subscribers
sit in the same `asyncio` event loop as the engine (see ADR 0007).

## Versioning summary

- **V1 path**: `/ws/v1/live` (this document).
- Adding a new `type` value: backward-compatible (clients ignore unknown
  types).
- Adding a new field to a payload: backward-compatible.
- Removing or renaming a field: breaking → bump to `/ws/v2/...`.
- Changing the envelope (`type`, `ts`, `payload`): breaking → V2.

## Where it lives in code

- Server: `backend/src/pitwall/api/ws.py`.
- Client: `frontend/src/hooks/useRaceFeed.ts`.

Both ends import the same JSON shapes from a single source of truth.
The TypeScript types are generated from `openapi_v1.yaml` for the
shared schemas (e.g. `RaceSnapshot`); the WebSocket-specific envelopes
are hand-written in `frontend/src/api/ws.ts` and must mirror this
document.
