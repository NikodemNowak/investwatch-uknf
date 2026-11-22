import { describe, expect, it } from "vitest";
import type { ServiceStatus, SystemStatus } from "@/api/types";
import { serviceLine } from "@/lib/system";

const status = (extra: Partial<SystemStatus> = {}): SystemStatus => ({
  checked_at: "2026-11-21T10:00:00Z",
  version: "0.1.0",
  services: [],
  queues: [],
  ...extra,
});
const svc = (name: ServiceStatus["name"], state: ServiceStatus["state"], detail?: string) => ({
  name,
  state,
  detail,
});

describe("serviceLine", () => {
  it("translates worker counts and the beat tick", () => {
    expect(serviceLine(svc("workers", "ok", "4"), status())).toBe("4 workery");
    const tick = status({ beat_last_tick: "2026-11-21T10:00:00Z" });
    expect(serviceLine(svc("beat", "ok"), tick, Date.parse("2026-11-21T10:00:23Z"))).toBe(
      "takt 23 s temu",
    );
  });
  it("shows the state, not the technical detail, when a service is not ok", () => {
    expect(serviceLine(svc("redis", "down", "ConnectionError: x"), status())).toBe("nie działa");
    expect(serviceLine(svc("ollama", "degraded", "pulling models"), status())).toBe("częściowo");
  });
  it("keeps model names and the bucket", () => {
    expect(serviceLine(svc("ollama", "ok", "gemma4:e2b-it-qat"), status())).toBe(
      "gemma4:e2b-it-qat",
    );
    expect(serviceLine(svc("minio", "ok", "investwatch"), status())).toBe("kosz investwatch");
  });
});
