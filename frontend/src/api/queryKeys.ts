import type { EntityQuery, FindingQuery, FirmQuery, ModuleId } from "@/api/types";

/** TanStack Query cache keys, in one place so invalidation stays consistent. */
export const queryKeys = {
  findings: ["findings"] as const,
  findingList: (query: FindingQuery) => ["findings", "list", query] as const,
  // Under "findings": a status change anywhere refreshes the aggregator too.
  entities: (query: EntityQuery) => ["findings", "entities", query] as const,
  entity: (key: string) => ["findings", "entity", key] as const,
  finding: (id: string) => ["findings", "detail", id] as const,
  findingTrace: (id: string) => ["findings", "trace", id] as const,
  system: ["system"] as const,
  summary: ["findings", "summary"] as const,
  trend: (module: ModuleId | undefined) => ["findings", "trend", module ?? "all"] as const,
  post: (id: string) => ["post", id] as const,
  render: (postId: string) => ["render", postId] as const,
  calibration: (module: ModuleId) => ["calibration", module] as const,
  thresholds: ["thresholds"] as const,
  sources: ["sources"] as const,
  connectors: ["connectors"] as const,
  firms: (query: FirmQuery) => ["firms", "list", query] as const,
  registryStatus: ["firms", "status"] as const,
};
