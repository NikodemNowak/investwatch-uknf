/**
 * API types.
 *
 * Section 1 mirrors `backend/src/investwatch/core/schemas.py` field by field. It is hand-written
 * while the backend has no OpenAPI to generate from; once it does, replace it with
 * `openapi-typescript` output. Change both sides in the same PR.
 * Section 2 holds request/response shapes of the plan 3.12 endpoints that are not in the
 * contract yet: the frontend's proposal, to be aligned with `backend/src/investwatch/api/`.
 */

/* ---------- 1. Contract (schemas.py) ---------- */

export type Platform = "web" | "facebook" | "instagram" | "tiktok" | "youtube" | "bing" | "sample";
export type ModuleId = "m1_third_party_ad" | "m2_risk_disclosure" | "m3_shadow_advisory";
export type Status = "new" | "in_review" | "confirmed" | "dismissed";
export type RiskLevel = "low" | "medium" | "high";
export type RuleStatus = "pass" | "fail" | "na" | "unknown";
export type CheckType = "text" | "render" | "llm";
export type Viewport = "desktop" | "tablet" | "phone";
export type FetchStatus = "ok" | "blocked" | "error" | "no_text";
export type FirmKind =
  "dom_maklerski" | "bank_maklerski" | "oddzial_zagraniczny" | "zagraniczna_bez_oddzialu";
export type TrendBucket = "hour" | "day" | "week";
/** Model second opinion: not needed / waiting in the `llm` queue / merged / model unavailable. */
export type LlmReviewState = "none" | "queued" | "done" | "unavailable";

/** x, y, width, height in CSS pixels of the full page. */
export type BBox = [number, number, number, number];

/** ISO 8601 datetime string, e.g. "2026-11-21T07:10:44Z". */
export type DateTimeString = string;
/** ISO 8601 date string, e.g. "2026-11-21". */
export type DateString = string;

/** How a post was obtained (ADR 0008). */
export interface PostProvenance {
  access_mode: string;
  legal_basis: string | null;
  fetched_at: DateTimeString | null;
  /** Fictional demo material (synthetic fixtures, fictional firms' pages). */
  synthetic: boolean;
  note: string | null;
  /** Why the source could not be read (robots.txt refusal, 403, throttling). */
  fetch_error?: string | null;
}

export interface Post {
  id: string;
  platform: Platform;
  collector: string;
  external_id: string;
  url: string;
  canonical_url: string;
  author: string;
  author_url: string | null;
  text: string;
  lang: string | null;
  content_hash: string;
  html_key: string | null;
  render_key: string | null;
  screenshot_keys: Partial<Record<Viewport, string>>;
  published_at: DateTimeString | null;
  first_seen_at: DateTimeString;
  last_seen_at: DateTimeString;
  fetch_status: FetchStatus;
  provenance?: PostProvenance | null;
}

export interface TextBlock {
  text: string;
  bbox: BBox;
  font_px: number;
  font_weight: number;
  color: string;
  background: string;
  opacity: number;
  visible: boolean;
  occluded: boolean;
  clipped: boolean;
  in_footer: boolean;
  in_collapsed: boolean;
  y_ratio: number;
  tag_path: string;
}

export interface RenderSnapshot {
  viewports: Partial<Record<Viewport, TextBlock[]>>;
  page_height: Partial<Record<Viewport, number>>;
}

export interface RegisteredFirm {
  id: string;
  name: string;
  aliases: string[];
  domains: string[];
  handles: string[];
  kind: FirmKind;
  country: string | null;
  services: string[];
  register_url: string;
  /** A fictional firm added for the demo (not in any KNF register). */
  fictional?: boolean;
}

export interface FirmMatch {
  firm: RegisteredFirm;
  confidence: number;
  method: "domain" | "handle" | "alias" | "fuzzy";
  matched_text: string;
  on: "author" | "content";
}

export interface Evidence {
  quote: string | null;
  viewport: Viewport | null;
  bbox: BBox | null;
  measurements: Record<string, number | string>;
}

export interface RuleResult {
  rule_id: string;
  name: string;
  status: RuleStatus;
  confidence: number;
  check_type: CheckType;
  weight: number;
  explanation: string;
  legal_basis: string;
  evidence: Evidence[];
}

export interface Finding {
  id: string;
  post_id: string;
  module: ModuleId;
  score: number;
  risk_level: RiskLevel;
  explanation: string;
  quotes: string[];
  firm: RegisteredFirm | null;
  firm_match: FirmMatch | null;
  advertiser: string | null;
  rules: RuleResult[];
  model: string;
  used_llm: boolean;
  /** Optional until every backend serves it; see `llmReviewOf`. */
  llm_review?: LlmReviewState;
  duplicates: number;
  status: Status;
  created_at: DateTimeString;
}

export interface Alert {
  finding: Finding;
  post: Post;
}

export interface CalibrationPoint {
  threshold: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  precision: number;
  recall: number;
  f1: number;
  f2: number;
}

export interface HistogramBin {
  lo: number;
  hi: number;
  count: number;
  positives: number;
  negatives: number;
}

export interface CalibrationReport {
  module: ModuleId;
  n_labels: number;
  n_positive: number;
  current_threshold: number;
  recommended_f1: number;
  recommended_f2: number;
  points: CalibrationPoint[];
  histogram: HistogramBin[];
  /** Fewer labels than this: the numbers are not meaningful yet. */
  min_labels?: number;
  labels_by_source?: Record<string, number>;
}

export interface TrendPoint {
  bucket_start: DateString;
  /** Start of the bucket (UTC), set for hourly buckets. */
  bucket_at?: string | null;
  module: ModuleId;
  total: number;
  high: number;
  medium: number;
  low: number;
}

export interface TrendSeries {
  bucket: TrendBucket;
  start: DateString;
  end: DateString;
  points: TrendPoint[];
}

/* ---------- 2. Endpoint shapes not yet in the contract (proposal) ---------- */

export interface Health {
  status: string;
  version: string;
}

/** A finding with its post embedded: `GET /api/findings` items and `GET /api/findings/{id}`. */
export interface FindingWithPost extends Finding {
  post: Post | null;
  /** Processing trace of the post (absent for posts never run through the pipeline). */
  trace?: ProcessingTrace | null;
  /** The publisher is on the KNF public warning list (a flag, not part of the score). */
  knf_warning?: KnfWarning | null;
  /** Occurrence group: the analysed post first, then duplicates (same text and layout). */
  occurrences?: Occurrence[];
  /** Earliest / latest sighting over the whole group. */
  first_seen_at?: DateTimeString | null;
  last_seen_at?: DateTimeString | null;
}

/** `db/schemas.py` `Occurrence`: one location of the material. */
export interface Occurrence {
  post_id: string;
  url: string;
  platform: Platform;
  author: string;
  first_seen_at: DateTimeString;
  last_seen_at: DateTimeString;
}

/** `registry/schemas.py` `KnfWarning`: match against the KNF public warning list. */
export interface KnfWarning {
  /** The listed entity. */
  name: string;
  method: "domain" | "name" | "fuzzy";
  matched_text: string;
  section: string;
  /** Snapshot date of the list (YYYY-MM-DD); the list itself has no per-entry date. */
  as_of: DateString;
  source_url: string;
}

/** `db/schemas.py` `TaskTrace`: the Celery task that handled a stage. */
export interface TaskTrace {
  task: string;
  task_id?: string | null;
  queue: string;
  worker?: string | null;
  retries?: number;
  /** "Check URL" job the task belongs to. */
  job_id?: string | null;
}

/** The model's second opinion on a post. */
export interface LlmTrace {
  state: LlmReviewState;
  model: string;
  prompt_tokens?: number | null;
  output_tokens?: number | null;
  /** Wall time of the model call. */
  ms?: number | null;
  error?: string | null;
  finished_at?: DateTimeString | null;
  task?: TaskTrace | null;
}

/** What the pipeline did with one post. */
export interface ProcessingTrace {
  analyzer: string;
  analyzed_at: DateTimeString;
  chars: number;
  tokens?: number | null;
  embed_model?: string | null;
  embedding_dim?: number | null;
  lang?: string | null;
  rules_version?: string | null;
  /** preprocess, rules, embed, total. */
  timings_ms?: Record<string, number>;
  llm?: LlmTrace | null;
  /** The `analyze` task that ran the fast pass. */
  task?: TaskTrace | null;
}

/* ---------- "Pod maską" (`GET /api/findings/{id}/trace`, `provenance/schemas.py`) ---------- */

/** One evidence copy in object storage with its SHA-256. */
export interface StoredObject {
  kind: "html" | "raw" | "render" | "screenshot";
  label: string;
  key: string;
  bucket: string;
  content_type: string;
  bytes?: number | null;
  sha256?: string | null;
}

/** How the material was obtained (raw envelope written by the collector). */
export interface FetchInfo {
  collector?: string | null;
  collector_version?: string | null;
  access_mode?: string | null;
  legal_basis?: string | null;
  source_url?: string | null;
  target?: string | null;
  fetched_at?: DateTimeString | null;
  user_agent?: string | null;
  /** `scheme://host:port`; null = direct connection. */
  proxy?: string | null;
  /** `allowed`, `disallowed`, `missing`; null = not a crawler fetch. */
  robots?: "allowed" | "disallowed" | "missing" | null;
  crawl_delay_s?: number | null;
  http_status?: number | null;
  elapsed_ms?: number | null;
  render?: string | null;
  render_ms?: number | null;
  discovered_by?: Record<string, unknown> | null;
}

/** `Finding.model` split into its parts. */
export interface ModelParts {
  rules_version?: string | null;
  llm_model?: string | null;
  classifier?: string | null;
  classifier_variant?: string | null;
  mock: boolean;
}

/** Everything the "Pod maską" panel shows about one finding. */
export interface UnderTheHood {
  finding_id: string;
  post_id: string;
  content_hash: string;
  render_hash?: string | null;
  tokens?: number | null;
  source?: {
    id: string;
    name: string;
    collector: string;
    cron: string;
    next_run_at?: DateTimeString | null;
    last_run_at?: DateTimeString | null;
  } | null;
  collect_job?: {
    task: string;
    task_id?: string | null;
    queue: string;
    worker?: string | null;
    run_id?: string | null;
    job_id?: string | null;
    cron?: string | null;
  } | null;
  fetch?: FetchInfo | null;
  objects: StoredObject[];
  trace?: ProcessingTrace | null;
  model: ModelParts;
  classifier_note?: string | null;
  similar: {
    post_id: string;
    url: string;
    author: string;
    similarity: number;
    finding_id?: string | null;
  }[];
  similar_available: boolean;
}

/* ---------- System status (`GET /api/system`, `status/schemas.py`) ---------- */

export type ServiceName =
  "api" | "database" | "redis" | "minio" | "workers" | "beat" | "ai" | "ollama";
export type ServiceState = "ok" | "degraded" | "down" | "disabled";

export interface ServiceStatus {
  name: ServiceName;
  state: ServiceState;
  detail?: string | null;
  latency_ms?: number | null;
}

export interface SystemStatus {
  checked_at: DateTimeString;
  version: string;
  services: ServiceStatus[];
  queues: { name: string; workers: string[] }[];
  next_run?: {
    source_id: string;
    source_name: string;
    cron: string;
    at: DateTimeString;
  } | null;
  beat_last_tick?: DateTimeString | null;
  ai?: {
    mode: string;
    rules_version?: string | null;
    llm_model?: string | null;
    embed_model?: string | null;
    llm_ready: boolean;
    embed_ready: boolean;
  } | null;
}

/** Query parameters of `GET /api/findings`. */
export interface FindingQuery {
  sort?: "created_at" | "score";
  module?: ModuleId;
  /** One platform or any of several (repeated query parameter). */
  platform?: Platform | Platform[];
  risk_level?: RiskLevel | RiskLevel[];
  /** One status or any of several; `["new", "in_review"]` is the open queue. */
  status?: Status | Status[];
  /** Inclusive lower bound on `created_at`, ISO date. */
  from?: DateString;
  /** Inclusive upper bound on `created_at`, ISO date. */
  to?: DateString;
  q?: string;
  page?: number;
  page_size?: number;
}

/** Paginated `GET /api/findings` response. */
export interface FindingPage {
  items: FindingWithPost[];
  total: number;
  page: number;
  page_size: number;
}

/** `GET/PUT /api/settings/thresholds`: score threshold per module. */
export type Thresholds = Record<ModuleId, number>;

export type SourceRunStatus = "ok" | "partial" | "error" | "running";
export type SourceStatus = "ok" | "blocked" | "error" | "running";

/** `GET /api/sources` item (`db/schemas.py` `Source`). */
export interface Source {
  id: string;
  name: string;
  platform: Platform;
  collector: string;
  target?: string;
  url: string;
  module_hint?: ModuleId | null;
  cron?: string;
  /** Cron expression (same as `cron`). */
  schedule: string;
  enabled: boolean;
  next_run_at?: DateTimeString | null;
  /** Precise status of the last run (`blocked` kept apart from `error`). */
  last_status?: SourceStatus | null;
  last_run_at: DateTimeString | null;
  last_run_status: SourceRunStatus | null;
  last_run_items: number;
  created_at?: DateTimeString;
  /** How the collector reaches its source (filled by the API from the connector). */
  access_mode?: AccessMode | null;
  /** Whether the connector may run now (filled by the API from the current settings). */
  connector_status?: ConnectorStatus | null;
  /** Why a `disabled` source never runs (e.g. its collector was removed), in Polish. */
  connector_reason?: string | null;
}

/** How a record is obtained (`collectors/policy.py` `AccessMode`). */
export type AccessMode = "official_api" | "open_dataset" | "file_import" | "analyst" | "crawler";
/** `ready` runs; the others never run (`collectors/policy.py` `ConnectorStatus`). */
export type ConnectorStatus = "ready" | "needs_credentials" | "needs_approval" | "disabled";

/** `GET /api/connectors` item (`collectors/policy.py` `ConnectorInfo`). */
export interface ConnectorInfo {
  name: string;
  label: string;
  access_mode: AccessMode;
  status: ConnectorStatus;
  /** Environment variables that must be set for the connector to run. */
  requires: string[];
  /** How UKNF obtains access (Polish). */
  how_to: string;
  lead_time?: string | null;
  legal_basis: string;
  quota?: string | null;
  /** Collector name used by sources, when the connector is one. */
  collector?: string | null;
}

/** `409` detail of `POST /api/sources/{id}/run` when the connector is not ready. */
export interface ConnectorBlocked {
  connector: string;
  status: ConnectorStatus;
  requires: string[];
  how_to: string;
}

/** File formats accepted by `POST /api/imports`. */
export type ImportFormat =
  | "meta_ads_json"
  | "meta_ads_csv"
  | "tiktok_ccl_json"
  | "youtube_api_json"
  | "uknf_sample"
  | "posts_jsonl";

/** `POST /api/imports` / `POST /api/submissions` response. */
export interface ImportResult {
  sha256: string;
  items: number;
  created: number;
  post_ids: string[];
  queued_for_analysis: number;
}

/** `POST /api/submissions` form: what an analyst saw (nothing is fetched). */
export interface Submission {
  text: string;
  url?: string;
  note?: string;
  /** PNG screenshot of what the analyst saw (max 10 MB). */
  screenshot?: File;
}

/** `POST /api/sources` body. */
export interface SourceCreate {
  name: string;
  collector: string;
  target: string;
  module_hint?: ModuleId | null;
  cron?: string;
  enabled?: boolean;
}

/** `GET /api/sources/{id}/runs` item. */
export interface ScrapeRun {
  id: string;
  source_id: string;
  started_at: DateTimeString;
  finished_at: DateTimeString | null;
  status: SourceStatus;
  items_new: number;
  items_seen: number;
  error: string | null;
}

/** `GET /api/stats/summary`. */
export interface ModuleSummary {
  module: ModuleId;
  total: number;
  high: number;
  medium: number;
  low: number;
  new: number;
}

export interface Summary {
  posts: number;
  findings: number;
  /** Status `new` or `in_review`. */
  open_findings: number;
  modules: ModuleSummary[];
  last_finding_at: DateTimeString | null;
}

/** `GET /api/firms` row. */
export interface FirmSummary {
  firm: RegisteredFirm;
  source: "knf" | "fixture" | "demo";
  active: boolean;
  findings: number;
}

export interface FirmsPage {
  total: number;
  items: FirmSummary[];
}

/** Query of `GET /api/firms`. */
export interface FirmQuery {
  q?: string;
  kind?: FirmKind;
  limit?: number;
  offset?: number;
}

export interface SyncResult {
  source: "live" | "snapshot";
  fetched_at: string;
  per_kind: Record<string, number>;
  total: number;
  added: number;
  removed: number;
  extra_firms: number;
  error: string | null;
}

/** `GET /api/firms/status`. */
export interface RegistryStatus {
  last_sync: SyncResult | null;
  synced_at: string | null;
  active_per_kind: Partial<Record<FirmKind, number>>;
  total_active: number;
  fictional: number;
  history: SyncResult[];
}

/** `POST /api/check` body: a URL or a raw text to analyse. */
export interface CheckRequest {
  url?: string;
  text?: string;
}

export type CheckJobState = "queued" | "running" | "done" | "failed";

/**
 * `GET /api/findings/{id}/review-queue`: where the model review waits. Analyst checks go to
 * `llm_priority`, which the worker drains before the batch queue `llm`.
 */
export interface ReviewQueuePosition {
  state: "queued" | "running" | "unknown";
  queue: "llm_priority" | "llm" | null;
  /** Reviews the worker takes before this one (running ones included). */
  ahead: number;
  /** All reviews waiting in both queues. */
  waiting: number;
}

/** `POST /api/check` and `GET /api/check/{job_id}` response. */
export interface CheckJob {
  job_id: string;
  state?: CheckJobState;
  post_id?: string | null;
  finding_ids?: string[];
  error?: string | null;
}

/**
 * Stages of a "check URL" job, in pipeline order. The backend sends `queued`, `fetched`,
 * `analyzed`/`failed`; `rendered` and `reviewed` (asynchronous LLM review) are optional.
 */
export type JobStage =
  | "queued"
  | "fetched"
  | "rendered"
  | "extracted"
  | "embedded"
  | "scored"
  | "analyzed"
  | "reviewed"
  | "failed";

export type LlmState = "queued" | "running" | "done" | "unavailable" | "failed";

/** Optional facts about a stage. */
export interface JobDetail {
  viewports?: number;
  model?: string;
  llm_state?: LlmState;
}

/** Socket.IO `job` event payload (progress of "Sprawdź"). */
export interface JobEvent {
  job_id: string;
  stage: JobStage;
  finding_ids: string[];
  error: string | null;
  post_id?: string | null;
  /** Set when the post repeats an earlier one: no new findings, no alert. */
  duplicate_of?: string | null;
  detail?: JobDetail;
  llm_state?: LlmState;
}

/* ---------- 3. Module reports (`backend/src/investwatch/reports/schemas.py`) ---------- */

/** Columns shared by every module report row. */
/** One row per location: duplicates repeat the finding under their own URL and dates. */
export interface ReportRow {
  finding_id: string;
  url: string;
  platform: Platform;
  score: number;
  risk_level: RiskLevel;
  status: Status;
  first_seen_at: DateTimeString;
  last_seen_at: DateTimeString;
  /** Locations in the finding's occurrence group. */
  occurrences: number;
}

/** M1: an investment firm advertised by a third party. */
export interface M1Row extends ReportRow {
  firm: string;
  advertiser: string;
  ad_text: string;
}

/** M2: a firm's own material with failed risk-disclosure rules. */
export interface M2Row extends ReportRow {
  firm: string;
  material: string;
  violated_rules: string[];
}

/** M3: an unregistered entity offering what looks like investment advice. */
export interface M3Row extends ReportRow {
  entity: string;
  offer_text: string;
  art76_signals: string[];
}

/** `GET /api/reports/{m1|m2|m3}.json`; the `.csv` variant takes `?sep=;` for Excel (PL). */
export interface Report {
  module: ModuleId;
  generated_at: DateTimeString;
  count: number;
  /** True when more findings matched than `limit`. */
  truncated: boolean;
  items: M1Row[] | M2Row[] | M3Row[];
}

/* ---------- 4. Result aggregator (`backend/src/investwatch/entities/schemas.py`) ---------- */

/** `firm`: matched to a register entry; `advertiser`: a publisher, author or domain. */
export type EntityKind = "firm" | "advertiser";
/** In the KNF register / a fictional demo firm / not matched to the register. */
export type RegisterState = "knf" | "fictional" | "absent";

/** `GET /api/entities` item: one entity with its M1/M2/M3 findings merged. */
export interface EntitySummary {
  /** `firm:<uuid>` or `name:<normalised name>`. */
  key: string;
  kind: EntityKind;
  name: string;
  firm: RegisteredFirm | null;
  knf_register: RegisterState;
  knf_warning: KnfWarning | null;
  modules: Record<ModuleId, number>;
  total: number;
  /** Status `new` or `in_review`. */
  open: number;
  confirmed: number;
  dismissed: number;
  highest_risk: RiskLevel;
  max_score: number;
  /** Locations over all findings, duplicates included. */
  occurrences: number;
  platforms: Platform[];
  first_seen_at: DateTimeString;
  last_seen_at: DateTimeString;
  latest_finding_id: string;
  latest_at: DateTimeString;
}

/** `GET /api/entities`. */
export interface EntitiesPage {
  items: EntitySummary[];
  total: number;
  /** Findings merged into the entities. */
  findings: number;
  truncated: boolean;
}

/** `GET /api/entities/{key}`: the entity with its findings, newest first. */
export interface EntityDetail extends EntitySummary {
  findings: FindingWithPost[];
}

/** Query of `GET /api/entities`: the findings filters; `q` searches entity names. */
export type EntityQuery = Omit<FindingQuery, "page" | "page_size" | "sort">;
