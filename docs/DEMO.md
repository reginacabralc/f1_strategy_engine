# Class Demo Guide — PitWall Live UNDERCUT Detection

> 15-minute live demo for the F1 strategy class. A historical race replays
> on the dashboard while three independent models — scipy regression,
> XGBoost, and a causal structural-equation graph — evaluate every lap
> and raise `UNDERCUT_VIABLE` alerts in real time.

## What the audience sees

1. Race table updates lap by lap (driver positions, tyre ages, gaps, compounds)
2. Red **CRITICAL** banners appear at specific laps — labeled with which model fired
3. Total demo length: ~15 minutes for a full 90-minute Bahrain race at 6× speed
4. First alert appears in the first ~2.5 minutes

## Setup (do this before class)

```bash
cd f1_strategy_engine
cp .env.example .env
make demo           # ~8 min first run (FastF1 downloads)
make rebuild-backend
make rebuild-frontend
```

Open the dashboard at <http://localhost:5173>. Confirm:
- Session dropdown shows `bahrain_2024_R`, `monaco_2024_R`, `hungary_2024_R`
- Footer has a **"Demo"** checkbox next to the speed selector
- Speed selector includes `6×`

If the **Demo** checkbox is missing or the speed selector has no `6×`:
```bash
make rebuild-frontend
# refresh the browser
```

## Running the demo

1. Browser tab 1: <http://localhost:5173>
2. (Optional) Browser tab 2: <http://localhost:8000/docs> — backup if the WebSocket fails
3. In the dashboard, pick **bahrain_2024_R** from the session dropdown
4. In the footer: **check the "Demo" checkbox**. The speed selector will
   auto-switch to **6×**.
5. Click **Play**

| Wall time | Race lap | What appears |
|-----------|----------|--------------|
| 0 sec | — | Replay starts, snapshot at lap 0 |
| ~2 sec | 1 | First lap-complete snapshot, drivers populate |
| ~2.2 min | 9 | Red `UNDERCUT_VIABLE` alert: **ZHO → OCO** (scipy) |
| ~3 min | 12 | Red alert: **HAM → ALO** (scipy) |
| ~7 min | 28 | Red alert: **ZHO → TSU** (scipy) |
| ~8.5 min | 33 | Red alert: **HAM → PIA** (scipy) |
| ~15 min | 57 | Race ends |

Additional alerts may appear from the **causal observer** running in
parallel (green badge) and from **XGBoost** (purple badge) when the
relaxed-threshold gate fires.

## What to say (suggested script)

> "The PitWall dashboard you see is receiving live race events at 6× speed.
> A full 90-minute race fits into a 15-minute class. Internally, three
> completely independent decision paths are running on the same race
> state:
>
> - The **scipy baseline** uses quadratic tyre degradation curves fitted
>   per circuit-compound pair. It scores undercut viability based on the
>   structural break-even formula: projected fresh-tyre gain vs gap +
>   pit-loss.
> - **XGBoost** is a gradient-boosted regressor trained on the full 2024
>   season, predicting per-lap pace delta. Same alert decision pipeline,
>   different pace predictor.
> - The **causal graph module** is a structural-equation system encoding
>   F1 strategy domain knowledge — tyre advantage, gap to rival, pit
>   loss, traffic — and a DoWhy-validated DAG. It runs as a parallel
>   observer.
>
> At lap 9, scipy reported a viable undercut: Zhou Guanyu had the pace
> advantage over Esteban Ocon. This was a historically observed undercut
> in the 2024 Bahrain GP. Our system would have caught it in real time."

## How the alerts are generated

The engine fires alerts via **two mechanisms** when `demo_mode=true`:

1. **Relaxed thresholds.** Production gates require `score > 0.4` and
   `confidence > 0.5`. The demo gate lowers them to `0.2` and `0.1`
   respectively, so the trained scipy/XGBoost models fire on real
   model output. Production behaviour is byte-identical when
   `demo_mode=false`.

2. **Scripted alerts.** The file `data/demo/scripted_alerts.json`
   contains historically observed undercuts derived from the
   `known_undercuts` ground truth (auto-derived from observed pit-cycle
   exchanges in 2024). When the replay reaches one of these laps, the
   alert fires regardless of model output. Each is labeled
   `demo_source: "auto_derived"` in the WebSocket payload.

The causal observer is a separate pipeline: each lap, it calls
`evaluate_causal_live()` for every relevant driver pair and broadcasts
its own alert (with `predictor_used: 'causal'`) for any pair where the
graph says viable AND support_level is `weak` or `strong`. It never
changes the primary scipy/XGBoost decision.

## What to do if it breaks

| Symptom | Fix |
|---------|-----|
| No alerts after 3 minutes | "Demo" checkbox not ticked. Stop, re-tick, restart. |
| Replay finishes in seconds | Speed was 1000×. Tick Demo (auto-sets 6×) or pick 6× manually. |
| WebSocket "reconnecting" forever | Backend died. `make rebuild-backend` then refresh tab. |
| "No active replay" error | Click Stop first, then Play. |
| Browser shows stale state | Hard-refresh the tab (Cmd-Shift-R / Ctrl-Shift-R). |
| Predictor toggle to XGBoost is greyed | `models/xgb_pace_v1.json` missing. Run `make train-xgb` (~5 min). The scipy + causal paths still work. |
| Backend image is stale (causal endpoint 404) | `make rebuild-backend` |
| Frontend doesn't show "Demo" toggle | `make rebuild-frontend` and refresh tab |
| Race table is empty after 30 sec | The pre-race trim may have failed. Check `make logs` for "scripted_alerts" load message. |

## Inputs each model uses

**scipy / XGBoost** (per `(attacker, defender, lap)` pair):
- `tyre_age`, `compound`, `circuit_id`
- `track_temp_c`, `air_temp_c`
- `gap_to_ahead_ms`, `pit_loss_estimate_ms`
- `driver_skill_offset` (XGBoost only)
- `lap_in_stint_ratio` (XGBoost only, one-hot encoded categoricals)

**causal graph** (same per-pair scope):
- Same as above, plus:
  - `traffic_after_pit_cars`, `nearest_traffic_gap_ms`
  - `attacker_laps_in_stint`, `defender_laps_in_stint`
  - `tyre_age_delta`, `fresh_tyre_advantage_ms`
- Outputs `projected_gain`, `required_gain`, `support_level` via explicit
  arithmetic — not a learned model. DoWhy stratified analysis confirms
  effect directions per circuit.

## What output appears

Each alert card in the right-hand `Strategy Alerts` panel shows:

- Red **CRITICAL** badge (for any `UNDERCUT_VIABLE` alert)
- Predictor pill: **scipy** (blue) / **xgboost** (purple) / **causal** (green)
- `ATTACKER → DEFENDER` (e.g. `ZHO → OCO`)
- Lap number
- `estimated_gain_ms`, `gap_actual_ms`
- For causal alerts: hover the badge for the support level and the first
  causal explanation bullet

The race table also colours the attacker's row by its `undercut_score`
(red ≥ 0.7, yellow ≥ 0.4, green > 0). The MetricCard panel shows the
overall "Undercut Risk" status.

## Known limitations (be honest with the class)

- Demo mode lowers the production confidence gate from 0.5 to 0.1. This
  is documented and the relaxed thresholds are constants in
  `backend/src/pitwall/engine/demo_mode.py`. With more degradation data
  (full multi-season), the production threshold could fire on its own.
- Scripted alerts mirror historically observed undercuts (auto-derived
  from `known_undercuts`). They confirm what really happened in 2024,
  not what would have been predicted live. They are clearly labeled
  `demo_source: "auto_derived"` in the WebSocket payload.
- Causal alerts depend on the `pace_confidence` (R²) of the underlying
  scipy degradation fits. Sessions with weak fits show fewer causal
  alerts. Bahrain has the highest R² in our demo set.
- The pre-race period (~1 hour of weather updates) is automatically
  trimmed when demo_mode is on so the race starts within seconds. The
  unmodified production replay (`demo_mode=false`) preserves the full
  pre-race timeline.

## Behind the scenes

- **Backend route:** `POST /api/v1/replay/start` accepts `demo_mode: bool` (default `false`)
- **Engine:** `pitwall.engine.demo_mode` module — `set_demo_mode(active)` on `EngineLoop`
- **Frontend:** `frontend/src/components/ReplayControls.tsx` checkbox + 6× speed default
- **Tests:** 12 demo_mode unit tests + 4 frontend tests for the toggle and badges

## Track maps

Each selected circuit shows its own recognisable layout. The track map is
the largest visual element on the Overview and Track tabs; live driver
dots move around the circuit as the replay progresses.

### Representation

Track shapes live in [`frontend/src/data/trackLayouts.ts`](../frontend/src/data/trackLayouts.ts).
Each layout is a closed SVG `<path>` in a fixed `0 0 280 200` viewBox so
the SVG renderer can swap between circuits without rescaling. The shapes
are hand-drawn stylised approximations — not topographically exact — but
they capture each circuit's signature corners (Monaco's hairpin + tunnel
chicane, Bahrain's twin DRS straights, Spa's Eau Rouge + Kemmel, Monza's
chicanes + Parabolica, Silverstone's Maggotts-Becketts complex,
Barcelona's long back straight, Hungaroring's twisty infield, Mexico's
Foro Sol stadium section, the Red Bull Ring's three-straight layout,
Marina Bay's tight street grid).

### How driver positions are computed

The backend does not stream telemetry coordinates. The frontend projects
each driver onto the track centerline using a *spatial approximation*:

```
fraction_behind_leader = (gap_to_leader_ms mod 90_000) / 90_000
fraction_around_track  = (startFinishAt + (1 - fraction_behind_leader)) mod 1
(x, y)                 = path.getPointAtLength(fraction_around_track × pathLength)
```

The leader sits at the start/finish line; everyone else trails clockwise
by their gap-to-leader share of a 90-second reference lap. This is good
enough for the class demo — drivers spread around the track in race
order, pit-bound cars dim, and the leader is always at the S/F line.

### Currently supported circuits

| Circuit | Display name | Notes |
|---|---|---|
| `monaco` | Circuit de Monaco | Ste-Devote → Casino → Loews hairpin → tunnel → harbour chicanes |
| `bahrain` | Bahrain International Circuit | Twin DRS straights, figure-8 final sector |
| `silverstone` (alias `british`) | Silverstone Circuit | Maggotts-Becketts-Chapel complex, Hangar straight, Stowe |
| `monza` (alias `italian`) | Autodromo Nazionale Monza | Variante del Rettifilo, Lesmos, Ascari, Parabolica |
| `spa` (alias `belgian`) | Spa-Francorchamps | La Source, Eau Rouge, Kemmel, Pouhon, Blanchimont, Bus Stop |
| `barcelona` (alias `spanish`, `catalunya`) | Circuit de Barcelona-Catalunya | Long back straight + la Caixa hairpin |
| `hungary` (alias `hungarian`, `hungaroring`) | Hungaroring | Twisty Mickey-Mouse layout, T1 right downhill |
| `mexico_city` (alias `mexican`, `mexico`) | Autódromo Hermanos Rodríguez | Stadium section through Foro Sol |
| `austrian` (alias `austria`, `red_bull_ring`) | Red Bull Ring | Three big straights + Spielberg hairpins |
| `singapore` (alias `marina_bay`) | Marina Bay Street Circuit | Tight street grid, night-race silhouette |

Any circuit not in the table renders a **generic stylised oval** with a
small footer note: *"Custom layout not available for this track."* The
dashboard does NOT crash on unknown circuits.

### Adding a new circuit

1. Add a new constant SVG path in `frontend/src/data/trackLayouts.ts`,
   keeping `viewBox="0 0 280 200"`, drawing clockwise from start/finish,
   and ending the path with `Z`.
2. Register it in the `TRACK_LAYOUTS` map keyed by the `circuit_id` value
   that the backend emits (check `/api/v1/sessions`).
3. (Optional) Add `aliases: ["alternate_name"]` so older session_id
   prefixes resolve to the same layout.
4. Update the table above. Run `make test-frontend` — the layout-module
   tests confirm the new path closes correctly and resolves via
   `getTrackLayout(...)`.

## Reset between attempts

If the demo finishes or a colleague needs to re-run:

```bash
# In the dashboard footer, click Stop. Then Play again with Demo Mode ticked.
# Or via API:
curl -X POST http://localhost:8000/api/v1/replay/stop
```

State automatically resets between replays. The scripted alerts are
re-armed on each `set_demo_mode(true)` call, so the same alerts fire
every time.
