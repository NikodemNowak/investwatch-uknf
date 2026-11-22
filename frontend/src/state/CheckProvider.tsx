import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api, getRealtime } from "@/api/client";
import { HttpError } from "@/api/http";
import { queryKeys } from "@/api/queryKeys";
import type { CheckJob, FindingWithPost, JobEvent, JobStage } from "@/api/types";
import { pl } from "@/i18n/pl";
import { checkProgress } from "@/lib/checkSteps";
import { reviewPollInterval } from "@/lib/polling";
import { primaryFinding, verdictOf } from "@/lib/verdict";
import { CheckContext } from "@/state/checkContext";
import type { CheckApi, CheckRun } from "@/state/checkContext";
import { useToasts } from "@/state/toastContext";

interface RunState {
  url: string;
  jobId: string | null;
  startedAt: number;
  stages: Partial<Record<JobStage, number>>;
  postId: string | null;
  findingIds: string[];
  duplicate: boolean;
  error: string | null;
}

const POLL_MS = 2000;
const QUEUE_POLL_MS = 3000;
const BUFFER = 50;

/** Merge one job event into the run (stages only move forward; ids accumulate). */
function applyEvent(run: RunState, event: JobEvent, at: number): RunState {
  const stages = { ...run.stages };
  stages[event.stage] ??= at;
  if (event.stage === "analyzed") stages.fetched ??= at;
  return {
    ...run,
    stages,
    postId: event.post_id ?? run.postId,
    findingIds: [...new Set([...run.findingIds, ...(event.finding_ids ?? [])])],
    duplicate: run.duplicate || Boolean(event.duplicate_of),
    error: event.error ?? run.error,
  };
}

/** The polled job state as an event, so a missed Socket.IO message cannot stall the run. */
function jobAsEvent(job: CheckJob): JobEvent | null {
  const base = {
    job_id: job.job_id,
    finding_ids: job.finding_ids ?? [],
    error: job.error ?? null,
    post_id: job.post_id ?? null,
  };
  switch (job.state) {
    case "running":
      return { ...base, stage: "fetched" };
    case "done":
      return { ...base, stage: "analyzed" };
    case "failed":
      return { ...base, stage: "failed" };
    default:
      return null;
  }
}

/** Runs "Sprawdź" checks and keeps the latest one alive across pages. */
export function CheckProvider({ children }: { children: ReactNode }) {
  const toasts = useToasts();
  const { pathname } = useLocation();
  const onCheckPage = useRef(false);
  onCheckPage.current = pathname.startsWith("/sprawdz");
  const [run, setRun] = useState<RunState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<CheckApi["submitError"]>(null);
  const [finishedAt, setFinishedAt] = useState<number | null>(null);
  const buffered = useRef<JobEvent[]>([]);
  const jobIdRef = useRef<string | null>(null);
  const toastedJob = useRef<string | null>(null);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    let cancelled = false;
    void getRealtime().then((realtime) => {
      if (cancelled) return;
      unsubscribe = realtime.on("job", (event) => {
        if (event.job_id === jobIdRef.current) {
          setRun((current) => (current ? applyEvent(current, event, Date.now()) : current));
        } else {
          // Events can beat the POST response; keep them until the job id is known.
          buffered.current = [...buffered.current, event].slice(-BUFFER);
        }
      });
    });
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  const submit = useCallback((url: string) => {
    const startedAt = Date.now();
    jobIdRef.current = null;
    buffered.current = [];
    setFinishedAt(null);
    setSubmitError(null);
    setSubmitting(true);
    setRun({
      url,
      jobId: null,
      startedAt,
      stages: {},
      postId: null,
      findingIds: [],
      duplicate: false,
      error: null,
    });
    api((b) => b.checkUrl({ url }))
      .then((job) => {
        jobIdRef.current = job.job_id;
        const early = buffered.current.filter((event) => event.job_id === job.job_id);
        buffered.current = [];
        setRun((current) => {
          if (!current) return current;
          let next: RunState = { ...current, jobId: job.job_id };
          for (const event of early) next = applyEvent(next, event, Date.now());
          const polled = jobAsEvent(job);
          return polled ? applyEvent(next, polled, Date.now()) : next;
        });
      })
      .catch((error: unknown) => {
        setRun(null);
        const known = error instanceof HttpError && (error.status === 422 || error.status === 409);
        setSubmitError({
          message: known && error.detail ? error.detail : pl.check.submitError,
          // A social-media URL cannot be fetched: the page offers the "Zgłoś materiał" form.
          submitInstead: known && error.code === "platform_url",
        });
      })
      .finally(() => setSubmitting(false));
  }, []);

  const analyzed = run?.stages.analyzed !== undefined;
  const failed = run?.stages.failed !== undefined;

  // Fallback polling until the job is analysed or failed.
  useEffect(() => {
    const jobId = run?.jobId;
    if (!jobId || analyzed || failed) return undefined;
    const timer = setInterval(() => {
      api((b) => b.getCheck(jobId))
        .then((job) => {
          const event = jobAsEvent(job);
          if (event)
            setRun((current) =>
              current && current.jobId === jobId ? applyEvent(current, event, Date.now()) : current,
            );
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [run?.jobId, analyzed, failed]);

  const postQuery = useQuery({
    queryKey: [...queryKeys.post(run?.postId ?? ""), analyzed],
    queryFn: () => api((b) => b.getPost(run?.postId ?? "")),
    enabled: Boolean(run?.postId),
  });

  const findingQueries = useQueries({
    queries: (analyzed ? (run?.findingIds ?? []) : []).map((id) => ({
      queryKey: queryKeys.finding(id),
      queryFn: () => api((b) => b.getFinding(id)),
      // Safety net while the model review is pending (Socket.IO `finding_updated` is primary).
      refetchInterval: (query: { state: { data?: FindingWithPost; error?: unknown } }) =>
        reviewPollInterval(query.state),
    })),
  });
  const findingsLoaded = findingQueries.every((q) => q.data !== undefined || q.isError);
  const findings = useMemo(
    () => findingQueries.map((q) => q.data).filter((f): f is FindingWithPost => f !== undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recompute when any result changes
    [findingQueries.map((q) => q.dataUpdatedAt).join(",")],
  );

  // Where the model review waits, so the step can say "czeka w kolejce (N przed)".
  const queued = analyzed ? findings.filter((f) => f.llm_review === "queued") : [];
  const primaryId = primaryFinding(findings)?.id;
  const waitingFor = (queued.find((f) => f.id === primaryId) ?? queued[0])?.id;
  const queueQuery = useQuery({
    queryKey: ["review-queue", waitingFor ?? ""],
    queryFn: () => api((b) => b.getReviewQueue(waitingFor ?? "")),
    enabled: Boolean(waitingFor),
    refetchInterval: QUEUE_POLL_MS,
    staleTime: 0,
  });
  const reviewQueue = waitingFor ? (queueQuery.data ?? null) : null;

  const progress = useMemo(
    () =>
      run
        ? checkProgress({
            url: run.url,
            startedAt: run.startedAt,
            stages: run.stages,
            post: postQuery.data ?? null,
            findings: analyzed && findingsLoaded ? findings : null,
            duplicate: run.duplicate,
            reviewQueue,
          })
        : null,
    [run, postQuery.data, analyzed, findingsLoaded, findings, reviewQueue],
  );

  useEffect(() => {
    if (!run?.jobId || !progress?.finished || toastedJob.current === run.jobId) return;
    toastedJob.current = run.jobId;
    setFinishedAt(Date.now());
    // On "Sprawdź" the result is already on screen; a toast would only cover it.
    if (progress.phase === "failed" || onCheckPage.current) return;
    const primary = primaryFinding(findings);
    toasts.show({
      key: "check",
      tone: "success",
      title: pl.check.doneToast,
      text: verdictOf(findings, progress.phase).headline,
      action: primary ? { label: pl.common.open, to: `/zgloszenia/${primary.id}` } : undefined,
    });
  }, [run?.jobId, progress, findings, toasts]);

  const value = useMemo<CheckApi>(() => {
    const current: CheckRun | null =
      run && progress
        ? {
            url: run.url,
            jobId: run.jobId,
            startedAt: run.startedAt,
            finishedAt,
            error: run.error,
            progress,
            post: postQuery.data ?? null,
            findings,
          }
        : null;
    return {
      run: current,
      submitting,
      submitError,
      submit,
      clearSubmitError: () => setSubmitError(null),
    };
  }, [run, progress, finishedAt, postQuery.data, findings, submitting, submitError, submit]);

  return <CheckContext.Provider value={value}>{children}</CheckContext.Provider>;
}
