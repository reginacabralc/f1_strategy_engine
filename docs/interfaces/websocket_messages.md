# WebSocket — formato de mensajes v1

> Fuente de verdad: este documento. WebSocket no se documenta en OpenAPI.

## Endpoint

```
ws://localhost:8000/ws/v1/live
```

## Reconnect

El cliente debe reconectar automáticamente con backoff exponencial (1s, 2s, 4s, máximo 16s). Heartbeat ping/pong cada 15 s.

## Envelope

Todos los mensajes son JSON con la forma:

```json
{
  "type": "lap_update | pit_stop | alert | track_status | replay_state | snapshot | error | ping | pong",
  "ts": "2024-05-26T13:45:21.503Z",
  "payload": { ... }
}
```

## Tipos de mensaje (server → client)

### `snapshot`

Enviado al conectar y cada N segundos como heartbeat lógico. Sirve para que el cliente recupere estado tras reconexión.

```json
{
  "type": "snapshot",
  "ts": "2024-05-26T13:45:21.503Z",
  "payload": {
    "session_id": "monaco_2024_R",
    "current_lap": 23,
    "track_status": "GREEN",
    "track_temp_c": 38.2,
    "active_predictor": "xgb",
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

### `lap_update`

Cuando un piloto completa una vuelta.

```json
{
  "type": "lap_update",
  "ts": "...",
  "payload": {
    "session_id": "monaco_2024_R",
    "lap": 23,
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

Cuando un piloto entra/sale a/de boxes.

```json
{
  "type": "pit_stop",
  "ts": "...",
  "payload": {
    "session_id": "monaco_2024_R",
    "lap": 24,
    "driver_code": "HAM",
    "phase": "in | out",
    "duration_ms": 2400,
    "new_compound": "HARD"
  }
}
```

### `alert`

Cuando el motor emite una alerta de undercut.

```json
{
  "type": "alert",
  "ts": "...",
  "payload": {
    "alert_id": "a3e2-...",
    "session_id": "monaco_2024_R",
    "lap": 23,
    "alert_type": "UNDERCUT_VIABLE | UNDERCUT_RISK | UNDERCUT_DISABLED_RAIN | SUSPENDED_SC | SUSPENDED_VSC | INSUFFICIENT_DATA",
    "attacker_code": "NOR",
    "defender_code": "VER",
    "estimated_gain_ms": 1800,
    "pit_loss_ms": 22000,
    "gap_actual_ms": 2500,
    "score": 0.62,
    "confidence": 0.71,
    "ventana_vueltas": 4,
    "predictor_used": "xgb"
  }
}
```

### `track_status`

Cambio de estado de pista.

```json
{
  "type": "track_status",
  "ts": "...",
  "payload": {
    "session_id": "monaco_2024_R",
    "lap": 25,
    "status": "GREEN | SC | VSC | RED | YELLOW",
    "started": true
  }
}
```

### `replay_state`

Inicio/pausa/fin de un replay.

```json
{
  "type": "replay_state",
  "ts": "...",
  "payload": {
    "run_id": "...",
    "session_id": "monaco_2024_R",
    "state": "started | stopped | finished",
    "speed_factor": 30,
    "pace_predictor": "xgb"
  }
}
```

### `error`

Error de servidor que el cliente debe mostrar.

```json
{
  "type": "error",
  "ts": "...",
  "payload": {
    "code": "FEED_DISCONNECTED | DB_UNAVAILABLE | MODEL_NOT_LOADED",
    "message": "Lost connection to feed; will retry"
  }
}
```

### `ping` / `pong`

Heartbeats cada 15 s. El cliente responde `pong` a cada `ping` del servidor.

```json
{ "type": "ping", "ts": "..." }
{ "type": "pong", "ts": "..." }
```

## Tipos de mensaje (client → server)

### `subscribe` (opcional V1)

Por ahora el cliente recibe todo. En V2 podría suscribirse selectivamente.

```json
{ "type": "subscribe", "payload": { "topics": ["alerts", "snapshots"] } }
```

### `pong`

Respuesta al ping.

## Comportamiento de backpressure

Si el cliente es lento:

- Los mensajes `snapshot` se mandan **siempre** (último gana, no se acumulan).
- Los mensajes `alert`, `pit_stop`, `track_status` **no se descartan** (son eventos críticos).
- Si la cola del cliente excede `max_queued_messages` (V1: 100), el servidor desconecta el cliente con código 1011 (server overloaded).

## Versionado

- V1: este documento.
- Cualquier breaking change → bump a `/ws/v2/live` y mantener V1 hasta que todos los clientes migren.

## Dónde lo consume el frontend

Hook `useRaceFeed` en [`frontend/src/hooks/useRaceFeed.ts`](../../frontend/src/hooks/useRaceFeed.ts).
