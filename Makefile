PROJECT_ROOT ?= $(shell pwd)
VENV_PATH ?= $(PROJECT_ROOT)/.venv
DATA_DIR ?= $(PROJECT_ROOT)/data
WEB_ROOT ?= $(PROJECT_ROOT)/web
ENV_FILE ?= $(PROJECT_ROOT)/.env
DB_PATH ?= $(PROJECT_ROOT)/demumumind.db

export PATH := $(VENV_PATH)/bin:$(PATH)

.PHONY: init sync dev test lint migrate backup clean

init:
	@echo "=== DemumuMind Panel — init ==="
	cp -n .env.example $(ENV_FILE) || true
	@KEY=$$(openssl rand -hex 32); \
	  sed -i "s/YOUR_PANEL_API_KEY_HERE/$$KEY/" $(ENV_FILE)
	chmod 600 $(ENV_FILE)
	$(MAKE) sync
	$(MAKE) migrate
	@echo "==> PANEL_API_KEY=$$KEY"
	@echo "==> Done. Run: make dev"

sync:
	uv sync
	cd $(WEB_ROOT) && pnpm install 2>/dev/null || echo "web skipped (pnpm not ready)"

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

lint:
	uv run ruff check app/
	uv run mypy --strict app/
	- cd $(WEB_ROOT) && pnpm svelte-check 2>/dev/null || true

migrate:
	uv run alembic upgrade head

backup:
	@mkdir -p $(DATA_DIR)
	sqlite3 $(DB_PATH) .dump > $(DATA_DIR)/backup_$$(date +%Y%m%d_%H%M%S).sql
	chmod 600 $(DATA_DIR)/backup_*.sql
	@echo "backup saved to $(DATA_DIR)/"

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -f *.db *.db-wal *.db-shm