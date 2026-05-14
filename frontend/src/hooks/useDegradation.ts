import { useQuery } from "@tanstack/react-query";
import { getDegradation } from "../api/client";
import type { Compound, DegradationCurve } from "../api/types";

export function useDegradation(circuit: string, compound: Compound) {
  return useQuery<DegradationCurve>({
    queryKey: ["degradation", circuit, compound],
    queryFn: () => getDegradation({ circuit, compound }),
    staleTime: 10 * 60_000,
    retry: false,
    enabled: circuit.length > 0,
  });
}
