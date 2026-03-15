
.PHONY: install install-hooks lint format typecheck test test-integration test-e2e infra-up infra-down migrate dev clean promptfoo-test promptfoo-view run-services run-gateway run-dashboard run-all stop-all

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

# ── Run services ─────────────────────────────────────────────────────

PID_DIR := .pids

run-services: $(PID_DIR)
	@echo "Starting Phase 1 services..."
	uv run uvicorn world_state_ledger.service:app --host 0.0.0.0 --port 8001 & echo $$! > $(PID_DIR)/world-state.pid
	uv run uvicorn task_graph_engine.service:app --host 0.0.0.0 --port 8003 & echo $$! > $(PID_DIR)/task-graph.pid
	uv run uvicorn execution_sandbox.service:app --host 0.0.0.0 --port 8007 & echo $$! > $(PID_DIR)/sandbox.pid
	uv run uvicorn evaluation_engine.service:app --host 0.0.0.0 --port 8008 & echo $$! > $(PID_DIR)/eval-engine.pid
	uv run uvicorn coding_agent.service:app --host 0.0.0.0 --port 8009 & echo $$! > $(PID_DIR)/coding-agent.pid
	@echo "Starting Phase 2 services..."
	uv run uvicorn spec_engine.service:app --host 0.0.0.0 --port 8010 & echo $$! > $(PID_DIR)/spec-engine.pid
	uv run uvicorn multi_model_router.service:app --host 0.0.0.0 --port 8011 & echo $$! > $(PID_DIR)/router.pid
	uv run uvicorn codebase_comprehension.service:app --host 0.0.0.0 --port 8012 & echo $$! > $(PID_DIR)/codebase.pid
	uv run uvicorn agent_comm_bus.service:app --host 0.0.0.0 --port 8013 & echo $$! > $(PID_DIR)/comm-bus.pid
	@echo "All services started. PIDs in $(PID_DIR)/"

run-gateway: $(PID_DIR)
	uv run uvicorn api_gateway:app --host 0.0.0.0 --port 8000 & echo $$! > $(PID_DIR)/gateway.pid
	@echo "API Gateway started on http://localhost:8000"

run-dashboard: $(PID_DIR)
	cd apps/dashboard && bun run dev & echo $$! > $(PID_DIR)/dashboard.pid
	@echo "Dashboard started on http://localhost:3000"

run-all: infra-up migrate run-services run-gateway run-dashboard
	@echo ""
	@echo "=== ARCHITECT system is running ==="
	@echo "  Dashboard:   http://localhost:3000"
	@echo "  API Gateway: http://localhost:8000"
	@echo "  Temporal UI: http://localhost:8080"
	@echo "  NATS Monitor: http://localhost:8222"
	@echo ""
	@echo "Run 'make stop-all' to shut everything down."

stop-all:
	@echo "Stopping services..."
	@-lsof -ti :8001,:8003,:8007,:8008,:8009,:8010,:8011,:8012,:8013,:8000 2>/dev/null | xargs kill 2>/dev/null || true
	@-lsof -ti :3000 2>/dev/null | xargs kill 2>/dev/null || true
	@rm -f $(PID_DIR)/*.pid 2>/dev/null || true
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker-compose.yml down
	@echo "All stopped."

$(PID_DIR):
	mkdir -p $(PID_DIR)
