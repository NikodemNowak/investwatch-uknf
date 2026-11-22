# data/fixtures/

Demo and test fixtures for the shared contract (`backend/src/investwatch/core/schemas.py`).
Every file validates against its model in `backend/tests/core/test_schemas.py`.

**All firms, people, handles and domains here are fictional** (domains use the reserved
`.example` TLD). Register URLs point to the real KNF register category pages only to show the
shape of the data. Do not replace them with real firms: the findings describe violations.

| File | Model | Content |
|---|---|---|
| `posts.json` | `list[Post]` | 10 posts: web, YouTube, Facebook, Instagram; one `blocked`, one `no_text` |
| `findings.json` | `list[Finding]` | 12 findings, 4 per module; M2 with all 19 rule results |
| `render_snapshot.json` | `RenderSnapshot` | real capture of `demo-sites/public/promo-zloto.html` = post `…0003` (PrimeFX24 landing): risk block 9 px vs 16 px body, collapsed on the phone |
| `shots/{desktop,tablet,phone}.png` | PNG | full-page screenshots from the same capture (bboxes in the snapshot and in finding `…05` match them) |
| `firms.json` | `list[RegisteredFirm]` | 8 firms, 2 per register kind |
| `calibration.json` | `CalibrationReport` | `GET /api/calibration/m2_risk_disclosure` |
| `trend.json` | `TrendSeries` | `GET /api/stats/trend?bucket=day` (14 days) |
| `synthetic/meta_ads.json`, `synthetic/tiktok_ccl.json`, `synthetic/youtube_api.json` | API shapes (`ads_archive`, CCL ad query + detail, `videos.list`) | **synthetic** records, `"synthetic": true`, for demos without credentials; loaded by the `sample` source with target `synthetic` |

M3 rule results use ids `76a`..`76e`; status `fail` means the art. 76 element **is present**.

Refresh the render fixtures after changing `promo-zloto.html` or `render/extract.js`: render the
page with `investwatch.render.browser.Renderer` and re-run the render rules of finding `…05`
(statuses must not change); `seed` uploads the shots for post `…0003`.

`knf/html/*.html` are trimmed copies (entity tables + pagination only) of real KNF register pages
fetched on 2026-11-21; `backend/tests/registry/test_knf.py` parses them offline. They are real
public register entries, unlike the fictional firms above.
