# Public, legally sourced evaluation data

The golden set (`LABELING.md`) was mostly synthetic, and M3 (shadow advisory) had only two
hold-out positives. This document lists the public sources we checked to grow it with **real,
legally usable, labelled** material: what we used, under which licence or legal basis, how it
was collected and labelled, and what we rejected and why. Checked on 2026-11-21.

Ground rules for every source: official or openly licensed; licence or terms read and cited;
no scraping of social platforms; robots.txt honoured; an honest User-Agent
(`InvestWatchBot/0.1 (+https://github.com/NikodemNowak/investwatch-uknf; golden-set research, HackNation 2026)`);
a fixed minimum interval per host; reproducible with one command (`make public-data`).

## Used

| Source id | What | Licence / legal basis | Method | Items |
|---|---|---|---|---|
| `knf_warnings` (registry snapshot) | KNF public warning list: entities KNF reported to prosecutors for unauthorised activity | Public sector information published under art. 6b of the Act on financial market supervision; re-use under the Act of 11 August 2021 on open data and re-use of public sector information, with source and retrieval date. knf.gov.pl robots.txt: `User-agent: * Allow: /` | `official_list`, one request | 465 of 669 rows kept (legal persons and web-only operators; private individuals dropped) in `data/registry/knf_warnings.json` |
| `knf_warnings_wayback` | Archived home pages (EN and `/pl/`) of warned entities' websites, from the Internet Archive | Internet Archive Terms of Use (access "for scholarship and research purposes"); documented CDX API; page text (c) its publisher, kept only as a redacted excerpt for text-and-data mining (art. 26³ of the Polish Copyright Act, implementing art. 4 of Directive 2019/790). Removal on request | `web_archive`, CDX + `id_` snapshot, >= 1.5 s between requests | 33 items (M3: 27 positive, 6 negative), 17 leakage groups |
| `firm_pages` | Polish landing and offer pages of KNF-registered / EEA-passported investment firms (brokers incl. CFD, TFI, robo-adviser) | Public marketing pages; fetched for text-and-data mining (art. 26³ pr. aut.) after checking robots.txt for our token and the TDM-reservation meta / header (none found); redacted excerpt only | `http_robots_respecting`, <= 3 pages per site, >= 3 s per host | 35 items (M2: 7 positive, 21 negative; M3: 7 negative), 11 domains |

All new items have `provenance.compliant = "yes"` and count towards headline metrics.

### How the items are built

1. **Loaders** (`backend/src/investwatch/golden/sources/`) download raw candidates into
   `data/golden/public/_candidates/` (git-ignored, re-created by `make public-data`):
   `knf_warnings.py` (one request, writes the committed registry snapshot), `wayback.py`
   (per warned domain: CDX query for 200/HTML captures, a capture one third into the
   history, i.e. while the offer was live rather than the parked page after the warning),
   `firm_pages.py` (start page + up to two same-site offer links). All use
   `sources/http.py`: honest User-Agent, robots.txt always honoured (no switch), per-host
   interval, refusals (robots, 401/403/429) are skipped, never retried another way.
2. **Labels** are committed in `data/golden/public/labels/<source>.jsonl`, one line per
   candidate and module (`label: null` = looked at and excluded, with the reason in `note`).
3. **Curation** (`curate.py`) joins labels with candidates into the committed
   `data/golden/public/<source>.jsonl`: a redacted excerpt (first 3,000 characters, the
   rule-relevant sentences in between up to 4,500, last 2,000; e-mail addresses and phone
   numbers removed) plus full provenance (`source`, `source_url` = exact retrieved or
   archived URL, `retrieved_at`, `licence`, `method`). A fresh checkout can re-curate from
   the committed records without re-downloading.
4. `make golden` reads every `public/*.jsonl` (`records.public_items`), matches the text
   against the KNF register like any real item and assigns the split.

### Labelling rules

* **M3 positives** (`knf_warnings_wayback`): a page is `1` only when the page itself shows
  the advisory activity (personal account manager guiding trades, individual advice,
  signals, managed / PAMM accounts, "individual portfolios"). Where KNF's notification names
  art. 69 ust. 2 pkt 4 (portfolio management) or pkt 5 (investment advice) the label is
  the regulator's finding plus that visible cue: `labeler: rule`, confidence 0.65-0.85.
  Where KNF names only order execution (pkt 1-3) but the page clearly advertises advisory
  services, `labeler: agent`, confidence 0.6-0.75. Pages of pkt 4/5 entities that show **no**
  advisory content (plain broker page, binary options, courses) are **excluded**: the text
  alone cannot carry the label. Parked, for-sale, expired and reused domains are excluded.
* **M3 negatives**: unlicensed brokers whose page advertises self-directed trading only
  (`agent`, 0.6-0.65), and licensed firms that do offer advice or portfolio management
  (Noble Securities advice promotion, Finax robo-adviser, DM BOŚ amIKE, Michael / Ström asset
  management): `0` by definition (LABELING.md: licensed firms), with the art. 76 elements
  marked present (`fail`). These are the tricky negatives.
* **M2** (`firm_pages`): `1` when a text rule clearly fails, otherwise `0`. Per-rule labels
  only where the text decides it: rule 1 `pass` when the full legal name is in the excerpt;
  3, 14, 16, 17 `pass` only when the disclaimer is present in the excerpt (checked by
  script); 16 `fail` for tax-benefit claims without the "depends on the client's individual
  situation and may change" note (art. 44(2)(f) of Delegated Regulation 2017/565); 12a / 14 /
  3 `fail` for one-year fund returns without any warning. Render rules are not labelled.
  English pages served by geo-redirect, corporate-finance pages, pages listing staff
  contact data and the disputable eToro copy-trader returns are excluded.
* Every label is `agent` or `rule`, never `human`: the hold-out still needs a human pass
  (`make label`) before numbers are quoted outside the team.

### Split and leakage

`assign_splits` stratifies by (module, origin, headline, public source), so each source gets
its own 60/40 split and the existing 208 items keep their split. Leakage groups:
`entity:<warned entity>` for archived pages (EN and PL captures of one entity stay
together), `domain:<host>` for firm pages, and `template:<name>` where several warned
entities used one scam-site template (5 domains share `template:forex-tier-table`,
`kraj-m.com` / `kraj-maklerow.com` share `template:kraj-maklerow`).

## Effect on the evaluation (`make eval`, rules mode)

Headline (hold-out, compliant sources). Baseline is `main` after the compliance clean-up
(#17: 179 items, 118 with text), after = this change (247 items, 186 with text):

| module | n | pos | precision | recall | F1 |
|---|---|---|---|---|---|
| m1_third_party_ad | 13 -> 13 | 7 -> 7 | 1.00 -> 1.00 | 0.86 -> 0.86 | 0.92 -> 0.92 |
| m2_risk_disclosure | 30 -> 41 | 15 -> 17 | 0.83 -> 0.67 | 0.67 -> 0.71 | 0.74 -> 0.69 |
| m3_shadow_advisory | 7 -> 23 | 1 -> 11 | 0.00 -> 0.50 | 0.00 -> 0.09 | 0.00 -> 0.15 |

Scored compliant items, both splits: M3 59 (36 positive; on `main` 1 hold-out positive),
M2 94. Existing items keep their split.

Per source (all splits): `knf_warnings_wayback` M3 recall 0.15 (4 / 27) at precision 1.00:
the current rules miss English pages and the typical scam-broker cues ("personal account
manager", "trading signals", "managed accounts"). `firm_pages` M2 precision 0.31: on real
compliant broker pages the rules over-fire (rule 2 "advertisement marking" on firms' own product pages, 15 and
16 on navigation and FAQ text). These are the gaps the new data exposes; the numbers are honest, not
tuned.

## Checked and rejected

| Source | Why not (now) |
|---|---|
| FCA Warning List (UK) | FCA website terms: material may be reused for personal or in-house use only, other re-use needs prior written permission (cl. 3.2, 3.9); scrapers, robots and spiders prohibited without consent (cl. 4.8(iii)). Only the Data section is under the Open Government Licence. |
| IOSCO I-SCAN | Portal returns 403 to automated clients; bulk access only through the I-SCAN API after signing the API Terms of Use Agreement (an organisation must sign). Worth requesting for production entity matching; not used without the signed agreement. |
| ESMA / other EU NCA warning lists | ESMA links to national lists, no consolidated download; each NCA has its own terms. KNF covers the Polish market we target. |
| CERT Polska Lista Ostrzeżeń (hole.cert.pl) | Public domain blocklist (TXT / CSV / JSON), but no licence stated on the download pages, the entries are mostly phishing (bank / courier / shop impersonation), not investment offers, and the list has no page text; fetching live phishing pages is unsafe. Candidate for a future router signal after asking CERT Polska about re-use terms. |
| EU DSA Transparency Database | CC BY 4.0 (data licence page), but statements of reasons are moderation metadata (category, ground, decision facts); they contain no content text to label for M1-M3. Usable later for aggregate context only. |
| Hugging Face datasets | API search ("polish scam", "polish fraud", "finfluencer", "investment scam", ...): no Polish financial-promotion data; hits are English / Hinglish SMS spam, fraud transactions or synthetic Q&A, not matching our module definitions. |
| Zenodo | Finfluencer records are survey studies (questionnaires), not text corpora; one MIT-licensed code+data record on finfluencer classification was not adopted because the origin of its texts is not documented on the record. |
| Mendeley "Multimodal Dataset for Investment-Related Deceptive Content" (10.17632/6wnd7jrt6z) | English aggregate of social-platform, bot and spam data; its own notes say labels are not verified scam status. |
| BrokerChooser Meta-ads scam study | Built from the Meta Ad Library; no open licence for the underlying items. |
| Kaggle | No relevant Polish dataset surfaced in web search; Kaggle search needs an account and its finance "fraud" sets are transaction tables. |

## Reproduce

```bash
make public-data   # re-download (polite: the Wayback part takes about an hour) and re-curate
make golden && make eval
cd backend && uv run python -m investwatch.golden.sources.curate --list knf_warnings_wayback  # unlabelled candidates
```

To remove an item on request, delete its line from `data/golden/public/labels/<source>.jsonl`
and `data/golden/public/<source>.jsonl`, then `make golden`.
