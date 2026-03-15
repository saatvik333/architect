
.PHONY: install install-hooks lint format typecheck test test-integration test-e2e infra-up infra-down migrate dev clean promptfoo-test promptfoo-view

install:
	uv sync --all-packages --group dev

install-hooks:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy libs/ services/ apps/

test:
	uv run pytest libs/ services/ apps/ -x -q

test-integration:
	uv run pytest tests/integration/ -m integration -x -q

test-e2e:
	uv run pytest tests/e2e/ -m e2e -x -q

test-all:
	uv run pytest -x -q

infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd libs/architect-db && uv run alembic upgrade head

dev: infra-up migrate
	@echo "Infrastructure is up. Run services individually or use 'make run-all'."

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

promptfoo-test:
	cd promptfoo && bun run test

promptfoo-view:
	cd promptfoo && bun run test:view
