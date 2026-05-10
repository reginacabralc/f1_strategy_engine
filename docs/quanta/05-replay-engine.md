# Quanta 05 — Replay Engine

## Concepto

El **Replay Engine** es el componente que reproduce una carrera histórica como si fuera en vivo. Lee la DB con datos de FastF1 ya ingeridos y emite eventos al motor al ritmo de un factor de velocidad configurable (1× = tiempo real, 60× = una hora de carrera en un minuto).

## Por qué importa para el producto

En V1 **no usamos OpenF1 en vivo** ([ADR 0002](../adr/0002-replay-first.md)). El replay es nuestra única fuente de eventos. Es lo que el motor consume, lo que el dashboard muestra, lo que el backtest usa.

## Diseño

```text
ReplayFeed(RaceFeed) implements:
  async def start(session_id: str, speed_factor: float) -> None
  async def stop() -> None
  async def events() -> AsyncIterator[Event]
```

### Flujo

```
1. Lee de DB: laps + pit_stops + track_status_events ordenados por timestamp.
2. Calcula T0 = primer evento de la sesión (race start).
3. Para cada evento:
     dt_real = (event.ts - T0).total_seconds()
     dt_simulated = dt_real / speed_factor
     await asyncio.sleep(dt_simulated - elapsed_simulated_so_far)
     yield event  # publica al asyncio.Queue
```

### Tipos de eventos emitidos

| Tipo | Cuándo |
|------|--------|
| `lap_complete` | Cuando un piloto cruza línea de meta |
| `pit_in` | Cuando un piloto entra a pit lane |
| `pit_out` | Cuando sale (con compound y tyre_age=0) |
| `track_status_change` | Inicio/fin de SC, VSC, RED |
| `weather_update` | Cambio de track_temp, condiciones |
| `session_start`, `session_end` | Inicio/fin de la sesión |

Schema completo: [`docs/interfaces/replay_event_format.md`](../interfaces/replay_event_format.md).

## Por qué procesar por orden de evento, no por wall-clock

Tentación: hacer un loop con `time.time()` y emitir eventos cuyo timestamp ya ha pasado. **Mala idea** porque:

- A factor 1000×, dormir microsegundos es ruido.
- Si el motor es lento procesando, el wall-clock se desincroniza.
- El test queda no-determinista.

Solución V1: **iteramos por evento siguiente, no por reloj**. Para cada evento, dormimos `(this_event.ts - prev_event.ts) / speed_factor` segundos antes de emitirlo. Mantiene determinismo.

## Ejemplo numérico

Mónaco 2024, factor 60×:

```
T0 = 14:03:22 UTC
Evento 1: lap_complete VER, ts=14:04:35, dt_real=73s, dt_simulated=1.22s
Evento 2: lap_complete LEC, ts=14:04:36, dt_real=74s, dt_simulated=1.23s
Evento 3: pit_in HUL, ts=14:25:10, dt_real=1308s, dt_simulated=21.8s
...
```

A factor 60×, la carrera de 90 minutos termina en 1.5 minutos.

## Modos de operación

| Modo | Cuándo |
|------|--------|
| `factor=1` | Demo en vivo, replay tiempo real |
| `factor=30..60` | Demo acelerada |
| `factor=1000` | CI / tests automáticos (carrera completa en segundos) |

## Riesgos / variantes

- **Drift acumulado**: no usamos `time.sleep` en bucle largo; en cambio computamos sleep relativo al evento siguiente.
- **Resolución de timestamps**: FastF1 da ms. Si dos eventos tienen el mismo `ts`, los emitimos en orden de recepción de DB (`lap_number ASC`).
- **Datos faltantes**: si un piloto no tiene vuelta válida en una ronda, `lap_complete` simplemente no se emite. El motor lo detecta como `data_stale_since`.

## Cómo correrlo

```bash
# CLI directa
python scripts/replay_cli.py --session monaco_2024_R --speed 30

# Via API
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "monaco_2024_R", "speed_factor": 30}'

# Stop
curl -X POST http://localhost:8000/api/v1/replay/stop
```

## Implementación

- Interfaz: [`backend/src/pitwall/feeds/base.py::RaceFeed`](../../backend/src/pitwall/feeds/base.py)
- Implementación: [`backend/src/pitwall/feeds/replay.py`](../../backend/src/pitwall/feeds/replay.py)
- Stub OpenF1: [`backend/src/pitwall/feeds/openf1.py`](../../backend/src/pitwall/feeds/openf1.py)

## Quanta relacionadas

- [08 — Arquitectura async](08-arquitectura-async.md)
