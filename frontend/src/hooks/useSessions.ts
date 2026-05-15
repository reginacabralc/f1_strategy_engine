import { useQuery } from "@tanstack/react-query";
import { getSessions } from "../api/client";
import type { SessionSummary } from "../api/types";

export function useSessions() {
  return useQuery<SessionSummary[]>({
    queryKey: ["sessions"],
    queryFn: getSessions,
    staleTime: 60_000,
  });
}
