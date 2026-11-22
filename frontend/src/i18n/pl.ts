/**
 * All user-facing Polish copy. The UI is Polish-only; components read strings from here
 * instead of hard-coding them, so wording changes stay in one place.
 */
import type {
  FirmKind,
  LlmReviewState,
  ModuleId,
  Platform,
  RegisterState,
  RiskLevel,
  Status,
  TrendBucket,
  Viewport,
} from "@/api/types";
import { count, formatInt, plural } from "@/lib/plural";

/** Plural forms used across the UI: [1, 2–4, 5+]. */
export const nouns = {
  problem: ["problem", "problemy", "problemów"],
  material: ["materiał", "materiały", "materiałów"],
  source: ["źródło", "źródła", "źródeł"],
  requirement: ["wymóg", "wymogi", "wymogów"],
  falseAlarm: ["fałszywy alarm", "fałszywe alarmy", "fałszywych alarmów"],
  finding: ["zgłoszenie", "zgłoszenia", "zgłoszeń"],
  compliant: ["zgodny materiał", "zgodne materiały", "zgodnych materiałów"],
  firm: ["firma", "firmy", "firm"],
  day: ["dzień", "dni", "dni"],
  violation: ["naruszenie", "naruszenia", "naruszeń"],
  fictionalFirm: ["fikcyjną firmę", "fikcyjne firmy", "fikcyjnych firm"],
  entity: ["podmiot", "podmioty", "podmiotów"],
  result: ["wynik", "wyniki", "wyników"],
  occurrence: ["wystąpienie", "wystąpienia", "wystąpień"],
  /** Genitive after a negation ("Nie oceniono 1 reguły", "… 5 reguł"). */
  ruleGenitive: ["reguły", "reguł", "reguł"],
} as const satisfies Record<string, readonly [string, string, string]>;

/** Polish UI copy. Components never hard-code user-facing strings. */
/** How a fictional demo firm is shown everywhere a registered one would say "z rejestru KNF". */
const FICTIONAL_FIRM = "Firma fikcyjna (demo) – udaje wpis w rejestrze KNF";
/** The same as a tag that never gets cut; the full sentence goes in its tooltip. */
const FICTIONAL_FIRM_TAG = "Firma fikcyjna (demo)";

export const pl = {
  appName: "InvestWatch",
  nav: {
    label: "Główna",
    check: "Sprawdź",
    review: "Do przejrzenia",
    entities: "Agregator wyników",
    monitoring: "Monitoring",
    sensitivity: "Czułość",
    registry: "Rejestr KNF",
    live: "Na żywo",
    offline: "Brak połączenia",
    mock: "Dane przykładowe",
  },
  common: {
    loading: "Wczytuję…",
    error: "Nie udało się wczytać danych.",
    retry: "Spróbuj ponownie",
    open: "Otwórz",
    close: "Zamknij",
    cancel: "Anuluj",
    dash: "–",
    never: "nigdy",
    today: "dziś",
    yesterday: "wczoraj",
    justNow: "przed chwilą",
    minutesAgo: (n: number) => `${n} min temu`,
    hoursAgo: (n: number) => `${n} godz. temu`,
    daysAgo: (n: number) => `${count(n, nouns.day)} temu`,
  },
  modules: {
    m1_third_party_ad: "Reklamy osób trzecich",
    m2_risk_disclosure: "Informacja o ryzyku",
    m3_shadow_advisory: "Doradztwo bez zezwolenia",
  } satisfies Record<ModuleId, string>,
  moduleTabs: {
    m1_third_party_ad: "Reklamy osób trzecich",
    m2_risk_disclosure: "Informacja o ryzyku",
    m3_shadow_advisory: "Doradztwo bez zezwolenia",
  } satisfies Record<ModuleId, string>,
  sensitivityTabs: {
    m1_third_party_ad: "Reklamy osób trzecich",
    m2_risk_disclosure: "Informacja o ryzyku",
    m3_shadow_advisory: "Doradztwo bez zezwolenia",
  } satisfies Record<ModuleId, string>,
  platforms: {
    web: "Strona WWW",
    facebook: "Facebook",
    instagram: "Instagram",
    tiktok: "TikTok",
    youtube: "YouTube",
    bing: "Bing (reklama)",
    sample: "Próbka UKNF",
  } satisfies Record<Platform, string>,
  platformLong: {
    web: "Strona internetowa",
    facebook: "Post na Facebooku",
    instagram: "Post na Instagramie",
    tiktok: "Film na TikToku",
    youtube: "Film na YouTube",
    bing: "Reklama w wyszukiwarce Bing (Microsoft Ad Library)",
    sample: "Próbka UKNF",
  } satisfies Record<Platform, string>,
  risk: {
    high: "Wysokie",
    medium: "Średnie",
    low: "Niskie",
  } satisfies Record<RiskLevel, string>,
  riskCards: {
    high: "Wysokie ryzyko",
    medium: "Średnie ryzyko",
    low: "Niskie ryzyko",
  } satisfies Record<RiskLevel, string>,
  statuses: {
    new: "Nowe",
    in_review: "W trakcie",
    confirmed: "Potwierdzone naruszenie",
    dismissed: "Oznaczone jako zgodne",
  } satisfies Record<Status, string>,
  viewports: {
    desktop: "Komputer",
    tablet: "Tablet",
    phone: "Telefon",
  } satisfies Record<Viewport, string>,
  firmKinds: {
    dom_maklerski: "Dom maklerski",
    bank_maklerski: "Bank z działalnością maklerską",
    oddzial_zagraniczny: "Oddział firmy zagranicznej",
    zagraniczna_bez_oddzialu: "Firma zagraniczna bez oddziału",
  } satisfies Record<FirmKind, string>,
  firmKindsPlural: {
    dom_maklerski: "Domy maklerskie",
    bank_maklerski: "Banki z działalnością maklerską",
    oddzial_zagraniczny: "Oddziały firm zagranicznych",
    zagraniczna_bez_oddzialu: "Firmy zagraniczne bez oddziału",
  } satisfies Record<FirmKind, string>,
  llmReview: {
    none: "Ocena modelu: niepotrzebna",
    queued: "Ocena modelu: w kolejce",
    done: "Ocena modelu: gotowa",
    unavailable: "Ocena modelu niedostępna: wynik z reguł",
  } satisfies Record<LlmReviewState, string>,

  check: {
    title: "Sprawdź stronę lub reklamę",
    lead: "Wklej adres. W kilka sekund zobaczysz, kto reklamuje, czy firma jest w rejestrze KNF i czy ostrzeżenie o ryzyku jest pokazane zgodnie z przepisami.",
    inputLabel: "Adres do sprawdzenia",
    placeholder: "https://",
    submit: "Sprawdź",
    invalidUrl: "Wpisz pełny adres strony, np. https://firma.pl/oferta",
    submitError: "Nie udało się rozpocząć sprawdzania.",
    examples: "Przykłady:",
    progress: "Postęp",
    progressCount: (done: number, total: number, seconds: string) =>
      `${done} z ${total} · ${seconds} s`,
    steps: {
      fetch: { run: "Pobieram stronę", done: "Pobrano stronę", wait: "Pobranie strony" },
      firm: {
        run: "Rozpoznaję firmę",
        done: "Rozpoznano firmę",
        wait: "Rozpoznanie firmy",
      },
      shots: { run: "Robię zrzuty", done: "Zrobiono zrzuty", wait: "Zrzuty strony" },
      measure: {
        run: "Mierzę ostrzeżenie",
        done: "Zmierzono ostrzeżenie",
        wait: "Pomiar ostrzeżenia",
      },
      llm: {
        run: "Model językowy czyta tekst",
        done: "Model językowy przeczytał tekst",
        wait: "Model językowy",
        queued: "Model językowy: w kolejce",
        skipped: "Model językowy pominięty",
      },
      final: { run: "Wynik końcowy", done: "Wynik końcowy", wait: "Wynik końcowy" },
    },
    detail: {
      fetchRun: "Zwykle ok. 1 sekundy",
      fetchDone: (domain: string, seconds: string) => `${domain} · ${seconds} s`,
      firmRun: "Szukam w rejestrze KNF",
      firmFound: (name: string) => `${name} z rejestru KNF`,
      firmFictional: (name: string) => `${name} · firma fikcyjna (demo)`,
      firmMissing: "Brak tej firmy w rejestrze KNF",
      firmNone: "Nie wskazano firmy inwestycyjnej",
      shotsRun: "Komputer, tablet i telefon",
      shots: (names: string[]) => names.join(", ").replace(/, ([^,]*)$/, " i $1"),
      shotsNone: "Ten materiał nie ma zrzutów",
      measureRun: "Wielkość, kontrast i położenie",
      measureNone: "Nie znaleziono ostrzeżenia o ryzyku",
      measureRules: (n: number) => `Sprawdzono ${count(n, nouns.requirement)}`,
      llmRun: "Czyta teraz, zwykle 10–20 sekund",
      llmWaiting: "Czeka na model językowy",
      llmQueued: (ahead: number) =>
        ahead > 0 ? `Czeka w kolejce (${ahead} przed)` : "Następna w kolejce",
      llmDone: (model: string, seconds: string | null) =>
        seconds ? `${model} · ${seconds} s` : model,
      llmNone: "Reguły wystarczyły",
      llmUnavailable: "Ocena modelu niedostępna: wynik z reguł",
      finalWait: "Pojawi się tutaj i w zgłoszeniach",
      finalDone: "Zapisano w zgłoszeniach",
      finalDuplicate: "Ta sama treść była już sprawdzana",
      failed: "Nie udało się",
    },
    pendingTitle: "Trwa sprawdzanie",
    pendingHeadline: "Analizuję stronę",
    pendingText: "Pierwsze wyniki pojawią się za kilka sekund.",
    preliminary: "Wynik wstępny (czeka na ocenę modelu)",
    final: "Wynik",
    /** Risk headlines come from `finding.banner`, so "Sprawdź" and the finding agree. */
    headline: {
      low: "Nie znaleziono naruszeń",
    },
    llmPendingSuffix: (n: number) =>
      n > 0
        ? `Model językowy sprawdza jeszcze ${count(n, nouns.requirement)}.`
        : "Model językowy jeszcze czyta tekst.",
    failedTitle: "Nie udało się sprawdzić",
    failedHeadline: "Strona nie została sprawdzona",
    failedReasons: {
      blocked: "Strona nie pozwala na automatyczne pobieranie (robots.txt lub blokada).",
      error: "Strona nie odpowiada albo zwróciła błąd.",
      no_text: "Na stronie nie ma tekstu do sprawdzenia.",
      other: "Spróbuj ponownie za chwilę.",
    },
    duplicateHeadline: "Ten materiał był już sprawdzany",
    duplicateText: "Treść się nie zmieniła, więc nie powstało nowe zgłoszenie.",
    who: "Kto reklamuje",
    ownSite: "Strona własna firmy",
    thirdParty: "Osoba trzecia, nie sama firma",
    registry: "Rejestr KNF",
    registryChecking: "Sprawdzam…",
    registryMissing: "Brak w rejestrze",
    registryFictional: FICTIONAL_FIRM,
    registryMissingText: "Podmiot nie ma zezwolenia KNF",
    registryNone: "Nie dotyczy",
    registryNoneText: "Materiał nie wskazuje firmy inwestycyjnej",
    firmFrom: (countryGenitive: string | null, kind: FirmKind) => {
      const where = countryGenitive ? `Firma z ${countryGenitive}` : "Firma zagraniczna";
      switch (kind) {
        case "zagraniczna_bez_oddzialu":
          return `${where}, działa w Polsce bez oddziału`;
        case "oddzial_zagraniczny":
          return `${where}, ma oddział w Polsce`;
        case "bank_maklerski":
          return "Bank z działalnością maklerską";
        default:
          return "Dom maklerski";
      }
    },
    stillChecking: (names: string) => `Sprawdzam jeszcze: ${names}`,
    noProblems: "Wszystkie sprawdzone wymogi są spełnione.",
    openFinding: "Otwórz zgłoszenie",
    seeShots: "Zobacz zrzuty strony",
    doneToast: "Gotowe",
    doneToastText: (headline: string) => headline,
  },

  demoBadge: {
    synthetic: "dane syntetyczne",
    syntheticHint:
      "Materiał fikcyjny przygotowany do demonstracji, nie pochodzi z realnego źródła.",
    fictionalFirm: "firma fikcyjna (demo)",
    fictionalFirmHint: "Firma dodana do demonstracji, nie występuje w rejestrach KNF.",
    youtubeNote:
      "Ocena InvestWatch, nie pochodzi z YouTube. Dane pobrane przez YouTube API Services.",
    youtubePrivacy: "Polityka prywatności Google",
  },
  review: {
    title: "Do przejrzenia",
    lead: (n: number) =>
      n === 0
        ? "Nic nie czeka na decyzję."
        : `${count(n, nouns.material)} ${plural(n, ["czeka", "czekają", "czeka"])} na decyzję. Najpoważniejsze są na górze.`,
    csv: "Pobierz raport CSV",
    all: "Wszystkie",
    search: "Szukaj",
    searchPlaceholder: "Szukaj firmy lub autora",
    columns: {
      risk: "Ryzyko",
      material: "Materiał i problem",
      kind: "Rodzaj",
      source: "Źródło",
      detected: "Wykryto",
    },
    empty: "Brak materiałów dla wybranych filtrów.",
    showMore: (n: number) => `Pokaż kolejne (${n})`,
    occurrences: (n: number) => count(n, nouns.occurrence),
    filterRisk: (label: string) => `Pokaż tylko: ${label}`,
    truncated: (shown: number, total: number) =>
      `Pokazuję ${formatInt(shown)} najpoważniejszych z ${formatInt(total)}. Zawęź filtry, żeby zobaczyć resztę.`,
    statusMenu: "Zmień status",
    statusMenuTitle: "Status zgłoszenia",
    openFinding: "Otwórz zgłoszenie",
    statusTag: {
      new: "Nowe",
      in_review: "W trakcie",
      confirmed: "Potwierdzone",
      dismissed: "Odrzucone",
    } satisfies Record<Status, string>,
    statusOptions: {
      new: "Nowe",
      in_review: "W trakcie",
      confirmed: "Potwierdź naruszenie",
      dismissed: "Odrzuć (to nie naruszenie)",
    } satisfies Record<Status, string>,
    trend: {
      title: "Wykryte naruszenia w czasie",
      /** Honest label of what the chart shows (hourly when all data is from the last 48 h). */
      period: (bucket: TrendBucket, n: number) =>
        bucket === "hour"
          ? `Ostatnie ${formatInt(n)} h, co godzinę`
          : bucket === "week"
            ? `Ostatnie ${formatInt(n)} tygodni`
            : `Ostatnie ${formatInt(n)} dni`,
      total: (n: number) => `razem ${formatInt(n)}`,
      high: "Wysokie ryzyko",
      medium: "Średnie ryzyko",
      sum: "Razem",
      day: "Dzień",
      hour: "Godzina",
      error: "Nie udało się wczytać trendu.",
      summary: (
        bucket: TrendBucket,
        n: number,
        total: number,
        high: number,
        medium: number,
        peak: string | null,
        peakN: number,
      ) => {
        const span =
          bucket === "hour"
            ? `w ostatnich ${formatInt(n)} h`
            : `w ostatnich ${formatInt(n)} dniach`;
        const when = bucket === "hour" ? `o ${peak ?? ""}` : `dnia ${peak ?? ""}`;
        return total === 0
          ? `Wykres: ${span} nie wykryto naruszeń.`
          : `Wykres: ${span} wykryto ${count(total, nouns.violation)}: ${formatInt(high)} wysokiego i ${formatInt(medium)} średniego ryzyka. Najwięcej, ${formatInt(peakN)}, ${when}.`;
      },
    },
    csvHeader: [
      "Ryzyko",
      "Wynik",
      "Rodzaj",
      "Materiał",
      "Problem",
      "Źródło",
      "Adres",
      "Wykryto",
      "Status",
    ],
  },

  filters: {
    label: "Filtry wyników",
    period: "Okres",
    source: "Źródło",
    risk: "Ryzyko",
    status: "Status",
    any: "Wszystkie",
    anySource: "Wszystkie źródła",
    clear: "Wyczyść filtry",
    results: (n: number) => count(n, nouns.result),
    periods: {
      all: "Cały okres",
      today: "Dziś",
      "7d": "Ostatnie 7 dni",
      "30d": "Ostatnie 30 dni",
      custom: "Własny zakres",
    },
    from: "Od",
    to: "Do",
    apply: "Zastosuj",
    range: (from: string, to: string) => `${from} – ${to}`,
    since: (from: string) => `od ${from}`,
    until: (to: string) => `do ${to}`,
    sources: (first: string, more: number) => (more > 0 ? `${first} +${more}` : first),
    statuses: {
      open: "Do decyzji",
      new: "Nowe",
      in_review: "W trakcie",
      confirmed: "Potwierdzone",
      dismissed: "Odrzucone",
      all: "Wszystkie",
    },
    statusHints: {
      open: "nowe i w trakcie",
      all: "także rozpatrzone",
    } as Partial<Record<string, string>>,
  },

  entities: {
    title: "Agregator wyników",
    lead: "Jeden obiekt na podmiot: zgłoszenia z modułów M1, M2 i M3 połączone po firmie lub reklamodawcy, ze statusem w rejestrze KNF i na liście ostrzeżeń.",
    count: (n: number) => count(n, nouns.entity),
    search: "Szukaj podmiotu",
    searchPlaceholder: "Szukaj firmy lub autora",
    stats: {
      entities: "Podmioty",
      inRegister: "Z rejestru KNF",
      warning: "Na liście ostrzeżeń KNF",
      multi: "W kilku modułach",
    },
    columns: {
      entity: "Podmiot",
      risk: "Najwyższe ryzyko",
      occurrences: "Wystąpienia",
      latest: "Ostatnio",
    },
    moduleShort: {
      m1_third_party_ad: "M1",
      m2_risk_disclosure: "M2",
      m3_shadow_advisory: "M3",
    } satisfies Record<ModuleId, string>,
    moduleLegend: "M1 reklamy osób trzecich · M2 informacja o ryzyku · M3 doradztwo bez zezwolenia",
    kind: {
      firm: "Firma",
      advertiser: "Reklamodawca lub autor",
    },
    register: {
      knf: "W rejestrze KNF",
      fictional: FICTIONAL_FIRM_TAG,
      absent: "Brak w rejestrze KNF",
    },
    /** Tooltip of the register tag where the tag alone says less than the full sentence. */
    registerHint: {
      fictional: FICTIONAL_FIRM,
    } as Partial<Record<RegisterState, string>>,
    warning: "Lista ostrzeżeń KNF",
    open: (n: number) => (n > 0 ? `${formatInt(n)} do decyzji` : "rozpatrzone"),
    platforms: (first: string, more: number) => (more > 0 ? `${first} +${more}` : first),
    empty: "Brak podmiotów dla wybranych filtrów.",
    truncated: "Wynik obejmuje tylko część zgłoszeń; zawęź filtry.",
    back: "Agregator wyników",
    notFound: "Nie ma takiego podmiotu.",
    detail: {
      findings: "Zgłoszenia",
      findingsDetail: (open: number, confirmed: number) =>
        `${formatInt(open)} do decyzji, ${formatInt(confirmed)} potwierdzone`,
      risk: "Najwyższe ryzyko",
      riskDetail: (score: string) => `najwyższy wynik ${score}`,
      occurrences: "Wystąpienia",
      seen: "Widziany",
      seenDetail: (first: string) => `pierwszy raz ${first}`,
      timeline: "Oś czasu",
      timelineLead: "Wszystkie zgłoszenia podmiotu, od najnowszego. Kliknij, żeby otworzyć.",
      columns: {
        date: "Data",
        risk: "Ryzyko",
        material: "Materiał i problem",
        kind: "Rodzaj",
        source: "Źródło",
        status: "Status",
      },
      openRegister: "Otwórz w rejestrze KNF",
    },
  },

  finding: {
    back: "Do przejrzenia",
    deleted: "Zgłoszenie usunięte (np. po resecie demo)",
    deletedText: "To zgłoszenie już nie istnieje. Aktualne zgłoszenia są na liście do przejrzenia.",
    deletedLink: "Wróć do listy zgłoszeń",
    headline: {
      hiddenRisk: (name: string) => `${name} ukrywa ostrzeżenie o ryzyku`,
      riskInfo: (name: string) => `${name}: braki w informacji o ryzyku`,
      thirdParty: (name: string) => `${name} reklamuje firmę inwestycyjną`,
      thirdPartyFirm: (name: string, firm: string) => `${name} reklamuje ${firm}`,
      advisory: (name: string) => `${name} oferuje doradztwo bez zezwolenia`,
      compliant: (name: string) => `${name}: bez naruszeń`,
      /** Real firm, not yet confirmed by an analyst: a possibility, not a statement of fact. */
      possible: {
        hiddenRisk: (name: string) => `${name}: ostrzeżenie o ryzyku może być ukryte`,
        riskInfo: (name: string) => `${name}: możliwe braki w informacji o ryzyku`,
        thirdParty: (name: string) => `${name}: możliwa reklama firmy inwestycyjnej`,
        thirdPartyFirm: (name: string, firm: string) => `${name}: możliwa reklama ${firm}`,
        advisory: (name: string) => `${name}: możliwe doradztwo bez zezwolenia`,
      },
      /** Risk from the model alone (no failed requirement): a signal to verify. */
      signal: (name: string, topic: string) => `${name}: sygnał do weryfikacji (${topic})`,
      signalTopic: {
        m1_third_party_ad: "reklama firmy inwestycyjnej",
        m2_risk_disclosure: "informacja o ryzyku",
        m3_shadow_advisory: "doradztwo bez zezwolenia",
      } satisfies Record<ModuleId, string>,
    },
    /** "Nie oceniono N reguł." from the `ai` service, with the right plural form. */
    notRated: (n: number) => `Nie oceniono ${count(n, nouns.ruleGenitive)}.`,
    /** Plain replacement of the classifier's technical sentence (details stay in "Pod maską"). */
    classifierPlain: {
      m1_third_party_ad: (certainty: string) =>
        `Wzorzec treści podobny do znanych reklam z linkiem afiliacyjnym lub kodem polecającym (model statystyczny, pewność ${certainty}).`,
      m2_risk_disclosure: (certainty: string) =>
        `Wzorzec treści podobny do znanych materiałów bez rzetelnej informacji o ryzyku (model statystyczny, pewność ${certainty}).`,
      m3_shadow_advisory: (certainty: string) =>
        `Wzorzec treści podobny do znanych ofert doradztwa inwestycyjnego bez zezwolenia (model statystyczny, pewność ${certainty}).`,
    },
    detected: (date: string) => `wykryto ${date}`,
    dismiss: "To nie naruszenie",
    confirm: "Potwierdź naruszenie",
    confirmed: "Naruszenie potwierdzone",
    dismissed: "Oznaczono jako zgodne",
    undo: "Cofnij decyzję",
    statusSaved: "Zapisano decyzję",
    statusError: "Nie udało się zapisać decyzji.",
    banner: {
      // n = 0: the score comes from the classifier, not from failed rules ("0 problemów" read
      // as a contradiction next to "Wysokie ryzyko").
      high: (n: number) =>
        n === 0
          ? "Wysokie ryzyko naruszenia"
          : `Wysokie ryzyko naruszenia: ${count(n, nouns.problem)}`,
      medium: (n: number) =>
        n === 0
          ? "Średnie ryzyko naruszenia"
          : `Średnie ryzyko naruszenia: ${count(n, nouns.problem)}`,
      low: (n: number) =>
        n === 0 ? "Niskie ryzyko: brak naruszeń" : `Niskie ryzyko: ${count(n, nouns.problem)}`,
    },
    riskScore: "wynik ryzyka",
    /** Material published by a firm from the KNF registers (its own site or account). */
    supervisedNote: "Firma z rejestru KNF · możliwe naruszenie – do weryfikacji przez analityka",
    fictionalNote: `${FICTIONAL_FIRM} · możliwe naruszenie – do weryfikacji przez analityka`,
    summary: {
      warningAdjectives: {
        "4": "za małe",
        "5": "blade",
        "6": "schowane",
        "7": "zwinięte",
        "8": "nieczytelne na telefonie",
      } as Record<string, string>,
      and: "i",
      warning: (list: string) => `Ostrzeżenie o ryzyku jest ${list}.`,
      also: (list: string) => `Do tego: ${list}.`,
    },
    /** Rule 5 failed although the contrast is fine (covered or see-through warning). */
    weak: {
      title: "Ostrzeżenie jest słabo widoczne",
      adjective: "słabo widoczne",
      occluded: "Tekst ostrzeżenia jest przesłonięty innym elementem.",
      transparent: "Tekst ostrzeżenia jest półprzezroczysty.",
      other: "Ostrzeżenie jest słabo eksponowane.",
    },
    problems: "Problemy",
    noProblems: "Nie znaleziono problemów.",
    /** High / medium risk without a failed requirement: the score comes from a signal. */
    signal: {
      title: {
        model: "Sygnał modelu – do weryfikacji",
        markers: "Sygnały w treści – do weryfikacji",
      },
      markersOnly: "Wynik ryzyka pochodzi ze znaczników w treści.",
      notRule:
        "Żaden ze sprawdzanych wymogów nie jest naruszony, więc to sygnał, a nie stwierdzone naruszenie.",
      check: {
        m1_third_party_ad:
          "Sprawdź, czy autor zarabia na polecaniu firmy (link afiliacyjny, kod polecający, prowizja).",
        m2_risk_disclosure: "Sprawdź ręcznie informację o ryzyku w materiale.",
        m3_shadow_advisory:
          "Sprawdź, czy autor udziela porad dopasowanych do klienta albo mówi, co kupić lub sprzedać.",
      } satisfies Record<ModuleId, string>,
      markers: "Znalezione w treści",
      foot: "Ocena modelu, nie wymóg z przepisu",
    },
    showOnShot: "Pokaż na zrzucie",
    passed: (n: number) =>
      `${count(n, nouns.requirement)} ${plural(n, ["spełniony", "spełnione", "spełnionych"])}`,
    unknown: (n: number) => `Do oceny przez model: ${count(n, nouns.requirement)}`,
    unresolved: (n: number) =>
      `Nierozstrzygnięte, do oceny analityka: ${count(n, nouns.requirement)}`,
    screenshot: "Zrzut strony",
    content: "Treść materiału",
    noShot: "Brak zrzutu dla tego ekranu.",
    shotError: "Nie udało się wczytać zrzutu.",
    whereOnPage: "Miejsce na stronie",
    whereHint: "Zaznaczony fragment poniżej jest powiększony.",
    zoomLabel: (factor: string, magnified: boolean) =>
      magnified ? `Powiększenie ${factor}×` : `Skala ${factor}×`,
    pageSample: (px: string) => `Tak wygląda tekst strony – ${px} px`,
    measures: {
      warning: "Ostrzeżenie",
      page: "Tekst strony",
      contrast: "Kontrast",
    },
    firmTitle: "Firma w rejestrze KNF",
    firmFictionalTitle: "Firma fikcyjna (demo)",
    firmFictional: FICTIONAL_FIRM,
    firmMissingTitle: "Rejestr KNF",
    firmMissing: "Podmiotu nie ma w żadnym z rejestrów KNF.",
    firmRows: {
      name: "Nazwa",
      kind: "Rodzaj",
      country: "Kraj",
      match: "Dopasowanie",
    },
    match: {
      domain: (v: string) => `Po domenie ${v}`,
      handle: (v: string) => `Po nazwie konta ${v}`,
      alias: (v: string) => `Po nazwie ${v}`,
      fuzzy: (v: string) => `Podobna nazwa: ${v}`,
    },
    openRegister: "Otwórz w rejestrze KNF",
    warning: {
      line: (date: string) => `Na liście ostrzeżeń publicznych KNF od ${date}`,
      entity: (name: string) => `Wpis: ${name}`,
      match: {
        domain: (v: string) => `dopasowanie po domenie ${v}`,
        name: (v: string) => `dopasowanie po nazwie ${v}`,
        fuzzy: (v: string) => `podobna nazwa: ${v}`,
      },
      asOfNote: "Data to stan listy w naszej migawce; KNF nie podaje dat wpisów.",
      open: "Lista ostrzeżeń publicznych KNF",
    },
    occurrences: {
      title: (n: number) => `Wystąpienia (${n})`,
      lead: "Ten sam tekst i układ w kilku miejscach: jedna ocena, każde miejsce zapisane.",
      range: (first: string, last: string) => `Pierwsze: ${first} · ostatnie: ${last}`,
      seen: (first: string, last: string) =>
        first === last ? `widziane ${first}` : `widziane ${first} – ${last}`,
    },
    history: "Historia",
    events: {
      seen: (collector: string) =>
        collector === "manual"
          ? "Dodano ręcznie w „Sprawdź”"
          : collector === "web"
            ? "Wykryto podczas monitoringu stron firm"
            : "Wykryto podczas monitoringu źródeł",
      measured: (n: number) =>
        n === 1 ? "Zmierzono ostrzeżenie na 1 ekranie" : `Zmierzono ostrzeżenie na ${n} ekranach`,
      analyzed: (n: number) => `Sprawdzono ${count(n, nouns.requirement)}`,
      llmDone: "Model językowy ocenił tekst",
      llmQueued: "Model językowy czeka w kolejce",
      llmUnavailable: "Ocena modelu niedostępna: wynik z reguł",
      decided: (label: string) => label,
    },
  },

  submitMaterial: {
    title: "Zgłoś materiał",
    lead: "Dla postów i reklam, których system nie pobiera sam (Facebook, Instagram, TikTok). Nic nie jest pobierane z sieci: analizujemy to, co tu wpiszesz.",
    url: "Adres materiału (opcjonalnie)",
    urlPlaceholder: "https://www.facebook.com/…",
    text: "Treść posta lub reklamy",
    textPlaceholder: "Wklej cały tekst, razem z drobnym drukiem i ostrzeżeniami",
    screenshot: "Zrzut ekranu (opcjonalnie, PNG do 10 MB)",
    chooseScreenshot: "Wybierz zrzut",
    noScreenshot: "Nie wybrano pliku",
    pngOnly: "Zrzut ekranu musi być plikiem PNG.",
    tooLarge: "Zrzut ekranu jest większy niż 10 MB.",
    note: "Notatka (opcjonalnie)",
    notePlaceholder: "Gdzie i kiedy to widziałeś",
    submit: "Zgłoś do analizy",
    submitted: "Przyjęto materiał",
    submittedText: "Analiza trwa kilka sekund; wynik pojawi się na liście zgłoszeń.",
    open: "Otwórz zgłoszenia",
    error: "Nie udało się zapisać materiału. Spróbuj ponownie.",
  },

  sources: {
    title: "Monitoring źródeł",
    lead: "Miejsca, które system sprawdza automatycznie. Korzystamy tylko z oficjalnych interfejsów i stron, które na to pozwalają.",
    add: "Dodaj źródło",
    working: "Działa",
    waiting: "Czeka na klucz lub zgodę",
    checkedToday: "Sprawdzono dziś",
    columns: {
      source: "Źródło",
      access: "Sposób dostępu",
      state: "Stan",
      last: "Ostatnio",
      found: "Znaleziono",
    },
    run: "Uruchom",
    runLabel: (name: string) => `Uruchom teraz: ${name}`,
    started: "Uruchomiono",
    runError: "Nie udało się uruchomić źródła.",
    notReady: {
      needs_credentials: "Źródło wymaga klucza",
      needs_approval: "Źródło wymaga zgody platformy",
      disabled: "Źródło jest wyłączone",
      ready: "Źródło gotowe",
    },
    accessModes: {
      official_api: "Oficjalne API",
      open_dataset: "Otwarty zbiór danych",
      file_import: "Wgranie pliku",
      analyst: "Zgłoszenie analityka",
      crawler: "Strony WWW, robots.txt",
    },
    states: {
      ok: "Działa",
      key: "Wymaga klucza",
      approval: "Wymaga zgody platformy",
      blocked: "Strona nie zezwala",
      off: "Wyłączone",
      error: "Błąd",
      running: "Sprawdza teraz",
      new: "Czeka na start",
    },
    access: {
      web: "Strony WWW, robots.txt",
      site: "Mapy witryn, robots.txt",
      youtube: "YouTube Data API",
      meta_ad_library: "Ad Library API",
      microsoft_ad_library: "Microsoft Ad Library API",
      tiktok: "Commercial Content API",
      tiktok_ccl: "Commercial Content API",
      sample: "Wgranie pliku",
      manual: "Ręcznie",
    } as Record<string, string>,
    cron: {
      everyMinutes: (n: number) => `co ${n} min`,
      everyHours: (n: number) => (n === 1 ? "co godzinę" : `co ${n} godz.`),
      daily: (time: string) => `codziennie o ${time}`,
    },
    empty: "Nie ma jeszcze żadnych źródeł.",
    report: "Zgłoś materiał",
    registryRow: {
      name: "Rejestr KNF",
      what: "4 rejestry firm inwestycyjnych",
      access: "Strona knf.gov.pl",
      found: (n: number) => `${formatInt(n)} firm`,
      snapshot: (date: string) => `Kopia z ${date}`,
    },
    dialog: {
      title: "Dodaj źródło",
      name: "Nazwa",
      namePlaceholder: "np. Strony brokerów CFD",
      collector: "Rodzaj źródła",
      target: "Adres lub zapytanie",
      targetPlaceholder: "https://",
      schedule: "Jak często",
      submit: "Dodaj",
      added: "Dodano źródło",
      error: "Nie udało się dodać źródła.",
      modes: {
        source: "Źródło automatyczne",
        file: "Import pliku",
      },
      notReadyHint: "Źródło zostanie dodane, ale nie ruszy, dopóki nie będzie dostępu.",
      format: "Format pliku",
      file: "Plik (CSV, JSON lub JSONL, do 10 MB)",
      chooseFile: "Wybierz plik",
      noFile: "Nie wybrano pliku",
      formats: {
        meta_ads_csv: "Eksport Meta Ad Library (CSV)",
        meta_ads_json: "Eksport Meta Ad Library (JSON)",
        tiktok_ccl_json: "Eksport TikTok Commercial Content (JSON)",
        youtube_api_json: "Odpowiedź YouTube Data API (JSON)",
        uknf_sample: "Próbki UKNF",
        posts_jsonl: "Materiały (JSONL)",
      },
      importSubmit: "Importuj",
      imported: (n: number) => `Zaimportowano: ${count(n, nouns.material)}`,
      importedText: (queued: number) => `Do analizy: ${formatInt(queued)}`,
      importError: "Nie udało się zaimportować pliku.",
    },
    collectors: {
      web: "Strona WWW",
      youtube: "YouTube",
      meta_ad_library: "Biblioteka reklam Meta",
      microsoft_ad_library: "Biblioteka reklam Microsoft (Bing)",
      tiktok: "Biblioteka reklam TikTok",
      site: "Strony firm z rejestru KNF",
    } as Record<string, string>,
    connectorState: {
      ready: "",
      needs_credentials: "wymaga klucza",
      needs_approval: "wymaga zgody platformy",
      disabled: "wyłączone",
    },
    schedules: [
      ["0 */6 * * *", "co 6 godz."],
      ["0 */12 * * *", "co 12 godz."],
      ["0 4 * * *", "codziennie o 04:00"],
    ] as const,
  },

  sensitivity: {
    title: "Czułość wykrywania",
    lead: (n: number) =>
      `Ustaw, od jakiego wyniku materiał trafia do przejrzenia. Liczby poniżej pochodzą z ${formatInt(n)} ${n === 1 ? "materiału" : "materiałów"} z ustaloną oceną. Oceny nadano według spisanych reguł i sprawdzono przez trzech niezależnych recenzentów AI, a spory rozstrzygał czwarty. Dochodzą do nich decyzje analityków w zgłoszeniach.`,
    threshold: "Próg zgłoszenia",
    more: "Więcej zgłoszeń",
    fewer: "Mniej fałszywych alarmów",
    sentence: {
      before: "Przy tym progu system zgłosi ",
      found: (found: number, total: number) => `${found} z ${total}`,
      middle: " prawdziwych naruszeń i da ",
      fp: (fp: number) => count(fp, nouns.falseAlarm),
      after: (negatives: number) => ` na ${count(negatives, nouns.compliant)}.`,
    },
    save: "Zapisz próg",
    saved: "Zapisano próg",
    saveError: "Nie udało się zapisać progu.",
    recommended: (value: string) => `Ustaw zalecany (${value})`,
    recall: "Wykryte naruszenia",
    recallDetail: (found: number, total: number, missed: number) =>
      `${found} z ${total} · pominięte: ${missed}`,
    precision: "Trafność zgłoszeń",
    precisionDetail: (fp: number, flagged: number) =>
      `${count(fp, nouns.falseAlarm)} na ${count(flagged, nouns.finding)}`,
    note: "Nadzorca woli nie przegapić naruszenia, dlatego zalecany próg stawia wykrywanie nieco wyżej niż trafność.",
    noLabels: "Nie ma jeszcze materiałów z ustaloną oceną dla tego rodzaju naruszeń.",
  },

  registry: {
    title: "Rejestr KNF",
    lead: "Firmy inwestycyjne, które mogą legalnie działać w Polsce. Dzięki tej liście system odróżnia firmę od osoby, która ją reklamuje, i od podmiotu bez zezwolenia.",
    current: "Aktualny",
    snapshot: "Z zapisanej kopii",
    failed: "Błąd pobierania",
    neverSynced: "Jeszcze nie pobrano",
    fetchedAt: (when: string) => `pobrano ${when}`,
    syncNow: "Pobierz teraz",
    syncQueued: "Pobieranie rejestru rozpoczęte",
    syncError: "Nie udało się rozpocząć pobierania.",
    search: "Szukaj w rejestrze",
    searchPlaceholder: "Szukaj po nazwie, nazwie handlowej lub domenie, np. xtb.com",
    columns: {
      firm: "Firma",
      kind: "Rodzaj",
      country: "Kraj",
      domain: "Domena",
      findings: "Zgłoszenia",
    },
    alias: (names: string[]) => `także: ${names.join(", ")}`,
    noAlias: "brak innych nazw",
    empty: "Nie znaleziono firmy. Sprawdź pisownię albo szukaj po domenie.",
    showMore: "Pokaż więcej",
    shown: (shown: number, total: number) => `${shown} z ${total}`,
    counts: (knf: number, fictional: number) =>
      fictional > 0
        ? `${count(knf, nouns.firm)} z rejestrów KNF. Lista zawiera też ${count(fictional, nouns.fictionalFirm)} do demonstracji, oznaczonych w tabeli i niewliczanych do tych liczb.`
        : `${count(knf, nouns.firm)} z rejestrów KNF.`,
    fictional: FICTIONAL_FIRM_TAG,
    fictionalHint: FICTIONAL_FIRM,
  },

  toast: {
    alertTitle: (name: string) => `Wysokie ryzyko: ${name}`,
    /** High score from the model alone, no failed requirement. */
    signalTitle: (name: string) => `Sygnał do weryfikacji: ${name}`,
    close: "Zamknij powiadomienie",
  },
  notFound: {
    title: "Nie ma takiej strony",
    back: "Wróć do sprawdzania",
  },

  /** "Pod maską" panel at the bottom of a finding: how the material was processed. */
  hood: {
    title: "Pod maską",
    lead: "Ślad przetwarzania tego materiału: skąd i jak go pobrano, gdzie leży kopia dowodowa i co zrobił z nim system.",
    chip: (source: string, when: string, mode: string) =>
      `Źródło: ${source} · pobrano ${when} · ${mode}`,
    loading: "Wczytywanie śladu…",
    error: "Nie udało się wczytać śladu przetwarzania.",
    none: "–",
    sections: {
      fetch: "Pozyskanie",
      storage: "Kopia dowodowa (MinIO)",
      analysis: "Analiza",
      timings: "Czas kroków",
      similar: "Podobne materiały (pgvector)",
    },
    rows: {
      source: "Źródło",
      schedule: "Harmonogram",
      nextRun: "Następne uruchomienie",
      job: "Zadanie",
      access: "Tryb dostępu",
      basis: "Podstawa",
      userAgent: "User-Agent",
      proxy: "Proxy",
      robots: "robots.txt",
      http: "Odpowiedź",
      render: "Render (Chromium)",
      fetchedAt: "Pobrano",
      textHash: "SHA-256 tekstu",
      layoutHash: "Odcisk układu",
      tokens: "Tokeny",
      embedding: "Embedding",
      lang: "Język",
      rules: "Reguły",
      classifier: "Klasyfikator",
      analyze: "Zadanie analizy",
      llm: "Model językowy",
      llmTask: "Zadanie modelu",
    },
    manual: "ręczne sprawdzenie („Sprawdź”)",
    chars: (n: string) => `${n} znaków`,
    direct: "bezpośrednio (bez proxy)",
    robots: {
      allowed: "zezwala",
      disallowed: "zabrania (nie pobrano)",
      missing: "brak pliku (dozwolone, RFC 9309)",
    } as Record<string, string>,
    access: {
      crawler: "crawler InvestWatchBot",
      official_api: "oficjalne API",
      open_dataset: "otwarty zbiór danych",
      file_import: "import pliku",
      analyst: "zgłoszenie analityka",
    } as Record<string, string>,
    /** Collector keys shown when the material has no named source. */
    collectors: {
      web: "Strona WWW",
      site: "Strony firm z rejestru KNF",
      youtube: "YouTube",
      meta_ad_library: "Meta Ad Library",
      microsoft_ad_library: "Microsoft Ad Library (Bing)",
      tiktok: "TikTok Ad Library",
      file_import: "Import pliku",
      open_dataset: "Otwarty zbiór danych",
      analyst: "Zgłoszenie analityka",
    } as Record<string, string>,
    httpLine: (status: number | null | undefined, ms: string | null) =>
      [status ? `HTTP ${status}` : null, ms ? `${ms} ms` : null].filter(Boolean).join(" · "),
    crawlDelay: (s: string) => `Crawl-delay ${s} s`,
    renderOk: (s: string | null) => (s ? `ok, ${s} s` : "ok"),
    renderOff: "wyłączony",
    task: (queue: string, id: string | null | undefined, worker: string | null | undefined) =>
      [`kolejka ${queue}`, id ? `id ${id}` : null, worker ? `worker ${worker}` : null]
        .filter(Boolean)
        .join(" · "),
    embedding: (dim: number | null | undefined, model: string | null | undefined) =>
      [dim ? `${dim} wymiarów` : null, model].filter(Boolean).join(" · ") || "–",
    classifierLine: (version: string, variant: string | null | undefined) =>
      variant === "embedding"
        ? `${version} (embedding bge-m3 + leksykon)`
        : `${version} (${variant ?? "leksykon"})`,
    noClassifier: "nie dotyczy (moduł oceniany regułami)",
    llmLine: (
      model: string,
      inTok: number | null | undefined,
      outTok: number | null | undefined,
      s: string | null,
    ) =>
      [
        model,
        inTok != null ? `${inTok} tok. wejścia` : null,
        outTok != null ? `${outTok} tok. wyjścia` : null,
        s ? `${s} s` : null,
      ]
        .filter(Boolean)
        .join(" · "),
    noLlm: "nie wywołano (wynik z reguł)",
    objectKinds: {
      html: "HTML strony",
      raw: "Surowe dane (JSON)",
      render: "Pomiar układu (JSON)",
      screenshot: "Zrzut",
    } as Record<string, string>,
    columns: { object: "Obiekt", key: "Klucz", size: "Rozmiar", sha: "SHA-256" },
    missingObject: "brak w magazynie",
    copy: "Kopiuj",
    copied: "Skopiowano",
    steps: {
      preprocess: "Przygotowanie tekstu",
      rules: "Reguły",
      embed: "Embedding",
      classifier: "Klasyfikator",
      advisory: "Elementy art. 76",
      llm: "Model językowy",
    } as Record<string, string>,
    total: (ms: string) => `Razem ${ms} ms (szybka ścieżka w usłudze ai)`,
    noTimings: "Brak pomiarów czasu (materiał sprzed śledzenia).",
    similarity: (pct: string) => `${pct}% podobieństwa`,
    noSimilar: "Brak podobnych materiałów w bazie.",
    similarOff: "Wyszukiwanie podobnych wymaga bazy PostgreSQL z pgvector i embeddingu.",
  },

  /** "Stan systemu" card on Monitoring (`GET /api/system`). */
  system: {
    title: "Stan systemu",
    checked: (time: string) => `sprawdzono ${time}`,
    checking: "Sprawdzanie usług…",
    error: "Nie udało się sprawdzić stanu systemu.",
    services: {
      api: "API",
      database: "Baza danych",
      redis: "Redis (kolejki)",
      minio: "MinIO (dowody)",
      workers: "Workery Celery",
      beat: "Harmonogram (Beat)",
      ai: "Usługa AI",
      ollama: "Ollama (modele)",
    } as Record<string, string>,
    states: {
      ok: "działa",
      degraded: "częściowo",
      down: "nie działa",
      disabled: "wyłączone",
    },
    nextRun: (name: string, when: string, cron: string) =>
      `Następne uruchomienie: ${name}, ${when} (cron ${cron})`,
    noNextRun: "Brak zaplanowanych uruchomień.",
    queues: "Kolejki",
    workerNoun: ["worker", "workery", "workerów"] as const,
    tick: (s: number) => `takt ${s} s temu`,
    bucket: (name: string) => `kosz ${name}`,
    memory: "w pamięci (tryb testowy)",
    models: (llm: string, embed: string) => `Modele: ${llm} · ${embed}`,
  },

  /** PDF reports (`render/pdf.py` on the server). */
  pdf: {
    finding: "Pobierz raport PDF",
    module: "Pobierz raport PDF",
    unavailable: "Raport PDF generuje serwer; w trybie demonstracyjnym jest niedostępny.",
  },

  /** Chart under the calibrator on "Czułość". */
  calibChart: {
    title: "Jak próg zmienia wynik",
    modes: { counts: "Liczba materiałów", rates: "Czułość i trafność" },
    found: "Wykryte",
    falseAlarms: "Fałszywe alarmy",
    missed: "Pominięte",
    recall: "Czułość (wykryte)",
    precision: "Trafność",
    threshold: "Próg",
    marker: (value: string) => `próg ${value}`,
    axisCount: "materiały",
    caption: (n: number, golden: number, analyst: number) =>
      `Liczone na ${formatInt(n)} ${n === 1 ? "materiale" : "materiałach"} z ustaloną oceną` +
      (golden || analyst
        ? ` (zbiór wzorcowy: ${formatInt(golden)}, decyzje analityków: ${formatInt(analyst)}).`
        : "."),
    table: "Pokaż dane w tabeli",
  },
};
