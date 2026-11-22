import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { FindingQuery } from "@/api/types";

/** Largest page the API serves; the list is triaged client-side within it. */
const PAGE_SIZE = 500;

/** Findings matching the server-side filters (date, source, status), highest score first. */
export function useFindingList(filters: FindingQuery) {
  const query: FindingQuery = { ...filters, sort: "score", page_size: PAGE_SIZE };
  return useQuery({
    queryKey: queryKeys.findingList(query),
    queryFn: () => api((b) => b.listFindings(query)),
    placeholderData: keepPreviousData,
  });
}
