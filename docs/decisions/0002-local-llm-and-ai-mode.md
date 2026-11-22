# 0002: Local LLM and AI_MODE

**Context:** The task forbids paid APIs and the jury may run the stack on a CPU-only machine; analysed content is Polish.

**Decision:** Separate `ai` service calling Ollama. GPU candidates: Bielik 11B v3.1 (Apache 2.0, Polish) and Gemma 12B, chosen by evaluation on the golden set (tie goes to Gemma, named in the task). CPU default: a 4-5B model. Embeddings: bge-m3 (MIT) via Ollama. `AI_MODE=rules` disables the LLM entirely (rules + classifier, deterministic).

**Consequences:** No torch in our images; the LLM is used only in a cascade (L-type rules or score near the threshold); demo data is pre-analysed by `seed`, so the demo works without a GPU.

**Update (21.11, roadmap 2.2):** default is now `AI_MODE=llm` with the model off the critical path: the `analyze` queue returns rules-only findings and the alert in seconds, `review_finding` on a separate `llm` queue (concurrency 1, 90 s budget per call) adds the model verdict later. CPU model: `gemma4:e2b-it-qat` (4.3 GB, 6-16 s per review, median 7.6 s, on a 20-thread CPU vs 27 s for `gemma3:4b`). When Ollama or the model is missing, findings are marked `llm_review=unavailable` and the review is retried.
