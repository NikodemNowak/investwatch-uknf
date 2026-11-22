import type { Backend, Realtime } from "@/api/backend";
import { httpBackend } from "@/api/http";
import { USE_MOCKS } from "@/config";

let backendPromise: Promise<Backend> | undefined;
let resolvedBackend: Backend | undefined;
let realtimePromise: Promise<Realtime> | undefined;

/** The active backend: HTTP, or the fixture-backed mock when `VITE_USE_MOCKS=1`. */
export function getBackend(): Promise<Backend> {
  backendPromise ??= (
    USE_MOCKS
      ? import("@/mocks/mockBackend").then((m) => m.mockBackend)
      : Promise.resolve(httpBackend)
  ).then((backend) => {
    resolvedBackend = backend;
    return backend;
  });
  return backendPromise;
}

/** The realtime channel (singleton); mock mode simulates alerts and job progress. */
export function getRealtime(): Promise<Realtime> {
  realtimePromise ??= USE_MOCKS
    ? import("@/mocks/mockBackend").then((m) => m.mockRealtime)
    : import("@/api/socket").then((m) => m.createSocketRealtime());
  return realtimePromise;
}

/** Shorthand: run one call against the active backend. */
export async function api<T>(call: (backend: Backend) => Promise<T>): Promise<T> {
  return call(await getBackend());
}

/**
 * The backend for synchronous helpers (URLs). It is resolved by the time anything that needs a
 * URL was fetched through it; before that, HTTP is a safe answer outside mock mode.
 */
export function syncBackend(): Backend | undefined {
  return resolvedBackend ?? (USE_MOCKS ? undefined : httpBackend);
}
