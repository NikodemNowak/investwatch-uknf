import { describe, expect, it } from "vitest";
import type { Finding, FindingWithPost, Post } from "@/api/types";
import {
  aggregateEntities,
  entityDetail,
  entityMatches,
  firmNameKey,
  normalizeName,
} from "@/lib/entities";
import findingsJson from "@/mocks/fixtures/findings.json";
import postsJson from "@/mocks/fixtures/posts.json";

const posts = postsJson as unknown as Post[];
const findings: FindingWithPost[] = (findingsJson as unknown as Finding[]).map((f) => ({
  ...f,
  post: posts.find((p) => p.id === f.post_id) ?? null,
}));

describe("aggregateEntities (mirror of entities/aggregate.py)", () => {
  const entities = aggregateEntities(findings);
  const byName = (name: string) => entities.find((e) => e.name === name);

  it("merges a firm's findings from several modules", () => {
    const kyrenia = byName("Kyrenia Prime Ltd");
    expect(kyrenia?.kind).toBe("firm");
    expect(kyrenia?.modules).toEqual({
      m1_third_party_ad: 2,
      m2_risk_disclosure: 1,
      m3_shadow_advisory: 0,
    });
    expect(kyrenia?.highest_risk).toBe("high");
    expect(kyrenia?.knf_register).toBe("knf");
  });

  it("gives an influencer one object over its M1 ads and M3 advice", () => {
    const kasia = byName("@InwestujZKasia");
    expect(kasia?.key).toBe("name:inwestujzkasia");
    expect(kasia?.knf_register).toBe("absent");
    expect([kasia?.modules.m1_third_party_ad, kasia?.modules.m3_shadow_advisory]).toEqual([1, 1]);
    expect([kasia?.open, kasia?.confirmed]).toEqual([1, 1]);
  });

  it("sorts the most serious first and drills down newest first", () => {
    const ranks = entities.map((e) => e.highest_risk);
    expect(ranks.indexOf("low")).toBeGreaterThan(ranks.lastIndexOf("high"));
    const detail = entityDetail(findings, "name:inwestujzkasia");
    const dates = detail?.findings.map((f) => f.created_at) ?? [];
    expect(dates).toEqual([...dates].sort().reverse());
    expect(entityDetail(findings, "name:nobody")).toBeNull();
  });

  it("searches names and normalises keys", () => {
    expect(normalizeName("  @Marcin  |  Giełda ")).toBe("marcin | giełda");
    const kyrenia = byName("Kyrenia Prime Ltd");
    expect(kyrenia && entityMatches(kyrenia, "kyrenia")).toBe(true);
    expect(kyrenia && entityMatches(kyrenia, "xtb")).toBe(false);
  });
});

describe("one entity per firm", () => {
  const base = findings.find((f) => f.firm && f.firm_match?.on === "author" && f.post);
  if (!base?.firm || !base.post || !base.firm_match) throw new Error("fixture without an M2 owner");
  const baseMatch = base.firm_match;
  const firm = { ...base.firm, id: "00000000-0000-4000-8000-0000000000f1", name: "XTB S.A." };
  const author = "X-Trade Brokers DM S.A. (XTB)";
  const owned: FindingWithPost = {
    ...base,
    id: "f-owned",
    firm,
    firm_match: { ...baseMatch, firm, on: "author" },
    post: { ...base.post, author },
  };
  const unmatched: FindingWithPost = {
    ...base,
    id: "f-unmatched",
    module: "m3_shadow_advisory",
    firm: null,
    firm_match: null,
    advertiser: author,
    post: { ...base.post, author },
  };

  it("files the publisher's unmatched material under the firm it publishes for", () => {
    const entities = aggregateEntities([owned, unmatched]);
    expect(entities.map((e) => e.name)).toEqual(["XTB S.A."]);
    expect(entities[0]?.total).toBe(2);
  });

  it("treats two register records of one firm as one entity", () => {
    const branch = {
      ...firm,
      id: "00000000-0000-4000-8000-0000000000f2",
      name: "Finax, o.c.p., a.s.",
    };
    const passport = {
      ...firm,
      id: "00000000-0000-4000-8000-0000000000f3",
      name: "Finax o.c.p., a.s.",
    };
    expect(firmNameKey(branch.name)).toBe(firmNameKey(passport.name));
    const entities = aggregateEntities([
      { ...owned, id: "a", firm: branch, firm_match: { ...baseMatch, firm: branch } },
      { ...owned, id: "b", firm: passport, firm_match: { ...baseMatch, firm: passport } },
    ]);
    expect(entities).toHaveLength(1);
    expect(entities[0]?.key).toBe(`firm:${branch.id}`);
  });
});
