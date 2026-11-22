import { describe, expect, it } from "vitest";
import type { Finding, FindingWithPost } from "@/api/types";
import findingsJson from "@/mocks/fixtures/findings.json";
import { verdictOf } from "@/lib/verdict";

const findings = findingsJson as unknown as Finding[];
const prime = findings.find((f) => f.id === "f0000000-0000-4000-8000-000000000005") as Finding;

describe("verdictOf", () => {
  it("carries the model signal when a high score has no failed rule", () => {
    const m1 = {
      ...prime,
      module: "m1_third_party_ad",
      risk_level: "high",
      rules: prime.rules.map((rule) => ({ ...rule, status: "pass" as const })),
      explanation: "x promuje y. Klasyfikator (leksykon): p = 0.97; wkład w logit: bonus +4.2.",
      post: null,
    } as FindingWithPost;
    const verdict = verdictOf([m1], "final");
    expect(verdict.problems).toEqual([]);
    expect(verdict.signal?.title).toBe("Sygnał modelu – do weryfikacji");
    expect(verdict.headline).toBe("Sygnał modelu – do weryfikacji");
  });

  it("has no signal when rules failed", () => {
    const verdict = verdictOf([{ ...prime, post: null } as FindingWithPost], "final");
    expect(verdict.signal).toBeNull();
    expect(verdict.headline).toMatch(/^Wysokie ryzyko naruszenia: /);
  });
});
