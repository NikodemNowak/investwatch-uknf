import { createContext, useContext } from "react";
import type { FindingWithPost, Post } from "@/api/types";
import type { CheckProgress } from "@/lib/checkSteps";

/** The check the analyst started last (kept while navigating between pages). */
export interface CheckRun {
  url: string;
  jobId: string | null;
  startedAt: number;
  finishedAt: number | null;
  error: string | null;
  progress: CheckProgress;
  post: Post | null;
  findings: FindingWithPost[];
}

export interface CheckApi {
  run: CheckRun | null;
  submitting: boolean;
  /**
   * Why `POST /api/check` was refused (bad URL, server down); `submitInstead` when the URL is
   * a social-media page that has to be reported by hand ("Zgłoś materiał").
   */
  submitError: { message: string; submitInstead: boolean } | null;
  submit: (url: string) => void;
  /** Forget the refusal (e.g. the material was reported by hand instead). */
  clearSubmitError: () => void;
}

export const CheckContext = createContext<CheckApi | null>(null);

/** Current "Sprawdź" run and the action to start one. */
export function useCheck(): CheckApi {
  const api = useContext(CheckContext);
  if (!api) throw new Error("useCheck outside CheckProvider");
  return api;
}
