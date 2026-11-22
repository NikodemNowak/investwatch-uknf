"""Public, legally sourced data for the golden set (`docs/eval/DATA_SOURCES.md`).

Each source has a loader module here that (re)downloads its raw data with an honest
User-Agent and robots.txt honoured, and writes *candidates* (git-ignored, under
`data/golden/public/_candidates/`). Labels live in `data/golden/public/labels/<source>.jsonl`;
`curate` joins them into the committed `data/golden/public/<source>.jsonl` that `make golden`
reads (`records.public_items`).
"""
