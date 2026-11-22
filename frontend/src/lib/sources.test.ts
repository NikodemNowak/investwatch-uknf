import { describe, expect, it } from "vitest";
import type { Source } from "@/api/types";
import { accessLabel, describeCron, isWaiting, registryRowState, sourceState } from "@/lib/sources";

describe("describeCron", () => {
  it("reads common schedules in Polish", () => {
    expect(describeCron("0 */6 * * *")).toBe("co 6 godz.");
    expect(describeCron("0 4 * * *")).toBe("codziennie o 04:00");
    expect(describeCron("*/30 * * * *")).toBe("co 30 min");
    expect(describeCron("0 4 * * 1")).toBe("0 4 * * 1");
  });
});

const base: Source = {
  id: "s1",
  name: "Meta",
  platform: "facebook",
  collector: "meta_ad_library",
  url: "",
  schedule: "0 */6 * * *",
  enabled: true,
  last_run_at: null,
  last_run_status: null,
  last_run_items: 0,
};

describe("sourceState", () => {
  it("follows the connector status before the last run", () => {
    expect(sourceState({ ...base, connector_status: "needs_credentials" })).toBe("key");
    expect(sourceState({ ...base, connector_status: "needs_approval" })).toBe("approval");
    expect(sourceState({ ...base, connector_status: "disabled", last_status: "ok" })).toBe("off");
    expect(sourceState({ ...base, connector_status: "ready", last_status: "ok" })).toBe("ok");
    expect(isWaiting({ ...base, connector_status: "needs_approval" })).toBe(true);
  });

  it("tells a site's refusal (robots.txt, TDM) apart from a missing key", () => {
    const refused = {
      ...base,
      connector_status: "ready" as const,
      last_status: "blocked" as const,
    };
    expect(sourceState(refused)).toBe("blocked");
    expect(isWaiting(refused)).toBe(false);
  });

  it("labels access by collector, then by access mode", () => {
    expect(accessLabel(base)).toBe("Ad Library API");
    expect(accessLabel({ ...base, collector: "gdelt", access_mode: "open_dataset" })).toBe(
      "Otwarty zbiór danych",
    );
  });
});

describe("registryRowState", () => {
  const sync = {
    source: "live" as const,
    fetched_at: "2026-11-20T13:47:05+00:00",
    per_kind: {},
    total: 1,
    added: 0,
    removed: 0,
    extra_firms: 0,
    error: null,
  };
  const status = {
    last_sync: sync,
    synced_at: "2026-11-21T08:00:00+00:00",
    active_per_kind: {},
    total_active: 1,
    fictional: 0,
    history: [],
    source_name: "",
    source_url: "",
  };

  it("says 'Działa' only for a live sync", () => {
    expect(registryRowState(status)).toEqual({ tone: "ok", label: "Działa" });
  });

  it("names the snapshot date when the register was loaded offline", () => {
    const offline = { ...status, last_sync: { ...sync, source: "snapshot" as const } };
    expect(registryRowState(offline)).toEqual({ tone: "medium", label: "Kopia z 20.11.2026" });
  });

  it("is an error without a sync or with a failed one", () => {
    expect(registryRowState({ ...status, synced_at: null }).tone).toBe("high");
    const failed = { ...status, last_sync: { ...sync, error: "timeout" } };
    expect(registryRowState(failed).tone).toBe("high");
  });
});
