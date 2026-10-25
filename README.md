# ResearchPilot — Build Plan

> An evidence-first, agentic AI research workspace.
> **Ask → Retrieve → Investigate → Verify → Deliver**

This file is the working plan for building ResearchPilot. It is based on *ResearchPilot Project Blueprint v2.0* and turns that blueprint into concrete milestones, decisions, and exit tests. Each item is a commitment, not a claim.

---

## 0. Progress tracker (update at the end of every session)

| | |
|---|---|
| **Current milestone** | M0 — Setup (not started) |
| **Next action** | Scaffold repo, `git init`, docker compose |
| **Blocked on (user)** | GitHub repo name + visibility (needed in M0) · Research domain + PDF corpus (needed by M1) · LLM decision (needed by M4) |
| **Last session** | 2026-10-25: planning only, no code yet |

### Milestone status

| ID | Milestone | Status | Est. sessions |
|---|---|---|---|
| M0 | Setup | ⬜ not started | 1 |
| M1 | PDF ingestion | ⬜ | 1 |
| M2 | Semantic search + minimal UI | ⬜ | 1 |
| M3 | Hybrid search + eval harness | ⬜ | 1 |
| M4 | Cited answers + experiments A–C | ⬜ | 1 |
| M5 | Reranking (cuttable) | ⬜ | 0.5 |
| M6 | Agent core | ⬜ | 2 |
| M7 | arXiv connector + verified report | ⬜ | 1 |
| M8 | Auth + security hardening | ⬜ | 1 |
| M9 | UI polish | ⬜ | 1 |
| M10 | Deploy + docs | ⬜ | 1 |
| | **Total** | | **≈ 11–12 working sessions** |

Status keys: ⬜ not started · 🟨 in progress · ✅ done (exit test passed) · ✂️ cut

### Session log

| Date | Milestone | Done | Next |
|---|---|---|---|
| 2026-10-25 | Planning | Read blueprint, wrote plan, chose FastAPI, auth approach, milestone schedule | Start M0 |

### Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-10-25 | FastAPI instead of Django | Async-native for LLM-heavy I/O; Pydantic shared by API, tools, and LLM outputs; resume variety |
| 2026-10-25 | Auth: `user_id` on every table from M0, login UI in M8, guest demo account | Protects LLM budget, keeps PDFs private, no schema rewrite later |
| 2026-10-25 | Milestone-based schedule, not calendar days | User's availability varies day to day |
| 2026-10-25 | All work pushed to the user's GitHub repo (account `PY1807`, SSH); deployed in M10 | Public portfolio piece; history shows how it was built |
| — | LLM provider | **Pending.** Proposal: local Ollama for dev, Claude API for eval/demo. Needed by M4. |

---

## 1. What we're building

A full-stack app that takes a focused research question and returns a **traceable, cited report**. It works over:

- PDFs the user uploads, and
- **one** approved external research source (an API connector, not a web crawler).

A **bounded agent** plans sub-questions, retrieves evidence, spots gaps, runs follow-up searches, checks that citations support their claims, and writes a report with findings, conflicts, limitations, and open questions.

**Core promise:** make research systematic and verifiable, not magically infallible.

**Guiding rule:** build the baseline, measure it, *then* add bounded agentic behavior.

### How it works, in plain words

**One line:** You ask a question, and ResearchPilot reads your papers, finds the evidence, checks it, and writes a report where every claim links to the exact page it came from.

**30-second version.** Think of a careful research assistant who always shows their notes:

1. **You ask** a focused question, like "When does reranking improve search quality?"
2. **It reads** the PDFs you uploaded and searches arXiv for related papers.
3. **It finds** the passages that actually talk about your question, the way a librarian pulls the right pages.
4. **It notices gaps.** If part of the question has no evidence yet, it searches again, with a limit on how many tries and how much it can spend.
5. **It fact-checks** every claim against the passage it cites.
6. **It reports** what the evidence supports, where sources disagree, and what's still unknown, with a link on every claim.

**Why it's different from asking a chatbot:** you can click any claim and see the source page. It tells you when evidence is weak instead of guessing. And it's tested against a fixed set of questions, so we can show measured results instead of just saying it works well.

| Plain idea | What's under the hood |
|---|---|
| The librarian | Search: embeddings + keyword search in PostgreSQL/pgvector |
| The research assistant | The agent: an LLM that plans and calls tools, within hard limits |
| The fact-checker | Citation check: each claim compared against its cited passage |
| The notebook | Run trace: every step saved so you can see how the answer was built |
| The exam | The benchmark: fixed questions with known answers, run after every change |

---

## 2. Stack decisions

| Area | Choice | Why |
|---|---|---|
| Repo layout | Monorepo: `backend/` (FastAPI), `frontend/` (React), `eval/`, `docs/` | One place for code, benchmark, and engineering log |
| Backend | FastAPI + Pydantic v2 | Async-native for I/O-heavy LLM/API calls and streaming progress (SSE); Pydantic models shared by API schemas, agent tool contracts, and structured LLM outputs; auto OpenAPI spec → generated TypeScript client |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic | `pgvector` has first-class SQLAlchemy support |
| Auth | `fastapi-users` (email/password, JWT) + guest demo account; optional GitHub sign-in | Protects LLM budget, isolates uploaded PDFs, enables saved projects |
| Frontend | React + TypeScript + Vite, TanStack Query, Tailwind | Fast dev loop, typed API calls |
| Database | PostgreSQL 16 + `pgvector` | Relational data and vectors in one DB |
| Keyword search | Postgres full-text search (`tsvector` + GIN) | Hybrid search with no extra service |
| Hybrid fusion | Reciprocal Rank Fusion (RRF) | Simple, no score calibration needed |
| LLM | `LLMProvider` adapter. **Provider pending** (see decision log). A fake provider is used for tests | Provider logic isolated; secrets server-side |
| Embeddings | Local `sentence-transformers` model behind an `Embedder` adapter | Free; swappable if quality falls short |
| Reranker | Local cross-encoder behind an adapter | Only added after baseline is measured |
| PDF parsing | `pypdf` (keeps page boundaries). OCR out of scope | Detect and report extraction failures clearly |
| Background jobs | Celery + Redis | Long research runs must not block an HTTP request |
| External connector | **arXiv API** (fallback: OpenAlex) | Open metadata and open-access PDFs |
| Local dev | `docker compose` (postgres+pgvector, redis, api, worker, web) | One-command setup |
| Tests | `pytest` + `pytest-asyncio` + `httpx` test client; Vitest for frontend | |
| Deployment | Hosted frontend + API + worker + managed Postgres with pgvector (single region) | Host chosen in M10 after a pricing check |

---

## 3. Architecture

A modular monolith with clear internal modules and no microservices.

```
React + TS  ──►  FastAPI service  ──►  Research Orchestrator (Celery worker)
 (dashboard,      (auth, validation,     (plan, tool calls, state,
  evidence,        ownership checks,      iteration + budget limits)
  report)          endpoints)                     │
                                                  ▼
                                   RAG + Source Connectors
                                   (parse, chunk, embed, search, arXiv)
                                                  │
                                                  ▼
                                   PostgreSQL + pgvector
```

### Backend layout (FastAPI)

Thin routers handle HTTP; service modules hold the logic and know nothing about HTTP.

| Module | Kind | Responsibility |
|---|---|---|
| `auth` | router | Sign-up/sign-in (`fastapi-users`, JWT), guest demo account |
| `projects` | router | `research_projects` CRUD, ownership checks |
| `sources` | router + service | Upload/registration, ingestion pipeline, `source_documents`, `document_chunks` |
| `runs` | router | Start/cancel runs, status, evidence, SSE progress stream |
| `reports` | router + service | `evidence_items`, `reports`, Markdown export |
| `retrieval` | service | Semantic, keyword, hybrid, rerank: pure functions over the DB |
| `connectors` | service | `SourceConnector` interface + `ArxivConnector` |
| `llm` | service | Provider adapter, prompts, structured-output validation, token/cost accounting |
| `agent` | service | Orchestrator loop, tool registry, budgets, `research_runs`, `run_events` |
| `db` | infra | SQLAlchemy models, async session, Alembic migrations |

### Auth approach

- **M0–M7:** no login UI, but every table carries `user_id` from day one, with a single hard-coded dev user.
- **M8:** email/password with JWT via `fastapi-users`; optional GitHub sign-in.
- **"Try the demo" guest account** on the seeded corpus with a small quota, so reviewers can use the app without signing up.

### Data model

`users`, `research_projects`, `source_documents`, `document_chunks` (with `embedding vector(n)` + `tsvector`), `research_runs`, `evidence_items`, `reports`, `run_events`.

Every chunk keeps: source ID, title, page/section, chunk index, **source type (uploaded / external)**, and ingestion status.

### API surface

```
POST /api/projects/                 create project
POST /api/projects/{id}/sources/    upload PDF / register external source
GET  /api/sources/{id}/status/      ingestion status
POST /api/projects/{id}/runs/       start research run
GET  /api/runs/{id}/                status, plan, progress
GET  /api/runs/{id}/evidence/       retrieved evidence
GET  /api/runs/{id}/report/         final report
POST /api/runs/{id}/cancel/         cancel run
```

### Agent tools

| Tool | In | Out |
|---|---|---|
| `search_sources` | sub-question, scope, filters | source IDs + metadata |
| `retrieve_evidence` | query, allowed sources, top-k | ranked chunks with page/URL + scores |
| `open_source` | source ID, page/section | text + location |
| `compare_evidence` | claim/question, evidence set | agreements, conflicts, unresolved |
| `check_citation_support` | claim, cited passage | supported / partial / unsupported + rationale |
| `generate_report` | verified findings + citations | structured report sections |

**Agent guardrails:** max iterations, max tool calls, wall-clock limit, token/cost budget. All tool inputs and outputs validated server-side. Document text is **untrusted data**, never instructions. Every state transition logged as a sanitized `run_event`. Runs are cancellable; retries are idempotent. Weak evidence is reported as weak.

---

## 4. Milestones

**Schedule is flexible.** Work happens in sessions, not on fixed dates. Some days cover two milestones, some days have no work. Target is roughly 11–12 working sessions (about 2 weeks of active work).

**Each milestone is sized to fit one working session.** It has a clear exit test, ends with a git commit, and leaves the app runnable. M6 is the only two-session milestone and is split into 6a and 6b.

**Legend:** 🧑 = needs the user's input before or during the milestone.

### M0 — Setup
- [ ] `git init`, monorepo folders, `.gitignore`, `.env.example`
- [ ] `docker compose`: postgres + pgvector, api, web (redis + worker join in M1)
- [ ] FastAPI skeleton with `/health`; SQLAlchemy async session; Alembic baseline
- [ ] All tables from the data model; `user_id` on top-level tables (children inherit via FK); seeded dev user
- [ ] React + Vite skeleton that calls `/health`
- [ ] `Makefile` (`make up`, `make test`, `make migrate`), CI with lint + tests
- [ ] `docs/engineering-log.md` started
- **Exit test:** `make up` starts everything; `make test` passes; the frontend shows API health.

### M1 — PDF ingestion 🧑
- 🧑 User picks the research domain and 10–15 PDFs (default: RAG/retrieval papers)
- [ ] Add Redis + Celery worker to docker compose (Redis on a non-default host port; a local Redis already uses 6379)
- [ ] Upload endpoint with size/type limits; file stored privately with a checksum
- [ ] `pypdf` extraction per page; clear failure status for scanned or empty PDFs
- [ ] Paragraph-aware chunking with configurable size and overlap; page number kept on each chunk
- [ ] Ingestion runs as a Celery task; status endpoint
- **Exit test:** uploading the corpus produces chunks with correct page numbers, checked on 3 random chunks.

### M2 — Semantic search + minimal UI
- [ ] Local embedding model behind `Embedder`; embeddings stored in pgvector with an HNSW index
- [ ] `retrieve(query, k)` service + endpoint
- [ ] UI: create project, upload PDFs, see ingestion status, run a search, click a result to open the PDF page
- [ ] 🧑 User writes or approves 10 test questions
- **Exit test:** for most of the 10 questions, a relevant passage appears in the top 5 and its link opens the right page.

### M3 — Hybrid search + evaluation harness 🧑
- [ ] Full-text `tsvector` column + GIN index; keyword search; RRF fusion
- [ ] `eval/` harness: versioned question set, versioned retrieval configs, Recall@k and Precision@k, latency
- [ ] Claude drafts 30–40 benchmark questions (direct facts, multi-source, conflicting, unanswerable)
- [ ] 🧑 **User reviews and labels the expected evidence (heaviest user task, ~2–3 h)**
- 🧑 **LLM decision needed before M4**
- **Exit test:** `make eval` prints a comparison table for semantic vs hybrid search.

### M4 — Cited answers + experiments A–C
- [ ] `LLMProvider` adapter with the chosen provider + fake provider for tests; token/cost accounting
- [ ] `answer(question)`: retrieve → generate an answer that cites chunk IDs → render citations as page links
- [ ] Prompt treats retrieved text as untrusted data
- [ ] Experiments A (baseline), B (chunk sizes), C (hybrid) recorded in `eval/results/`
- [ ] Citation-support and answer-correctness metrics added
- **Exit test:** cited answers for the 10 test questions; user spot-checks that 5 citations actually support their claims.

### M5 — Reranking ✂️ cuttable
- [ ] Local cross-encoder reranker behind an adapter
- [ ] Experiment D; results table updated
- **Exit test:** experiment D results recorded, whether it helped or not.

### M6a — Agent core
- [ ] Pydantic tool schemas + tool registry: `search_sources`, `retrieve_evidence`, `open_source`, `compare_evidence`
- [ ] Orchestrator loop: plan → tool call → assess → decide; state persisted in `research_runs`
- [ ] Budgets: max iterations, max tool calls, wall-clock limit, token/cost limit
- [ ] Every step written to `run_events`
- **Exit test:** a run on a test question finishes within budget, and a run with a tiny budget stops cleanly with a "budget reached" status.

### M6b — Runs as background jobs
- [ ] Runs execute on Celery; cancel endpoint; idempotent retries
- [ ] SSE progress stream; UI progress view showing the plan and each step
- [ ] Prompt-injection test documents added to the corpus
- **Exit test:** start a run from the UI, watch progress live, cancel a second run mid-way, and confirm the injection documents don't change the agent's behavior.

### M7 — arXiv connector + verified report
- [ ] `ArxivConnector`: search, metadata, open-access PDF ingest; rate limiting and attribution
- [ ] `check_citation_support` + `generate_report`: findings, comparison table, conflicts, limitations, open questions
- [ ] Uploaded vs external source badges in the report
- [ ] Experiment E: agentic follow-up vs best non-agentic config
- **Exit test:** one end-to-end run uses both uploaded PDFs and arXiv papers and produces a report where every claim has a checked citation.

### M8 — Auth + security hardening
- [ ] `fastapi-users` sign-up/sign-in (JWT); optional GitHub sign-in
- [ ] Guest demo account with a small quota on the seeded corpus
- [ ] Ownership checks on every endpoint, with tests that user A can't read user B's data
- [ ] Rate limits, per-user quotas, deletion cascade tests (project → files → chunks → embeddings → reports)
- **Exit test:** the ownership and deletion test suites pass.

### M9 — UI polish
- [ ] Saved projects and run history
- [ ] Evidence inspector and research trace view
- [ ] Markdown export; cost and latency view
- [ ] Clear error states everywhere
- **Exit test:** 🧑 user completes a full run without help and gives UX feedback.

### M10 — Deploy + docs 🧑
- 🧑 User creates a hosting account
- [ ] Deploy frontend, API, worker, and managed Postgres + pgvector; secrets in the host's secret manager
- [ ] Health checks, structured logs, request/run IDs, error reporting
- [ ] Seeded demo corpus
- [ ] Final README: setup, architecture, measured eval results, known limitations
- **Exit test:** a new person opens the public URL, uses "Try the demo", and finishes a run.

### If time slips
Cut in this order: M5 (reranking), then Markdown export and cost view from M9, then GitHub sign-in.
**Never cut:** citations, evaluation, budget limits, a reliable end-to-end flow.

---

## 5. Scope

| Priority | Features |
|---|---|
| **P0** | Question, PDF upload, ingestion, RAG, citations, agent follow-up, saved project, final report |
| **P1** | arXiv connector, hybrid/rerank experiment, research trace, Markdown export, cost/latency view |
| **P2 (later)** | More connectors, collaboration, crawling, multi-agent |

**Non-goals:** unrestricted web crawling, multi-agent frameworks, "exhaustive" or "guaranteed true" claims, payments, mobile, teams, arbitrary code execution, Kubernetes.

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated conclusions | Ground claims in passages; `check_citation_support`; flag uncertainty |
| Missed evidence | Measure Recall@k; hybrid + rerank; inspect failures |
| Conflicting sources | Keep source-level findings; explain disagreement |
| Prompt injection in docs | Untrusted-data framing; tools can't be granted by document text |
| Privacy | Server-side ownership checks; private file storage; tested deletion |
| Runaway loops / cost | Hard budgets; cancellation; per-user quotas |
| Provider/API failures | Output validation; bounded retries; sanitized error logs |
| External API terms | Respect arXiv rate limits, attribution, licensing |

---

## 7. Launch checklist

- [ ] Create project and submit a question
- [ ] PDFs ingested with page metadata; extraction failures are clear
- [ ] Postgres stores records + pgvector embeddings
- [ ] Every source records provenance (uploaded / external)
- [ ] Baseline RAG produces cited answers
- [ ] Agent tools defined, validated, bounded by time/cost/iterations
- [ ] arXiv connector works within API rules
- [ ] Report has findings, citations, conflicts, limitations, open questions
- [ ] Evidence and research trace are inspectable
- [ ] Benchmark compares baseline with at least one alternative
- [ ] Auth, ownership, upload limits, secrets, deletion tested
- [ ] Deployed demo with sample content; docs cover setup, eval, limitations

---

## 8. Working agreement

### How we work
- One milestone per session where possible. Each ends with passing tests, a commit, and a runnable app.
- The user reviews every milestone's diff and should be able to explain it.
- Measured results are recorded honestly, including regressions. No invented numbers.
- Gaps between sessions are fine. The tracker in section 0 is the source of truth for where we are.
- **Keep it explainable.** The architecture can be as complex as it needs to be, but anyone should be able to understand the product. Every new major component gets a plain-language row in the "How it works, in plain words" table in section 1. If a part can't be explained in one sentence, simplify the part or the explanation.

### Git and GitHub
- All work lives in the user's GitHub repo (account `PY1807`, pushed over SSH). The repo is created in M0.
- **Single branch only: `main`.** No feature branches, no PRs. Commits are pushed incrementally as work progresses.
- It's fine if `main` is briefly broken; fix forward with the next commit.
- Small, focused commits with clear messages, so the history reads as a build log.
- **Never committed:** `.env` files, API keys, uploaded PDFs, model caches. Only `.env.example` with placeholder values.
- Deployment happens from `main` in M10.

### Learning agreement

This project is also how the user learns a new stack. The user knows full-stack basics. These are **new**, and each gets explained when it first appears:

| New tech | First appears | What the user will learn |
|---|---|---|
| Docker / docker compose | M0 | Containers, images, volumes, running several services together |
| Alembic | M0 | Database migrations: versioning schema changes like git versions code |
| Redis + Celery | M1 | Task queues: running slow work in the background so the API stays fast |
| Embeddings | M2 | How text becomes a list of numbers where similar meaning = nearby numbers |
| pgvector | M2 | Storing those vectors in Postgres and finding nearest neighbours fast (HNSW index) |
| RAG | M2–M4 | Retrieve relevant passages first, then have the LLM answer only from them |

Likely new too, explained the same way unless the user says they already know it: full-text search + RRF (M3), retrieval metrics like Recall@k (M3), cross-encoder reranking (M5), agent loops and tool calling (M6a), Server-Sent Events (M6b).

**During development, for each new tech, Claude will:**
1. **Before coding:** give a short concept brief in chat covering the problem it solves, how it works underneath (e.g. what an embedding model actually computes), and a simple mental model.
2. **While coding:** explain the *why* behind non-obvious choices (chunk size, index type, retry settings) as they come up. Standard full-stack parts are not over-explained.
3. **After it works:** suggest one small hands-on check the user can run, e.g. a `psql` query that shows the nearest chunks to a question.
4. **Record it in `DECISIONS.md`**, written during development, not up front, because the real reasons come from building.

**`DECISIONS.md` entry format** (simple language, one entry per technology):

```markdown
## <Technology> (added in M<n>)
**What it does in ResearchPilot:** one or two sentences.
**Why it helps / what it adds:** a few bullets.
**Trade-offs and alternatives:** why this over the main alternatives in its space (e.g. pgvector vs Pinecone vs Qdrant), and what we give up.
**How it works underneath:** a short plain explanation.
**Where to look:** files in the repo that use it.
```

### How Claude resumes a session (Claude doesn't remember past chats)
1. Read **section 0** of this README, then the latest entries in `docs/engineering-log.md`.
2. Run `make up` and `make test` to confirm the app is in the state the tracker claims.
3. Continue from **Next action**. If it's blocked on the user, ask for that first.
4. Keep the working set small: touch only the current milestone's modules, and read files when needed instead of loading the whole repo.
5. At the end of the session: tick checkboxes, update the milestone status, **Next action**, **Blocked on**, and the session log, add or extend `DECISIONS.md` entries for any new tech introduced, then commit.
