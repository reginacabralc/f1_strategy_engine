# Stream C — Frontend

> Owner: _por asignar_. Backup: Stream D.
> Cubre Etapa 8 del [plan maestro](00-master-plan.md).

## Mantra

"UI fea pero funcional > UI bonita pero rota."

## Responsabilidades

1. App React + Vite + TypeScript bootstrap.
2. Cliente API tipado (generado de OpenAPI).
3. Hook `useRaceFeed` con WebSocket reconectable.
4. Componentes: `SessionPicker`, `RaceTable`, `DegradationChart`, `AlertFeed`, `BacktestView`.
5. Toggle de predictor en UI.
6. 1 test E2E con Playwright.

## Archivos owned

```
frontend/
  package.json, vite.config.ts, tsconfig.json
  src/
    main.tsx, App.tsx
    api/client.ts, api/ws.ts, api/types.ts (generado)
    hooks/useRaceFeed.ts, useSessions.ts
    components/
      SessionPicker.tsx
      RaceTable.tsx
      DegradationChart.tsx
      AlertFeed.tsx
      PredictorToggle.tsx
      BacktestView.tsx
    styles/
  tests/
```

## Tareas

### Día 1 — Kickoff
- [x] Esquema visual del dashboard en pizarra/figjam (no necesita ser bonito).
      Repo artifact: [`docs/frontend_dashboard_wireframe.md`](../../docs/frontend_dashboard_wireframe.md).
- [x] Acordar con B: shape de OpenAPI y WebSocket.
      Confirmed against [`docs/interfaces/openapi_v1.yaml`](../../docs/interfaces/openapi_v1.yaml)
      and [`docs/interfaces/websocket_messages.md`](../../docs/interfaces/websocket_messages.md).

### Día 2 — Bootstrap (E8 esqueleto)
- [x] `frontend/package.json` con Vite + React + TS + TanStack Query + Tailwind + Recharts.
- [x] `vite.config.ts` con proxy a backend en dev.
- [x] App esqueleto: layout con header + main.
- [x] Hook `useSessions` que llama a `/api/v1/sessions`.
- [x] Component `<SessionPicker>` con dropdown.

### Día 3 — Tabla mock (E8)
- [x] Component `<RaceTable>` con datos mock estáticos en JSON.
  - Columnas: Pos, Driver, Team, Gap, Compound, Tyre Age, Score (barra de color).
- [x] Layout responsive básico (móvil OK pero no prioritario).

### Día 4 — Cliente API + WS skeleton (E8)
- [x] `api/client.ts` con `fetch` tipado.
- [x] `api/types.ts` generado de `docs/interfaces/openapi_v1.yaml` con `openapi-typescript`.
- [x] `hooks/useRaceFeed.ts` esqueleto con WebSocket reconectable (backoff exponencial).

### Día 5 — Chart de degradación (E8)
- [x] Component `<DegradationChart>` con Recharts.
  - X = tyre_age, Y = lap_time_ms.
  - Curva ajustada (línea) + puntos reales (scatter, si el backend los devuelve).
- [x] Llamar a `/api/v1/degradation?circuit=&compound=` vía `useDegradation` hook.
- [x] Conectar `<SessionPicker>` para que cambie circuito (derivado de la sesión seleccionada).

### Día 6 — Conexión real con WS (E8 + integración con B)
- [ ] `useRaceFeed` consume mensajes reales del backend.
- [ ] Tabla se actualiza con `snapshot` y `lap_update`.
- [ ] Component `<AlertFeed>` muestra últimas 20 alertas con flash al recibir.

### Día 7 — Toggle predictor + UX
- [ ] Component `<PredictorToggle>` (radio scipy/xgb) que llama `POST /api/v1/config/predictor`.
- [ ] Indicador visual del predictor activo en la tabla.
- [ ] Loading states + error states limpios.

### Día 8 — Pulido visual mínimo
- [ ] Tailwind: paleta consistente (3 colores + grises).
- [ ] Score: barra de color verde→rojo según score 0..1.
- [ ] Animación sutil cuando llega alerta (CSS only, no JS).
- [ ] Responsive: tabla scroll horizontal en móvil.

### Día 9 — Backtest view + tests
- [ ] Component `<BacktestView>` que muestra resultados de `/api/v1/backtest/{session}`.
  - Tabla de TP, FP, FN.
  - Comparación scipy vs xgboost lado a lado.
- [ ] Vitest tests para componentes (snapshot básico).
- [ ] 1 happy-path Playwright: cargar app, seleccionar sesión, play, ver alertas.

### Día 10 — Demo polish
- [ ] Copy y mensajes de error en español o inglés (consistente).
- [ ] Página vacía (no hay datos) con mensaje útil.
- [ ] Branding mínimo (logo emoji + nombre).
- [ ] Build prod (`pnpm build`) funciona.

## Definition of Done por tarea
- Tipos generados de OpenAPI, no escritos a mano.
- Tests con Vitest cuando hay lógica.
- Lighthouse no es prioritario en V1.

## Riesgos del stream
1. **Tentación de pulir visual antes de tener datos**: NO. Funcional primero.
2. **Estado disperso**: centralizar en `useRaceFeed` y prop drill — sin Redux, sin Zustand, sin Context complicado.
3. **WS reconnect bug**: testear desconectando backend en dev, debe reconectar.
4. **Mostrar undefined**: defensivo en renderers, fallback a `'-'`.

## Coordinación
- **Con B**: OpenAPI (commit a `docs/interfaces/openapi_v1.yaml`) + WS messages.
- **Con D**: Dockerfile frontend, integración con docker-compose.
- **Con A**: shape de `/api/v1/degradation` y `/api/v1/backtest/{id}`.

## Lo que NO hacemos en V1
- Replay scrubber (timeline interactiva).
- Heatmaps de degradación.
- Comparador de stints lado a lado.
- Animaciones complejas con D3.
- Dark mode toggle.
- i18n.
- PWA / offline.
- Auth.
