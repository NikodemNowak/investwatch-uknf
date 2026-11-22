import type { Backend } from "@/api/backend";
import type {
  CalibrationReport,
  CheckJob,
  ConnectorBlocked,
  ConnectorInfo,
  EntitiesPage,
  EntityDetail,
  FindingPage,
  FindingWithPost,
  FirmQuery,
  FirmsPage,
  Health,
  ImportResult,
  ModuleId,
  Post,
  RegistryStatus,
  RenderSnapshot,
  ReviewQueuePosition,
  Source,
  Summary,
  SystemStatus,
  Thresholds,
  TrendSeries,
  UnderTheHood,
} from "@/api/types";
import { compactQuery } from "@/lib/filters";

/** Error with the HTTP status and the server's `detail`, so the UI can explain failures. */
export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly detail: string | null,
    /** Structured `detail` (409 from a source whose connector is not ready). */
    readonly blocked: ConnectorBlocked | null = null,
    /** Machine-readable reason of a structured `detail` (`platform_url`). */
    readonly code: string | null = null,
  ) {
    super(`${path}: HTTP ${status}`);
  }
}

const isBlocked = (value: unknown): value is ConnectorBlocked =>
  Boolean(value) &&
  typeof value === "object" &&
  typeof (value as { how_to?: unknown }).how_to === "string" &&
  typeof (value as { status?: unknown }).status === "string";

const isCoded = (value: unknown): value is { code: string; message: string } =>
  Boolean(value) &&
  typeof value === "object" &&
  typeof (value as { code?: unknown }).code === "string" &&
  typeof (value as { message?: unknown }).message === "string";

async function errorOf(response: Response, path: string): Promise<HttpError> {
  let detail: unknown = null;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      detail = (body as { detail: unknown }).detail;
    }
  } catch {
    // Non-JSON error bodies carry nothing worth showing.
  }
  if (isBlocked(detail)) return new HttpError(response.status, path, detail.how_to, detail);
  if (isCoded(detail)) {
    return new HttpError(response.status, path, detail.message, null, detail.code);
  }
  return new HttpError(response.status, path, typeof detail === "string" ? detail : null);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      accept: "application/json",
      ...(init?.body ? { "content-type": "application/json" } : {}),
    },
  });
  if (!response.ok) throw await errorOf(response, path);
  return (await response.json()) as T;
}

/** POST a multipart form (file imports, analyst submissions). */
async function postForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    body: form,
    headers: { accept: "application/json" },
  });
  if (!response.ok) throw await errorOf(response, path);
  return (await response.json()) as T;
}

/** Set `query` on `params`; arrays repeat the key (`status=new&status=in_review`). */
function appendAll(params: URLSearchParams, query: object): URLSearchParams {
  for (const [key, value] of Object.entries(compactQuery(query))) {
    if (Array.isArray(value)) for (const item of value) params.append(key, String(item));
    else params.set(key, String(value));
  }
  return params;
}

/** Build `?a=1&b=2` from defined values only. */
export function searchParams(query: object): string {
  const text = appendAll(new URLSearchParams(), query).toString();
  return text ? `?${text}` : "";
}

function withPost(item: FindingWithPost): FindingWithPost {
  return { ...item, post: item.post ?? null };
}

const SHORT: Record<ModuleId, string> = {
  m1_third_party_ad: "m1",
  m2_risk_disclosure: "m2",
  m3_shadow_advisory: "m3",
};

const id = encodeURIComponent;

/** Backend over the real REST API (same origin; vite/nginx proxy `/api`). */
export const httpBackend: Backend = {
  getHealth: () => request<Health>("/api/health"),
  getSummary: () => request<Summary>("/api/stats/summary"),
  getTrend: (module) =>
    request<TrendSeries>(`/api/stats/trend${searchParams({ module, bucket: "auto" })}`),
  listFindings: async (query) => {
    const page = await request<FindingPage>(`/api/findings${searchParams(query)}`);
    return { ...page, items: page.items.map(withPost) };
  },
  getFinding: async (findingId) =>
    withPost(await request<FindingWithPost>(`/api/findings/${id(findingId)}`)),
  updateFindingStatus: async (findingId, status) =>
    withPost(
      await request<FindingWithPost>(`/api/findings/${id(findingId)}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    ),
  getReviewQueue: (findingId) =>
    request<ReviewQueuePosition>(`/api/findings/${id(findingId)}/review-queue`),
  listEntities: (query) => request<EntitiesPage>(`/api/entities${searchParams(query)}`),
  getEntity: async (key) => {
    const detail = await request<EntityDetail>(`/api/entities/${id(key)}`);
    return { ...detail, findings: detail.findings.map(withPost) };
  },
  getPost: (postId) => request<Post>(`/api/posts/${id(postId)}`),
  getRender: async (postId) => {
    try {
      return await request<RenderSnapshot>(`/api/posts/${id(postId)}/render`);
    } catch (error) {
      if (error instanceof HttpError && error.status === 404) return null;
      throw error;
    }
  },
  screenshotUrl: (post, viewport) =>
    post.screenshot_keys[viewport] ? `/api/posts/${id(post.id)}/screenshots/${viewport}` : null,
  getCalibration: (module) => request<CalibrationReport>(`/api/calibration/${module}`),
  getThresholds: () => request<Thresholds>("/api/settings/thresholds"),
  putThresholds: (thresholds) =>
    request<Thresholds>("/api/settings/thresholds", {
      method: "PUT",
      body: JSON.stringify(thresholds),
    }),
  listSources: () => request<Source[]>("/api/sources"),
  createSource: (body) =>
    request<Source>("/api/sources", { method: "POST", body: JSON.stringify(body) }),
  runSource: (sourceId) => request<Source>(`/api/sources/${id(sourceId)}/run`, { method: "POST" }),
  listConnectors: () => request<ConnectorInfo[]>("/api/connectors"),
  importFile: (file, format) => {
    const form = new FormData();
    form.set("file", file);
    form.set("format", format);
    return postForm<ImportResult>("/api/imports", form);
  },
  submitMaterial: ({ text, url, note, screenshot }) => {
    const form = new FormData();
    form.set("text", text);
    if (url) form.set("url", url);
    if (note) form.set("note", note);
    if (screenshot) form.set("screenshot", screenshot);
    return postForm<ImportResult>("/api/submissions", form);
  },
  checkUrl: (body) =>
    request<CheckJob>("/api/check", { method: "POST", body: JSON.stringify(body) }),
  getCheck: (jobId) => request<CheckJob>(`/api/check/${id(jobId)}`),
  listFirms: (query: FirmQuery) => request<FirmsPage>(`/api/firms${searchParams(query)}`),
  getRegistryStatus: () => request<RegistryStatus>("/api/firms/status"),
  syncRegistry: async () => {
    await request<unknown>("/api/firms/sync", { method: "POST" });
  },
  reportCsvUrl: (module, query) => {
    const filters = { ...query, module: undefined, page: undefined, page_size: undefined };
    const params = appendAll(new URLSearchParams({ sep: ";" }), filters);
    return `/api/reports/${SHORT[module]}.csv?${params.toString()}`;
  },
  reportPdfUrl: (module, query) => {
    const filters = { ...query, module: undefined, page: undefined, page_size: undefined };
    return `/api/reports/${module ? SHORT[module] : "all"}.pdf${searchParams(filters)}`;
  },
  findingPdfUrl: (findingId) => `/api/findings/${id(findingId)}/report.pdf`,
  getFindingTrace: (findingId) => request<UnderTheHood>(`/api/findings/${id(findingId)}/trace`),
  getSystem: () => request<SystemStatus>("/api/system"),
};
