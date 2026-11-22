import { describe, expect, it } from "vitest";
import type { FindingWithPost } from "@/api/types";
import {
  DEFAULT_FILTERS,
  activeFilterCount,
  filtersQuery,
  matchesQuery,
  periodRange,
  readFilters,
  writeFilters,
} from "@/lib/filters";

const TODAY = new Date(2026, 10, 21, 12, 0);

describe("filter bar state in the URL", () => {
  it("reads defaults from empty params and ignores junk", () => {
    expect(readFilters(new URLSearchParams())).toEqual(DEFAULT_FILTERS);
    const junk = readFilters(new URLSearchParams("okres=wczoraj&zrodlo=myspace&status=x&od=21.11"));
    expect(junk).toEqual({ ...DEFAULT_FILTERS, from: undefined, to: undefined });
  });

  it("round-trips every field and keeps unrelated params", () => {
    const filters = {
      period: "custom" as const,
      from: "2026-11-01",
      to: "2026-11-15",
      platforms: ["youtube" as const, "web" as const],
      risk: "high" as const,
      status: "confirmed" as const,
    };
    const params = writeFilters(new URLSearchParams("rodzaj=m1_third_party_ad"), filters);
    expect(params.get("rodzaj")).toBe("m1_third_party_ad");
    expect(params.get("status")).toBe("potwierdzone");
    expect(params.get("zrodlo")).toBe("youtube,web");
    // Platforms come back in display order.
    expect(readFilters(params)).toEqual({ ...filters, platforms: ["web", "youtube"] });
    expect(activeFilterCount(filters)).toBe(4);
  });

  it("drops defaults and the custom range of a preset", () => {
    const params = writeFilters(new URLSearchParams("od=2026-11-01&status=odrzucone"), {
      ...DEFAULT_FILTERS,
      period: "7d",
    });
    expect(params.toString()).toBe("okres=7-dni");
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
  });
});

describe("filtersQuery", () => {
  it("maps presets to inclusive local-day ranges", () => {
    expect(periodRange({ period: "today" }, TODAY)).toEqual({
      from: "2026-11-21",
      to: "2026-11-21",
    });
    expect(periodRange({ period: "7d" }, TODAY)).toEqual({ from: "2026-11-15", to: "2026-11-21" });
    expect(periodRange({ period: "30d" }, TODAY).from).toBe("2026-10-23");
    expect(periodRange({ period: "all" }, TODAY)).toEqual({});
  });

  it("asks for the open queue by default and drops empty values", () => {
    expect(filtersQuery(DEFAULT_FILTERS, { today: TODAY })).toEqual({
      status: ["new", "in_review"],
    });
    const query = filtersQuery(
      { ...DEFAULT_FILTERS, status: "all", platforms: ["tiktok"], risk: "low" },
      { today: TODAY, withRisk: false },
    );
    expect(query).toEqual({ platform: ["tiktok"] });
  });
});

describe("matchesQuery with several values", () => {
  const finding = {
    module: "m1_third_party_ad",
    risk_level: "high",
    status: "in_review",
    created_at: "2026-11-20T10:00:00Z",
    post: { platform: "youtube" },
    quotes: [],
  } as unknown as FindingWithPost;

  it("accepts any listed value and treats [] as any", () => {
    expect(matchesQuery(finding, { status: ["new", "in_review"] })).toBe(true);
    expect(matchesQuery(finding, { status: ["confirmed"] })).toBe(false);
    expect(matchesQuery(finding, { platform: [] })).toBe(true);
    expect(matchesQuery(finding, { platform: ["web", "youtube"], risk_level: "high" })).toBe(true);
    expect(matchesQuery(finding, { from: "2026-11-21" })).toBe(false);
  });
});
