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
- [x] `useRaceFeed` consume mensajes reales del backend.
- [x] Tabla se actualiza con `snapshot` y `lap_update`.
- [x] Component `<AlertFeed>` muestra últimas 20 alertas con flash al recibir.

### Día 7 — Toggle predictor + UX
- [x] Component `<PredictorToggle>` (radio scipy/xgb) que llama `POST /api/v1/config/predictor`.
- [x] Indicador visual del predictor activo en la tabla.
- [x] Loading states + error states limpios.

### Día 8 — Pulido visual mínimo
- [x] Tailwind: paleta consistente (3 colores + grises).
- [x] Score: barra de color verde→rojo según score 0..1.
- [x] Animación sutil cuando llega alerta (CSS only, no JS).
- [x] Responsive: tabla scroll horizontal en móvil.

### Día 9 — Backtest view + tests
- [x] Component `<BacktestView>` que muestra resultados de `/api/v1/backtest/{session}`.
  - Tabla de TP, FP, FN.
  - Comparación scipy vs xgboost lado a lado.
  - Added `src/hooks/useBacktest.ts` (TanStack Query, disabled when no session, predictor in key).
  - Added `src/components/BacktestView.tsx` — two-panel grid, per-predictor metrics + TP/FP/FN tables,
    graceful empty/loading/unavailable states. One failing predictor does not hide the other.
  - Integrated into `App.tsx` below the Degradation + TrackMap row.
  - 15 Vitest tests in `src/components/BacktestView.test.tsx` — all passing.
  - `pnpm lint` ✅ · `pnpm typecheck` ✅ · `pnpm test` 58/58 ✅ · `pnpm build` ✅.
- [x] Vitest tests para componentes (snapshot básico).
- [x] 1 happy-path Playwright: cargar app, seleccionar sesión, play, ver alertas.
      Added `@playwright/test 1.60.0`, `playwright.config.ts` (Firefox, webServer: pnpm dev,
      mocked API), and `tests/e2e/demo.spec.ts` (1 test: branding → session pick → table/alert/chart
      panels present). `.playwright-libs/` holds extracted `libasound.so.2` for WSL2 environments
      without system ALSA; gitignored, populated by `pnpm test:e2e:setup`.
      `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 playwright test` → 1 passed.

### Día 10 — Demo polish
- [x] Copy y mensajes de error en español o inglés (consistente).
      English throughout. Removed stale dev-day comments. All empty states, error messages, and
      hint copy are consistent English. Actionable messages tell user what to do next (select a
      session, start a replay, run make fit-degradation, etc.).
- [x] Página vacía (no hay datos) con mensaje útil.
      Added `no-session-hint` banner in App.tsx when no session selected.
      Improved empty states: AlertPanel, RaceTable, DegradationChart, SessionPicker.
      TrackMapPanel and ReplayControls footer copy cleaned up.
- [x] Branding mínimo (logo emoji + nombre).
      Added 🏎 emoji before PITWALL in TopBar. Live lap counter (currentLap / totalLaps)
      now uses real data from snapshot and session list when available.
- [x] Build prod (`pnpm build`) funciona.

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
