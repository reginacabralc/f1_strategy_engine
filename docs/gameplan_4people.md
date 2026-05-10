# Gameplan — 4 personas, 2 semanas

> Documento operativo del equipo. Si no estás familiarizado con el proyecto, empieza por [README](../README.md), luego [`docs/architecture.md`](architecture.md), luego este archivo.

## Asignación de streams

| Stream | Persona | Email | Responsabilidad principal | Skill ideal |
|--------|---------|-------|---------------------------|-------------|
| **A — Datos & ML** | _por asignar_ | _email_ | Ingesta FastF1, schema DB, degradación, **XGBoost**, backtest | Python+SQL, ETL, scipy/xgboost |
| **B — Motor & API** | _por asignar_ | _email_ | Replay engine, motor undercut, FastAPI, WebSocket | Python async, FastAPI, lógica algorítmica |
| **C — Frontend** | _por asignar_ | _email_ | Dashboard React, charts, hooks WS | React+TS, UX básico |
| **D — Plataforma** | _por asignar_ | _email_ | Docker, CI, tests, docs, ADRs, observabilidad | DevOps, testing, redacción técnica |

> ✏️ **Acción Día 0**: actualicen los nombres y emails arriba antes del kickoff.

## Quién toca qué archivos (evita conflicts)

| Path | Stream owner | Pueden modificar |
|------|--------------|------------------|
| `backend/src/pitwall/ingest/` | A | A (otros con review) |
| `backend/src/pitwall/degradation/` | A | A |
| `backend/src/pitwall/ml/` | A | A |
| `backend/src/pitwall/feeds/` | B | B |
| `backend/src/pitwall/engine/` | B | B (A para `PacePredictor`) |
| `backend/src/pitwall/api/` | B | B |
| `backend/src/pitwall/db/models.py` | A | A (con review de B) |
| `backend/src/pitwall/db/migrations/` | A | A |
| `frontend/` | C | C |
| `docker/`, `docker-compose.yaml` | D | D |
| `.github/workflows/` | D | D |
| `Makefile` | D | D + cualquiera para nuevos targets propios |
| `docs/interfaces/*` | **compartido** | Ver [AGENTS.md](../AGENTS.md), avisar al equipo |
| `docs/adr/` | quien escribe la decisión | revisión obligatoria del afectado |
| `docs/quanta/` | quien escribe la quanta | libre |
| `notebooks/` | A | libre, pero documentar outputs |

## Calendario

### Daily

- 15 minutos. 9:30 AM (ajustar al equipo).
- Formato:
  1. ¿Qué hice ayer?
  2. ¿Qué haré hoy?
  3. ¿Qué me bloquea?
- No hay "agenda" más allá. Si surge tema largo, breakout de 2 personas después.

### Demos

- **Día 5 (Viernes S1)**: demo interna. Replay → motor → alert llega a un cliente WS de prueba.
- **Día 10 (Viernes S2)**: demo final. End-to-end en máquina limpia, dashboard pulido, backtest comparativo, video de 3 min.

### Sync points

| Día | Qué se sincroniza |
|-----|-------------------|
| Día 1 PM | Interfaces compartidas commiteadas |
| Día 2 PM | `docker compose up` smoke test conjunto |
| Día 4 PM | `ReplayFeed` lee de DB real |
| Día 6 PM | Dashboard recibe alertas reales |
| Día 8 PM | XGBoost entrenado y cargable |
| Día 9 PM | Backtest comparativo + métricas |
| Día 10 AM | Dry-run completo de la demo final |

## Política de PRs

- **Tamaño**: ≤ 400 líneas idealmente. Excepción: schema/migraciones iniciales y modelos serializados.
- **Reviewers**: mínimo 1, idealmente del stream que consume tu output.
- **CI verde**: bloqueante.
- **Conventional Commits**: ver [AGENTS.md](../AGENTS.md).
- **Squash merge**.
- **Branch eliminado** tras merge.
- **Descripción**: qué, por qué, cómo testeé.

## Política de merge

- Squash merge desde GitHub UI.
- Commit final con título conventional commit + body con qué/por qué.
- No force push a `main`.

## Plan de contingencia

| Si... | Entonces... |
|-------|-------------|
| **A** se atrasa con la ingesta | B usa fixture sintético; cargamos solo Mónaco. |
| **A** se atrasa con XGBoost | Lo entregamos con métricas parciales o sobre 1 circuito. **No se puede recortar XGBoost del MVP** (requisito del profesor). |
| **B** se atrasa con el motor | C trabaja sobre alertas mock; entregamos motor parcial con backtest visible. |
| **C** se atrasa con el dashboard | UI minimalista con tabla HTML; demo híbrida terminal + UI. |
| **D** se atrasa con Docker | Instrucciones manuales en README; CI con un solo workflow. |

**Innegociable**: XGBoost integrado vía `PacePredictor` y comparado con baseline. Sin esto, no hay entrega aceptable.

## Cómo entregar XGBoost

Cualquiera del equipo debe poder regenerar el modelo:

```bash
make ingest-demo    # carga las 3 carreras de demo
make fit-degradation
make train-xgb
docker compose restart backend
```

El modelo se persiste en `models/xgb_pace_v1.json` (gitignored). El comando reporta MAE@k y guarda metadata en `model_registry`. Si el comando falla, el equipo debe poder bootstrappearlo en < 30 minutos.

## Comunicación

- Canal principal: _Slack/Discord/_ (decidir Día 0).
- Threads por stream para tareas largas.
- Issues en GitHub para tareas accionables.
- Decisiones grandes → ADR (no se decide solo en Slack).

## Definition of Ready (antes de empezar tarea)

- [ ] Tarea descrita con qué/por qué/criterio de done.
- [ ] Stream owner clara.
- [ ] Si depende de otra tarea, esa otra está hecha o tiene mock.
- [ ] Cabe en ≤ 1 día (si no, romperla).

## Definition of Done (antes de mergear)

Ver [AGENTS.md → Definition of Done](../AGENTS.md#definition-of-done).

## Si te bloqueas

1. Postear en el thread del stream.
2. Si en 30 min nadie responde y es urgente, ping al PM/owner.
3. Si es bloqueo grande, llevarlo al daily siguiente.
4. **Nunca** trabajes 2+ horas en algo bloqueado sin avisar.
