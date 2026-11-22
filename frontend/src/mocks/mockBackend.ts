import type { Backend, Realtime, RealtimeEvents } from "@/api/backend";
import type {
  CalibrationReport,
  CheckJob,
  Finding,
  FindingWithPost,
  FirmKind,
  FirmSummary,
  JobEvent,
  ModuleId,
  Post,
  ProcessingTrace,
  RegisteredFirm,
  RegistryStatus,
  RenderSnapshot,
  Source,
  Summary,
  Thresholds,
  TrendSeries,
  Viewport,
} from "@/api/types";
import { Emitter } from "@/lib/emitter";
import { aggregateEntities, entityDetail, entityMatches } from "@/lib/entities";
import { queryFindings } from "@/lib/filters";
import { riskLevelFor } from "@/lib/calibration";
import { domainOf } from "@/lib/format";
import calibrationJson from "@/mocks/fixtures/calibration.json";
import findingsJson from "@/mocks/fixtures/findings.json";
import postsJson from "@/mocks/fixtures/posts.json";
import renderJson from "@/mocks/fixtures/render_snapshot.json";
import firmsJson from "@/mocks/fixtures/firms.json";
import trendJson from "@/mocks/fixtures/trend.json";
import desktopShot from "@/mocks/fixtures/shots/desktop.png";
import phoneShot from "@/mocks/fixtures/shots/phone.png";
import tabletShot from "@/mocks/fixtures/shots/tablet.png";
import { mockConnectors, mockSources } from "@/mocks/sources";
import { HttpError } from "@/api/http";
import { syntheticRecords } from "@/mocks/synthetic";
import { mockSystem, mockTrace } from "@/mocks/trace";

// JSON imports widen string literals; the fixtures are validated against schemas.py in backend CI.
const fixturePosts = postsJson as unknown as Post[];
const calibration = calibrationJson as unknown as CalibrationReport;
const firms = firmsJson as unknown as RegisteredFirm[];
const render = renderJson as unknown as RenderSnapshot;
const trend = trendJson as unknown as TrendSeries;
const SHOTS: Record<Viewport, string> = {
  desktop: desktopShot,
  tablet: tabletShot,
  phone: phoneShot,
};
/** The only post with screenshots in the fixtures (PrimeFX24 landing page). */
const RENDERED_POST_ID = "a0000000-0000-4000-8000-000000000003";
/** Finding produced by a simulated "Sprawdź" of the PrimeFX24 page. */
const CHECK_FINDING_ID = "f0000000-0000-4000-8000-000000000005";
/** Finding announced by the simulated background alert. */
const BACKGROUND_ALERT_ID = "f0000000-0000-4000-8000-000000000006";
const BACKGROUND_ALERT_DELAY_MS = 15_000;
const LLM_MODEL = "gemma4:e2b-it-qat";
const SNAPSHOT_PER_KIND: Record<FirmKind, number> = {
  dom_maklerski: 28,
  bank_maklerski: 10,
  oddzial_zagraniczny: 10,
  zagraniczna_bez_oddzialu: 709,
};
const SNAPSHOT_TOTAL = Object.values(SNAPSHOT_PER_KIND).reduce((a, b) => a + b, 0);

const fixtureFindings = findingsJson as unknown as Finding[];
const synthetic = syntheticRecords(fixtureFindings, firms, "2026-11-21");
const posts = [...fixturePosts, ...synthetic.posts];
const postById = new Map(posts.map((post) => [post.id, post]));
let findings: FindingWithPost[] = [...fixtureFindings, ...synthetic.findings].map((finding) => ({
  ...finding,
  llm_review: finding.used_llm ? "done" : "none",
  post: postById.get(finding.post_id) ?? null,
}));
let thresholds: Thresholds = {
  m1_third_party_ad: 0.7,
  m2_risk_disclosure: calibration.current_threshold,
  m3_shadow_advisory: 0.7,
};
const jobs = new Map<string, CheckJob>();
let jobCounter = 0;

const emitter = new Emitter<RealtimeEvents>();

const delay = <T>(value: T, ms = 120): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));

function findOrThrow(id: string): FindingWithPost {
  const finding = findings.find((item) => item.id === id);
  if (!finding) throw new Error(`finding ${id} not found`);
  return finding;
}

function replace(id: string, patch: (finding: FindingWithPost) => FindingWithPost): void {
  findings = findings.map((item) => (item.id === id ? patch(item) : item));
}

/** The contract `Finding` (Socket.IO payloads carry no post or trace). */
function plainFinding(finding: FindingWithPost): Finding {
  const copy: Partial<FindingWithPost> = { ...finding };
  delete copy.post;
  delete copy.trace;
  return copy as Finding;
}

function emitAlert(id: string): void {
  const finding = findOrThrow(id);
  if (!finding.post) return;
  emitter.emit("alert", { finding: plainFinding(finding), post: finding.post });
}

function trace(llm: ProcessingTrace["llm"]): ProcessingTrace {
  return {
    analyzer: "ai",
    analyzed_at: new Date().toISOString(),
    chars: 1932,
    tokens: 412,
    embed_model: "bge-m3",
    embedding_dim: 1024,
    lang: "pl",
    rules_version: "rules-v1",
    timings_ms: { preprocess: 12, rules: 180, embed: 240, total: 460 },
    llm,
  };
}

/** Pick the fixture finding whose post shares the checked domain; PrimeFX24 otherwise. */
function findingForUrl(url: string): FindingWithPost {
  const domain = domainOf(url);
  return (
    findings.find(
      (f) => f.module === "m2_risk_disclosure" && f.post && domainOf(f.post.url) === domain,
    ) ?? findOrThrow(CHECK_FINDING_ID)
  );
}

/** Replays the real pipeline: alert from rules first, model review ~6 s later. */
function simulateCheck(jobId: string, url: string): void {
  const target = findingForUrl(url);
  const original = structuredClone(target);
  const postId = target.post_id;
  const emit = (event: Omit<JobEvent, "job_id" | "error" | "finding_ids">, ids: string[] = []) =>
    emitter.emit("job", { job_id: jobId, error: null, finding_ids: ids, ...event });
  const update = (job: Partial<CheckJob>) =>
    jobs.set(jobId, { ...(jobs.get(jobId) ?? { job_id: jobId }), ...job });

  setTimeout(() => emit({ stage: "queued" }), 150);
  setTimeout(() => {
    update({ state: "running", post_id: postId });
    emit({ stage: "fetched", post_id: postId });
  }, 700);
  setTimeout(() => {
    replace(target.id, (f) => ({
      ...f,
      status: "new",
      created_at: new Date().toISOString(),
      llm_review: "queued",
      used_llm: false,
      rules: f.rules.map((rule) =>
        rule.check_type === "llm" ? { ...rule, status: "unknown" } : rule,
      ),
      trace: trace(null),
    }));
    update({ state: "done", finding_ids: [target.id] });
    emit({ stage: "analyzed", post_id: postId }, [target.id]);
    emitAlert(target.id);
  }, 1900);
  setTimeout(() => {
    replace(target.id, (f) => ({
      ...f,
      rules: original.rules,
      llm_review: "done",
      used_llm: true,
      model: `${LLM_MODEL}+rules-v1`,
      trace: trace({
        state: "done",
        model: LLM_MODEL,
        prompt_tokens: 1240,
        output_tokens: 310,
        ms: 5600,
        finished_at: new Date().toISOString(),
      }),
    }));
    emitter.emit("finding_updated", plainFinding(findOrThrow(target.id)));
  }, 7600);
}

function firmRows(): FirmSummary[] {
  return firms.map((firm) => ({
    firm,
    source: "demo",
    active: true,
    findings: findings.filter((f) => f.firm?.id === firm.id).length,
  }));
}

const fold = (text: string) =>
  text.toLocaleLowerCase("pl").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");

/** Fixture-backed implementation of the API, with in-memory writes. */
export const mockBackend: Backend = {
  getHealth: () => delay({ status: "ok", version: "mock" }),
  getSummary: () => {
    const modules = (
      ["m1_third_party_ad", "m2_risk_disclosure", "m3_shadow_advisory"] as ModuleId[]
    ).map((module) => {
      const own = findings.filter((f) => f.module === module);
      return {
        module,
        total: own.length,
        high: own.filter((f) => f.risk_level === "high").length,
        medium: own.filter((f) => f.risk_level === "medium").length,
        low: own.filter((f) => f.risk_level === "low").length,
        new: own.filter((f) => f.status === "new").length,
      };
    });
    const summary: Summary = {
      posts: posts.length,
      findings: findings.length,
      open_findings: findings.filter((f) => f.status === "new" || f.status === "in_review").length,
      modules,
      last_finding_at: null,
    };
    return delay(summary);
  },
  getTrend: (module) =>
    delay({ ...trend, points: trend.points.filter((p) => !module || p.module === module) }),
  listFindings: (query) => delay(queryFindings(findings, query)),
  getFinding: (id) => delay(findOrThrow(id)),
  updateFindingStatus: (id, status) => {
    replace(id, (item) => ({ ...item, status }));
    return delay(findOrThrow(id));
  },
  getReviewQueue: (id) =>
    delay({
      state: findOrThrow(id).llm_review === "queued" ? "queued" : "unknown",
      queue: "llm_priority",
      ahead: 0,
      waiting: 0,
    }),
  listEntities: (query) => {
    // Every fixture firm is fictional (the register itself is not bundled).
    const { q, ...filters } = query;
    const matched = queryFindings(findings, { ...filters, page_size: findings.length || 1 }).items;
    const items = aggregateEntities(matched, () => true).filter((e) => entityMatches(e, q));
    return delay({ items, total: items.length, findings: matched.length, truncated: false });
  },
  getEntity: (key) => {
    const detail = entityDetail(findings, key, () => true);
    return detail
      ? delay(detail)
      : Promise.reject(new HttpError(404, `/api/entities/${key}`, null));
  },
  getPost: (id) => {
    const post = postById.get(id);
    return post ? delay(post) : Promise.reject(new Error(`post ${id} not found`));
  },
  getRender: (postId) => delay(postId === RENDERED_POST_ID ? render : null),
  screenshotUrl: (post, viewport) => (post.id === RENDERED_POST_ID ? SHOTS[viewport] : null),
  getCalibration: (module: ModuleId) =>
    // Only M2 has a calibration fixture; the other modules reuse its curve for the demo.
    delay({ ...calibration, module, current_threshold: thresholds[module], min_labels: 20 }),
  getThresholds: () => delay(thresholds),
  putThresholds: (next) => {
    thresholds = { ...thresholds, ...next };
    findings = findings.map((item) => ({
      ...item,
      risk_level: riskLevelFor(item.score, thresholds[item.module]),
    }));
    return delay(thresholds);
  },
  listSources: () => delay<Source[]>(mockSources),
  createSource: (body) => {
    const created: Source = {
      id: `s0000000-0000-4000-8000-${String(mockSources.length + 1).padStart(12, "0")}`,
      name: body.name,
      platform: "web",
      collector: body.collector,
      target: body.target,
      url: body.target,
      module_hint: body.module_hint ?? null,
      cron: body.cron ?? "0 */6 * * *",
      schedule: body.cron ?? "0 */6 * * *",
      enabled: true,
      next_run_at: null,
      last_status: null,
      last_run_at: null,
      last_run_status: null,
      last_run_items: 0,
      created_at: new Date().toISOString(),
      access_mode: mockConnectors.find((c) => c.collector === body.collector)?.access_mode ?? null,
      connector_status:
        mockConnectors.find((c) => c.collector === body.collector)?.status ?? "ready",
    };
    mockSources.push(created);
    return delay(created);
  },
  runSource: (sourceId) => {
    const found = mockSources.find((s) => s.id === sourceId);
    if (!found) return Promise.reject(new HttpError(404, `/api/sources/${sourceId}/run`, null));
    const info = mockConnectors.find((c) => c.collector === found.collector);
    if (info && info.status !== "ready") {
      const blocked = {
        connector: info.name,
        status: info.status,
        requires: info.requires,
        how_to: info.how_to,
      };
      return Promise.reject(
        new HttpError(409, `/api/sources/${sourceId}/run`, info.how_to, blocked),
      );
    }
    found.last_status = "running";
    found.last_run_status = "running";
    setTimeout(() => {
      found.last_status = "ok";
      found.last_run_status = "ok";
      found.last_run_at = new Date().toISOString();
    }, 3000);
    return delay({ ...found });
  },
  listConnectors: () => delay(mockConnectors),
  importFile: (file) =>
    delay({
      sha256: "0".repeat(64),
      items: 3,
      created: 3,
      post_ids: [],
      queued_for_analysis: file.size > 0 ? 3 : 0,
    }),
  submitMaterial: () =>
    delay({ sha256: "0".repeat(64), items: 1, created: 1, post_ids: [], queued_for_analysis: 1 }),
  checkUrl: (body) => {
    jobCounter += 1;
    const jobId = `mock-job-${jobCounter}`;
    const job: CheckJob = { job_id: jobId, state: "queued", finding_ids: [] };
    jobs.set(jobId, job);
    simulateCheck(jobId, body.url ?? "");
    return delay(job, 80);
  },
  getCheck: (jobId) => {
    const job = jobs.get(jobId);
    return job ? delay(job) : Promise.reject(new Error(`job ${jobId} not found`));
  },
  listFirms: (query) => {
    const needle = fold(query.q?.trim() ?? "");
    const rows = firmRows().filter(
      (row) =>
        (!query.kind || row.firm.kind === query.kind) &&
        (!needle ||
          [row.firm.name, ...row.firm.aliases, ...row.firm.domains].some((v) =>
            fold(v).includes(needle),
          )),
    );
    const offset = query.offset ?? 0;
    return delay({ total: rows.length, items: rows.slice(offset, offset + (query.limit ?? 50)) });
  },
  getRegistryStatus: () => {
    // The register itself is not bundled: counts of the committed snapshot
    // (data/registry/knf_registry.json, 2026-11-21). The fixture firms are fictional.
    const perKind: Partial<Record<FirmKind, number>> = SNAPSHOT_PER_KIND;
    const status: RegistryStatus = {
      last_sync: {
        source: "live",
        fetched_at: "2026-11-21T03:17:00Z",
        per_kind: perKind,
        total: SNAPSHOT_TOTAL,
        added: 0,
        removed: 0,
        extra_firms: 0,
        error: null,
      },
      synced_at: "2026-11-21T03:17:00Z",
      active_per_kind: perKind,
      total_active: SNAPSHOT_TOTAL,
      fictional: firms.length,
      history: [],
    };
    return delay(status);
  },
  syncRegistry: () => delay(undefined),
  reportCsvUrl: () => null,
  reportPdfUrl: () => null,
  findingPdfUrl: () => null,
  getFindingTrace: (id) => delay(mockTrace(findOrThrow(id))),
  getSystem: () => delay(mockSystem()),
};

let backgroundAlertScheduled = false;

/** Simulated Socket.IO channel: always connected, one background alert after start. */
export const mockRealtime: Realtime = {
  on: (event, handler) => {
    if (!backgroundAlertScheduled) {
      backgroundAlertScheduled = true;
      setTimeout(() => emitAlert(BACKGROUND_ALERT_ID), BACKGROUND_ALERT_DELAY_MS);
    }
    return emitter.on(event, handler);
  },
  isConnected: () => true,
};
