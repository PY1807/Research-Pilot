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
