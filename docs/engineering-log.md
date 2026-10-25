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
