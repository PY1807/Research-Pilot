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
