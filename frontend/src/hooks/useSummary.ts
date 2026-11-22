import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";

/** Headline counts (nav pill: findings waiting for a decision). */
export function useSummary() {
  return useQuery({
    queryKey: queryKeys.summary,
    queryFn: () => api((b) => b.getSummary()),
    refetchInterval: 60_000,
  });
}
