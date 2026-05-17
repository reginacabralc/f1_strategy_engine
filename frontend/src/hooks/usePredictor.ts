import { useEffect, useRef, useState } from "react";
import { setPredictor, ApiError } from "../api/client";
import type { PredictorName } from "../api/types";

// Maximum time we keep showing the optimistic target after a successful
// /api/v1/config/predictor call, in case the next snapshot (which confirms
// active_predictor via WebSocket) is slow to arrive. After this expires, the
// hook clears pendingTarget and the UI falls back to the actual active
// predictor from the snapshot. Tuned to comfortably cover demo speed 6×
// where lap_complete events arrive every ~15 s.
const PENDING_TIMEOUT_MS = 3_000;

interface UsePredictorOptions {
  /** Current active predictor as reported by the latest WebSocket snapshot.
   *  When this matches the pendingTarget we clear pending immediately
   *  (the backend has confirmed the switch). */
  activePredictor?: PredictorName;
}

export function usePredictor(options: UsePredictorOptions = {}) {
  const { activePredictor } = options;
  const [pendingTarget, setPendingTarget] = useState<PredictorName | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function clearPending(): void {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setPendingTarget(null);
  }

  // Clear the optimistic target as soon as the next snapshot confirms the
  // switch landed. This is what removes the visible lag — without it the UI
  // would flicker back to the previous active_predictor for several seconds.
  useEffect(() => {
    if (pendingTarget !== null && activePredictor === pendingTarget) {
      clearPending();
    }
  }, [activePredictor, pendingTarget]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  async function switchPredictor(predictor: PredictorName): Promise<void> {
    if (pendingTarget !== null) return;
    setError(null);
    setPendingTarget(predictor);

    // Safety-net timeout so the UI doesn't appear stuck if the next snapshot
    // is unusually slow (paused replay, dropped connection, etc.).
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setPendingTarget(null);
      timerRef.current = null;
    }, PENDING_TIMEOUT_MS);

    try {
      await setPredictor(predictor);
      // Successful POST. Keep pendingTarget set until either:
      //   (a) the activePredictor effect above sees the snapshot confirm, or
      //   (b) the PENDING_TIMEOUT_MS safety-net fires.
      // Either way the UI no longer flickers back to the stale value.
    } catch (e) {
      // POST failed: clear pending immediately so the UI snaps back.
      clearPending();
      if (e instanceof ApiError && e.status === 409) {
        if (predictor === "xgboost") {
          setError(
            "XGBoost model not available. Train it with 'make train-xgb' first.",
          );
        } else {
          setError(`${predictor} predictor is not loaded.`);
        }
      } else {
        setError("Could not switch predictor.");
      }
    }
  }

  return { pendingTarget, error, switchPredictor };
}
