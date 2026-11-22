import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { ImportFormat, SourceCreate, Submission } from "@/api/types";

/** Monitored sources. */
export function useSources() {
  return useQuery({
    queryKey: queryKeys.sources,
    queryFn: () => api((b) => b.listSources()),
    refetchInterval: 30_000,
  });
}

/** Data connectors with their status (`GET /api/connectors`). */
export function useConnectors() {
  return useQuery({
    queryKey: queryKeys.connectors,
    queryFn: () => api((b) => b.listConnectors()),
    staleTime: 60_000,
  });
}

/** Run a source now; a 409 means the connector is not ready (shown as a message). */
export function useRunSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api((b) => b.runSource(id)),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}

/** Import a file of collected material (`POST /api/imports`). */
export function useImportFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, format }: { file: File; format: ImportFormat }) =>
      api((b) => b.importFile(file, format)),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

/** Record what an analyst saw (`POST /api/submissions`). */
export function useSubmitMaterial() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (submission: Submission) => api((b) => b.submitMaterial(submission)),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

/** Add a source. */
export function useCreateSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SourceCreate) => api((b) => b.createSource(body)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.sources }),
  });
}
