# AGENTS.md

DemumuMind Panel — Enterprise AI Gateway: aggregates any OpenAI/Anthropic/Gemini-compatible provider behind one OpenAI-compatible API + SvelteKit admin panel.

## Commands

```bash
source .venv/bin/activate          # first — everything runs from venv
make dev                           # uvicorn app.main:app :8000 (reload)
make test                          # uv run pytest -v
make lint                          # ruff + mypy --strict + pnpm svelte-check
make migrate                       # alembic upgrade head
make backup                        # sqlite3 .dump -> data/backup_*.sql
cd web && pnpm build               # static build -> web/build (deploy artifact)
cd web && pnpm check               # svelte-check (0 errors expected)
```

**Required verification order before commit/PR** (CI enforces it): `ruff check app/ tests/` → `mypy --strict app/` → `pytest -v` → `cd web && pnpm check`. All four must be green. Backend and web are verified separately — a web-only change still needs `pnpm check`.

## Architecture / routing

- **`app/api/v1/routes.py`** — public OpenAI/Anthropic/Gemini endpoints (`/v1/chat/completions`, `/v1/models`, `/v1/usage*`). Client auth: `Authorization: Bearer dm-...` OR `X-Api-Key`.
- **`app/api/v1/admin_routes.py`** — admin CRUD (`/v1/admin/*`). Auth: `Authorization: Bearer $PANEL_API_KEY` (from `.env`, NOT a `dm-` key). `login` sets a cookie.
- **`app/services/dispatch.py`** — core request path: resolve → guardrails → cache → translate → pool.request → translate_response → record usage. Cost extraction (`usage.cost`/`pricing`/unknown) lives here.
- **`app/services/provider_manager.py`** — in-memory cache of providers/models/keys (SSOT is DB), `resolve(user_model_id)`.
- **`app/services/pool.py`** — httpx client; auth headers per protocol (openai=Bearer, anthropic=x-api-key, gemini=x-goog-api-key); `_url()` naive join (base_url + path).
- **`app/services/translate.py`** — protocol translation openai↔anthropic/gemini (request AND response). Same-protocol → passthrough. `anthropic↔gemini` direct not supported.
- **`app/services/discovery.py`** — `GET /models` parse + import + workability test; SSE streaming via `discover_and_test_stream`.
- **`app/services/finops.py`** — usage aggregation by agent/provider/timeseries.
- **`app/core/db.py`** — SQLite (WAL + busy_timeout 30000) OR Postgres (`postgresql+asyncpg`, pool 10). Switch via `DATABASE_URL`.
- **`app/main.py`** — lifespan: `init_db → provider_manager.load → seed → hot_reload`. `AUTO_MIGRATE=1` runs `alembic upgrade head` at startup.

## SSOT & data rules (from CONTRIBUTING)

- DB is the single source of truth for providers/models/keys/budgets — never hardcode provider names or model lists.
- `user_model_id` is **globally unique** (`app/models.py` `unique=True`) — it's the routing key for `{"model": "..."}`. Discover skips duplicates from a second provider (`skipped_global_alias`) instead of 500.
- Absolute imports only (`from app...`), no relative.
- Errors are values (`AppError` with code/status), never bare `except: pass`.
- Never log full `api_key`/`Authorization`/`key_hash` — first 8 chars max.
- `metadata` columns map to Python attr `meta` (SQLAlchemy reserves `metadata`); DB column name stays `metadata`.

## Migrations

- Alembic, `file_template = %%(rev)s_%%(slug)s`, run automatically on boot when `AUTO_MIGRATE=1`.
- New column → `alembic revision` + hand-edit, **SQLite needs `batch_alter_table`** for any constraint/FK change (`op.batch_alter_table`). Plain `op.add_constraint`/`drop_column` fails on SQLite.
- Tests never touch alembic: `tests/conftest.py` sets `AUTO_MIGRATE=0` + in-memory SQLite → `create_all` from models. So model changes are picked up by tests automatically; prod needs the migration.

## Tests

- `pytest` + `pytest-asyncio` (asyncio_mode=auto), in-memory SQLite, httpx ASGITransport. `tests/conftest.py` wipes tables between tests.
- Existing coverage: api, cleanup, discovery, failover, provider_manager, translate, usage (pricing/cost).
- Load testing: `harness/load/load_test.py` (asyncio+httpx, no external deps): `--base --key --model --concurrency --duration --mix`.

## Frontend (web/)

- SvelteKit 5 (runes `$state`/`$derived`), Svelte 5, Tailwind 4, `adapter-static` with `paths.base = '/demumumind'` (`svelte.config.js`). UI components in `web/src/lib/components/ui/`.
- Deploy = `pnpm build` → static `web/build` served by reverse proxy under `/demumumind` prefix. Frontend-only change: rebuild, no backend restart.
- `web/src/lib/api.ts` wraps all fetch; `PANEL_API_KEY` stored in `panelKey` store, sent as Bearer.
- Playground (`web/src/routes/playground/+page.svelte`) hits `/v1/chat/completions` with streaming; free models show `— FREE` suffix.

## Operations (this box)

- Backend runs as sprite-env service `demumumind` (uvicorn `app.main:app` on `127.0.0.1:8000`). Restart: `/.sprite/bin/sprite-env services restart demumumind` (~6s boot, runs migration).
- Public: `https://test-sprite-busun.sprites.app/demumumind/` → rproxy :8080 → :8000 (strips `/demumumind`).
- Logs: `/.sprite/logs/services/demumumind.log`. Redis on `127.0.0.1:6379` (cache + hot_reload; falls back to 5s polling if down).
- Shared harness client key: `.secrets/dm-harness-key.env` (gitignored). Harness configs are examples only — user's live `~/.config/opencode` / `~/.omp` are NOT auto-edited.

## Docs

- `docs/harness-integration.md` — using the panel as provider from opencode/omp/Claude/Codex.
- `docs/provider-setup.md` — adding any upstream provider (`base_url + api_key + models`), `/v1` suffix pitfalls, alias collisions, troubleshooting.
- `harness/examples/` — opencode + omp example configs.
