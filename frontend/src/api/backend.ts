import type {
  Alert,
  CalibrationReport,
  CheckJob,
  CheckRequest,
  EntitiesPage,
  EntityDetail,
  EntityQuery,
  ConnectorInfo,
  Finding,
  FindingPage,
  FindingQuery,
  FindingWithPost,
  FirmQuery,
  FirmsPage,
  Health,
  ImportFormat,
  ImportResult,
  JobEvent,
  ModuleId,
  Post,
  RegistryStatus,
  RenderSnapshot,
  ReviewQueuePosition,
  Source,
  SourceCreate,
  Submission,
  Status,
  Summary,
  SystemStatus,
  Thresholds,
  TrendSeries,
  UnderTheHood,
  Viewport,
} from "@/api/types";

/** Everything the UI asks of the server; implemented over HTTP and by the mock backend. */
export interface Backend {
  getHealth(): Promise<Health>;
  getSummary(): Promise<Summary>;
  /** Findings per day for the last 14 days, split by risk level (one module or all). */
  getTrend(module?: ModuleId): Promise<TrendSeries>;
  listFindings(query: FindingQuery): Promise<FindingPage>;
  getFinding(id: string): Promise<FindingWithPost>;
  updateFindingStatus(id: string, status: Status): Promise<FindingWithPost>;
  /** Where the finding's model review waits in the queue (Sprawdź progress). */
  getReviewQueue(id: string): Promise<ReviewQueuePosition>;
  /** Result aggregator: entities over the filtered findings, most serious first. */
  listEntities(query: EntityQuery): Promise<EntitiesPage>;
  /** One entity with all its findings; rejects with `HttpError` 404 when unknown. */
  getEntity(key: string): Promise<EntityDetail>;
  getPost(id: string): Promise<Post>;
  /** Layout snapshot of a rendered page; null when the post was not rendered. */
  getRender(postId: string): Promise<RenderSnapshot | null>;
  /** URL of the screenshot for a viewport, or null when none exists. */
  screenshotUrl(post: Post, viewport: Viewport): string | null;
  getCalibration(module: ModuleId): Promise<CalibrationReport>;
  getThresholds(): Promise<Thresholds>;
  putThresholds(thresholds: Thresholds): Promise<Thresholds>;
  listSources(): Promise<Source[]>;
  createSource(body: SourceCreate): Promise<Source>;
  /** Run a source now; rejects with `HttpError` 409 (`blocked`) when its connector is not ready. */
  runSource(id: string): Promise<Source>;
  listConnectors(): Promise<ConnectorInfo[]>;
  importFile(file: File, format: ImportFormat): Promise<ImportResult>;
  submitMaterial(submission: Submission): Promise<ImportResult>;
  checkUrl(request: CheckRequest): Promise<CheckJob>;
  getCheck(jobId: string): Promise<CheckJob>;
  listFirms(query: FirmQuery): Promise<FirmsPage>;
  getRegistryStatus(): Promise<RegistryStatus>;
  syncRegistry(): Promise<void>;
  /**
   * Download URL of the official module report (CSV, `;`-separated) for the filters, or null
   * when the backend has none (mock mode exports client-side).
   */
  reportCsvUrl(module: ModuleId, query: FindingQuery): string | null;
  /** Download URL of the module report PDF (all three modules when `module` is undefined). */
  reportPdfUrl(module: ModuleId | undefined, query: FindingQuery): string | null;
  /** Download URL of a finding's one-page evidence PDF, or null without a server. */
  findingPdfUrl(findingId: string): string | null;
  /** How the finding's material was collected, stored and analysed ("Pod maską"). */
  getFindingTrace(findingId: string): Promise<UnderTheHood>;
  /** Health of every service and the next scheduled run (Monitoring). */
  getSystem(): Promise<SystemStatus>;
}

/** Socket.IO events the UI listens to. */
export interface RealtimeEvents {
  alert: Alert;
  job: JobEvent;
  /** A finding changed after a model review (full finding, without post). */
  finding_updated: Finding;
  /** Synthetic: connection state changes. */
  connection: boolean;
}

/** Subscription side of the realtime channel. */
export interface Realtime {
  on<K extends keyof RealtimeEvents>(
    event: K,
    handler: (payload: RealtimeEvents[K]) => void,
  ): () => void;
  isConnected(): boolean;
}
