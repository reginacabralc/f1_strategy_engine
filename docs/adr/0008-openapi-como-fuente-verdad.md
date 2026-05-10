# ADR 0008 — OpenAPI generado por FastAPI como fuente de verdad del API

## Estado

**Aceptado** — 2026-05-09

## Contexto

Backend (Stream B) y frontend (Stream C) trabajan en paralelo. Si Stream B cambia un endpoint y no avisa, Stream C lo descubre rompiendo en runtime. Posibles soluciones:

1. Documento manual (Markdown / Notion).
2. OpenAPI escrito a mano y validado.
3. OpenAPI generado por FastAPI a partir de los modelos Pydantic.
4. tRPC / GraphQL (cambio de paradigma).

Profesor exige OpenAPI documentado.

## Decisión

**OpenAPI auto-generado por FastAPI** es la fuente de verdad. Mecanismo:

1. Endpoints definidos con FastAPI + modelos Pydantic.
2. CI exporta `openapi.json` y lo valida con `openapi-spec-validator`.
3. `openapi.json` se commitea a `docs/interfaces/openapi_v1.yaml` (convertido a YAML para legibilidad).
4. Frontend genera tipos TypeScript desde el YAML con `openapi-typescript`.
5. Si el backend cambia un endpoint, el CI falla al generar tipos del frontend (mismatch).

## Consecuencias

**Positivas:**

- Cero documento manual que se desactualice.
- Cliente TS tipado automáticamente.
- Validación bidireccional: backend valida requests con Pydantic, frontend valida con tipos generados.
- Cumple requisito del profesor con cero esfuerzo extra.

**Negativas:**

- WebSocket no es OpenAPI (es un protocolo distinto). Lo documentamos manualmente en [`docs/interfaces/websocket_messages.md`](../interfaces/websocket_messages.md).
- Cambio de schema = regenerar tipos en frontend. CI lo automatiza pero hay que avisar.

**Neutras:**

- `Field(..., description="...")` en Pydantic se vuelve documentación pública. Hay que escribirlo bien.

## Alternativas consideradas

1. **OpenAPI escrito a mano** — descartada: costo de mantener sincronizado con código real.
2. **GraphQL** — descartada: pocos endpoints, no justifica el cambio de paradigma.
3. **tRPC** — descartada: backend es Python, no Node.

## Referencias

- [FastAPI OpenAPI docs](https://fastapi.tiangolo.com/advanced/extending-openapi/)
- [openapi-typescript](https://github.com/drwpow/openapi-typescript)
- [`docs/interfaces/openapi_v1.yaml`](../interfaces/openapi_v1.yaml)
