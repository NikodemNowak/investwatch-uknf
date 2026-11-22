### What moved and why

Labels: the 38 real hold-out items with text carry the blind agent-consensus review
(`docs/eval/LABELING.md`; agents, not people). It turned 8 KNF warning-list pages from M3 = 1
to 0, so the M3 hold-out now has only 3 positives in 22 items. Read every difference against
its interval: one item moves F1 by 0.05 to 0.3 and most intervals overlap. Nothing below was
tuned on the hold-out. Rule fixes come from train-split errors
(`ai/tests/test_rules_error_analysis.py`, one test per root cause). The heads and all
thresholds come from train-split cross-validation (`make train`).

- **M2, 0.65 → 0.80 F1.**
  - Rule changes alone (`rules-v2, old thresholds`) raise precision from 0.61 to 0.89.
    Menus, buttons and footers of real licensed broker pages no longer count as unlabelled
    promotion (rule 2) or as gain claims (rule 3). The investor's own expectation in CFD and
    bond education is no longer a forecast (rule 15).
  - The train-split F2 threshold (0.30 instead of 0.6) gives recall back. The score is a
    noisy-OR of rule weights, so one failed 0.5-weight rule scored 0.4–0.5 and never
    reached 0.6, while the label says one breach is a breach.
- **M2 regression:** rule 3 lost both of its hold-out true positives (per-rule F1
  0.80 → 0.00). The fix for firm pages is too strict for those two pages: a bare "zyski" on
  a long page now counts as a gain claim only with a figure, or when it dominates the text.
  It was not re-tuned, because the only evidence is the hold-out.
- **M3, 0.00 → 0.55 F1 (3 positives).**
  - The bilingual art. 76 cues from train pages (personal account manager / opiekun konta,
    trading signals / sygnały, PAMM / managed accounts) find 2 of the 3 positives (0.50, 3 false positives).
  - The bge-m3 head finds all 3, at 5 false positives. Precision stays the weak point,
    because train pages of warning-list brokers look a lot like advice. One of the 5
    (br-stone.net) has no art. 76 lexicon hit and is opened only by the head, at 0.50, right on
    the 0.5 gate (`M3_HEAD_GATE` in `ai/src/investwatch_ai/analyze.py`); bge-m3 vectors from a
    different Ollama build moved it across (see the quality-round note above).
  - The lexicon-only fallback gets 3/3 at 6 false positives.
- **M1: the heads do not help on this hold-out.**
  - Rules-v2 alone reach 0.92 (6/6, 1 FP), up from 0.83 before.
  - The bge-m3 head scores 0.83 (one miss). The lexicon fallback scores 0.75 (4 false
    positives at its train-CV threshold of 0.19).
  - Train CV had favoured the heads, and 13 items cannot settle it: every M1 interval
    overlaps.
  - M1 is where losing Ollama costs most. `CLASSIFIER=false` restores the rules-only score.
- **Synthetic training data.** The `golden-only training` row drops the 444 train-only
  generated texts. Without them, M1 has 4 false positives instead of 1, and M3 has 12
  instead of 5. The generated hard negatives mostly buy precision.
- **LLM review (gemma4:e2b-it-qat on an RTX 5080, about 1.3 s per reviewed item; 100 items reviewed).**
  - It changes verdicts on 87 items. Mostly it resolves rule 9 (and 11) from `unknown` to
    `pass` (75), leaves rule 18 `unknown` when it cannot confirm (27) and sets rule 2 to
    `pass` on broker pages (18).
  - At module level it changes nothing on this hold-out. Per rule it costs rule 2 its only
    true positive and adds one rule-3 false positive.
  - It explains findings, but it does not improve detection here.
- **KNF warning list:** treated as an "unauthorised entity" flag that opens an M3 finding,
  not as a score floor. Used as a 0.8 floor, it had pushed M3 to 11 false positives once the
  review showed that listed brokers' pages are not advice. As a flag it still opens 7 extra
  findings and changes 3 decisions, through the head's low threshold.
