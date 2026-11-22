# Golden set: labelling guide

The golden set (`data/golden/golden.jsonl`) is what `make eval` scores and what the calibration
panel (`GET /api/calibration/{module}`) learns thresholds from. It is only as good as its
labels, so every label follows the rules below. The latest report is in
[`latest.md`](latest.md).

## Files

| Path | What |
|---|---|
| `data/golden/golden.jsonl` | One `GoldenItem` per line (schema: `backend/src/investwatch/golden/schemas.py`). Built by `make golden`; reviews are written here. |
| `data/golden/labels/real.jsonl` | Proposed labels of real posts: `{ref, module, label, labeler, confidence, note}`; `ref` = `<platform>:<external_id>` in `raw/posts.jsonl`. |
| `data/golden/raw/posts.jsonl` | Texts of collected real posts (referenced, not copied). Items whose post is removed from here drop out of the set on the next `make golden`. |
| `data/golden/synthetic/` | Generated pages (`pages/`) and render snapshots (`render/`) of synthetic and demo-sites items. |
| `data/golden/public/<source>.jsonl` | Curated public-data items (redacted excerpt, label, provenance); `public/labels/` holds the labeller's decisions. See `DATA_SOURCES.md`. |
| `data/golden/predictions.jsonl` | Scores of the last full `make eval`; `seed` loads them into the `labels` table. |

## Sources and legality

Every item carries `provenance` (`collector`, `method`, `compliant`). Only legally obtained
content may enter the set:

| `method` | Meaning | Headline metrics |
|---|---|---|
| `generator` | Built by `golden/synth.py`, fictional firms on `.example` domains | yes |
| `demo_site` | Our own pages in `demo-sites/` | yes |
| `http_robots_respecting` | Public web page fetched by the `web` collector, robots.txt honoured | yes |
| `official_api` | A platform API used within its terms (e.g. YouTube Data API) | yes |
| `manual` | Supplied by a team member, source URL in the note | yes, once `compliant` is `yes` |
| `official_list` | A regulator's published list (KNF warning list) | yes |
| `web_archive` | Internet Archive snapshot via its documented CDX API (pages of KNF-warned entities) | yes |
| `open_dataset` | A published dataset under an open licence | yes |
| `yt_dlp`, `meta_ad_library_page`, `tiktok_page` | Platform pages fetched outside an official API | **no**: reported separately only |

Public sources, their licences and the rejected ones are documented in
[`DATA_SOURCES.md`](DATA_SOURCES.md); their curated items live in `data/golden/public/`
(labels in `public/labels/`, `labeler: rule` = a documented rule over an official source).

Do not add new items scraped from social platforms. To add real content, use the `web`
collector (it respects robots.txt), an official API, or paste the material by hand with its URL
(`method: manual`).

## What the label means

`label` is about the item's `module`; `1` = the module should raise it.

**M1 `m1_third_party_ad`** (third party promotes an investment firm). `1` when a person or page
other than the firm itself promotes the firm's services: referral or affiliate links, promo
codes, sign-up bonuses, "sponsored by" segments, giveaways tied to opening an account. `0` for
news about the firm, complaints, warnings, independent comparisons without affiliate links,
job offers, education that only mentions the firm, the firm's own channel (that is M2).

**M2 `m2_risk_disclosure`** (marketing material breaks the disclosure rules). `1` when at least
one rule of attachment 4 fails. Per-rule labels (`rule_labels`) use `fail` / `pass` / `na`
(not applicable); leave a rule out when you cannot tell (it is then not scored). Render rules
(4 to 8, 13) need a render snapshot; for real items without one, do not label them.

**M3 `m3_shadow_advisory`** (unlicensed investment advice). `1` when an entity that is not in
the KNF registers with advice permission (A5) offers advice in the sense of art. 76 UoIF:
recommendations tailored to the client's situation (76a) about financial instruments (76b),
buy / sell / hold calls (76c), or managing someone else's portfolio (76e). `0` for education,
market commentary, a person showing their own portfolio, tax or property advice, generic
signals of a licensed broker, and licensed firms. Element labels: `fail` = element present.

Tricky negatives are the most valuable items: material that looks like a violation but is not
(education with a disclaimer, a compliant page with past performance, a licensed adviser).

## Confirming labels

Real items were proposed by an AI agent (`labeler: agent`) or by a documented rule over an
official list (`labeler: rule`). The hold-out split needs a review of every item before its
numbers are quoted: by a person (`--labeler human`, the default) or, as done so far, by an
agent consensus (`--labeler agent`, below).

```bash
make label BY=<github-login>          # interactive: hold-out, compliant sources, unreviewed
cd backend && uv run python -m investwatch.golden.label --status
cd backend && uv run python -m investwatch.golden.label --module m3 --split train --by <login>
```

Keys: `Enter`/`a` accept, `0`/`1` set the label, `x` exclude (asks for a reason), `s` skip,
`q` quit. Each decision is saved at once to `golden.jsonl` as a `review`
(`accepted` / `changed` / `excluded`, who, when, previous label) and survives `make golden`.

Spreadsheet instead of a terminal:

```bash
cd backend
uv run python -m investwatch.golden.label --export-csv ../data/sheet.csv
# fill `decision` (accept / change / exclude), `new_label` for change, optional `comment`
uv run python -m investwatch.golden.label --import-csv ../data/sheet.csv --by <login>
```

Rules for reviewers:

1. Read the whole text and open the URL if the text is cut. Judge the item, not the module's
   output.
2. When two reasonable people could disagree, exclude the item with a reason. A small clean
   set beats a large noisy one.
3. Two reviewers per hold-out item where time allows; the second one uses `--reviewed`.
4. Never change a label to make a metric look better. Never look at `predictions.jsonl` while
   labelling.

### Agent-consensus review of the hold-out (2026-11-21)

No person reviewed the hold-out; the team lead asked for an agent review instead, and the
reports say so. The 38 real hold-out items with text were each judged **blind** by three
Claude Sonnet reviewers with different lenses (legal, analyst, false-positive sceptic),
without the proposed label or any model output; the 4 split votes were adjudicated by Claude
Opus. 34 verdicts were unanimous. The verdicts were imported with

```bash
cd backend && uv run python -m investwatch.golden.label --import-csv <sheet.csv> \
    --by "agent-consensus:3xsonnet+opus" --labeler agent
```

so every reviewed item has `labeler: agent` and a `review` with that `by`; reports never count
it as human. 10 verdicts differ from the proposed label (9 changed, 1 excluded). Most notably,
KNF warning-list pages labelled M3 = 1 by the list rule (`labeler: rule`) are 0 on their
visible text: KNF listed those entities for unauthorised brokerage, not investment advice.
Consequences:

* Warning-list membership stays an entity-level "unauthorised entity" signal
  (`knf_warning` on `/analyze`), never a text label for M3.
* `make train` leaves out the 7 train items labelled only by the list rule.
* The 25 YouTube hold-out items without text stay unscored.

## Split

`make golden` assigns a deterministic 60/40 train / hold-out split by leakage group: web pages
by domain, social posts by author, synthetic pages by fictional firm. A group never spans both
splits. Groups are stratified by module, origin and headline eligibility. Thresholds and
weights may be tuned on `train` only; quoted numbers come from `holdout`.

## Adding items

* **Synthetic**: add a `PageSpec` (M2, flags map to rule labels in `rule_labels()`) or a
  `TextSpec` (M1/M3, with `rules="2=fail 3=na"` notation) in `golden/synth.py`, then
  `make golden`. New flags need a rule mapping and a test.
* **Demo pages**: add the page to `demo-sites/public/` and a `DemoPage` with the rules it
  targets in `golden/demo.py`.
* **Real**: put the post in `raw/posts.jsonl` (compliant collection only, see above), add a
  line to `labels/real.jsonl`, run `make golden`, then confirm it with `make label`.

Then `make eval` and commit `golden.jsonl`, `predictions.jsonl` and `docs/eval/latest.md`
together. `seed` reloads the golden labels into the calibration panel.
