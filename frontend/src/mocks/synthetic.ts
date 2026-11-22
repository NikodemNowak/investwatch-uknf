import type { Finding, Platform, Post, RegisteredFirm, RuleResult, Status } from "@/api/types";
import { riskLevelFor } from "@/lib/calibration";

/**
 * Deterministic filler records for mock mode only, so the dense list, facets and the 30-day
 * trend can be judged at a realistic volume. Fictional names and `.example` domains, like
 * data/fixtures; the footer marks the whole mock mode as sample data.
 */

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const ADVERTISERS: [string, Platform][] = [
  ["@ZyskNaGieldzie", "instagram"],
  ["Forex z Anią", "youtube"],
  ["@krypto.ola", "tiktok"],
  ["Inwestor Wieczorem", "facebook"],
  ["@trader_bartek", "tiktok"],
  ["Rynki po godzinach", "youtube"],
  ["@mama.inwestuje", "instagram"],
  ["Złota Rybka Inwestycje", "facebook"],
];
const ADVISERS: [string, Platform][] = [
  ["Akademia Wolności Finansowej", "web"],
  ["@sygnaly.vip", "tiktok"],
  ["Klub Inwestora Premium", "facebook"],
  ["Doradztwo Rodzinne N.", "web"],
];
const QUOTES = {
  m1_third_party_ad: [
    "Załóż konto z moim kodem i odbierz bonus na start.",
    "Ten broker płaci mi za polecenie, ale naprawdę warto.",
    "Link w bio, kod ZYSK20 na zero prowizji.",
  ],
  m2_risk_disclosure: [
    "Zyskaj nawet 18% w skali roku na portfelu obligacji.",
    "Wyniki z ostatnich 3 miesięcy: +48%.",
    "Inwestuj bez prowizji, pierwsza transakcja gratis.",
  ],
  m3_shadow_advisory: [
    "Przygotuję dla Ciebie indywidualny portfel na podstawie ankiety.",
    "Kup teraz, zanim kurs odjedzie. Sygnał tylko dla VIP.",
    "Konsultacja 1:1: powiem, w co ulokować oszczędności.",
  ],
} as const;
const STATUSES: Status[] = ["new", "new", "in_review", "confirmed", "dismissed"];
const THRESHOLD = 0.7;

const uuid = (prefix: string, n: number) =>
  `${prefix}0000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const slug = (text: string) =>
  text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ł/g, "l")
    .replace(/[^a-z0-9]+/g, "");

function urlFor(platform: Platform, author: string, n: number): string {
  const handle = slug(author);
  switch (platform) {
    case "youtube":
      return `https://www.youtube.com/watch?v=mock${n}${handle.slice(0, 4)}`;
    case "tiktok":
      return `https://www.tiktok.com/@${handle}/video/7${String(n).padStart(9, "0")}`;
    case "instagram":
      return `https://www.instagram.com/p/mock${n}${handle.slice(0, 3)}/`;
    case "facebook":
      return `https://www.facebook.com/${handle}/posts/${900000 + n}`;
    default:
      return author.includes(".")
        ? `https://${author}/oferta-${n}`
        : `https://${handle}.example/oferta-${n}`;
  }
}

/** ~48 extra records spread over 30 days before `end`, built on the fixture rule sets. */
export function syntheticRecords(
  base: readonly Finding[],
  firms: readonly RegisteredFirm[],
  end: string,
): { findings: Finding[]; posts: Post[] } {
  const random = mulberry32(2026_11_21);
  const pick = <T>(list: readonly T[]): T => list[Math.floor(random() * list.length)] as T;
  const templates = {
    m1_third_party_ad: base.filter((f) => f.module === "m1_third_party_ad"),
    m2_risk_disclosure: base.filter((f) => f.module === "m2_risk_disclosure"),
    m3_shadow_advisory: base.filter((f) => f.module === "m3_shadow_advisory"),
  };
  const endMs = Date.parse(`${end}T07:40:00Z`);
  const findings: Finding[] = [];
  const posts: Post[] = [];

  for (let n = 1; n <= 48; n += 1) {
    const roll = random();
    const module =
      roll < 0.45 ? "m1_third_party_ad" : roll < 0.8 ? "m2_risk_disclosure" : "m3_shadow_advisory";
    const template = pick(templates[module]);
    const firm = module === "m3_shadow_advisory" ? null : pick(firms);
    const [author, platform]: [string, Platform] =
      module === "m1_third_party_ad"
        ? pick(ADVERTISERS)
        : module === "m3_shadow_advisory"
          ? pick(ADVISERS)
          : [firm?.domains[0] ?? "firma.example", "web"];
    // Skew towards recent days: volume grows over the window.
    const ageDays = Math.floor(Math.pow(random(), 1.6) * 30);
    const created = new Date(endMs - ageDays * 86_400_000 - Math.floor(random() * 50_000_000));
    const rules: RuleResult[] = template.rules.map((rule) => {
      if (rule.status === "na" || random() > 0.3) return rule;
      return { ...rule, status: rule.status === "fail" ? "pass" : "fail" };
    });
    const fails = rules.filter((rule) => rule.status === "fail");
    const score = Math.min(0.995, Math.max(0.03, 0.18 * fails.length + random() * 0.35 - 0.1));
    const quote = pick(QUOTES[module]);
    const postId = uuid("b", n);
    const url = urlFor(platform, author, n);
    posts.push({
      id: postId,
      platform,
      collector: platform === "web" ? "web" : `${platform}_collector`,
      external_id: url,
      url,
      canonical_url: url,
      author,
      author_url: null,
      text: quote,
      lang: "pl",
      content_hash: `mock${n}`,
      html_key: null,
      render_key: null,
      screenshot_keys: {},
      published_at: null,
      first_seen_at: created.toISOString(),
      last_seen_at: created.toISOString(),
      fetch_status: "ok",
    });
    findings.push({
      ...template,
      id: uuid("e", n),
      post_id: postId,
      score,
      risk_level: riskLevelFor(score, THRESHOLD),
      explanation: fails.map((rule) => rule.name).join(" · "),
      quotes: [quote],
      firm,
      firm_match: null,
      advertiser: module === "m2_risk_disclosure" ? null : author,
      rules,
      duplicates: random() < 0.2 ? Math.floor(random() * 4) + 1 : 0,
      status: ageDays < 2 ? "new" : pick(STATUSES),
      created_at: created.toISOString().replace(/\.\d{3}Z$/, "Z"),
    });
  }
  return { findings, posts };
}
