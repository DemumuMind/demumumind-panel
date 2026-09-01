# Universal provider setup

Panel is a generic OpenAI-compatible gateway. Any `https://api.example.com/v1` with an API key works without code changes.

## Add any provider (base_url + api_key + models)

### 1. Create provider

```bash
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-provider",
    "base_url": "https://api.example.com/v1",
    "api_key": "sk-...",
    "protocol": "openai"
  }' \
  https://test-sprite-busun.sprites.app/demumumind/v1/admin/providers -X POST
# or locally
# http://127.0.0.1:8000/v1/admin/providers
```

Fields:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | unique, human label |
| `base_url` | yes | must include `/v1` if provider expects `/v1/models`, no trailing `/` needed (`pool.py` normalizes) |
| `api_key` | no | leave `null` for keyless (ollama `http://localhost:11434/v1`) |
| `protocol` | no | `openai` (default, covers most generic), `anthropic`, `gemini`, `cohere`, `ollama`, `azure` |
| `is_active` | no | `true` by default |

**base_url pitfalls:** `https://api.anthropic.com/v1` + `protocol=anthropic` → path `v1/messages` → full `.../v1/v1/messages` (double). Use `https://api.anthropic.com` for anthropic, `https://api.openai.com/v1` for openai. `base_url` is validated on create/update — must include `http://` or `https://`.

### 2. Discover models

Panel calls `GET {base_url}/models` and parses:

* openai-compatible: `{ data: [{ id: "gpt-4o", pricing: {...} }] }`
* gemini: `{ models: [{ name: "models/gemini-..." }] }`

It tolerates `pricing` as string or number, `:free`/`-free` suffix → `free:true`, `per_request_limits` → `limits`.

```bash
# light discover (import only, no ping)
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -X POST https://test-sprite-busun.sprites.app/demumumind/v1/admin/providers/{id}/discover
# SSE stream: stage:listing → stage:import (per-model) → done {total, imported, skipped, ok_count}

# full test (pings each model with max_tokens=5, 2 concurrent, 0.2s stagger)
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -X POST "https://test-sprite-busun.sprites.app/demumumind/v1/admin/providers/{id}/discover?test=1"
```

If provider has no `/models` → `total 0`, create models manually:

```bash
curl -H "Authorization: Bearer $PANEL_API_KEY" -H "Content-Type: application/json" \
  -d '{"provider_id":"<id>","user_model_id":"my-alias","internal_model":"real-id"}' \
  https://test-sprite-busun.sprites.app/demumumind/v1/admin/models -X POST
```

**Alias collision:** `user_model_id` is composite-unique per `(provider_id, user_model_id)` — the same alias is allowed across providers. `resolve()` returns the first active match (default provider wins); use `"provider-name/alias"` (e.g. `openrouter/gpt-4o`) or per-key `model_mapping` to target a specific provider.

### 3. Test

```bash
# quick connectivity check
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -X POST https://test-sprite-busun.sprites.app/demumumind/v1/admin/providers/{id}/test
# -> { ok, models: ["..."], message }

# single model ping
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -X POST https://test-sprite-busun.sprites.app/demumumind/v1/admin/providers/{id}/models/{internal}/test

# end-to-end (needs client key)
curl -H "Authorization: Bearer dm-..." -H "Content-Type: application/json" \
  -d '{"model":"my-alias","messages":[{"role":"user","content":"hi"}]}' \
  https://test-sprite-busun.sprites.app/demumumind/v1/chat/completions
```

### 4. Auth pool (optional)

Primary `api_key` + pool `POST /v1/admin/providers/{id}/keys {"api_key":"sk-..."}` — round-robin with 5s cooldown on 429.

### 5. Pricing / free

Auto from `/models` `pricing` or `usage.cost` (OpenRouter). For providers that disclose nothing — set manually `PATCH /v1/admin/models/{id}/pricing {"price_prompt_per_token":1e-6, "free":true}` — existing usage rows are reconciled.

### 6. Local providers

Ollama: `base_url=http://host.docker.internal:11434`, `api_key=null`, `protocol=ollama`
(panel sends `/api/chat`, translates images/options). Same for vLLM/LMStudio with
`protocol=openai` (`http://host.docker.internal:8000/v1`).

## Image models

Providers listing `gpt-image`, `dall-e`, `flux`, `sdxl`, `imagen`… get `kind=image`
in model metadata. They are excluded from the chat workability test (`ok/listed`)
and routed to `/v1/images/generations` — either directly or automatically when
a chat request targets an image model. Generated images land in `data/images/`
and appear on the admin **Images** page.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Discover: 0 models` | provider returns a non-standard `/models` shape | Add models manually via `POST /v1/admin/models` |
| `Cannot read properties of null (reading 'ok_count')` | provider `/models` unreachable aborted the SSE | fixed — panel now emits `event:error` with the upstream message; update panel |
| `UNIQUE constraint failed: models.user_model_id` | same alias inserted twice for one provider | composite `(provider_id, user_model_id)` unique — re-run discover, or use `provider/alias` |
| `HTTP 401` on test/discover | wrong `api_key` or wrong auth header | verify `app/services/pool.py` `_PROTOCOL_HEADERS` for the protocol (azure uses `api-key`, anthropic `x-api-key`, gemini `x-goog-api-key`, others Bearer) |
| `database is locked` | SQLite WAL under many concurrent writers | mitigated `busy_timeout 30000` + retry in `dispatch`; for higher load switch to Postgres (`DATABASE_URL=postgresql+asyncpg://…`) + `scripts/migrate_sqlite_to_postgres.py` |

See also `docs/harness-integration.md` for consuming the panel from opencode/omp.
