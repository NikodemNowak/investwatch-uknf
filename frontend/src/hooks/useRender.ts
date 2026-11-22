import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";

/** Layout snapshot of a post (page heights per viewport); null when not rendered. */
export function useRender(postId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.render(postId ?? ""),
    queryFn: () => api((b) => b.getRender(postId ?? "")),
    enabled: Boolean(postId),
    staleTime: Infinity,
  });
}
