# Decisions

Why ResearchPilot uses each technology, in plain language. Entries are written while building, once the real reasons are clear.

---

## Docker + docker compose (added in M0)

**What it does in ResearchPilot:**
Runs every service the app needs (Postgres with pgvector, the FastAPI server, the React dev server, and later Redis and a Celery worker) in isolated containers. `make up` starts all of them with one command.

**Why it helps / what it adds:**
- **Same setup everywhere.** Your laptop, GitHub's CI machines, and the production server all run the exact same Postgres + pgvector version. No "works on my machine" bugs.
- **No manual installs.** pgvector normally has to be compiled into Postgres. Here it's just an image name: `pgvector/pgvector:0.8.0-pg16`.
- **Isolation.** Your Mac already runs its own Postgres on port 5432. Ours lives in a container and is exposed on 5433, so the two never interfere.
- **Deployment-ready.** The `backend/Dockerfile` is close to what will run in production in M10.

**Trade-offs and alternatives:**
| Option | Why not (for now) |
|---|---|
| Install everything with Homebrew | Works, but every service is set up by hand, versions drift between machines, and it doesn't help with deployment |
| Kubernetes | Built for running many machines at scale. Far too heavy for one app; the blueprint explicitly rules it out |
| Podman | A Docker-compatible alternative with no background daemon. Fine, but Docker has better macOS tooling and far more learning material |

What we give up: Docker Desktop uses a few GB of memory, and file access between macOS and containers is slightly slower than native.

**How it works underneath:**
- An **image** is a frozen, layered snapshot of a small Linux system with a program installed. Each line in a `Dockerfile` creates one layer. Docker caches layers, which is why we copy `pyproject.toml` and install dependencies *before* copying the code: editing code doesn't trigger a reinstall.
- A **container** is a running copy of an image. It isn't a full virtual machine: on Linux it's an ordinary process that the kernel isolates (its own filesystem, network, and process list) using features called *namespaces* and *cgroups*. On a Mac, Docker Desktop runs one small hidden Linux VM, and all containers share it.
- A **volume** stores data outside the container, so the database survives restarts (`pgdata` in our compose file). A **bind mount** maps a folder from your Mac into the container. That's how code edits show up live (`./backend:/app`).
- **docker compose** reads `docker-compose.yml`, creates a private network where services find each other by name (the API connects to `db:5432`, not `localhost`), and starts them in dependency order. The `healthcheck` plus `depends_on: condition: service_healthy` means the API waits until Postgres is actually ready.

**Where to look:** `docker-compose.yml`, `backend/Dockerfile`, `backend/.dockerignore`, `docker/postgres/init-test-db.sql`, `Makefile`

**Try it yourself:**
- `docker compose ps` shows running services and their ports.
- `docker compose logs -f api` shows live API logs.
- `make psql` opens a SQL shell inside the database container. Try `\dt` to list tables.

---

## Alembic (added in M0)

**What it does in ResearchPilot:**
Keeps the database structure (tables, columns, indexes) in sync with our Python models, through versioned migration files that are committed to git.

**Why it helps / what it adds:**
- **The schema has a history.** Every change is a file in `backend/alembic/versions/`, reviewed and committed like code.
- **Every database gets the same changes.** Laptop, test database, CI, and production all run `alembic upgrade head` and end up identical.
- **Reversible.** Each migration has `upgrade()` and `downgrade()`, so a bad change can be rolled back.
- **Autogenerate saves typing.** Alembic compares the models with the live database and writes a draft migration.
- **Tests prove the migrations work.** The test suite builds its database *only* by running the migrations, never by creating tables directly from models.

**Trade-offs and alternatives:**
| Option | Why not |
|---|---|
| `Base.metadata.create_all()` | Creates missing tables but can never change an existing one (add a column, add an index). Fine for a demo, useless once there's real data |
| Django migrations | Only work with the Django ORM. We use FastAPI + SQLAlchemy, and Alembic is SQLAlchemy's official migration tool, written by the same author |
| Raw SQL files (e.g. Flyway, dbmate) | Language-neutral, but nothing is generated from the models, so every change is written twice |

What we give up: autogenerate isn't magic. It can't see things like Postgres extensions or data changes, so every generated migration has to be read and sometimes edited. Our first migration needed `CREATE EXTENSION vector` added by hand.

**How it works underneath:**
- Each migration file has a `revision` ID and a `down_revision` pointing to the one before it, which forms a chain (like git commits).
- Alembic stores the currently applied revision in a one-row table called `alembic_version` inside the database.
- `alembic upgrade head` walks the chain from the stored revision to the newest one and runs each `upgrade()` inside a transaction. Postgres can roll back schema changes too, so a failed migration leaves nothing half-done.
- `alembic revision --autogenerate` loads our models (`Base.metadata`), inspects the real database, and writes the difference as Python code.
- `alembic check` reports whether models and database have drifted apart. It's useful as a safety check.
- A **naming convention** in `app/db/base.py` gives every constraint a predictable name (e.g. `fk_research_runs_user_id_users`), so later migrations can find and change it.

**Where to look:** `backend/alembic/env.py`, `backend/alembic/versions/`, `backend/alembic.ini`, `backend/app/db/base.py`, `backend/app/db/models.py`

**Try it yourself:**
- `docker compose exec api alembic history` shows the migration chain.
- `docker compose exec api alembic current` shows which revision the database is on.
- In `make psql`, run `SELECT * FROM alembic_version;` to see where Alembic stores that revision.

---

## Redis (added in M1)

**What it does in ResearchPilot:**
Holds the queue of background jobs. When you upload a PDF, the API puts a small message ("ingest source 42") into Redis, and the Celery worker takes it out and does the work.

**Why it helps / what it adds:**
- **Very fast.** Redis keeps its data in memory, so adding and taking messages takes microseconds.
- **Decouples the API from slow work.** The API and the worker never talk directly; they only share the queue. Either can restart without the other noticing.
- **Tiny to run.** One small container with no configuration.
- **Useful later.** The same Redis can hold rate-limit counters (M8) and caches if we need them.

**Trade-offs and alternatives:**
| Option | Why not (for now) |
|---|---|
| RabbitMQ | A dedicated message broker with stronger delivery guarantees and routing features. More to run and learn, and we don't need its extras for one queue |
| Postgres as the queue (e.g. `SELECT ... FOR UPDATE SKIP LOCKED`) | One less service, and a perfectly valid choice. But Celery's support for it is weak, and Redis is the standard pairing employers expect to see |
| Kafka | Built for huge event streams across many services. Massive overkill here |

What we give up: Redis keeps data in memory, so a hard crash can lose queued messages that weren't saved to disk yet. That's acceptable here because the real job status lives in Postgres (a stuck `pending` source can simply be re-queued with `make reingest`).

**How it works underneath:**
- Redis is a key-value store where values can be data structures: strings, lists, sets, hashes. Everything lives in RAM, and a single thread processes commands one at a time, which makes each command atomic without locks.
- Celery uses a Redis **list** as the queue. The API runs `LPUSH` to add a message on one end; workers run a blocking pop (`BRPOP`) on the other end, which waits efficiently until a message arrives.
- With `acks_late`, Celery also keeps the in-flight message aside until the task finishes, so a crashed worker's job is redelivered instead of lost.

**Where to look:** `docker-compose.yml` (the `redis` service), `backend/app/worker.py` (`broker=settings.redis_url`)

**Try it yourself:**
- `docker compose exec redis redis-cli ping` replies `PONG`.
- `docker compose exec redis redis-cli llen celery` shows how many jobs are waiting (usually 0, because the worker is fast).

---

## Celery (added in M1)

**What it does in ResearchPilot:**
Runs slow jobs in a separate worker process. Today that's PDF ingestion (extract text, chunk, save). From M6 it also runs whole research agent runs, which can take minutes.

**Why it helps / what it adds:**
- **The API stays fast.** Uploading 16 papers took 1.5 seconds; the worker then processed them in the background in 0.2–3.5 seconds each.
- **Survives crashes.** With `task_acks_late`, a job is only marked done after it finishes. If the worker dies mid-job, the job runs again.
- **Retries.** Ingestion retries automatically (with growing delays) if the database is briefly unreachable.
- **Scales out.** Run more workers, or raise `--concurrency`, and jobs spread across them with no code change.

**Trade-offs and alternatives:**
| Option | Why not |
|---|---|
| FastAPI `BackgroundTasks` | Runs inside the API process after the response. Simple, but if the API restarts, the job is lost, and heavy work slows the API down |
| RQ (Redis Queue) | Simpler than Celery and a good choice for small apps. Fewer features (scheduling, retries with backoff, routing) and less common in job listings |
| Dramatiq / arq | Lighter, modern alternatives (arq is async-native). Smaller ecosystems |
| Temporal | Durable workflows with full step history. Powerful for long agent runs, but a large system to operate for a solo project |

What we give up: Celery is big, its configuration has many sharp edges, and it's synchronous at heart. Our ingestion code is async, so each task wraps it in `asyncio.run()` and uses its own unpooled database engine (connections can't be shared across event loops).

**How it works underneath:**
- In the API, `ingest_source_task.delay(source_id)` doesn't run the function. It serializes the task name and arguments to JSON and pushes that message to Redis.
- The worker (`celery -A app.worker worker`) imports the same code, waits on the queue, and when a message arrives, looks up the function by name (`sources.ingest`) and calls it with the arguments.
- `--concurrency=2` starts 2 child processes, so 2 jobs run in parallel. `worker_prefetch_multiplier=1` makes each process take only one job at a time, so a long job doesn't hold others hostage.
- Because a job can run twice (retry, or redelivery after a crash), tasks must be **idempotent**: running them again gives the same result. Ingestion deletes a source's old chunks before inserting new ones.
- The API enqueues the job only *after* committing the database row. Otherwise the worker could pick up the message before the row exists.

**Where to look:** `backend/app/worker.py`, `backend/app/sources/tasks.py`, `backend/app/sources/router.py` (`upload_source`), `docker-compose.yml` (the `worker` service)

**Try it yourself:**
- `make worker-logs`, then upload a PDF and watch `Task sources.ingest[...] received` and `succeeded in 0.8s`.
- `make reingest` re-queues every source; watch the worker process them all again.


---

## Embeddings: BAAI/bge-small-en-v1.5 via FastEmbed (added in M2)

**What it does in ResearchPilot:**
Turns every chunk, and every search question, into a list of 384 numbers (a vector) that captures its meaning. Search then finds chunks whose vectors point in nearly the same direction as the question's.

**Why it helps / what it adds:**
- **Finds meaning, not just words.** "Why do models miss facts in the middle of a long prompt?" finds the *Lost in the Middle* paper even though the wording differs.
- **Free and local.** Runs on the CPU inside our containers: no API key, no per-request cost, no data leaves the machine.
- **Fits our chunks.** Reads up to 512 tokens; our chunks are about 300.
- **Swappable.** The app only talks to an `Embedder` interface, so a hosted model can replace it later without touching ingestion or search.

**Trade-offs and alternatives:**
| Option | Why not (for now) |
|---|---|
| `all-MiniLM-L6-v2` | Very popular and fast, but stops reading at 256 word pieces, so it would silently cut off the end of our ~300-token chunks |
| `sentence-transformers` library | Same models, but needs PyTorch (1–2 GB, with unused GPU libraries on CI's Intel Linux). FastEmbed runs the same model through ONNX Runtime (~50 MB) |
| Hosted embeddings (OpenAI, Voyage, Cohere) | Often higher quality, but cost money per call, need an API key, and send our text to a third party. Can be swapped in via the adapter if M3 shows we need it |
| Larger local models (bge-base, bge-large) | Better quality, but 3–10× slower on CPU. A candidate experiment for M3 |

What we give up: a small model is weaker on loose paraphrases. The M2 smoke test shows this: one question phrased as "where the answer sits inside a long prompt" missed the paper that calls it "position of relevant information".

**How it works underneath:**
1. **Tokenize:** the text is split into word pieces (`retriev` + `##al`), each mapped to an ID.
2. **Transformer:** 12 layers of self-attention let every token look at every other token, so each token's vector reflects its meaning *in context*.
3. **Pooling:** the special first token (`[CLS]`), trained to summarise the whole text, becomes the text's single vector.
4. **Normalize:** the vector is scaled to length 1, so only its direction matters.
- The model was trained on huge numbers of (question, relevant passage) pairs to place matching pairs close together and push non-matching pairs apart (contrastive learning).
- bge models expect a short instruction in front of *queries* but not passages; FastEmbed's `query_embed` adds it.
- **Similarity** is the cosine of the angle between two vectors: 1 means same direction (same meaning), around 0 means unrelated.

**Where to look:** `backend/app/embeddings.py`, `backend/app/sources/ingestion.py` (embedding step), `backend/app/main.py` (model preloaded at startup)

**Try it yourself:** search in the UI for a question phrased in your own words, then open the linked page and check whether the passage really answers it.

---

## pgvector and the HNSW index (added in M2)

**What it does in ResearchPilot:**
Stores each chunk's embedding in a `vector(384)` column in Postgres, next to its text and page number, and finds the closest chunks to a question with one SQL query.

**Why it helps / what it adds:**
- **One database for everything.** Vectors live in the same row as the text, page, source, and owner, so search can filter by project and join to source titles in a single query.
- **No extra service.** No separate vector database to run, secure, back up, or keep in sync.
- **Fast enough to scale.** The HNSW index answers searches in milliseconds (66–180 ms end to end here, including embedding the question).

**Trade-offs and alternatives:**
| Option | Why not (for now) |
|---|---|
| Pinecone | Fully managed and very scalable, but a paid external service, and every chunk's text and metadata would need syncing to it |
| Qdrant / Weaviate / Milvus | Dedicated vector databases with more search features. One more service to run and keep consistent with Postgres |
| FAISS | A fast in-memory library, not a database: no persistence, no filtering by project, no transactions |
| No index (exact search) | Fine at 1,279 chunks, but compares the question against *every* row, so it slows down linearly as the corpus grows |

What we give up: dedicated vector databases can be faster at hundreds of millions of vectors and offer more tuning. At our scale Postgres is the simpler, safer choice; the blueprint says to reconsider only if measurements justify it.

**How it works underneath:**
- **Distance operators:** `<=>` is cosine distance (what we use), `<->` is straight-line (L2) distance, `<#>` is negative inner product. Our score is `1 - cosine distance`.
- **HNSW (Hierarchical Navigable Small World)** is a graph index. When a vector is added, it is linked to its nearest neighbours. Upper layers contain a few vectors with long links (motorways); the bottom layer contains all of them with short links (local streets).
- **Searching:** start at the top layer, greedily hop towards the question's vector, drop a layer, refine, and repeat. Only a small fraction of vectors is ever compared.
- **It's approximate.** It can occasionally miss a true nearest neighbour; `m` (links per node, 16), `ef_construction` (effort while building, 64), and `ef_search` (effort while searching) trade speed for accuracy.
- **Filtering gotcha:** the index finds neighbours across *all* projects, then `WHERE project_id = …` removes other projects' chunks, which could leave fewer than k results. pgvector 0.8's **iterative scan** (`SET LOCAL hnsw.iterative_scan = strict_order`) keeps walking the graph until k rows survive the filter.
- `vector_cosine_ops` in the index definition must match the operator in queries (`<=>`); otherwise Postgres can't use the index.

**Where to look:** `backend/app/db/models.py` (`embedding` column and HNSW index), `backend/alembic/versions/*_add_chunk_embeddings.py`, `backend/app/retrieval/service.py`

**Try it yourself (in `make psql`):**
```sql
\d document_chunks          -- see the vector(384) column and the hnsw index
SELECT vector_dims(embedding), left(embedding::text, 60) FROM document_chunks LIMIT 1;
-- The 3 chunks most similar to one chunk from Lost in the Middle:
WITH q AS (SELECT c.embedding FROM document_chunks c JOIN source_documents s ON s.id = c.source_id
           WHERE s.title LIKE '02_%' AND c.page_number = 1 LIMIT 1)
SELECT s.title, c.page_number, round((1 - (c.embedding <=> q.embedding))::numeric, 3) AS similarity
FROM document_chunks c JOIN source_documents s ON s.id = c.source_id, q
ORDER BY c.embedding <=> q.embedding LIMIT 4;
```

---

# Problems solved

Real problems hit while building, and how each was fixed. Each entry has the problem, the fix in plain words, and the technical fix.

## Session 1 (2026-10-25): setup, M0, M1

### Environment and tooling

**1. Docker couldn't see the project folder**
- **Problem:** Starting the containers failed with `Mounts denied: the path ... is not shared from the host`.
- **Simple fix:** Docker Desktop had been told it may not touch *any* folder on the Mac. We allowed it to use `/Users`.
- **Technical fix:** Docker Desktop's `FilesharingDirectories` setting was an empty list, so bind mounts (`./backend:/app`) were refused. Added `/Users` in Settings → Resources → File sharing.

**2. Image downloads hung or failed**
- **Problem:** `docker pull` either hung forever or failed with `docker-credential-desktop: executable file not found`.
- **Simple fix:** Docker's login helper was missing or broken, and Docker Desktop was very old. Updating Docker fixed the hang, and putting Docker's own folder first on the PATH lets it find the helper.
- **Technical fix:** symlinks in `/usr/local/bin` pointed to `/Volumes/Docker/...` (the unmounted installer disk), and the old helper (Docker 4.38) hung. Updated to 4.96. Added `/Applications/Docker.app/Contents/Resources/bin` to `PATH`. While diagnosing, a temporary `DOCKER_CONFIG` without `credsStore` confirmed the helper was the cause.

**3. Port 5432 already in use**
- **Problem:** Postgres couldn't start: `bind: address already in use` on port 5432.
- **Simple fix:** another Postgres was already running on the Mac. Ours now uses a different door, 5433, and the old one is left alone.
- **Technical fix:** mapped `"5433:5432"` in `docker-compose.yml`. Inside Docker, containers still use 5432; only the host-side port changed. Updated the default URLs in `config.py`, `conftest.py`, and `.env.example`.

**4. Port 6379 already in use (Redis)**
- **Problem:** a local Redis already owned port 6379.
- **Simple fix:** our Redis doesn't need to be reachable from the Mac at all, so we don't open a port for it.
- **Technical fix:** the `redis` service has no `ports:` entry. The API and worker reach it as `redis:6379` on Docker's internal network. Simpler and more secure.

**5. Docker Desktop window wouldn't open**
- **Problem:** Docker was running, but its window didn't appear.
- **Simple fix:** restarted Docker Desktop, then opened its Settings page with a direct link.
- **Technical fix:** `osascript -e 'quit app "Docker"'`, then `open -a Docker`, then `open "docker-desktop://dashboard/settings"`. The harmless `-600` error came from sending a command while the app was still quitting or starting.

**6. Pushing to the new GitHub repo safely**
- **Problem:** GitHub's suggested commands include `echo "# Research-Pilot" >> README.md` and an HTTPS remote.
- **Simple fix:** skipped the README line, which would have overwritten our plan, and used the SSH login that already works.
- **Technical fix:** `git remote add origin git@github.com:PY1807/Research-Pilot.git`, then `git push -u origin main`. HTTPS would have needed a credential helper that isn't set up.

### Database and migrations

**7. Alembic didn't create the pgvector extension**
- **Problem:** the autogenerated migration created all 8 tables but didn't enable `vector`.
- **Simple fix:** Alembic only compares tables, so we added the extension line by hand.
- **Technical fix:** added `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` to `upgrade()`, and `DROP EXTENSION` to `downgrade()`. Verified with downgrade → upgrade and `alembic check`.

**8. A misleading constraint name**
- **Problem:** the unique rule on `(source_id, chunk_index)` was named `uq_document_chunks_source_id`, as if it covered only one column.
- **Simple fix:** changed the naming rule so names include every column.
- **Technical fix:** the naming convention went from `%(column_0_name)s` to `%(column_0_N_name)s`, giving `uq_document_chunks_source_id_chunk_index`. Predictable names let later migrations find constraints.

**9. Alembic deprecation warning**
- **Problem:** tests printed `No path_separator found in configuration`.
- **Simple fix:** added the setting the newer Alembic expects.
- **Technical fix:** added `path_separator = os` to `alembic.ini`.

### Backend code

**10. An old FastAPI pattern flagged by the linter**
- **Problem:** Ruff rule B008: "Do not perform function call `Depends` in argument defaults".
- **Simple fix:** switched to FastAPI's modern style for shared dependencies.
- **Technical fix:** defined `SessionDep = Annotated[AsyncSession, Depends(get_session)]` and `CurrentUser` the same way. Routes declare `session: SessionDep`.

**11. File saving would freeze the whole API**
- **Problem:** Ruff rule ASYNC240: blocking file operations inside an `async` route.
- **Simple fix:** writing a 50 MB file inside the async route would make every other request wait. The file work now happens on a side thread.
- **Technical fix:** `_save_upload` became a normal (sync) function, called with `await run_in_threadpool(...)`. Moving and deleting files work the same way, so the event loop stays free.

**12. Database connections and multiple event loops (prevented)**
- **Problem:** async database connections belong to the event loop that opened them. Tests and Celery tasks each create new loops, and reusing pooled connections across loops crashes.
- **Simple fix:** in those places, open a fresh connection each time instead of reusing a pool.
- **Technical fix:** tests use `NullPool` (`env == "test"`). Each Celery task runs `asyncio.run(...)` with its own `create_async_engine(..., poolclass=NullPool)` and disposes it afterwards.

**13. The worker could look for a row that isn't saved yet (prevented)**
- **Problem:** if the job is queued before the database commit, a fast worker might start before the new source row exists.
- **Simple fix:** save first, then queue the job.
- **Technical fix:** `ingest_source_task.delay(...)` is called only after `await session.commit()` in `upload_source`.

**14. Retries could duplicate chunks (prevented)**
- **Problem:** a job can run twice, after a crash with `acks_late` or after a retry.
- **Simple fix:** each run first throws away the previous run's chunks, so running twice gives the same result.
- **Technical fix:** `ingest_source` deletes `DocumentChunk` rows for the source before inserting new ones (idempotent). Covered by `test_running_ingestion_twice_does_not_duplicate_chunks`.

**15. Small frontend and framework fixes**
- `vite.config.ts` uses `process.env`, which TypeScript didn't recognize. Fixed by installing `@types/node`.
- Starlette renamed `HTTP_413_REQUEST_ENTITY_TOO_LARGE`. Fixed by switching to `HTTP_413_CONTENT_TOO_LARGE`.

### Data quality (found by running on the real 16 papers)

**16. Tiny useless chunks**
- **Problem:** 7 chunks were tiny, as small as 9 characters (e.g. `Model av.`).
- **Simple fix:** a short table header got stranded before a long table row. The chunker now never closes a chunk that has almost nothing new in it.
- **Technical fix:** a chunk is flushed only if its new content is at least `chunk_min_size` (200 characters); otherwise it may run slightly over `chunk_size`. Smallest chunk went from 9 to 76 characters (a page containing only a figure caption). Regression test: `test_short_fragment_before_long_run_is_not_left_alone`.

**17. Ligatures broke keyword matching**
- **Problem:** 56 chunks contained `ﬁne-tuning` and `speciﬁc`, where "fi" is a single special character, so searching "fine-tuning" wouldn't find them.
- **Simple fix:** convert special typographic characters into normal letters before chunking.
- **Technical fix:** `unicodedata.normalize("NFKC", text)` in `clean_page_text`. Ligature chunks went from 56 to 0, and "fine-tuning" now matches 83 chunks. Test: `test_clean_page_text_replaces_ligatures`.

**18. Known noise, logged for M3 (not fixed yet)**
- **Problem:** 68 chunks contain a repeated page header ("Published as a conference paper at ICLR 2024"); 16 chunks come from reference lists; table and figure text comes through as loose numbers.
- **Plan:** remove lines repeated on most pages, and possibly drop References sections, in M3, when the benchmark can measure whether it helps.

### Testing and verification

**19. A false alarm in the page-number check**
- **Problem:** one exit-test chunk "wasn't found" on its page.
- **Simple fix:** the two PDF tools read a math symbol differently (`documentsz` vs `documents z`), so we checked with several phrases instead of one.
- **Technical fix:** compared 6 eight-word probes from different parts of the chunk against `pdftotext` output for pages p−1, p, p+1. A chunk passes if its matches occur only on the claimed page. All 3 random chunks passed.

**20. Re-ingestion looked finished before it started**
- **Problem:** right after `make reingest`, the stats were unchanged.
- **Simple fix:** the check ran before the worker had picked up the jobs (the old status was still `ready`). We now wait for the worker to report the jobs done.
- **Technical fix:** counted `Task sources.ingest ... succeeded` lines in the worker logs until 16 new ones appeared. Lesson: with background jobs, check the job's completion, not the old state.

**21. A wrong assertion in my own test**
- **Problem:** `test_chunks_respect_size_and_overlap` failed although the code was right.
- **Simple fix:** the overlap carries the last *two* sentences when both fit, and the test assumed one. The test was rewritten to check what the overlap actually guarantees.
- **Technical fix:** the assertions now check that the next chunk begins with a suffix of the previous chunk that includes its final sentence.

### Finding the research papers

**22. Paper search APIs misbehaved**
- **Problem:** Semantic Scholar answered `Too Many Requests` (it rate-limits requests without a key). OpenAlex's broad search returned off-topic papers and some mismatched arXiv IDs. arXiv's API returned empty responses.
- **Simple fix:** searched arXiv directly for the topic, then looked up each exact paper elsewhere, instead of trusting a fuzzy search.
- **Technical fix:** arXiv now redirects `http://` to `https://`, and `curl` without `-L` saved the empty redirect, so we switched to `https://export.arxiv.org/api/query`. Then batch-looked-up citation counts in OpenAlex by exact DOI (`10.48550/arxiv.<id>`), and re-verified the final 16 IDs and titles through arXiv `id_list`.
- **Caveat found:** OpenAlex undercounts citations for arXiv preprints (it counts the arXiv copy only), so papers were chosen by their role in the debate, not by those numbers.

## Session 1, continued (2026-10-25): M2

### Embeddings and search

**23. Picking a model that wouldn't cut off our chunks**
- **Problem:** the most popular small model, `all-MiniLM-L6-v2`, only reads 256 word pieces; our chunks are about 300 tokens.
- **Simple fix:** chose a model that reads up to 512 tokens.
- **Technical fix:** `BAAI/bge-small-en-v1.5` (384 dimensions, 512-token limit). Input beyond the limit is silently truncated, so the limit must exceed the chunk size.

**24. Avoiding a 1–2 GB PyTorch install**
- **Problem:** `sentence-transformers` requires PyTorch, which is huge on Linux and slows Docker builds and CI.
- **Simple fix:** used a lighter library that runs the same model.
- **Technical fix:** FastEmbed runs the model's ONNX export through ONNX Runtime (~50 MB). The model itself (65 MB) downloads once into `backend/.cache/fastembed`, which is git-ignored.

**25. Tests must not download a model**
- **Problem:** CI would download 65 MB on every run, and real embeddings make tests slow and less predictable.
- **Simple fix:** tests use a fake embedder that's instant and always gives the same answer.
- **Technical fix:** `HashEmbedder` hashes each word into one of 384 dimensions and normalizes the vector, so texts that share words still score as similar. Selected with `EMBEDDING_PROVIDER=hash` in `tests/conftest.py`. The adapter (`Embedder` interface) makes the swap invisible to the rest of the code.

**26. Alembic forgot to import pgvector**
- **Problem:** the autogenerated migration used `pgvector.sqlalchemy.vector.VECTOR` without importing `pgvector`, so it would crash with `NameError`.
- **Simple fix:** reading the generated migration caught it before running; the missing import was added.
- **Technical fix:** added `import pgvector.sqlalchemy` to the migration, and to `alembic/script.py.mako` so future migrations include it automatically. Verified with upgrade → downgrade → upgrade and `alembic check`.

**27. Filtered vector search could return too few results (prevented)**
- **Problem:** the HNSW index searches across all projects; filtering to one project afterwards can leave fewer than k results.
- **Simple fix:** tell the index to keep searching until it has enough results from the right project.
- **Technical fix:** `SET LOCAL hnsw.iterative_scan = strict_order` before the query (pgvector 0.8). `SET LOCAL` applies only to the current transaction.

**28. The first search took 2.2 seconds**
- **Problem:** the API loaded the embedding model on the first search request.
- **Simple fix:** load the model when the API starts, before any user arrives.
- **Technical fix:** a FastAPI `lifespan` hook calls `get_embedder()` (cached with `lru_cache`) at startup, skipped in tests. First search after a restart: 2.2 s → 0.18 s.

**29. Embedding the corpus was slower than expected (logged, not fixed)**
- **Problem:** re-embedding 1,279 chunks took about 8 minutes, against an estimate of 2–3.
- **Likely cause:** 2 worker processes each run ONNX Runtime with threads for all 8 CPUs, so they compete for the same cores.
- **Plan:** if it matters (larger corpora, M7 arXiv ingestion), limit ONNX threads per process or run one worker process for embedding.

### Testing and verification

**30. Reading smoke-test misses instead of trusting the number**
- **Problem:** the M2 smoke test scored 7/10. The number alone doesn't say *why* 3 questions missed.
- **Simple fix:** looked at what search actually returned for each miss.
- **Findings:** one "miss" was a labelling mistake (other papers genuinely answer the question, but only one paper was listed); two were real retrieval failures (a loose paraphrase, and generic introduction text crowding out a specific method).
- **What changes:** M3's benchmark allows several relevant passages per question; hybrid search (M3) and reranking (M5) target the two real failure types. The labels were not edited to raise the score.
