# Engineering log

One entry per working session: decision · reason · alternative · result · next.

## 2026-10-25 — M0 Setup

- **Decision:** Redis and the Celery worker are added in M1, not M0.
  **Reason:** Nothing uses them until ingestion runs in the background, and each new tool gets explained when it's first needed.
- **Decision:** `user_id` lives on top-level tables only (projects, sources, runs). Chunks, evidence, reports, and events inherit ownership through their parent's foreign key.
  **Reason:** Ownership has one source of truth, so it can't drift between parent and child rows. Child lookups always filter by an already-checked parent anyway.
  **Alternative:** `user_id` on every table. More duplication, and a risk of inconsistent rows.
- **Decision:** The pgvector `embedding` column and the full-text column are not created yet.
  **Reason:** The vector size depends on the embedding model chosen in M2. Adding them later through new migrations is also good Alembic practice.
- **Decision:** Status columns are plain `VARCHAR` with Python enums, not native Postgres `ENUM` types.
  **Reason:** Adding a new status later is a code-only change, with no `ALTER TYPE` migration.
- **Decision:** The `users` table already has the columns `fastapi-users` expects (`hashed_password`, `is_active`, `is_superuser`, `is_verified`).
  **Reason:** Adding auth in M8 needs no change to the table's shape.
- **Issue:** Docker Desktop had an empty file-sharing list and a broken credential helper link, which blocked mounts and image pulls. See the M0 notes in the README progress tracker.

## 2026-10-25 — M1 PDF ingestion

- **Decision:** Chunks never cross page boundaries.
  **Reason:** Every citation must point to exactly one page.
  **Trade-off:** A few chunks at page ends are shorter than the target size.
- **Decision:** Chunk size ~1200 characters (~300 tokens), overlap ~200, sentence-based, preferring paragraph breaks.
  **Reason:** Fits common embedding models' input limits; overlap keeps facts that straddle a boundary whole. M3 compares sizes.
- **Decision:** Ingestion is idempotent (deletes old chunks first), enqueued only after the DB commit, with `acks_late`.
  **Reason:** Jobs can run twice (retry, worker crash); results must be identical.
- **Decision:** File handling in the upload route runs in a thread (`run_in_threadpool`).
  **Reason:** Ruff's ASYNC rules flagged blocking disk writes inside an async route; they would stall every other request.
- **Issue found on real data:** 7 tiny chunks (e.g. "Model av.") where a short fragment preceded a long unbroken run (tables, author lists).
  **Fix:** Never close a chunk with less than `min_size` of new text. Result: min chunk 9 → 76 characters (the remaining one is a page with only a figure caption).
- **Issue found on real data:** 56 chunks contained typographic ligatures (`ﬁne-tuning`), which keyword search would miss.
  **Fix:** Unicode NFKC normalization in `clean_page_text`. 0 ligatures afterwards.
- **Result:** 16 papers, 338 pages → 1,279 chunks (avg 1,027 characters). Exit test: 3 random chunks verified against `pdftotext` output of the claimed page; all found only on that page.
- **Known limitations (for later):** figure and table text is extracted as plain text (axis labels, numbers); reference lists are chunked like body text and may add noise to search. Revisit in M3 if the benchmark shows it hurts. Math symbols can glue onto words (`documentsz`).
- **Note:** the arXiv API now redirects HTTP to HTTPS; the M7 connector must use HTTPS.

## 2026-10-25 — M2 Semantic search + first UI

- **Decision:** `BAAI/bge-small-en-v1.5` via FastEmbed (ONNX), 384 dimensions.
  **Reason:** 512-token input fits our chunks; free and local; no PyTorch. `all-MiniLM-L6-v2` would truncate at 256.
- **Decision:** Embedding behind an `Embedder` adapter; `HashEmbedder` in tests.
  **Reason:** No model download in CI; real model swappable later.
- **Decision:** HNSW index (`m=16`, `ef_construction=64`, cosine) plus `hnsw.iterative_scan = strict_order` for project-filtered queries.
- **Decision:** UI gets a real visual system now (Tailwind v4 tokens, light/dark), not deferred to M9.
  **Reason:** Low cost now; better to demo.
- **Result:** 1,279 chunks embedded (~8 min on CPU). Search latency 66–180 ms. 35 backend + 7 frontend tests.
- **Smoke test (`eval/smoke_questions.json`, 10 paraphrased questions):** hit rate @5 = 7/10, @1 = 5/10.
  - q06 miss = labelling too narrow (Liu p3 and Leng p2 also answer it).
  - q01 miss = paraphrase gap ("where the answer sits" vs "position of relevant information").
  - q02 miss = generic RAG introductions outrank the Self-Route method (p4).
  - These become M3 benchmark cases; baseline recorded as-is.
- **Known issue:** CPU oversubscription during embedding (2 worker processes × 8 ONNX threads).

## 2026-10-25 — M3 Hybrid search + evaluation harness

- **Decision:** Keyword search with Postgres full-text search (generated `tsvector` + GIN), any-word (OR) matching, `ts_rank_cd`.
- **Decision:** Hybrid = RRF (k=60) over the top 50 of each method; default search mode; keyword weight 1.0 (weighted RRF available).
- **Decision:** Benchmark labels are (paper, page) pairs so they survive chunk-size changes; 37 questions (24 fact, 6 multi, 3 conflict, 4 unanswerable), draft labels pending user review via pooled review sheet.
- **Decision:** Drop number-only chunks (`prose_ratio < 0.2`) and remove repeated headers/footers/page numbers. 1,279 → 1,202 chunks.
- **Results (draft labels, cleaned corpus, 33 answerable questions):**

  | Mode | hit@5 | mrr@10 | precision@5 | source_recall@10 | p50 ms |
  |---|---|---|---|---|---|
  | semantic | 0.697 | 0.442 | 0.255 | 0.745 | 24 |
  | keyword | 0.606 | 0.401 | 0.200 | 0.664 | 27 |
  | hybrid | 0.818 | 0.528 | 0.321 | 0.679 | 57 |

- **Smoke set (10 paraphrased questions):** semantic 7/10, keyword 3/10, hybrid 5/10. Combined 43 questions: hybrid 32, semantic 30.
- **Before vs after clean-up (hit@5):** semantic 0.636 → 0.697, keyword 0.545 → 0.606, hybrid 0.818 → 0.818.
- **Findings:** hybrid's edge depends on query wording; multi-source/conflict source recall is low (~0.3–0.4) in all modes (diversity problem, candidate fix: MMR); search scores can't detect unanswerable questions.
- **Next:** user reviews labels (`eval/review/benchmark_v1_review.md`), re-run `make eval` on reviewed labels; M4 needs the LLM decision.

## 2026-11-14 — M4 Cited answers (code) + experiment B

- **Decision (user):** Gemini API for answers (free tier, multimodal) and Grok for the second model. Label review deferred until after M4; all numbers stay provisional.
- **Finding:** xAI Grok has no standing free API tier (billed per token, checked 2026-11). Groq (different company) has a free tier with the same OpenAI-compatible API, so both are presets of one `OpenAICompatibleProvider`; whichever has a key is used.
- **Decision:** `LLMProvider` adapter over plain `httpx` (no vendor SDKs). Fallback chain moves on only for rate limits/outages (429, 5xx, timeouts), never for bad keys or requests.
  **Reason:** free-tier rate limits are the main operational risk; config errors must stay visible.
- **Decision:** JSON output validated with Pydantic (one retry quoting the error) instead of provider-enforced JSON schemas.
  **Reason:** Gemini and OpenAI-style APIs support different schema subsets; this works identically everywhere.
- **Decision:** answers cite passage labels (`S1…Sn`), not chunk UUIDs. Unknown labels are dropped and counted (`dropped_citations`), and claims without a citation are flagged in the UI.
  **Reason:** short labels are easy for the model to copy and trivial to validate; UUIDs invite typos.
- **Decision:** answers are saved as `research_runs` (`config.kind = "answer"`) with `evidence_items`, `reports` and `run_events`. No migration needed.
- **Decision:** judge = a different model where possible (`LLM_JUDGE_PROVIDERS=grok,groq,gemini`); correctness judged against the labelled reference pages, since there are no written reference answers.
- **Decision:** answer-eval results JSON holds metrics, verdicts and (paper, page) references only; claim text and quotes go to the git-ignored spot-check sheet in `eval/review/`.
- **Result:** 98 backend + 12 frontend tests; lint clean. LLM experiments (A, C, exit test) not run yet: no API key in `.env`.
- **Incident:** experiment B (chunk sizes) was interrupted when the session ended, leaving the corpus half re-chunked at 800 characters. Restored to 1200 (1,198 chunks; M3 had 1,202, difference not yet explained). B to be re-run.

## 2026-11-14 — M5 Reranking

- **Decision:** cross-encoder `Xenova/ms-marco-MiniLM-L-6-v2` via FastEmbed's `TextCrossEncoder` (already a dependency), re-scoring the top 30 hybrid results. `OverlapReranker` (word overlap) in tests.
- **Decision:** answers retrieve with rerank by default (`answer_retrieval_mode`); the search box stays on hybrid with "Reranked" as an option.
  **Reason:** quality jump is large; latency on this laptop (5–9 s) is fine next to an LLM call but not for a search box.
- **Experiment D (draft labels, 33 answerable questions):**

  | Config | hit@5 | hit@10 | MRR@10 | source_recall@10 | p50 |
  |---|---|---|---|---|---|
  | hybrid | 0.788 | 0.848 | 0.500 | 0.710 | 117 ms |
  | rerank L-6, top 20 | 0.818 | 0.970 | 0.618 | 0.808 | 4.5 s |
  | **rerank L-6, top 30** | 0.848 | 0.970 | 0.693 | 0.838 | 6.5 s |
  | rerank L-6, top 50 | 0.909 | 0.970 | 0.705 | 0.851 | 10.9 s |
  | rerank L-12, top 30 | 0.879 | 0.970 | 0.736 | 0.846 | 13.7 s |

  Smoke set (10 paraphrased): hit@5 semantic 0.7, hybrid 0.5, rerank 0.7; hit@10 0.8 / 0.6 / 0.9.
- **Finding:** the laptop slows ~5× under sustained load (same test 1.2 s → 6.3 s), so all latencies this session are inflated; semantic search measured 92 ms vs 24 ms in M3.
- **Fix:** stuck ingestion after worker restarts: Celery `visibility_timeout` 900 s, `make reingest-stuck`, eval runner refuses a partly ingested corpus.
- **Result:** 105 backend + 13 frontend tests. Exit test met: experiment D recorded.
