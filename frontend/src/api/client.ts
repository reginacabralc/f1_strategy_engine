// Base URL is intentionally empty — the Vite dev proxy forwards /api/* and
// /health/* to the backend. In production, nginx does the same routing.
// Never hardcode a host here.

import type {
  BacktestResult,
  CausalPredictionOut,
  Compound,
  DegradationCurve,
  PredictorName,
  RaceSnapshot,
  ReplayRun,
  ReplayStopResponse,
  SessionSummary,
  SetPredictorResponse,
} from "./types";

// ─── Error ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly statusText: string,
    readonly path: string,
  ) {
    super(`API ${status}: ${statusText} — ${path}`);
    this.name = "ApiError";
  }
}

// ─── Core fetch ──────────────────────────────────────────────────────────────

function buildUrl(
  path: string,
  params?: Record<string, string | undefined>,
): string {
  const defined = Object.fromEntries(
    Object.entries(params ?? {}).filter(([, v]) => v !== undefined),
  ) as Record<string, string>;
  if (Object.keys(defined).length === 0) return path;
  return `${path}?${new URLSearchParams(defined).toString()}`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText, path);
  }
  return res.json() as Promise<T>;
}

// ─── Generic helpers (backward compat for useSessions etc.) ──────────────────

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
};

// ─── Typed endpoint helpers ───────────────────────────────────────────────────

/** GET /api/v1/sessions */
export function getSessions(): Promise<SessionSummary[]> {
  return apiFetch<SessionSummary[]>("/api/v1/sessions");
}

/** GET /api/v1/sessions/{session_id}/snapshot */
export function getSessionSnapshot(sessionId: string): Promise<RaceSnapshot> {
  return apiFetch<RaceSnapshot>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/snapshot`,
  );
}

/** GET /api/v1/degradation?circuit=&compound= */
export function getDegradation(params: {
  circuit: string;
  compound: Compound;
}): Promise<DegradationCurve> {
  return apiFetch<DegradationCurve>(
    buildUrl("/api/v1/degradation", {
      circuit: params.circuit,
      compound: params.compound,
    }),
  );
}

/** POST /api/v1/replay/start */
export function startReplay(
  sessionId: string,
  speedFactor?: number,
  demoMode?: boolean,
): Promise<ReplayRun> {
  return apiFetch<ReplayRun>("/api/v1/replay/start", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      ...(speedFactor !== undefined ? { speed_factor: speedFactor } : {}),
      ...(demoMode !== undefined ? { demo_mode: demoMode } : {}),
    }),
  });
}

/** POST /api/v1/replay/stop */
export function stopReplay(): Promise<ReplayStopResponse> {
  return apiFetch<ReplayStopResponse>("/api/v1/replay/stop", {
    method: "POST",
  });
}

/** POST /api/v1/config/predictor */
export function setPredictor(
  predictor: PredictorName,
): Promise<SetPredictorResponse> {
  return apiFetch<SetPredictorResponse>("/api/v1/config/predictor", {
    method: "POST",
    body: JSON.stringify({ predictor }),
  });
}

/** GET /api/v1/backtest/{session_id} */
export function getBacktestResult(
  sessionId: string,
  predictor?: PredictorName,
): Promise<BacktestResult> {
  return apiFetch<BacktestResult>(
    buildUrl(`/api/v1/backtest/${encodeURIComponent(sessionId)}`, {
      predictor,
    }),
  );
}

/** GET /api/v1/causal/prediction
 *
 * Returns the causal structural-equation viability prediction for one
 * driver pair at one lap. Read-only — does not alter live engine state.
 *
 * All parameters are optional; the backend applies defaults (Bahrain lap 30,
 * NOR vs VER, MEDIUM age 15 vs HARD age 25, gap 5000 ms, pit_loss 21000 ms).
 */
export function getCausalPrediction(params?: {
  session_id?: string;
  circuit_id?: string;
  lap_number?: number;
  total_laps?: number;
  attacker?: string;
  attacker_compound?: string;
  attacker_tyre_age?: number;
  defender?: string;
  defender_compound?: string;
  defender_tyre_age?: number;
  gap_ms?: number;
  pit_loss_ms?: number;
  track_status?: string;
  rainfall?: boolean;
}): Promise<CausalPredictionOut> {
  const stringParams: Record<string, string | undefined> = {};
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) stringParams[k] = String(v);
    }
  }
  return apiFetch<CausalPredictionOut>(
    buildUrl("/api/v1/causal/prediction", stringParams),
  );
}
