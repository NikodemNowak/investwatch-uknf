import { describe, expect, it } from "vitest";
import type { Finding, FindingWithPost, Post } from "@/api/types";
import findingsJson from "@/mocks/fixtures/findings.json";
import postsJson from "@/mocks/fixtures/posts.json";
import { checkProgress } from "@/lib/checkSteps";
import type { CheckSnapshot } from "@/lib/checkSteps";

const post = (postsJson as unknown as Post[])[2] as Post;
const base = (findingsJson as unknown as Finding[])[4] as Finding;
const finding = (patch: Partial<FindingWithPost>): FindingWithPost => ({ ...base, post, ...patch });

const snap = (patch: Partial<CheckSnapshot>): CheckSnapshot => ({
  url: "https://primefx24.example/pl/promo-zloto",
  startedAt: 0,
  stages: { queued: 100 },
  post: null,
  findings: null,
  duplicate: false,
  ...patch,
});

describe("checkProgress", () => {
  it("starts with fetching running and the rest waiting", () => {
    const p = checkProgress(snap({}));
    expect(p.steps.map((s) => s.state)).toEqual(["run", "wait", "wait", "wait", "wait", "wait"]);
    expect(p.phase).toBe("pending");
  });

  it("completes steps in order: screenshots never jump ahead of the firm", () => {
    const p = checkProgress(snap({ stages: { queued: 100, fetched: 300 }, post }));
    expect(p.steps.map((s) => s.state)).toEqual(["done", "run", "wait", "wait", "wait", "wait"]);
    expect(p.steps[0]?.detail).toBe("primefx24.example · 0,3 s");
  });

  it("shows a preliminary result while the model review is queued", () => {
    const p = checkProgress(
      snap({
        stages: { queued: 1, fetched: 2, analyzed: 3 },
        post,
        findings: [finding({ llm_review: "queued" })],
      }),
    );
    expect(p.done).toBe(4);
    expect(p.steps[1]?.detail).toBe("Kyrenia Prime Ltd z rejestru KNF");
    expect(p.steps[3]?.detail).toBe("9 px, kontrast 1,7:1, w stopce");
    expect(p.steps[4]?.state).toBe("run");
    expect(p.phase).toBe("preliminary");
    expect(p.finished).toBe(false);
  });

  it("never presents a fictional demo firm as registered", () => {
    if (!base.firm) throw new Error("fixture without a firm");
    const p = checkProgress(
      snap({
        stages: { queued: 1, fetched: 2, analyzed: 3 },
        post,
        findings: [finding({ firm: { ...base.firm, fictional: true } })],
      }),
    );
    expect(p.steps[1]?.detail).toBe("Kyrenia Prime Ltd · firma fikcyjna (demo)");
  });

  it("says honestly that the model review waits in the queue, and how many go first", () => {
    const at = (reviewQueue: CheckSnapshot["reviewQueue"]) =>
      checkProgress(
        snap({
          stages: { queued: 1, fetched: 2, analyzed: 3 },
          post,
          findings: [finding({ llm_review: "queued" })],
          reviewQueue,
        }),
      ).steps[4];
    const queued = at({ state: "queued", queue: "llm_priority", ahead: 2, waiting: 40 });
    expect(queued?.label).toBe("Model językowy: w kolejce");
    expect(queued?.detail).toBe("Czeka w kolejce (2 przed)");
    expect(at({ state: "queued", queue: "llm_priority", ahead: 0, waiting: 1 })?.detail).toBe(
      "Następna w kolejce",
    );
    const running = at({ state: "running", queue: null, ahead: 0, waiting: 0 });
    expect(running?.label).toBe("Model językowy czyta tekst");
    expect(running?.detail).toBe("Czyta teraz, zwykle 10–20 sekund");
    expect(at(null)?.detail).toBe("Czeka na model językowy");
  });

  it("finishes when the model is done, unavailable or not needed", () => {
    for (const llm_review of ["done", "unavailable", "none"] as const) {
      const p = checkProgress(
        snap({ stages: { analyzed: 3 }, post, findings: [finding({ llm_review })] }),
      );
      expect(p.finished).toBe(true);
      expect(p.phase).toBe("final");
      expect(p.steps[4]?.state).toBe(llm_review === "done" ? "done" : "skip");
    }
  });

  it("marks the running step as failed", () => {
    const p = checkProgress(snap({ stages: { queued: 1, failed: 2 } }));
    expect(p.steps[0]?.state).toBe("fail");
    expect(p.phase).toBe("failed");
    expect(p.finished).toBe(true);
  });
});
