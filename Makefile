.PHONY: up down logs worker-logs migrate revision seed test lint format psql reset-db ingest-corpus reingest eval review-sheet apply-review

API := http://localhost:8000/api

up: ## Build and start all services, apply migrations, seed the dev user
	docker compose up -d --build --wait db redis api worker
	docker compose up -d web
	$(MAKE) migrate
	$(MAKE) seed
	@echo "API: http://localhost:8000/docs   Web: http://localhost:5173"

down: ## Stop all services (data is kept)
	docker compose down

logs: ## Follow logs from all services
	docker compose logs -f

worker-logs: ## Follow the Celery worker's logs (see ingestion jobs run)
	docker compose logs -f worker

migrate: ## Apply all pending database migrations
	docker compose exec api alembic upgrade head

revision: ## Autogenerate a migration from model changes: make revision m="add embeddings"
	docker compose exec api alembic revision --autogenerate -m "$(m)"

seed: ## Create the development user (safe to re-run)
	docker compose exec api python -m app.scripts.seed_dev_user

test: ## Run backend tests (separate test database) and frontend tests
	docker compose exec api pytest -q
	docker compose exec web npm test

lint: ## Lint backend and frontend
	docker compose exec api ruff check .
	docker compose exec api ruff format --check .
	docker compose exec web npm run lint

format: ## Auto-format backend code
	docker compose exec api ruff format .
	docker compose exec api ruff check --fix .

psql: ## Open a SQL shell on the development database
	docker compose exec db psql -U researchpilot -d researchpilot

reset-db: ## Delete all local data and start fresh
	docker compose down -v

ingest-corpus: ## Create a project and upload every PDF in data/corpus/
	@project=$$(curl -sf -X POST $(API)/projects/ -H 'Content-Type: application/json' \
		-d '{"title": "RAG vs long-context LLMs", "question": "When is retrieval-augmented generation better than long-context prompting, and what are the trade-offs?"}' \
		| python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])') && \
	echo "Project: $$project" && \
	for f in data/corpus/*.pdf; do \
		curl -s -o /dev/null -w "%{http_code}  $$f\n" -F "file=@$$f;type=application/pdf" $(API)/projects/$$project/sources/; \
	done

reingest: ## Re-chunk every uploaded source (after changing chunking code or settings)
	docker compose exec api python -m app.scripts.reingest

eval: ## Score semantic, keyword and hybrid search on the benchmark (results in eval/results/)
	docker compose exec api python -m app.evaluation.runner --benchmark /eval/$(or $(b),benchmark_v1.json)

review-sheet: ## Build the labelling sheet (eval/review/) from pooled search results
	docker compose exec api python -m app.evaluation.review_sheet --benchmark /eval/$(or $(b),benchmark_v1.json)

apply-review: ## Write ticks from the reviewed sheet back into the benchmark labels
	docker compose exec api python -m app.evaluation.apply_review --benchmark /eval/$(or $(b),benchmark_v1.json)
