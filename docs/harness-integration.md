# Harness integration

DemumuMind Panel is a drop-in OpenAI-compatible gateway. Any LLM harness
(opencode, omp, Claude Code, Codex, Cursor, etc.) can use it as a single
`base_url` instead of configuring every upstream provider separately.

## Quick start

### 1. Create a shared key

```bash
curl -H "Authorization: Bearer $PANEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"monthly_budget":0}' \
  https://test-sprite-busun.sprites.app/demumumind/v1/admin/keys -X POST
# → { "api_key": "dm-..." }
```

`monthly_budget:0` = unlimited. Store the key in an env var (never commit it).

### 2. Verify the key works

```bash
# list available models
curl -H "Authorization: Bearer dm-..." \
  https://test-sprite-busun.sprites.app/demumumind/v1/models | jq .

# send a chat request
curl -H "Authorization: Bearer dm-..." \
  -H "Content-Type: application/json" \
  -d '{"model":"z-ai/glm-5.2:free","messages":[{"role":"user","content":"hi"}]}' \
  https://test-sprite-busun.sprites.app/demumumind/v1/chat/completions
```

### 3. Configure your harness

---

## opencode

Add a provider to `~/.config/opencode/opencode.jsonc`:

```jsonc
"demumumind": {
  "name": "DemumuMind",
  "env": ["DEMUMUMIND_API_KEY"],
  "npm": "@ai-sdk/openai-compatible",
  "options": {
    "baseURL": "https://test-sprite-busun.sprites.app/demumumind/v1",
    "apiKey": "$DEMUMUMIND_API_KEY"
  },
  "models": {
    "z-ai/glm-5.2:free": { "name": "GLM 5.2 Free" },
    "minimax/minimax-m3:free": { "name": "MiniMax M3 Free" },
    "gpt-5.6-sol": { "name": "GPT 5.6 Sol" }
  }
}
```

Then set `"model": "demumumind/z-ai/glm-5.2:free"` at the top of the config,
or `export DEMUMUMIND_API_KEY=dm-...` before running opencode.

---

## omp (Oh My Pi)

Add to `~/.omp/agent/models.yml`:

```yaml
providers:
  demumumind:
    name: DemumuMind
    api: openai-completions
    baseUrl: https://test-sprite-busun.sprites.app/demumumind/v1
    apiKey: dm-...
    models:
      - id: z-ai/glm-5.2:free
        name: GLM 5.2 Free
        contextWindow: 131072
      - id: minimax/minimax-m3:free
        name: MiniMax M3 Free
        contextWindow: 131072
      - id: gpt-5.6-sol
        name: GPT 5.6 Sol
        contextWindow: 400000
```

Then set `~/.omp/agent/config.yml` model roles to `demumumind/...`:

```yaml
modelRoles:
  default: demumumind/z-ai/glm-5.2:free
  task: demumumind/gpt-5.6-sol
```

---

## Claude Code

```bash
export ANTHROPIC_BASE_URL=https://test-sprite-busun.sprites.app/demumumind/v1
export ANTHROPIC_API_KEY=dm-...
```

Claude Code sends `POST /messages` which the panel translates through
`app/api/v1/routes.py:185`.

---

## Codex / OpenAI SDK

```bash
export OPENAI_BASE_URL=https://test-sprite-busun.sprites.app/demumumind/v1
export OPENAI_API_KEY=dm-...
```

---

## Available models

Query the full catalogue:

```bash
curl -H "Authorization: Bearer dm-..." \
  https://test-sprite-busun.sprites.app/demumumind/v1/models?limit=1000
```

Each model is routed through its upstream provider automatically.
Pricing and free/unlimited badges are shown in the Usage page and
can be configured per model in the Panel's Models page.

### Image generation

```bash
curl -H "Authorization: Bearer dm-..." -H "Content-Type: application/json" \
  -d '{"model":"gpt-image-2","prompt":"a red apple","n":1,"size":"1024x1024"}' \
  https://test-sprite-busun.sprites.app/demumumind/v1/images/generations
```

Image models are auto-detected at discovery and routed to the images endpoint.
Generated images appear on the panel's **Images** page (`/images`).

### Usage by provider

```bash
curl -H "Authorization: Bearer dm-..." \
  https://test-sprite-busun.sprites.app/demumumind/v1/usage/by-provider?limit=10 | jq .
```

## Key management

- One key per harness = separate `agent_type` in Usage (`/v1/usage`).
- Keys can be mapped per-model via `model_mapping` at creation time.
- Budget = 0 (unlimited) by default; set `monthly_budget` to cap spend.
- Revoke a key: `DELETE /v1/admin/keys/{id}`.

## Notes

- `baseURL` must end in `/v1` for opencode (`@ai-sdk/openai-compatible`).
- The panel accepts `Authorization: Bearer` (preferred) and `X-Api-Key`.
- CORS is configured per `CORS_ORIGINS` in `.env` — not needed for CLI/SDK.