# 0006: Rule engine in YAML and noisy-OR scoring

**Context:** M2 checks 18 rules (attachment 4) of three kinds: text, render and LLM. Results must be explainable, per rule, with legal basis and evidence.

**Decision:** Rules declared in `risk_rules.yaml` (id, name, legal basis, type, weight) and implemented as pure functions registered with `@rule`. Each returns `pass/fail/na/unknown` with confidence. Score = `1 - prod(1 - w_i * c_i * [fail_i])`; per-module threshold; `high` >= tau, `medium` >= tau - 0.2.

**Consequences:** One severe violation gives a high score and several minor ones accumulate; `na`/`unknown` never raise the score; weights and thresholds are tunable on the golden set via the calibration panel.
