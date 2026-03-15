#!/usr/bin/env bash
# ARCHITECT — one-command development environment setup
#
# Usage:
#   ./scripts/dev-setup.sh
#
# This script:
#   1. Installs uv (if not present)
#   2. Syncs all workspace dependencies
#   3. Starts infrastructure services (Postgres, Redis) via Docker Compose
#   4. Runs database migrations
#   5. Verifies the setup with a health check

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

cd "$PROJECT_ROOT"

# ── Step 1: Install uv if not present ──────────────────────────────────────────
info "Checking for uv..."
if command -v uv &>/dev/null; then
    ok "uv is installed: $(uv --version)"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv installed: $(uv --version)"
fi

# ── Step 2: Sync workspace dependencies ────────────────────────────────────────
info "Syncing workspace dependencies..."
uv sync --all-packages --group dev
ok "Dependencies synced."

# ── Step 3: Copy .env if not present ───────────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        ok "Created .env from .env.example"
    else
        warn "No .env.example found; skipping .env creation."
    fi
else
    ok ".env already exists."
fi

# ── Step 4: Start infrastructure ───────────────────────────────────────────────
info "Starting infrastructure services (Docker Compose)..."
if command -v docker &>/dev/null; then
    if [ -f infra/docker-compose.yml ]; then
        docker compose -f infra/docker-compose.yml up -d
        ok "Infrastructure services started."
    else
        warn "infra/docker-compose.yml not found; skipping Docker Compose."
    fi
else
    warn "Docker not found. Please install Docker to run infrastructure services."
fi

# ── Step 5: Wait for Postgres to be ready ──────────────────────────────────────
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q postgres; then
    info "Waiting for Postgres to be ready..."
    for i in $(seq 1 30); do
        if docker exec "$(docker ps --filter 'name=postgres' --format '{{.ID}}' | head -1)" pg_isready -U architect &>/dev/null; then
            ok "Postgres is ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            warn "Postgres did not become ready in 30 seconds."
        fi
        sleep 1
    done
fi

# ── Step 6: Run database migrations ───────────────────────────────────────────
if [ -d libs/architect-db/migrations ]; then
    info "Running database migrations..."
    uv run alembic -c libs/architect-db/alembic.ini upgrade head 2>/dev/null || warn "Migration failed or alembic not configured yet."
else
    warn "No migrations directory found; skipping."
fi

# ── Step 7: Install pre-commit and pre-push hooks ────────────────────────────
info "Setting up Git hooks..."
if uv run pre-commit install 2>/dev/null; then
    ok "Pre-commit hooks installed."
else
    warn "Pre-commit setup skipped (pre-commit may not be installed)."
fi
if uv run pre-commit install --hook-type pre-push 2>/dev/null; then
    ok "Pre-push hooks installed."
else
    warn "Pre-push hook setup skipped."
fi

# ── Step 8: Verify setup ──────────────────────────────────────────────────────
info "Running basic verification..."
uv run python -c "import architect_common; print('architect-common OK')" 2>/dev/null && ok "architect-common importable." || warn "architect-common import failed."

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ARCHITECT dev environment is ready!   ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Useful commands:"
echo "  uv run pytest libs/ services/ apps/ -x -q    # Run unit tests"
echo "  uv run ruff check .                           # Lint"
echo "  uv run mypy libs/ services/ apps/             # Type check"
echo "  architect health                               # Check service health"
echo ""
