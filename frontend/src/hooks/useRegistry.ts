import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { FirmQuery } from "@/api/types";

/** Firms of the KNF registers matching a search. */
export function useFirms(query: FirmQuery) {
  return useQuery({
    queryKey: queryKeys.firms(query),
    queryFn: () => api((b) => b.listFirms(query)),
    placeholderData: keepPreviousData,
  });
}

/** Last register sync and firm counts per register. */
export function useRegistryStatus() {
  return useQuery({
    queryKey: queryKeys.registryStatus,
    queryFn: () => api((b) => b.getRegistryStatus()),
  });
}

/** Queue a register sync, then refresh the status a little later. */
export function useSyncRegistry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api((b) => b.syncRegistry()),
    onSuccess: () => {
      setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: ["firms"] });
      }, 5000);
    },
  });
}
