# Replay Event Format v1

> Eventos que emite `ReplayFeed` (y emitirá `OpenF1Feed` en V2). El motor consume esto vía `RaceFeed`.

## Filosofía

- **Eventos atómicos**: cada evento describe un cambio puntual, no estado completo.
- **Timestamps absolutos**: cada evento tiene `ts` (UTC ISO 8601 con ms).
- **Identificadores estables**: `driver_code` y `session_id` son strings fijos, no IDs internos.

## Tipo base

```python
@dataclass
class Event:
    type: Literal[
        "session_start", "session_end",
        "lap_complete",
        "pit_in", "pit_out",
        "track_status_change",
        "weather_update",
        "data_stale",
    ]
    session_id: str
    ts: datetime
    payload: dict  # forma depende de type
```

## Tipos de evento

### `session_start`

```json
{
  "type": "session_start",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:00:00Z",
  "payload": {
    "circuit_id": "monaco",
    "total_laps": 78,
    "drivers": ["VER", "LEC", "..."]
  }
}
```

### `session_end`

```json
{
  "type": "session_end",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T15:08:32Z",
  "payload": {
    "final_classification": [
      {"position": 1, "driver_code": "LEC", "total_laps": 78, "total_time_ms": 8423000},
      ...
    ]
  }
}
```

### `lap_complete`

El evento más común. Emitido cada vez que un piloto cruza meta.

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

### `pit_in`

```json
{
  "type": "pit_in",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:55:10Z",
  "payload": {
    "driver_code": "HAM",
    "lap_number": 24
  }
}
```

### `pit_out`

```json
{
  "type": "pit_out",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:55:32Z",
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

### `track_status_change`

```json
{
  "type": "track_status_change",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:30:15Z",
  "payload": {
    "lap_number": 12,
    "status": "SC",
    "previous_status": "GREEN"
  }
}
```

### `weather_update`

```json
{
  "type": "weather_update",
  "session_id": "monaco_2024_R",
  "ts": "2024-05-26T13:50:00Z",
  "payload": {
    "track_temp_c": 38.5,
    "air_temp_c": 24.0,
    "humidity": 0.62,
    "rainfall": false
  }
}
```

### `data_stale`

Emitido si el feed detecta que un piloto no ha enviado datos en N segundos.

```json
{
  "type": "data_stale",
  "session_id": "monaco_2024_R",
  "ts": "...",
  "payload": {
    "driver_code": "BOT",
    "stale_since_lap": 23,
    "reason": "missing | dnf | retired"
  }
}
```

## Orden de emisión

Garantizado:

- `session_start` antes de cualquier otro evento de esa sesión.
- `pit_in` antes que el `pit_out` correspondiente del mismo piloto.
- `lap_complete` en orden de `lap_number` por piloto.

NO garantizado:

- Orden global entre pilotos (dos `lap_complete` en el mismo `ts` pueden llegar en cualquier orden).

El motor debe ser tolerante a esto.

## Cómo lo consume el motor

```python
async def consume_feed(feed: RaceFeed):
    async for event in feed.events():
        state.apply(event)
        if event.type == "lap_complete":
            await maybe_emit_alerts(state)
```

El motor decide qué hacer en cada tipo. La interfaz es estable.

## Diferencias entre `ReplayFeed` y `OpenF1Feed`

| Aspecto | ReplayFeed | OpenF1Feed (V2) |
|---------|------------|-----------------|
| Determinismo | Total | Sujeto a lag y reintentos |
| Velocidad | Configurable (factor) | 1× obligatorio |
| Datos faltantes | Conocidos en advance | Se descubren on-the-fly |
| Origen `ts` | DB | API |

El motor no se entera de cuál es. Esa es la promesa.

## Versionado

V1 = este documento. Cambios en payload requieren ADR. Cambios en tipos disponibles también.
