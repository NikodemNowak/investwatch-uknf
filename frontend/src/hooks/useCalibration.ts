import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { ModuleId } from "@/api/types";

/** Precision/recall per threshold for one module. */
export function useCalibration(module: ModuleId) {
  return useQuery({
    queryKey: queryKeys.calibration(module),
    queryFn: () => api((b) => b.getCalibration(module)),
  });
}

/** Save one module's threshold (the API replaces all three, so merge with the current ones). */
export function useSaveThreshold() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ module, value }: { module: ModuleId; value: number }) => {
      const current = await api((b) => b.getThresholds());
      return api((b) => b.putThresholds({ ...current, [module]: value }));
    },
    onSuccess: (_saved, { module }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.calibration(module) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.findings });
    },
  });
}
