import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";

/** "Pod maską" of a finding; `enabled` defers the request. */
export function useFindingTrace(id: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.findingTrace(id),
    queryFn: () => api((b) => b.getFindingTrace(id)),
    enabled,
    staleTime: 60_000,
  });
}
