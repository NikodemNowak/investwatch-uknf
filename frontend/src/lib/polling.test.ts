import { describe, expect, it } from "vitest";
import { HttpError } from "@/api/http";
import type { FindingWithPost } from "@/api/types";
import { retryUnlessGone, reviewPollInterval } from "@/lib/polling";

const queued = { llm_review: "queued" } as FindingWithPost;
const gone = new HttpError(404, "/api/findings/x", "finding not found");

describe("reviewPollInterval", () => {
  it("polls while the model review is queued", () => {
    expect(reviewPollInterval({ data: queued })).toBe(5000);
    expect(reviewPollInterval({ data: { llm_review: "done" } as FindingWithPost })).toBe(false);
  });

  it("stops for good when the finding was deleted (404), even with stale data", () => {
    expect(reviewPollInterval({ data: queued, error: gone })).toBe(false);
  });

  it("keeps polling through a transient error", () => {
    expect(reviewPollInterval({ data: queued, error: new HttpError(502, "/x", null) })).toBe(5000);
  });
});

describe("retryUnlessGone", () => {
  it("never retries a 404 and retries other errors once", () => {
    expect(retryUnlessGone(0, gone)).toBe(false);
    expect(retryUnlessGone(0, new Error("network"))).toBe(true);
    expect(retryUnlessGone(1, new Error("network"))).toBe(false);
  });
});
