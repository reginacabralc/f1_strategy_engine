// Generated types live in ./openapi.ts — run `pnpm generate:api` to refresh.
// This file is the single import target for the rest of the codebase:
// named re-exports so components don't need to know the openapi.ts structure.
//
// Rule: do NOT hand-write types here. If a type is missing, update
// docs/interfaces/openapi_v1.yaml and regenerate.

export type { components, paths, operations } from "./openapi";

import type { components } from "./openapi";

// --- Scalar enums ---

export type Compound = components["schemas"]["Compound"];
export type PredictorName = components["schemas"]["PredictorName"];
export type TrackStatus = components["schemas"]["TrackStatus"];
export type AlertType = components["schemas"]["AlertType"];

// --- Response/request bodies ---

export type Health = components["schemas"]["Health"];
export type Problem = components["schemas"]["Problem"];
export type SessionSummary = components["schemas"]["SessionSummary"];
export type DriverState = components["schemas"]["DriverState"];
export type RaceSnapshot = components["schemas"]["RaceSnapshot"];
export type DegradationCurve = components["schemas"]["DegradationCurve"];
export type ReplayStartRequest = components["schemas"]["ReplayStartRequest"];
export type ReplayRun = components["schemas"]["ReplayRun"];
export type ReplayStopResponse = components["schemas"]["ReplayStopResponse"];
export type SetPredictorRequest = components["schemas"]["SetPredictorRequest"];
export type SetPredictorResponse = components["schemas"]["SetPredictorResponse"];
export type UndercutMatch = components["schemas"]["UndercutMatch"];
export type BacktestResult = components["schemas"]["BacktestResult"];
