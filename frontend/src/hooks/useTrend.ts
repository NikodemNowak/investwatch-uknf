import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { ModuleId } from "@/api/types";

/** Findings per day for the last 14 days (`GET /api/stats/trend`), one module or all. */
export function useTrend(module: ModuleId | undefined) {
  return useQuery({
    queryKey: queryKeys.trend(module),
    queryFn: () => api((b) => b.getTrend(module)),
    refetchInterval: 60_000,
  });
}
