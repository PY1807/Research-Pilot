.PHONY: up down logs migrate revision seed test lint format psql reset-db

up: ## Build and start all services, apply migrations, seed the dev user
	docker compose up -d --build --wait db api
	docker compose up -d web
	$(MAKE) migrate
	$(MAKE) seed
	@echo "API: http://localhost:8000/docs   Web: http://localhost:5173"

down: ## Stop all services (data is kept)
	docker compose down

logs: ## Follow logs from all services
	docker compose logs -f

migrate: ## Apply all pending database migrations
	docker compose exec api alembic upgrade head

revision: ## Autogenerate a migration from model changes: make revision m="add embeddings"
	docker compose exec api alembic revision --autogenerate -m "$(m)"

seed: ## Create the development user (safe to re-run)
	docker compose exec api python -m app.scripts.seed_dev_user

test: ## Run backend tests against the separate test database
	docker compose exec api pytest -q

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
