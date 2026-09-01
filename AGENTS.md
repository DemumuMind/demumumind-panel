# AGENTS.md

DemumuMind Panel — Enterprise AI Gateway: aggregates any OpenAI/Anthropic/Gemini/Cohere/Ollama-compatible provider (plus Azure, Mistral, xAI, Groq, Together, DeepSeek) behind one OpenAI-compatible API + SvelteKit admin panel.

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

- **`app/api/v1/routes.py`** — public endpoints: `/v1/chat/completions`, `/v1/images/generations`, `/v1/messages` (anthropic), `/v1/v1beta/models/{model}:generateContent` (gemini), `/v1/models`, `/v1/usage*`. Client auth: `Authorization: Bearer dm-...` OR `X-Api-Key`.
- **`app/api/v1/admin_routes.py`** — admin CRUD (`/v1/admin/*`). Auth: `Authorization: Bearer $PANEL_API_KEY` (from `.env`, NOT a `dm-` key). `login` sets a cookie. Also serves `/v1/admin/images/generations` (history) + file endpoint.
- **`app/services/dispatch.py`** — core request path: resolve → guardrails → cache → translate → pool.request → translate_response → record usage. Cost extraction (`usage.cost`/`pricing`/unknown) lives here. `image_generation()` routes to provider `images/generations` (120s timeout). `_provider_path` handles cohere=`v2/chat`, ollama=`api/chat`.
- **`app/services/provider_manager.py`** — in-memory cache of providers/models/keys (SSOT is DB). `resolve(user_model_id)` — first-match, supports `provider/name` prefix for colliding aliases. `_models_by_provider` dict for explicit routing.
- **`app/services/pool.py`** — httpx client; auth headers per protocol: openai=Bearer, azure=api-key, anthropic=x-api-key, gemini=x-goog-api-key, cohere/ollama=Bearer. `_url()` naive join (base_url + path). Optional `request_timeout` param.
- **`app/services/translate.py`** — protocol translation between openai/anthropic/gemini/cohere/ollama/azure (all 25 pairs via `_TO_OPENAI`/`_FROM_OPENAI` canonical OpenAI shape). Same-protocol → passthrough. `azure`/`mistral`/`xai`/`groq`/`together`/`deepseek` normalize to `openai`.
- **`app/services/discovery.py`** — `GET /models` parse + import + workability test; SSE streaming via `discover_and_test_stream`. Image models (`gpt-image`, `dall-e`, `flux`…) get `kind=image` → skip chat ping, `ok/listed`.
- **`app/services/finops.py`** — usage aggregation by agent/provider/timeseries with `free_requests`, `unlimited_requests`, `unknown_requests`, `cached_requests`.
- **`app/core/db.py`** — SQLite (WAL + busy_timeout 30000, retry on `database is locked`) OR Postgres (`postgresql+asyncpg`, pool 10). Switch via `DATABASE_URL`.
- **`app/main.py`** — lifespan: `init_db → provider_manager.load → seed → hot_reload`. `AUTO_MIGRATE=1` runs `alembic upgrade head` at startup.

## SSOT & data rules (from CONTRIBUTING)

- DB is the single source of truth for providers/models/keys/budgets — never hardcode provider names or model lists.
- `user_model_id` is **composite unique** (`UniqueConstraint(provider_id, user_model_id)` — `app/models.py:57`). Same alias across providers is allowed; `resolve()` returns the first active match (default provider wins). Explicit `"provider-name/alias"` prefix supported for colliding aliases.
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
- Existing coverage: api, cleanup, discovery, failover, provider_manager, translate (incl. cohere/ollama/vision/tools), usage (pricing/cost/free).
- Load testing: `harness/load/load_test.py` (asyncio+httpx, no external deps): `--base --key --model --concurrency --duration --mix`.

## Frontend (web/)

- SvelteKit 5 (runes `$state`/`$derived`), Svelte 5, Tailwind 4, `adapter-static` with `paths.base = '/demumumind'` (`svelte.config.js`). UI components in `web/src/lib/components/ui/`.
- Deploy = `pnpm build` → static `web/build` served by reverse proxy under `/demumumind` prefix. Frontend-only change: rebuild, no backend restart.
- `web/src/lib/api.ts` wraps all fetch; `PANEL_API_KEY` stored in `panelKey` store, sent as Bearer.
- Routes: Dashboard, Providers, Models, Keys, Playground, Usage, **Images** (`/images` — image generation history grid), Plugins, MCP.
- Playground (`web/src/routes/playground/+page.svelte`) hits `/v1/chat/completions` with streaming; free models show `— FREE` suffix.
- Image files are served via `fetchImageGenerationBlob` (admin endpoint needs the Bearer header, so `<img>` can't hit it directly — fetch → blob URL).

## Operations (this box)

- Backend runs as sprite-env service `demumumind` (uvicorn `app.main:app` on `127.0.0.1:8000`). Restart: `/.sprite/bin/sprite-env services restart demumumind` (~6s boot, runs migration).
- Public: `https://test-sprite-busun.sprites.app/demumumind/` → rproxy :8080 → :8000 (strips `/demumumind`).
- Logs: `/.sprite/logs/services/demumumind.log`. Redis on `127.0.0.1:6379` (cache + hot_reload; falls back to 5s polling if down).
- Shared harness client key: `.secrets/dm-harness-key.env` (gitignored). Harness configs are examples only — user's live `~/.config/opencode` / `~/.omp` are NOT auto-edited.

## Docs

- `docs/harness-integration.md` — using the panel as provider from opencode/omp/Claude/Codex.
- `docs/provider-setup.md` — adding any upstream provider (`base_url + api_key + models`), `/v1` suffix pitfalls, alias collisions, troubleshooting.
- `harness/examples/` — opencode + omp example configs.
