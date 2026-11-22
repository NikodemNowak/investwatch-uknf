import { HttpError } from "@/api/http";
import type { FindingWithPost } from "@/api/types";

const REVIEW_POLL_MS = 5000;

/** True for a 404: the object is gone (e.g. the demo was reset) and asking again cannot help. */
export const isGone = (error: unknown): boolean =>
  error instanceof HttpError && error.status === 404;

/** React Query `retry`: once for transient errors, never for a 404. */
export const retryUnlessGone = (failureCount: number, error: unknown): boolean =>
  !isGone(error) && failureCount < 1;

/** Poll a finding while its model review is queued; stop for good once it is gone. */
export function reviewPollInterval(state: {
  data?: FindingWithPost;
  error?: unknown;
}): number | false {
  if (isGone(state.error)) return false;
  return state.data?.llm_review === "queued" ? REVIEW_POLL_MS : false;
}
