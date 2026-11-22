/**
 * Turns raw rule results of a finding into plain-language problems (what is wrong, where,
 * measured values) and the model signal shown next to them. Pure functions; all copy comes
 * from i18n/pl.ts.
 */
import type {
  Finding,
  FindingWithPost,
  LlmReviewState,
  RegisteredFirm,
  RuleResult,
  Viewport,
} from "@/api/types";
import { pl } from "@/i18n/pl";
import { formatContrast, formatNumber } from "@/lib/format";

/** Plain-language title of a failed rule ("what is wrong"), by rule id. */
const FAIL_TITLES: Record<string, string> = {
  "1": "Brak nazwy firmy",
  "2": "Brak oznaczenia „reklama”",
  "3": "Brak rzetelnej informacji o ryzyku",
  "4": "Ostrzeżenie jest za małe",
  "5": "Ostrzeżenie jest blade",
  "6": "Ostrzeżenie jest schowane",
  "7": "Ostrzeżenie trzeba rozwinąć",
  "8": "Ostrzeżenie nieczytelne na niektórych urządzeniach",
  "9": "Tekst jest trudny do zrozumienia",
  "10": "Ostrzeżenie w innym języku",
  "11": "Nierzetelne porównanie",
  "12a": "Wyniki z za krótkiego okresu",
  "12b": "Wyniki bez warunków i waluty",
  "13": "Wyniki z przeszłości dominują",
  "14": "Brak ostrzeżenia przy wynikach",
  "15": "Prognoza zysku bez zastrzeżenia",
  "16": "Brak informacji o podatkach",
  "17": "Sugeruje aprobatę KNF",
  "18": "KNF jako gwarancja bezpieczeństwa",
  "76a": "Rekomendacja dla konkretnej osoby",
  "76b": "Dotyczy instrumentów finansowych",
  "76c": "Sygnały „kup” i „sprzedaj”",
  "76d": "Usługa oferowana w Polsce",
  "76e": "Zarządza cudzymi pieniędzmi",
};

/** One-line explanation for the check result, when there is no measurement to quote. */
const SHORT_TEXTS: Record<string, string> = {
  "1": "Nie podano pełnej nazwy firmy.",
  "2": "Materiał nie jest oznaczony jako reklama.",
  "3": "Obietnica zysku bez ostrzeżenia obok.",
  "6": "Daleko od obietnicy zysku, poza pierwszym ekranem.",
  "7": "Na telefonie trzeba je rozwinąć, żeby je zobaczyć.",
  "8": "Na mniejszych ekranach jest nieczytelne albo znika.",
  "9": "Język nie jest dostosowany do klienta detalicznego.",
  "10": "Reklama po polsku, ostrzeżenie w innym języku.",
  "11": "Porównanie bez rzetelnych i aktualnych danych.",
  "12a": "Pokazano wyniki z okresu krótszego niż 5 lat.",
  "12b": "Brak waluty i informacji o opłatach przy wynikach.",
  "13": "Wyniki z przeszłości są najważniejszym elementem.",
  "14": "Brak zastrzeżenia, że wyniki nie gwarantują przyszłych.",
  "15": "Obietnica wyniku bez zastrzeżenia o niepewności.",
  "16": "Brak informacji, że podatki zależą od sytuacji klienta.",
  "17": "Wzmianka o KNF sugeruje, że nadzór poleca ofertę.",
  "18": "Nadzór KNF podany jako gwarancja bezpieczeństwa.",
  "76a": "Porada dobrana do sytuacji konkretnej osoby.",
  "76b": "Dotyczy akcji, ETF-ów lub innych instrumentów.",
  "76c": "Mówi, co kupić, sprzedać albo trzymać.",
  "76d": "Usługa skierowana do klientów w Polsce.",
  "76e": "Proponuje zarządzanie cudzymi pieniędzmi.",
};

/** Short lowercase names for "Sprawdzam jeszcze: …". */
const SHORT_NAMES: Record<string, string> = {
  "2": "oznaczenie reklamy",
  "3": "ostrzeżenie o ryzyku",
  "9": "zrozumiałość",
  "10": "język",
  "11": "porównania",
  "12a": "wyniki historyczne",
  "15": "prognozy",
  "17": "wzmianki o KNF",
  "18": "KNF jako gwarancja",
};

/** One failed requirement as shown to the analyst. */
export interface Problem {
  rule: RuleResult;
  title: string;
  /** Short explanation for the check result list. */
  short: string;
  /** Longer explanation for the finding page. */
  text: string;
  lawShort: string;
  lawLong: string;
  /** Measured or matched in the text: red; judged by the model: amber. */
  severe: boolean;
  /** First located evidence (viewport + bbox), if any. */
  located: { viewport: Viewport; bbox: [number, number, number, number] } | null;
}

const num = (value: number | string | undefined): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

const truthy = (value: number | string | undefined): boolean =>
  value === 1 || value === "true" || value === "True";

/** All measurements of a rule's evidence, merged (first value wins). */
export function measurementsOf(rule: RuleResult): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  for (const evidence of rule.evidence) {
    for (const [key, value] of Object.entries(evidence.measurements ?? {})) {
      if (!(key in out)) out[key] = value;
    }
  }
  return out;
}

const ON_DEVICE: Record<Viewport, string> = {
  desktop: "komputerze",
  tablet: "tablecie",
  phone: "telefonie",
};

/** Devices on which rule 8 failed, from the measurement (older results: evidence viewports). */
export function failedDevices(rule: RuleResult): Viewport[] {
  const listed = measurementsOf(rule).failed_viewports;
  const raw =
    typeof listed === "string"
      ? listed.split(",")
      : rule.evidence.map((e) => e.viewport).filter((v): v is Viewport => Boolean(v));
  const order: Viewport[] = ["desktop", "tablet", "phone"];
  return order.filter((v) => raw.includes(v));
}

/** "na telefonie", "na tablecie i telefonie". */
function onDevices(devices: Viewport[]): string {
  const names = devices.map((d) => ON_DEVICE[d]);
  if (names.length <= 1) return `na ${names[0] ?? "telefonie"}`;
  return `na ${names.slice(0, -1).join(", ")} i ${names[names.length - 1] ?? ""}`;
}

/** WCAG AA minimum for the risk warning (rule 5). */
const MIN_CONTRAST = 4.5;

/**
 * Rule 5 failed for something other than low colour contrast (the warning is covered by another
 * element or see-through): the measured contrast is fine and must not be quoted as the reason.
 */
function weakNotPale(rule: RuleResult): boolean {
  if (rule.rule_id !== "5") return false;
  const contrast = num(measurementsOf(rule).contrast);
  return contrast === undefined || contrast >= MIN_CONTRAST;
}

/** Neutral one-liner for a rule 5 failure that is not about contrast. */
function weakText(rule: RuleResult): string {
  const m = measurementsOf(rule);
  if (truthy(m.occluded)) return pl.finding.weak.occluded;
  const opacity = num(m.opacity);
  if (opacity !== undefined && opacity < 1) return pl.finding.weak.transparent;
  return rule.explanation || pl.finding.weak.other;
}

function titleOf(rule: RuleResult): string {
  if (weakNotPale(rule)) return pl.finding.weak.title;
  if (rule.rule_id === "8") return `Ostrzeżenie nieczytelne ${onDevices(failedDevices(rule))}`;
  return FAIL_TITLES[rule.rule_id] ?? rule.name;
}

function shortText(rule: RuleResult): string {
  const m = measurementsOf(rule);
  const risk = num(m.risk_font_px);
  const main = num(m.dominant_font_px);
  if (rule.rule_id === "4" && risk !== undefined && main !== undefined)
    return `${formatNumber(risk)} px przy tekście strony ${formatNumber(main)} px.`;
  const contrast = num(m.contrast);
  if (weakNotPale(rule)) return weakText(rule);
  if (rule.rule_id === "5" && contrast !== undefined)
    return `Kontrast ${formatContrast(contrast)}, a minimum to 4,5:1.`;
  if (rule.rule_id === "6" && truthy(m.in_footer)) return "W stopce strony.";
  if (rule.rule_id === "8")
    return `Nieczytelne, ucięte lub brak ${onDevices(failedDevices(rule))}.`;
  return SHORT_TEXTS[rule.rule_id] ?? rule.explanation;
}

function longText(rule: RuleResult): string {
  const m = measurementsOf(rule);
  const risk = num(m.risk_font_px);
  const main = num(m.dominant_font_px);
  if (rule.rule_id === "4" && risk !== undefined && main !== undefined)
    return `Ma ${formatNumber(risk)} px, a reszta strony ${formatNumber(main)} px. Ostrzeżenie powinno być co najmniej tak czytelne jak informacja o zysku.`;
  const contrast = num(m.contrast);
  if (weakNotPale(rule)) return weakText(rule);
  if (rule.rule_id === "5" && contrast !== undefined)
    return `Tekst ostrzeżenia ma kontrast z tłem ${formatContrast(contrast)}. Minimum to 4,5:1.`;
  const y = num(m.y_ratio);
  if (rule.rule_id === "6" && y !== undefined && y > 0.6)
    return `Jest w dolnej części strony (${Math.round(y * 100)}% wysokości), daleko od obietnicy zysku.`;
  if (rule.rule_id === "7" && truthy(m.in_collapsed))
    return "Ostrzeżenie jest zwinięte. Żeby je przeczytać, trzeba je najpierw rozwinąć.";
  return rule.explanation;
}

/** "art. 44 ust. 2 lit. c rozporządzenia del. 2017/565" → "Art. 44 ust. 2 lit. c rozporządzenia 2017/565". */
export function lawLong(basis: string): string {
  const text = basis.replace(/\bdel\.\s*/g, "").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** "art. 44 ust. 2 lit. c i e rozporządzenia del. 2017/565" → "art. 44 ust. 2 lit. c, e". */
export function lawShort(basis: string): string {
  return basis
    .replace(/\s+rozporządzenia.*$/i, "")
    .replace(/\s+instrumentami finansowymi.*$/i, "")
    .replace(/ i /g, ", ")
    .trim();
}

/** Failed rules as problems: measured first, then located, then catalogue order. */
export function problemsOf(rules: readonly RuleResult[]): Problem[] {
  return rules
    .filter((rule) => rule.status === "fail")
    .map((rule) => {
      const evidence = rule.evidence.find((e) => e.bbox && e.viewport);
      return {
        rule,
        title: titleOf(rule),
        short: shortText(rule),
        text: longText(rule),
        lawShort: lawShort(rule.legal_basis),
        lawLong: lawLong(rule.legal_basis),
        severe: rule.check_type !== "llm",
        located:
          evidence?.bbox && evidence.viewport
            ? { viewport: evidence.viewport, bbox: evidence.bbox }
            : null,
      };
    })
    .sort(
      (a, b) =>
        Number(b.severe) - Number(a.severe) ||
        Number(Boolean(b.located)) - Number(Boolean(a.located)),
    );
}

/** Rules the model has not settled yet, as short names ("oznaczenie reklamy, prognozy"). */
export function pendingNames(rules: readonly RuleResult[]): string[] {
  return rules
    .filter((rule) => rule.status === "unknown")
    .map((rule) => SHORT_NAMES[rule.rule_id] ?? rule.name.toLocaleLowerCase("pl"));
}

/** Model review state; older backends only say whether the model was used. */
export function llmReviewOf(finding: Finding): LlmReviewState {
  return finding.llm_review ?? (finding.used_llm ? "done" : "none");
}

/**
 * Short display name of a firm: its first alias (trade names come first) when shorter than the
 * registered name, else the registered name. A firm without trade names would otherwise be
 * shown under a former name ("MICHAEL/STRÖM DOM MAKLERSKI Sp. z o.o.").
 */
export function firmLabel(firm: RegisteredFirm): string {
  const alias = firm.aliases[0];
  return alias && alias.length < firm.name.length ? alias : firm.name;
}

/** Who the material is about: advertiser for M1/M3, trade name of the firm for M2. */
export function subjectOf(finding: FindingWithPost): string {
  if (finding.module === "m2_risk_disclosure") {
    return (finding.firm && firmLabel(finding.firm)) ?? finding.post?.author ?? "";
  }
  return finding.advertiser ?? finding.post?.author ?? finding.firm?.name ?? "";
}

const HIDDEN_RISK = new Set(["4", "5", "6", "7", "8"]);

/**
 * Page title of a finding, e.g. "PrimeFX24 ukrywa ostrzeżenie o ryzyku". A real firm's finding
 * that no analyst confirmed yet is phrased as a possibility; a score from the model alone (no
 * failed requirement) is titled as a signal to verify. Fictional demo firms keep the plain title.
 */
export function headlineOf(finding: FindingWithPost): string {
  const name = subjectOf(finding);
  const h = pl.finding.headline;
  const failed = finding.rules.filter((rule) => rule.status === "fail");
  // M1/M3 risk often comes from the classifier score alone (no failed rule): a high or medium
  // finding is never titled "bez naruszeń".
  if (failed.length === 0 && finding.risk_level === "low") return h.compliant(name);
  const confirmed = finding.status === "confirmed";
  if (failed.length === 0 && !confirmed) return h.signal(name, h.signalTopic[finding.module]);
  const t = confirmed || finding.firm?.fictional === true ? h : h.possible;
  switch (finding.module) {
    case "m2_risk_disclosure":
      return failed.some((rule) => HIDDEN_RISK.has(rule.rule_id))
        ? t.hiddenRisk(name)
        : t.riskInfo(name);
    case "m1_third_party_ad": {
      const firm = finding.firm ? firmLabel(finding.firm) : undefined;
      return firm ? t.thirdPartyFirm(name, firm) : t.thirdParty(name);
    }
    default:
      return t.advisory(name);
  }
}

/** Font sizes and contrast measured on the risk warning (for the screenshot strip). */
export interface WarningMeasures {
  warningPx?: number;
  pagePx?: number;
  contrast?: number;
  fontFailed: boolean;
  contrastFailed: boolean;
  /** "w stopce" when the warning sits in the footer. */
  inFooter: boolean;
}

/** Measurements of the risk warning across the render rules of a finding. */
export function warningMeasures(rules: readonly RuleResult[]): WarningMeasures {
  const out: WarningMeasures = { fontFailed: false, contrastFailed: false, inFooter: false };
  for (const rule of rules) {
    const m = measurementsOf(rule);
    out.warningPx ??= num(m.risk_font_px);
    out.pagePx ??= num(m.dominant_font_px);
    out.contrast ??= num(m.contrast);
    if (truthy(m.in_footer)) out.inFooter = true;
    if (rule.status === "fail" && num(m.risk_font_px) !== undefined) out.fontFailed = true;
    if (rule.status === "fail" && (num(m.contrast) ?? MIN_CONTRAST) < MIN_CONTRAST)
      out.contrastFailed = true;
  }
  return out;
}

const GENITIVE: Record<string, string> = {
  AT: "Austrii",
  BE: "Belgii",
  BG: "Bułgarii",
  CY: "Cypru",
  CZ: "Czech",
  DE: "Niemiec",
  DK: "Danii",
  EE: "Estonii",
  ES: "Hiszpanii",
  FI: "Finlandii",
  FR: "Francji",
  GB: "Wielkiej Brytanii",
  GR: "Grecji",
  HR: "Chorwacji",
  HU: "Węgier",
  IE: "Irlandii",
  IS: "Islandii",
  IT: "Włoch",
  LI: "Liechtensteinu",
  LT: "Litwy",
  LU: "Luksemburga",
  LV: "Łotwy",
  MT: "Malty",
  NL: "Holandii",
  NO: "Norwegii",
  PL: "Polski",
  PT: "Portugalii",
  RO: "Rumunii",
  SE: "Szwecji",
  SI: "Słowenii",
  SK: "Słowacji",
};

/** "CY" → "Cypru" (for "Firma z Cypru"); null when unknown. */
export const countryGenitive = (code: string | null): string | null =>
  code ? (GENITIVE[code.toUpperCase()] ?? null) : null;

const WARNING_ADJECTIVES = pl.finding.summary.warningAdjectives;

const joinPl = (parts: string[]): string =>
  parts.length <= 1
    ? (parts[0] ?? "")
    : `${parts.slice(0, -1).join(", ")} ${pl.finding.summary.and} ${parts.at(-1)}`;

/**
 * One plain sentence about what is wrong, built from the problems, e.g. "Ostrzeżenie o ryzyku
 * jest za małe, blade i schowane. Do tego: brak oznaczenia „reklama”."
 */
export function summaryOf(problems: readonly Problem[]): string {
  const warning = problems
    .map((p) =>
      weakNotPale(p.rule) ? pl.finding.weak.adjective : WARNING_ADJECTIVES[p.rule.rule_id],
    )
    .filter((a): a is string => Boolean(a));
  const others = problems
    .filter((p) => !WARNING_ADJECTIVES[p.rule.rule_id])
    .slice(0, warning.length ? 2 : 3)
    .map((p) => p.title.charAt(0).toLocaleLowerCase("pl") + p.title.slice(1));
  const sentences: string[] = [];
  if (warning.length) sentences.push(pl.finding.summary.warning(joinPl(warning)));
  if (others.length) {
    const list = joinPl(others);
    sentences.push(
      warning.length
        ? pl.finding.summary.also(list)
        : `${list.charAt(0).toLocaleUpperCase("pl")}${list.slice(1)}.`,
    );
  }
  return sentences.join(" ");
}

/**
 * The material was published by a registered firm itself (its own domain or account), not by
 * a page that only claims to be the firm ("domena spoza rejestru"). Such findings are shown as
 * a possible violation for the analyst to verify (ADR 0009).
 */
export function isSupervisedPublisher(finding: Finding): boolean {
  const match = finding.firm_match;
  return (
    finding.module === "m2_risk_disclosure" &&
    match?.on === "author" &&
    finding.firm?.fictional !== true &&
    !match.matched_text.includes("domena spoza rejestru")
  );
}

/** The model/rules explanation when it reads as prose; null for the rule-list format. */
export function proseExplanation(explanation: string): string | null {
  const text = explanation.trim();
  if (
    !text ||
    /^naruszenia:/i.test(text) ||
    /\b\d+[ab]? [A-ZŁŚŻŹ][^;]*;/.test(text) ||
    text.includes(" · ")
  )
    return null;
  return text;
}

/**
 * The classifier's sentence as the `ai` service writes it ("Klasyfikator (embedding bge-m3 +
 * leksykon): p = 0.99; wkład w logit: ..."). Decimals never have a space after the dot; the
 * sentence end does.
 */
const CLASSIFIER_SENTENCE = /Klasyfikator \([^)]*\): p = (\d+(?:\.\d+)?)(?:[^.]|\.(?!\s|$))*\./;

/**
 * The finding explanation for analysts: the classifier's technical sentence becomes plain Polish
 * ("Wzorzec treści podobny do ..., pewność 0,99"); the technical one stays in "Pod maską".
 */
export function plainExplanation(finding: Finding): string {
  return finding.explanation
    .replace(NO_ELEMENTS, "")
    .replace(/o zysku o ryzyku/g, "o zysku ani o ryzyku")
    .replace(NOT_RATED, (_sentence, n: string) => pl.finding.notRated(Number(n)))
    .replace(CLASSIFIER_SENTENCE, (_sentence, p: string) =>
      pl.finding.classifierPlain[finding.module](Number(p).toFixed(2).replace(".", ",")),
    )
    .replace(MARKERS, (_list, listed: string) => `(sygnały: ${uniqueMarkers(listed).join(", ")})`);
}

const MARKERS = /\(sygnały: ([^)]*)\)/;
/** "Elementy doradztwa … (art. 76 UoIF): brak." says nothing to the analyst: dropped on display. */
const NO_ELEMENTS = /Elementy doradztwa inwestycyjnego \(art\. 76 UoIF\): brak\.\s*/;
/** The `ai` service writes "Nie oceniono 1 reguł." for every count. */
const NOT_RATED = /Nie oceniono (\d+) reguł\./;
const MAX_MARKERS = 3;

/**
 * The `ai` service's marker list, each marker once (ignoring case and line breaks): a ranking
 * page repeats its "Advertisement" label on every row.
 */
function uniqueMarkers(listed: string): string[] {
  const unique = new Map<string, string>();
  for (const raw of listed.split(", ")) {
    const marker = raw.replace(/\s+/g, " ").trim();
    const key = marker.toLowerCase();
    if (marker && !unique.has(key)) unique.set(key, marker);
  }
  return [...unique.values()];
}

/** Why a high or medium finding without a failed requirement scored high. */
export interface ModelSignal {
  title: string;
  /** Plain explanation: model certainty (or the markers), that no rule failed, what to check. */
  text: string;
  /** Promotion markers the `ai` service quoted ("kod promocyjny: X"), one line each. */
  markers: string[];
}

/**
 * The finding's risk comes from a signal (the classifier or content markers), not from a failed
 * requirement: say so instead of "Nie znaleziono problemów" next to "Wysokie ryzyko". Null when
 * a requirement failed or the risk is low.
 */
export function modelSignalOf(finding: Finding): ModelSignal | null {
  if (finding.risk_level === "low" || finding.rules.some((rule) => rule.status === "fail"))
    return null;
  const s = pl.finding.signal;
  const p = CLASSIFIER_SENTENCE.exec(finding.explanation)?.[1];
  const listed = MARKERS.exec(finding.explanation)?.[1] ?? "";
  const markers = uniqueMarkers(listed).slice(0, MAX_MARKERS);
  const first =
    p === undefined
      ? s.markersOnly
      : pl.finding.classifierPlain[finding.module](Number(p).toFixed(2).replace(".", ","));
  return {
    title: p === undefined ? s.title.markers : s.title.model,
    text: `${first} ${s.notRule} ${s.check[finding.module]}`,
    markers,
  };
}

/**
 * The first whole sentence of a description, for list rows (the rest is on the finding page and
 * in the row's tooltip). Breaks only after a word of two or more lowercase letters, outside
 * parentheses, before a capital: never after "S.A.", "art.", a list letter ("a, b.") or a URL.
 */
export function firstSentence(text: string): string {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "(" || c === "[") depth++;
    else if ((c === ")" || c === "]") && depth > 0) depth--;
    else if (
      depth === 0 &&
      (c === "." || c === "!" || c === "?") &&
      /^\s+[A-ZĄĆĘŁŃÓŚŹŻ@„"]/u.test(text.slice(i + 1, i + 3)) &&
      /\p{Ll}{2}$/u.test(text.slice(0, i))
    )
      return text.slice(0, i + 1);
  }
  return text;
}

/** Plain one-line description of a finding for lists and notifications. */
export function describeFinding(finding: Finding): string {
  return (
    proseExplanation(plainExplanation(finding)) ??
    (summaryOf(problemsOf(finding.rules)) || plainExplanation(finding))
  );
}
