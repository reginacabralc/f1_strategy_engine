import { useQuery } from "@tanstack/react-query";
import { getBacktestResult } from "../api/client";
import type { BacktestResult, PredictorName } from "../api/types";

export function useBacktest(sessionId?: string | null, predictor?: PredictorName) {
  return useQuery<BacktestResult>({
    queryKey: ["backtest", sessionId ?? null, predictor ?? null],
    queryFn: () => getBacktestResult(sessionId!, predictor),
    enabled: !!sessionId,
    retry: false,
    staleTime: 5 * 60_000,
  });
}
