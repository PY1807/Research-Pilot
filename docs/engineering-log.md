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
