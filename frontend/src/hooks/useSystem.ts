import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";

/** Service health and the next scheduled run (the server caches it for a few seconds). */
export function useSystem() {
  return useQuery({
    queryKey: queryKeys.system,
    queryFn: () => api((b) => b.getSystem()),
    refetchInterval: 30_000,
  });
}
