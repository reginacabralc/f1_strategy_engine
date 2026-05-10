# Quanta 08 — Arquitectura async (asyncio.Queue como bus interno)

## Concepto

Un sistema event-driven necesita un mecanismo para que un productor (replay) emita eventos que múltiples consumidores reciban. Las opciones tradicionales: Kafka, Redis Streams, RabbitMQ, message queues.

PitWall usa **`asyncio.Queue`** in-process. Esta quanta explica por qué y cómo.

## Por qué importa para el producto

Decidir bien la capa de mensajería al inicio evita reescribir el motor más adelante. Pero también evita complejidad innecesaria. Un broker pesado en V1 nos cuesta días de trabajo y nada de valor.

## Decisión

Ver [ADR 0007](../adr/0007-asyncio-sin-broker.md). Resumen:

- 1 productor (`ReplayFeed`).
- 1 consumidor principal (`UndercutEngine`).
- N consumidores de WebSocket (broadcaster).
- Volumen: < 1000 eventos/min en peor caso.
- Todo en mismo proceso → `asyncio.Queue` cubre.

## Diseño

```python
# core/topics.py
events_topic = asyncio.Queue(maxsize=10_000)
alerts_topic = asyncio.Queue(maxsize=1_000)
snapshot_topic = asyncio.Queue(maxsize=1_000)

# Replay produces
async def replay_loop():
    async for event in replay_feed.events():
        await events_topic.put(event)

# Engine consumes events, produces alerts/snapshots
async def engine_loop():
    while True:
        event = await events_topic.get()
        state.apply(event)
        if event.type == "lap_complete":
            for pair in compute_relevant_pairs(state):
                decision = evaluate_undercut(state, pair, predictor)
                if decision.should_alert:
                    await alerts_topic.put(decision)
            await snapshot_topic.put(state.snapshot())

# WS broadcaster fan-out
async def ws_broadcast_loop():
    while True:
        msg = await alerts_topic.get()  # o select sobre múltiples queues
        for client in connected_clients:
            await client.send_json(msg.to_dict())
```

## Garantías

| Garantía | ¿La tenemos? | Notas |
|----------|-----|-------|
| At-least-once delivery | Sí | Dentro del proceso. Si crash, perdemos in-flight. |
| Orden | Sí | `asyncio.Queue` es FIFO. |
| Backpressure | Sí | `maxsize` bloquea al productor si está lleno. |
| Persistence | No | Los eventos no se persisten al queue (sí los persistimos a DB en otro hilo). |
| Multi-process | No | Un solo proceso backend en V1. |
| Multi-host | No | Igual. |

## Patrones de error

### Cliente WS lento

Si un cliente WebSocket es lento, no queremos bloquear al broadcaster. Solución V1:

```python
async def send_to_client(client, msg):
    try:
        await asyncio.wait_for(client.send_json(msg), timeout=1.0)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await disconnect(client)
```

### Queue lleno

Si el productor produce más rápido de lo que el motor consume, `events_topic` se llena. Opciones:

1. Bloquear al productor (`await put`).
2. Drop policy: descartar eventos viejos.

V1 usa **opción 1** porque el productor es replay: si bloqueamos, el factor de velocidad se ralentiza, pero ningún evento se pierde.

### Crash del motor

Si el motor crashea, los eventos en cola se pierden. Strategy:

- En V1: aceptable. Replay es determinista, lo reiniciamos.
- En V2: posible reemplazar `asyncio.Queue` con Redis Streams para persistencia.

## Migración a V2 (cuando importe)

Si crece a múltiples instancias del backend:

```python
# core/topics.py — interfaz idéntica
class EventBus(Protocol):
    async def publish(self, topic: str, msg: dict) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[dict]: ...

# V1
class InMemoryBus: ...      # asyncio.Queue por dentro

# V2
class RedisStreamBus: ...   # Redis Streams por dentro
```

El cambio es localizado a `core/topics.py`. El motor no se toca.

## Pruebas

Tests del motor son síncronos:

```python
async def test_motor_emits_alert_on_undercut_scenario():
    bus = InMemoryBus()
    motor = UndercutEngine(bus, predictor=mock_predictor)
    asyncio.create_task(motor.run())

    await bus.publish("events", lap_complete_event(...))
    await bus.publish("events", lap_complete_event(...))

    alert = await asyncio.wait_for(bus.subscribe("alerts").__anext__(), timeout=1)
    assert alert.type == "UNDERCUT_VIABLE"
```

## Implementación

- Topics: [`backend/src/pitwall/core/topics.py`](../../backend/src/pitwall/core/topics.py)
- Engine loop: [`backend/src/pitwall/engine/__init__.py`](../../backend/src/pitwall/engine/__init__.py)
- WS broadcaster: [`backend/src/pitwall/api/ws.py`](../../backend/src/pitwall/api/ws.py)

## Quanta relacionadas

- [05 — Replay engine](05-replay-engine.md)
