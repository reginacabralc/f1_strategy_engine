# ADR 0007 — asyncio in-process, sin message broker en V1

## Estado

**Aceptado** — 2026-05-09

## Contexto

El sistema tiene flujo de eventos:

```text
ReplayFeed → Motor → WebSocket subscribers
```

Una arquitectura "correcta" de manual diría: pub/sub vía Kafka / Redis Streams / RabbitMQ. Eso permite escalar productores y consumidores independientemente.

Realidad de V1:

- Un solo proceso backend.
- Un solo productor (replay).
- Un consumidor principal (motor) + N consumidores WebSocket.
- Volumen: < 1000 eventos/minuto en peor caso (factor 60×).

## Decisión

**`asyncio.Queue`** (o `anyio` equivalente) como bus pub/sub interno. No introducimos Kafka, Redis Streams, RabbitMQ, ni Celery.

Estructura:

```python
# Topics in-process
events_topic: asyncio.Queue   # ReplayFeed -> Motor
alerts_topic: asyncio.Queue   # Motor -> WebSocket broadcaster
snapshot_topic: asyncio.Queue # Motor -> WebSocket broadcaster
```

WebSocket broadcaster mantiene set de conexiones y emite a todas (o a las suscritas a ese tipo de mensaje).

## Consecuencias

**Positivas:**

- Cero servicios adicionales en docker-compose.
- Latencia mínima (sin red, sin serialización).
- Debugging trivial (todo es Python en el mismo proceso).
- Tests son síncronos: empuja eventos al queue, consume del otro lado.

**Negativas:**

- Si crece a múltiples instancias del backend (V2+), hay que reemplazar este bus. La interfaz actual encapsula el queue, así que el cambio es localizado.
- Si el motor se cae, los eventos en el queue se pierden. En V1 esto es aceptable: replay es determinista, lo reiniciamos.

**Neutras:**

- WebSocket clients que se conecten tarde no reciben histórico — solo el snapshot actual + nuevos eventos. Esto es lo que queremos para una UI.

## Alternativas consideradas

1. **Kafka + Kafka-Python** — descartada: 2 servicios adicionales, ZooKeeper o KRaft, debugging pesado, total overkill.
2. **Redis Streams** — descartada: 1 servicio adicional, ganancia mínima sobre asyncio.Queue para V1.
3. **RabbitMQ** — descartada: misma razón.
4. **Celery con broker** — descartada: Celery es para tareas batch, no event streaming.
5. **Server-Sent Events (SSE) sobre WebSocket** — considerada para V2; en V1 WebSocket cubre.

## Referencias

- [`docs/architecture.md` § 3](../architecture.md)
- [Python asyncio docs](https://docs.python.org/3/library/asyncio.html)
