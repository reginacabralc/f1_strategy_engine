import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SessionSummary } from "../api/types";

export function useSessions() {
  return useQuery<SessionSummary[]>({
    queryKey: ["sessions"],
    queryFn: () => api.get<SessionSummary[]>("/api/v1/sessions"),
    staleTime: 60_000,
  });
}
