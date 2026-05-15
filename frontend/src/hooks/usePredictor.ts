import { useState } from "react";
import { setPredictor, ApiError } from "../api/client";
import type { PredictorName } from "../api/types";

export function usePredictor() {
  const [pendingTarget, setPendingTarget] = useState<PredictorName | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function switchPredictor(predictor: PredictorName): Promise<void> {
    if (pendingTarget !== null) return;
    setError(null);
    setPendingTarget(predictor);
    try {
      await setPredictor(predictor);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setError("XGBoost model not available. Staying on scipy.");
      } else {
        setError("Could not switch predictor.");
      }
    } finally {
      setPendingTarget(null);
    }
  }

  return { pendingTarget, error, switchPredictor };
}
