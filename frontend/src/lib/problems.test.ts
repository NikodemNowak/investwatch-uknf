import { describe, expect, it } from "vitest";
import type { Finding, FindingWithPost, RuleResult } from "@/api/types";
import findingsJson from "@/mocks/fixtures/findings.json";
import {
  failedDevices,
  firmLabel,
  isSupervisedPublisher,
  headlineOf,
  lawLong,
  lawShort,
  llmReviewOf,
  modelSignalOf,
  problemsOf,
  plainExplanation,
  proseExplanation,
  describeFinding,
  firstSentence,
  summaryOf,
  warningMeasures,
} from "@/lib/problems";

const findings = findingsJson as unknown as Finding[];
const prime = findings.find((f) => f.id === "f0000000-0000-4000-8000-000000000005") as Finding;

describe("problems", () => {
  it("shortens and normalises the legal basis", () => {
    const basis = "art. 44 ust. 2 lit. c i e rozporządzenia del. 2017/565";
    expect(lawShort(basis)).toBe("art. 44 ust. 2 lit. c, e");
    expect(lawLong(basis)).toBe("Art. 44 ust. 2 lit. c i e rozporządzenia 2017/565");
    expect(lawShort("art. 24 ust. 3 MiFID II")).toBe("art. 24 ust. 3 MiFID II");
  });

  it("lists measured problems first, in plain words", () => {
    const problems = problemsOf(prime.rules);
    expect(problems[0]?.title).toBe("Ostrzeżenie jest za małe");
    const font = problems.find((p) => p.rule.rule_id === "4");
    expect(font?.short).toBe("9 px przy tekście strony 16 px.");
    const llm = problems.findIndex((p) => !p.severe);
    expect(problems.slice(llm).every((p) => !p.severe)).toBe(true);
  });

  it("reads warning measurements", () => {
    const m = warningMeasures(prime.rules);
    expect(m.warningPx).toBe(9);
    expect(m.pagePx).toBe(16);
    expect(m.contrast).toBeCloseTo(1.74);
    expect(m.fontFailed && m.contrastFailed).toBe(true);
  });

  it("does not blame contrast when rule 5 failed for an occluded warning", () => {
    const rule: RuleResult = {
      rule_id: "5",
      name: "Ekspozycja i kontrast ryzyka",
      status: "fail",
      check_type: "render",
      legal_basis: "art. 44 ust. 2 lit. d rozporządzenia del. 2017/565",
      explanation:
        "Ostrzeżenie o ryzyku jest słabo eksponowane: tekst jest przesłonięty innym elementem.",
      evidence: [{ measurements: { contrast: 5.74, opacity: 1, occluded: "true" } }],
    } as unknown as RuleResult;
    const [problem] = problemsOf([rule]);
    expect(problem?.title).toBe("Ostrzeżenie jest słabo widoczne");
    expect(problem?.short).toBe("Tekst ostrzeżenia jest przesłonięty innym elementem.");
    expect(problem?.text).toBe("Tekst ostrzeżenia jest przesłonięty innym elementem.");
    expect(problem?.text).not.toContain("kontrast");
    expect(warningMeasures([rule]).contrastFailed).toBe(false);
    expect(summaryOf(problemsOf([rule]))).toBe("Ostrzeżenie o ryzyku jest słabo widoczne.");
    const pale = {
      ...rule,
      evidence: [{ measurements: { contrast: 2.1 } }],
    } as unknown as RuleResult;
    expect(problemsOf([pale])[0]?.title).toBe("Ostrzeżenie jest blade");
    expect(warningMeasures([pale]).contrastFailed).toBe(true);
  });

  it("titles the finding after the firm's trade name", () => {
    expect(headlineOf({ ...prime, status: "confirmed", post: null } as FindingWithPost)).toBe(
      "PrimeFX24 ukrywa ostrzeżenie o ryzyku",
    );
  });

  it("phrases an unconfirmed finding about a real firm as a possibility", () => {
    const open = { ...prime, status: "new", post: null } as FindingWithPost;
    expect(headlineOf(open)).toBe("PrimeFX24: ostrzeżenie o ryzyku może być ukryte");
    if (!prime.firm) throw new Error("fixture without a firm");
    const fictional = { ...open, firm: { ...prime.firm, fictional: true } } as FindingWithPost;
    expect(headlineOf(fictional)).toBe("PrimeFX24 ukrywa ostrzeżenie o ryzyku");
    const advisory = { ...open, module: "m3_shadow_advisory", advertiser: "JR NETMEDIA" };
    expect(headlineOf(advisory as FindingWithPost)).toBe(
      "JR NETMEDIA: możliwe doradztwo bez zezwolenia",
    );
  });

  it("titles a model-only finding as a signal to verify", () => {
    const passed = prime.rules.map((rule) => ({ ...rule, status: "pass" as const }));
    const m3 = {
      ...prime,
      module: "m3_shadow_advisory",
      advertiser: "JR NETMEDIA",
      risk_level: "high",
      status: "new",
      rules: passed,
      post: null,
    } as FindingWithPost;
    expect(headlineOf(m3)).toBe("JR NETMEDIA: sygnał do weryfikacji (doradztwo bez zezwolenia)");
    const firm = prime.firm ? { ...prime.firm, fictional: true } : null;
    expect(headlineOf({ ...m3, firm })).toContain("sygnał do weryfikacji");
  });

  it("never titles a high or medium finding without failed rules as compliant", () => {
    const passed = prime.rules.map((rule) => ({ ...rule, status: "pass" as const }));
    const m1 = { ...prime, module: "m1_third_party_ad" as const, rules: passed, post: null };
    expect(headlineOf({ ...m1, risk_level: "high" } as FindingWithPost)).not.toContain(
      "bez naruszeń",
    );
    expect(headlineOf({ ...m1, risk_level: "low" } as FindingWithPost)).toContain("bez naruszeń");
  });

  it("falls back to used_llm when llm_review is missing", () => {
    expect(llmReviewOf({ ...prime, llm_review: undefined, used_llm: true })).toBe("done");
    expect(llmReviewOf({ ...prime, llm_review: "queued" })).toBe("queued");
  });
});

describe("plainExplanation", () => {
  it("drops an empty list of art. 76 elements and pluralises unrated rules", () => {
    const m3 = {
      ...prime,
      module: "m3_shadow_advisory",
      explanation:
        "Elementy doradztwa inwestycyjnego (art. 76 UoIF): brak. Podmiot nie występuje w rejestrach KNF jako autor publikacji.",
    } as Finding;
    expect(plainExplanation(m3)).toBe(
      "Podmiot nie występuje w rejestrach KNF jako autor publikacji.",
    );
    const one = { ...prime, explanation: "Nie wykryto naruszeń. Nie oceniono 1 reguł." };
    expect(plainExplanation(one)).toBe("Nie wykryto naruszeń. Nie oceniono 1 reguły.");
    const two = { ...prime, explanation: "Nie wykryto naruszeń. Nie oceniono 2 reguł." };
    expect(plainExplanation(two)).toBe("Nie wykryto naruszeń. Nie oceniono 2 reguł.");
  });

  it("fixes the missing „ani” in stored M1 explanations", () => {
    const m1 = {
      ...prime,
      explanation: "x promuje y; reklama oznaczona, bez twierdzeń o zysku o ryzyku.",
    };
    expect(plainExplanation(m1)).toBe(
      "x promuje y; reklama oznaczona, bez twierdzeń o zysku ani o ryzyku.",
    );
  });
});

describe("summaryOf", () => {
  it("reads like the mockup", () => {
    const summary = summaryOf(problemsOf(prime.rules));
    expect(summary.startsWith("Ostrzeżenie o ryzyku jest za małe, blade, schowane")).toBe(true);
    expect(proseExplanation("Naruszenia: 1 Identyfikacja firmy; 2 Oznaczenie reklamy")).toBeNull();
    expect(proseExplanation(prime.explanation)).toBe(prime.explanation);
    expect(proseExplanation("Identyfikacja firmy · Oznaczenie reklamy")).toBeNull();
  });
});

describe("isSupervisedPublisher", () => {
  const owned = findings.find(
    (f) => f.module === "m2_risk_disclosure" && f.firm_match?.on === "author",
  );
  it("marks a registered firm's own material, not a look-alike domain or a mention", () => {
    if (!owned?.firm_match) throw new Error("fixture without an M2 owner");
    expect(isSupervisedPublisher(owned)).toBe(true);
    const clone = {
      ...owned,
      firm_match: { ...owned.firm_match, matched_text: "Firma S.A. (domena spoza rejestru)" },
    };
    expect(isSupervisedPublisher(clone)).toBe(false);
    expect(isSupervisedPublisher({ ...owned, module: "m1_third_party_ad" })).toBe(false);
    if (!owned.firm) throw new Error("fixture without a firm");
    // A fictional demo firm only pretends to be in the register: never "Firma z rejestru KNF".
    expect(isSupervisedPublisher({ ...owned, firm: { ...owned.firm, fictional: true } })).toBe(
      false,
    );
  });
});

describe("firmLabel", () => {
  const firm = prime.firm;
  it("prefers a short trade name and never a longer former name", () => {
    if (!firm) throw new Error("fixture without a firm");
    expect(firmLabel({ ...firm, name: "XTB S.A.", aliases: ["XTB"] })).toBe("XTB");
    const strom = {
      ...firm,
      name: "MICHAEL/STRÖM DOM MAKLERSKI S.A.",
      aliases: ["MICHAEL/STRÖM DOM MAKLERSKI Sp. z o.o."],
    };
    expect(firmLabel(strom)).toBe("MICHAEL/STRÖM DOM MAKLERSKI S.A.");
  });
});

describe("render rule copy matches the measurement", () => {
  const rule = (id: string, measurements: Record<string, string | number>, viewport = "phone") =>
    ({
      rule_id: id,
      name: id,
      status: "fail",
      confidence: 0.9,
      check_type: "render",
      weight: 0.5,
      explanation: "x",
      legal_basis: "art. 44",
      evidence: [{ quote: null, viewport, bbox: null, measurements }],
    }) as RuleResult;

  it("names only the devices where rule 8 failed", () => {
    expect(problemsOf([rule("8", { failed_viewports: "phone" })])[0]?.title).toBe(
      "Ostrzeżenie nieczytelne na telefonie",
    );
    expect(problemsOf([rule("8", { failed_viewports: "tablet,phone" })])[0]?.title).toBe(
      "Ostrzeżenie nieczytelne na tablecie i telefonie",
    );
    expect(failedDevices(rule("8", {}, "tablet"))).toEqual(["tablet"]);
  });

  it("says 'w dolnej części' for 71% of the page height", () => {
    const text = problemsOf([rule("6", { y_ratio: 0.71 })])[0]?.text ?? "";
    expect(text).toContain("w dolnej części strony (71% wysokości)");
    expect(text).not.toContain("samym dole");
  });
});

describe("plainExplanation", () => {
  const technical =
    "@InwestujZKasia promuje Kyrenia Prime Ltd (sygnały: kod KASIA); reklama nieoznaczona. " +
    "Klasyfikator (embedding bge-m3 + leksykon): p = 0.99; wkład w logit: obietnica zysku +1.2, embedding +0.8.";
  const m1 = { ...prime, module: "m1_third_party_ad", explanation: technical } as Finding;

  it("replaces the classifier sentence with plain Polish for analysts", () => {
    const text = plainExplanation(m1);
    expect(text).not.toMatch(/Klasyfikator|logit|bge-m3|p = /);
    expect(text).toContain("@InwestujZKasia promuje Kyrenia Prime Ltd");
    expect(text).toContain(
      "Wzorzec treści podobny do znanych reklam z linkiem afiliacyjnym lub kodem polecającym (model statystyczny, pewność 0,99).",
    );
  });

  it("names advisory offers for M3 and leaves other text alone", () => {
    const m3 = {
      ...prime,
      module: "m3_shadow_advisory",
      explanation:
        "Elementy doradztwa: a, b. Klasyfikator (leksykon): p = 0.83. Podmiot figuruje na liście.",
    } as Finding;
    expect(plainExplanation(m3)).toBe(
      "Elementy doradztwa: a, b. Wzorzec treści podobny do znanych ofert doradztwa inwestycyjnego bez zezwolenia (model statystyczny, pewność 0,83). Podmiot figuruje na liście.",
    );
    expect(plainExplanation(prime)).toBe(prime.explanation);
  });

  it("is what list rows show", () => {
    expect(describeFinding(m1)).not.toContain("Klasyfikator");
  });

  it("lists each content signal once (findings stored before the ai dedup)", () => {
    const repeated = {
      ...m1,
      explanation:
        "inwestomat.eu promuje XTB S.A. (sygnały: Advertisement, Advertisement, advertisement, z mojego\nlinku, Advertisement); reklama oznaczona.",
    } as Finding;
    expect(plainExplanation(repeated)).toBe(
      "inwestomat.eu promuje XTB S.A. (sygnały: Advertisement, z mojego linku); reklama oznaczona.",
    );
    expect(modelSignalOf({ ...repeated, rules: [] })?.markers).toEqual([
      "Advertisement",
      "z mojego linku",
    ]);
  });
});

describe("modelSignalOf", () => {
  // kontomaniak.pl: a ranking page, high risk from the M1 classifier, every checked rule met.
  const passed = prime.rules
    .filter((rule) => rule.rule_id === "2" || rule.rule_id === "3")
    .map((rule) => ({ ...rule, status: "pass" as const }));
  const ranking = {
    ...prime,
    module: "m1_third_party_ad",
    risk_level: "high",
    score: 1,
    rules: passed,
    explanation:
      "kontomaniak.pl promuje ALIOR BANK S.A., XTB S.A. i inne firmy (razem 5) (sygnały: kod promocyjny: KONTOMANIAK, kod promocyjny: KONTOMANIAK, Otwórz rachunek\nKonto); reklama oznaczona, z ostrzeżeniem o ryzyku. " +
      "Klasyfikator (leksykon): p = 1.00; wkład w logit: wezwanie do działania +5.9, bonus +4.2.",
  } as Finding;

  it("explains a high score without failed rules as a model signal to verify", () => {
    const signal = modelSignalOf(ranking);
    expect(signal).not.toBeNull();
    expect(signal?.title).toBe("Sygnał modelu – do weryfikacji");
    expect(signal?.text).toContain(
      "Wzorzec treści podobny do znanych reklam z linkiem afiliacyjnym lub kodem polecającym (model statystyczny, pewność 1,00).",
    );
    expect(signal?.text).toContain("Żaden ze sprawdzanych wymogów nie jest naruszony");
    expect(signal?.text).not.toMatch(/Klasyfikator|logit/);
  });

  it("quotes the content markers once each, on one line", () => {
    expect(modelSignalOf(ranking)?.markers).toEqual([
      "kod promocyjny: KONTOMANIAK",
      "Otwórz rachunek Konto",
    ]);
  });

  it("says the score comes from the markers when no classifier ran", () => {
    const plain = {
      ...ranking,
      risk_level: "medium",
      explanation: "@kasia promuje Kyrenia Prime Ltd (sygnały: kod KASIA); reklama oznaczona.",
    } as Finding;
    const signal = modelSignalOf(plain);
    expect(signal?.title).toBe("Sygnały w treści – do weryfikacji");
    expect(signal?.text).not.toContain("model statystyczny");
    expect(signal?.markers).toEqual(["kod KASIA"]);
  });

  it("is absent when a rule failed or the risk is low", () => {
    expect(modelSignalOf(prime)).toBeNull();
    expect(modelSignalOf({ ...ranking, risk_level: "low" } as Finding)).toBeNull();
  });
});

describe("firstSentence", () => {
  it("keeps the first whole sentence for list rows", () => {
    expect(
      firstSentence(
        "Ostrzeżenie o ryzyku jest za małe i blade. Do tego: brak nazwy firmy i brak oznaczenia „reklama”.",
      ),
    ).toBe("Ostrzeżenie o ryzyku jest za małe i blade.");
  });

  it("does not break after abbreviations, list letters or inside parentheses", () => {
    const m1 =
      "@kasia promuje Dom Maklerski Wisła Capital S.A. (sygnały: Link w bio. Kod KASIA); reklama oznaczona. Wzorzec treści podobny do znanych reklam.";
    expect(firstSentence(m1)).toBe(
      "@kasia promuje Dom Maklerski Wisła Capital S.A. (sygnały: Link w bio. Kod KASIA); reklama oznaczona.",
    );
    const m3 =
      "Elementy doradztwa inwestycyjnego (art. 76 UoIF): a, c, d. Podmiot nie występuje w rejestrach KNF jako autor publikacji. Wzorzec treści.";
    expect(firstSentence(m3)).toBe(
      "Elementy doradztwa inwestycyjnego (art. 76 UoIF): a, c, d. Podmiot nie występuje w rejestrach KNF jako autor publikacji.",
    );
  });

  it("returns a single sentence unchanged", () => {
    expect(firstSentence("Nie wykryto naruszeń.")).toBe("Nie wykryto naruszeń.");
    expect(firstSentence("Brak opisu")).toBe("Brak opisu");
  });
});
