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
| `protocol` | no | `openai` (default, covers 95% generic), `anthropic`, `gemini` |
| `is_active` | no | `true` by default |

**base_url pitfalls:** `https://api.anthropic.com/v1` + `protocol=anthropic` → path `v1/messages` → full `.../v1/v1/messages` (double). Use `https://api.anthropic.com` for anthropic, `https://api.openai.com/v1` for openai. UI does not validate scheme — `http://` for local is fine.

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

**Alias collision:** `user_model_id` is globally unique for routing (`POST /v1/chat/completions {"model":"gpt-4o"}` is unambiguous). If second provider lists `gpt-4o` already owned by first, discover skips it (`skipped_global_alias` in log) instead of 500. Use provider-prefixed alias (`openrouter/gpt-4o`) or per-key `model_mapping` to disambiguate.

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

Ollama: `base_url=http://host.docker.internal:11434/v1`, `api_key=null`, `protocol=openai`. Same for vLLM/LMStudio.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Discover: 0 models` | provider returns `{models:[...]}` not `{data:[{id}]}` | Check `parse_model_items` fallback, or add manually |
| `Cannot read properties of null (reading 'ok_count')` | already fixed `325975a` — now shows `event:error` toast | update panel |
| `UNIQUE constraint failed: models.user_model_id` | fixed `325975a` — now skips global alias | use prefixed alias |
| `HTTP 401` on test/discover | wrong `api_key` or missing `Bearer` | verify `pool.py:18` headers per protocol |
| `database is locked` | SQLite WAL under 16+ concurrent writers | already mitigated `busy_timeout 30000` + retry, or switch to Postgres `DATABASE_URL=postgresql+asyncpg://` |

See also `docs/harness-integration.md` for consuming the panel from opencode/omp.
