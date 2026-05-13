# Stream C Dashboard Wireframe

Day 1 sketch for the MVP React dashboard. This replaces the ephemeral
whiteboard/FigJam artifact with a repo-local note so Stream B/C can keep the
same mental model.

```text
+----------------------------------------------------------------------------+
| PitWall - F1 Strategy Engine                         [Session dropdown v]   |
+----------------------------------------------------------------------------+
| Race Order                                           Predictor: scipy/xgb    |
| +----+--------+----------+--------+----------+----------+----------------+  |
| | Pos| Driver | Team     | Gap    | Compound | Tyre Age | Score          |  |
| +----+--------+----------+--------+----------+----------+----------------+  |
| | 1  | VER    | RBR      | -      | M        | 12       | ##.. 15%       |  |
| | 2  | LEC    | Ferrari  | +3.2s  | M        | 14       | #### 72%       |  |
| +----+--------+----------+--------+----------+----------+----------------+  |
|                                                                            |
| Degradation                                     Alerts                     |
| +------------------------------------------+    +-----------------------+  |
| | scatter actual lap times + fitted curve  |    | latest undercut calls |  |
| | x: tyre_age, y: lap_time_ms              |    | max 20, newest first  |  |
| +------------------------------------------+    +-----------------------+  |
|                                                                            |
| Backtest summary                                                           |
| +------------------------------------------------------------------------+ |
| | scipy vs xgboost: TP / FP / FN, precision, recall, notes              | |
| +------------------------------------------------------------------------+ |
+----------------------------------------------------------------------------+
```

## Agreed Contracts

- Sessions: `GET /api/v1/sessions` returns `SessionSummary[]` and powers the
  header dropdown.
- Live race state: initial and reconnect state comes from WebSocket `snapshot`;
  REST `GET /api/v1/sessions/{session_id}/snapshot` is available for an active
  replay.
- Live updates: WebSocket messages follow
  [`docs/interfaces/websocket_messages.md`](interfaces/websocket_messages.md).
- Predictor toggle: `POST /api/v1/config/predictor` accepts `scipy` or
  `xgboost`.

The Day 2 skeleton intentionally renders the header, session dropdown, and
mock race table first. Degradation, alerts, predictor toggle, and backtest
panels are the planned Day 4+ surfaces.
