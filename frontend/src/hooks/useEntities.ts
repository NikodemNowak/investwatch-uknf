import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { EntityQuery } from "@/api/types";

/** Result aggregator: entities over the filtered findings. */
export function useEntities(query: EntityQuery) {
  return useQuery({
    queryKey: queryKeys.entities(query),
    queryFn: () => api((b) => b.listEntities(query)),
    placeholderData: keepPreviousData,
  });
}

/** One entity with its findings (drill-down). */
export function useEntity(key: string) {
  return useQuery({
    queryKey: queryKeys.entity(key),
    queryFn: () => api((b) => b.getEntity(key)),
  });
}
