import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { Status } from "@/api/types";
import { reviewPollInterval } from "@/lib/polling";

/** One finding with its post and trace. */
export function useFinding(id: string) {
  return useQuery({
    queryKey: queryKeys.finding(id),
    queryFn: () => api((b) => b.getFinding(id)),
    refetchInterval: (query) => reviewPollInterval(query.state),
  });
}

/** Set the analyst status; refreshes the lists and the nav count. */
export function useSetStatus(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (status: Status) => api((b) => b.updateFindingStatus(id, status)),
    onSuccess: (finding) => {
      queryClient.setQueryData(queryKeys.finding(id), finding);
      void queryClient.invalidateQueries({ queryKey: queryKeys.findings });
    },
  });
}
