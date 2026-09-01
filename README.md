# DemumuMind — Panel

Enterprise AI Gateway. Aggregates any OpenAI/Anthropic/Gemini-compatible
provider into a single API + browser admin panel.

## Quick start

```bash
# universal path — override via DEMUMIND_ROOT
export PROJECT_ROOT=/opt/demumumind-panel  # or use pwd
cd $PROJECT_ROOT

make init
# → generates PANEL_API_KEY, installs deps, runs migrations

make dev
# → uvicorn on http://localhost:8000

# frontend (separate terminal)
cd web && pnpm dev
# → SvelteKit on http://localhost:5173
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `PROJECT_ROOT` | `$(pwd)` | Корень проекта |
| `DATABASE_URL` | `sqlite+aiosqlite:///./demumumind.db` | SQLite WAL / PostgreSQL |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Опционально; fallback polling 5с |
| `PANEL_API_KEY` | — | Генерируется `make init`; hmac-соль для ключей |
| `CORS_ORIGINS` | `http://localhost:5173` | Dev: localhost; Prod: ваш домен |
| `BIND_ADDR` | `0.0.0.0:8000` | Хост:порт для uvicorn |
| `AUTO_MIGRATE` | `1` | Запускать `alembic upgrade head` при старте |

## Commands

```bash
# админка
curl http://localhost:8000/health -i
curl -H "Authorization: Bearer $PANEL_API_KEY" http://localhost:8000/v1/admin/seed -X POST
curl -H "Authorization: Bearer $PANEL_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"MyProvider","base_url":"https://...","protocol":"openai"}' \
  http://localhost:8000/v1/admin/providers -X POST

# клиентский запрос (после создания ключа)
curl -H "Authorization: Bearer dm-<key>" \
  -d '{"model":"my-model","messages":[{"role":"user","content":"hi"}]}' \
  http://localhost:8000/v1/chat/completions

# тесты и линты
make test
make lint
```

## Systemd (production)

```bash
sudo mkdir -p /opt/demumumind-panel/data /var/log/demumumind
sudo cp demumumind.service /etc/systemd/system/
sudo cp .env /opt/demumumind-panel/
sudo chmod 600 /opt/demumumind-panel/.env
sudo systemctl daemon-reload && sudo systemctl enable --now demumumind
```

## Architecture

```
PROJECT_ROOT/
├── app/           # FastAPI async backend
│   ├── api/       # HTTP routes (v1 public + admin, MCP, auth)
│   ├── core/      # DB, Redis, error handlers
│   ├── services/  # translate, failover, dispatch, cache, plugins, MCP
│   ├── models.py  # 8 SQLAlchemy tables (SSOT)
│   ├── schemas.py # Pydantic DTOs
│   ├── seed.py    # Idempotent seed
│   └── main.py    # FastAPI app + lifespan
├── web/           # SvelteKit admin panel
├── alembic/       # Migrations
├── tests/         # pytest-asyncio (75+ tests)
├── docs/          # Integration guides
├── harness/       # Example configs for LLM harnesses
└── demumumind.service
```

## Harness integration

The panel is a drop-in OpenAI-compatible gateway. Any LLM harness
(opencode, omp, Claude Code, Codex, Cursor) can use it as a single
`base_url` instead of configuring every upstream provider separately.

```bash
# 1. Create a shared key (one-time)
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"monthly_budget":0}' \
  http://localhost:8000/v1/admin/keys -X POST
# → { "api_key": "dm-..." }

# 2. Verify
curl -H "Authorization: Bearer dm-..." \
  http://localhost:8000/v1/models?limit=3 | jq .
curl -H "Authorization: Bearer dm-..." \
  -d '{"model":"z-ai/glm-5.2:free","messages":[{"role":"user","content":"hi"}]}' \
  http://localhost:8000/v1/chat/completions
```

See [docs/harness-integration.md](docs/harness-integration.md) and
[harness/examples/](harness/examples/) for opencode, omp, Claude Code,
and Codex configuration examples.