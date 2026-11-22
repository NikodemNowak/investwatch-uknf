import { describe, expect, it } from "vitest";
import type { UnderTheHood } from "@/api/types";
import { formatBytes, shortHash, shortId, sourceName, timingSteps } from "@/lib/hood";

describe("formatBytes", () => {
  it("uses B, kB and MB with a decimal comma", () => {
    expect(formatBytes(812)).toBe("812 B");
    expect(formatBytes(48_213)).toBe("48,2 kB");
    expect(formatBytes(1_400_000)).toBe("1,4 MB");
    expect(formatBytes(null)).toBe("–");
  });
});

describe("shortHash / shortId", () => {
  it("cuts long values", () => {
    expect(shortHash("8d90a8798f394c096c0560189a46")).toBe("8d90a8798f39…");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash(undefined)).toBe("–");
    expect(shortId("7f1c2a9e-4b3d-4e1a")).toBe("7f1c2a9e");
    expect(shortId(null)).toBeNull();
  });
});

describe("timingSteps", () => {
  it("keeps the order, drops total and computes shares of it", () => {
    const { steps, total } = timingSteps({ preprocess: 10, rules: 30, embed: 60, total: 100 });
    expect(total).toBe(100);
    expect(steps.map((s) => s.key)).toEqual(["preprocess", "rules", "embed"]);
    expect(steps[2]?.share).toBeCloseTo(0.6);
  });
  it("sorts steps in pipeline order whatever the stored key order", () => {
    const { steps } = timingSteps({ embed: 5, total: 9, rules: 3, preprocess: 1 });
    expect(steps.map((s) => s.key)).toEqual(["preprocess", "rules", "embed"]);
  });
  it("falls back to the sum when total is missing or smaller", () => {
    expect(timingSteps({ rules: 5, embed: 15 }).total).toBe(20);
    expect(timingSteps(undefined)).toEqual({ steps: [], total: 0 });
  });
});

describe("sourceName", () => {
  const base = { objects: [], similar: [], similar_available: false, model: { mock: false } };
  it("prefers the monitored source, then a manual check", () => {
    const withSource = {
      ...base,
      source: { id: "s", name: "Strony firm", collector: "site", cron: "0 4 * * *" },
    } as unknown as UnderTheHood;
    expect(sourceName(withSource, "Sprawdź")).toBe("Strony firm");
    const manual = { ...base, fetch: { collector: "manual" } } as unknown as UnderTheHood;
    expect(sourceName(manual, "Sprawdź")).toBe("Sprawdź");
  });

  it("names a bare collector key in Polish", () => {
    const labels = { meta_ad_library: "Meta Ad Library", file_import: "Import pliku" };
    const meta = { ...base, fetch: { collector: "meta_ad_library" } } as unknown as UnderTheHood;
    expect(sourceName(meta, "Sprawdź", labels)).toBe("Meta Ad Library");
    const other = { ...base, fetch: { collector: "rss" } } as unknown as UnderTheHood;
    expect(sourceName(other, "Sprawdź", labels)).toBe("rss");
  });
});
