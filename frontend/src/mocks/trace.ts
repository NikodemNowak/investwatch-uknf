import type { FindingWithPost, SystemStatus, UnderTheHood } from "@/api/types";
import { mockSources } from "@/mocks/sources";

const UA =
  "Mozilla/5.0 (compatible; InvestWatchBot/1.0; +https://github.com/NikodemNowak/investwatch-uknf)";
const ACCESS: Record<string, string> = {
  web: "crawler",
  manual: "crawler",
  site: "crawler",
  youtube: "official_api",
  meta_ad_library: "official_api",
  tiktok: "official_api",
};
const BASIS: Record<string, string> = {
  crawler: "art. 26³ pr. aut. (TDM, zastrzeżenia respektowane); robots.txt",
  official_api: "oficjalne API platformy (regulamin dewelopera)",
  file_import: "import pliku przez analityka",
};

/** Deterministic fake SHA-256 (hex) so the mock panel looks like the real one. */
function fakeSha(seed: string): string {
  let out = "";
  for (let round = 0; out.length < 64; round++) {
    let h = (2166136261 ^ round) >>> 0;
    for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619) >>> 0;
    out += h.toString(16).padStart(8, "0");
  }
  return out.slice(0, 64);
}

/** "Pod maską" for a fixture finding: shaped like `GET /api/findings/{id}/trace`. */
export function mockTrace(finding: FindingWithPost): UnderTheHood {
  const post = finding.post;
  const postId = post?.id ?? finding.post_id;
  const collector = post?.collector ?? "sample";
  const access = ACCESS[collector] ?? "file_import";
  const crawler = access === "crawler";
  const source = mockSources.find((s) => s.collector === collector) ?? mockSources[0];
  const seen = post?.first_seen_at ?? finding.created_at;
  const objects: UnderTheHood["objects"] = [
    {
      kind: crawler ? "html" : "raw",
      label: crawler ? "html" : "raw",
      key: crawler ? `raw/${postId}.html` : `raw/${postId}.json`,
      bucket: "investwatch",
      content_type: crawler ? "text/html" : "application/json",
      bytes: crawler ? 48_213 : 3_402,
      sha256: fakeSha(`${postId}:raw`),
    },
    ...Object.entries(post?.screenshot_keys ?? {}).map(([viewport, key]) => ({
      kind: "screenshot" as const,
      label: viewport,
      key,
      bucket: "investwatch",
      content_type: "image/png",
      bytes: 412_000,
      sha256: fakeSha(`${postId}:${viewport}`),
    })),
  ];
  if (post?.render_key) {
    objects.splice(1, 0, {
      kind: "render",
      label: "render",
      key: post.render_key,
      bucket: "investwatch",
      content_type: "application/json",
      bytes: 96_540,
      sha256: fakeSha(`${postId}:render`),
    });
  }
  const parts = finding.model.split("+");
  return {
    finding_id: finding.id,
    post_id: postId,
    content_hash: fakeSha(`${postId}:text`),
    render_hash: post?.render_key ? fakeSha(`${postId}:layout`) : null,
    tokens: finding.trace?.tokens ?? 412,
    source: source
      ? {
          id: source.id,
          name: source.name,
          collector: source.collector,
          cron: source.cron ?? "*/30 * * * *",
          next_run_at: source.next_run_at ?? new Date(Date.now() + 7 * 60_000).toISOString(),
          last_run_at: source.last_run_at,
        }
      : null,
    collect_job: {
      task: "investwatch.scrape_source",
      task_id: "7f1c2a9e-4b3d-4e1a-9c55-0d2f6b8e1a10",
      queue: "scrape",
      worker: "3f9c1d2e7a40",
      run_id: "2d6f0b1e-8a4c-4f2d-b1e3-5a7c9d0e2f41",
      cron: source?.cron ?? null,
    },
    fetch: {
      collector,
      collector_version: "1.0",
      access_mode: access,
      legal_basis: BASIS[access],
      source_url: post?.url,
      target: post?.url,
      fetched_at: seen,
      user_agent: crawler ? UA : null,
      proxy: null,
      robots: crawler ? "allowed" : null,
      crawl_delay_s: crawler ? 2 : null,
      http_status: crawler ? 200 : null,
      elapsed_ms: crawler ? 184 : null,
      render: crawler && post?.render_key ? "ok" : null,
      render_ms: crawler && post?.render_key ? 2_840 : null,
    },
    objects,
    trace: finding.trace ?? {
      analyzer: "ai",
      analyzed_at: finding.created_at,
      chars: post?.text.length ?? 0,
      tokens: 412,
      embed_model: "bge-m3",
      embedding_dim: 1024,
      lang: "pl",
      rules_version: parts.find((p) => p.includes("rules-")) ?? null,
      timings_ms: { preprocess: 12, rules: 180, embed: 240, classifier: 4, total: 460 },
      task: {
        task: "investwatch.analyze_post",
        task_id: "c2b8e4f0-1a6d-4c3e-8f7b-9d0a2e5c6b13",
        queue: "analyze",
        worker: "8b2e4c6a1d93",
      },
      llm: finding.used_llm
        ? {
            state: "done",
            model: parts[0] ?? "gemma4:e2b-it-qat",
            prompt_tokens: 1180,
            output_tokens: 214,
            ms: 5600,
            finished_at: finding.created_at,
            task: {
              task: "investwatch.review_finding",
              task_id: "e9d1f3a7-5b2c-4d8e-a6f0-3c4b7e1d2a98",
              queue: "llm",
              worker: "c41a7e905b28",
            },
          }
        : null,
    },
    model: {
      rules_version: parts.find((p) => p.includes("rules-")) ?? null,
      llm_model: finding.used_llm ? (parts[0] ?? null) : null,
      classifier: finding.module === "m2_risk_disclosure" ? null : "lr-v1",
      classifier_variant: finding.module === "m2_risk_disclosure" ? null : "embedding",
      mock: false,
    },
    classifier_note:
      finding.module === "m2_risk_disclosure"
        ? null
        : "Klasyfikator (embedding bge-m3 + leksykon): p = 0.83; wkład w logit: obietnica zysku +1.2, embedding +0.8.",
    similar: [],
    similar_available: false,
  };
}

/** A healthy stack, as `GET /api/system` reports it. */
export function mockSystem(): SystemStatus {
  const now = new Date();
  const next = new Date(now.getTime() + 7 * 60_000);
  return {
    checked_at: now.toISOString(),
    version: "mock",
    services: [
      { name: "api", state: "ok", detail: "0.1.0", latency_ms: 0 },
      { name: "database", state: "ok", detail: "postgresql", latency_ms: 2 },
      { name: "redis", state: "ok", latency_ms: 1 },
      { name: "minio", state: "ok", detail: "investwatch", latency_ms: 4 },
      { name: "workers", state: "ok", detail: "4", latency_ms: 210 },
      { name: "beat", state: "ok", detail: "last tick 23 s ago" },
      { name: "ai", state: "ok", detail: "rules-v2", latency_ms: 18 },
      { name: "ollama", state: "ok", detail: "gemma4:e2b-it-qat", latency_ms: 18 },
    ],
    queues: [
      { name: "analyze", workers: ["8b2e4c6a1d93"] },
      { name: "llm", workers: ["c41a7e905b28"] },
      { name: "maintenance", workers: ["8b2e4c6a1d93"] },
      { name: "scrape", workers: ["3f9c1d2e7a40"] },
    ],
    next_run: {
      source_id: mockSources[0]?.id ?? "s1",
      source_name: mockSources[0]?.name ?? "Strony firm z rejestru KNF",
      cron: mockSources[0]?.cron ?? "*/30 * * * *",
      at: next.toISOString(),
    },
    beat_last_tick: new Date(now.getTime() - 23_000).toISOString(),
    ai: {
      mode: "llm",
      rules_version: "rules-v2",
      llm_model: "gemma4:e2b-it-qat",
      embed_model: "bge-m3",
      llm_ready: true,
      embed_ready: true,
    },
  };
}
