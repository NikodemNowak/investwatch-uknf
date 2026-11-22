# 0009: Fair treatment of real, registered firms

## Context

`make demo` imports a few public pages of real firms from the golden set. A review of a real run
found findings that would mislead a regulator:

- **Finax o.c.p., a.s.** (a Slovak investment firm passported to Poland, in the KNF register of
  notified EEA firms with A5) was shown as "doradztwo bez zezwolenia", high risk: `finax.eu` was
  not a known domain, the author name did not match, and the register's bogus trade name
  "Ireland" turned the page into an ad for Citadel Securities (Ireland).
- **X-Trade Brokers DM S.A. (XTB)**, the former name of XTB S.A., appeared as a second entity
  "Brak w rejestrze KNF": XTB S.A. has no A5, so M3 ran on its IKE page (on the cookie banner,
  "dopasowana do Twoich potrzeb") and the M3 finding carried only the author string.
- Rules fired on boilerplate: a tax-rate FAQ as a "gain claim", a RODO notice's "Kliknij" as an
  unlabelled ad, a calculator label "Spodziewany wynik" as a forecast, "mam 18 lat" as a MAM
  account, "wypracować strategie" as a past result, the legal form written out ("Spółka
  Akcyjna") as a missing firm name.
- One formal omission (rule 16, tax note) put a supervised firm under "Wysokie ryzyko".

## Decision

1. **Matching.** Web author strings match registered, former and trade names (brackets split,
   "DM"/"BM" expanded, a bracketed domain checked); a country or seat is never an alias;
   curated domains for firms whose register entry lists none (`data/registry/brands.json`).
   Social display names are not used: anybody can name a page "XTB".
   On ad-library records the advertiser / payer of record (Bing author, the "Reklamodawca:" and
   "Płatnik:" lines of Meta, TikTok and Bing items) decides: when it names a registered firm, or
   carries the brand of the firm the ad names (same group: "Swissquote Bank Europe SA" for
   Swissquote Capital Markets Ltd, "FxPro Financial Services Ltd" for FXPRO), the ad is the
   firm's own material (M2), never a third party's promotion (M1). An affiliate who pays for
   an ad naming a broker stays M1.
2. **M3 only outside the registers.** M3 means "advice without a licence". A firm in any KNF
   register (Polish firms, branches, notified EEA firms) is supervised; its own material goes
   through M2, never M3. This matches the labelling guide (`docs/eval/LABELING.md`: licensed
   firms are M3 = 0).
3. **Rules read content, not boilerplate** (fixes above, each with a unit test on our own text).
4. **Risk level for a registered firm's own material** (author match on its domain, handle or
   name; not a look-alike "domena spoza rejestru"): `high` only when an unambiguous rule fails
   with confidence ≥ 0.75: rule 3 (gains without any risk warning), 4-7 (warning measured as too
   small, hidden, behind a click), 14 (past results without the disclaimer), 17-18 (KNF as
   approval or safety). Otherwise at most `medium`. The score is unchanged, so `make eval`
   numbers do not move; only the triage label does. The explanation and the finding page say
   "Firma z rejestru KNF · możliwe naruszenie – do weryfikacji przez analityka".
5. **Aggregator.** One entity per registered firm id; two register records of one legal entity
   (branch + cross-border notification) share the smallest id; a publisher's unmatched findings
   join the firm it publishes for.
6. **Demo set.** Real firm pages stay to show fair treatment: DM BOŚ and Michael / Ström (no
   findings), XTB and Finax (medium: a tax benefit without the "depends on your situation / may
   change" note, art. 44(2)(f) Reg. 2017/565, the same label the golden set gives these pages).
   Left out: investors.pl (a TFI; the TFI register is not in our KNF snapshot, so it would show
   as unregistered) and cmcmarkets.com (only an ad-label point on a home page). Strong cases come
   from the fictional `demo-sites`. KNF warning-list entities (archived pages) stay: KNF itself
   names them.
7. **Comparisons of licensed firms.** A page that names two or more register firms by their
   full registered names and is by none of them (a broker ranking such as
   kontomaniak.pl/ranking-kont-maklerskich) is M1: the page owner advertises the listed firms.
   Its advice-like words ("osobisty menedżer", "ankieta MiFID", funds that manage capital)
   describe the listed firms' licensed services, so they do not open M3; only the page's own
   buy / sell call (`advisory_buy_sell`) or a KNF warning does, and the embedding head cannot
   open M3 alone there. Short brand matches (a common word such as "Shares") do not count.
   `make eval` (rules): no prediction changes.

## Consequences

- `make eval EMBED=1`, hold-out: M3 FP 6 → 4 (precision 0.33 → 0.43, recall unchanged); M2
  FP 4 → 5 because Ipopema Securities' own page is now matched to the firm and M2 runs on it.
  Train: M2 FP 4 → 2, M3 unchanged. Without the embedding (lexicon heads) M3 FP goes 9 → 6.
  Nothing was tuned on the hold-out split. Details in `docs/eval/latest.md`.
- A registered broker without A5 that gives personal advice is not flagged by M3; M2 still
  checks its material, and KNF supervises it directly.
- TFIs and other registers (banks' own lists, agents) are still missing from the snapshot.
