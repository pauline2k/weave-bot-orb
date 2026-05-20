# Multi-Org Support Guide

> How weave-bot-orb supports multiple organizations on one deployment.

---

## What Changed

The system was originally hardcoded to a single org (ORB) — one LLM (Gemini), one chat platform (Discord), and one Grist doc. Multi-org support adds the ability to serve multiple organizations from the same deployment, each with their own LLM provider, chat platform, and storage backend.

### Summary of Changes

**Agent (core pipeline)**
- New **org config system** (`agent/core/org_config.py`) — YAML-based org profiles with `${VAR}` env var substitution for secrets
- New **LLM factory** (`agent/llm/factory.py`) — creates the correct extractor based on org config
- New **OpenAI-compatible extractor** (`agent/llm/openai_compat.py`) — supports HuggingFace Inference API, vLLM, and any OpenAI-compatible endpoint
- **Shared prompt builder** (`agent/llm/prompts.py`) — extracted from Gemini, accepts configurable timezone
- **Per-org Grist credentials** — each org saves to its own Grist doc with correct record URLs
- **`org_id` field** flows through `ParseRequest` → `ParseTask` → LLM factory → Grist save
- **Field rename**: `discord_message_id` (int) → `client_reference_id` (str) for platform-agnostic tracking

**Slack adapter (new)**
- New `slack/` directory — full Slack bot using `slack-bolt` with Socket Mode
- Monitors channels for links and image uploads
- Formats results using Slack Block Kit
- Webhook server on port 3001 for agent callbacks

**Discord bot (updated)**
- Sends `org_id: "orb"` and `client_reference_id` (was `discord_message_id`) to agent
- Reads `ORG_ID` from environment (defaults to `"orb"`)

### Architecture

```
                    ┌──────────────────────┐
                    │   Org Config (YAML)  │
                    │  orb: gemini+discord │
                    │  org2: openai+slack  │
                    └──────────┬───────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
┌────────┴────────┐   ┌───────┴───────┐   ┌────────┴────────┐
│  Discord Bot    │   │  Agent API    │   │  Slack Bot      │
│  (ORB)          │   │  (shared)     │   │  (Org #2)       │
│  port 3000      │   │  port 8000    │   │  Socket Mode    │
└────────┬────────┘   └───────┬───────┘   └────────┬────────┘
         │                    │                     │
         │  POST /parse       │  POST /parse        │
         │  {org_id: "orb"}   │  {org_id: "org2"}   │
         ├───────────────────►│◄────────────────────┤
         │                    │                     │
         │              ┌─────┴─────┐               │
         │              │ Task Runner│               │
         │              │ org_id →   │               │
         │              │ config →   │               │
         │              │ LLM select │               │
         │              └─────┬─────┘               │
         │                    │                     │
         │          ┌─────────┼─────────┐           │
         │          │         │         │           │
         │    ┌─────┴───┐ ┌──┴───┐ ┌───┴────┐      │
         │    │ Gemini  │ │OpenAI│ │ Grist  │      │
         │    │(ORB)    │ │compat│ │per-org │      │
         │    └─────────┘ │(Org2)│ └────────┘      │
         │                └──────┘                  │
```

---

## Things the Team Needs to Know

### 1. Deploy Agent + Discord Bot Together

The `discord_message_id` field was renamed to `client_reference_id` in the agent API. Both services must be deployed at the same time to avoid mismatched field names.

In practice, Pydantic v2 ignores extra fields by default, so a brief mismatch during rolling deploys won't crash either service. But callbacks route by `request_id`, not the renamed field — so the system is safe during deploys. Still, deploy both together to be clean.

### 2. ORB Requires Zero Migration

The existing Railway deployment works unchanged. When no `orgs.yaml` file exists, the agent falls back to building a default `"orb"` config from the same env vars it always used (`GEMINI_API_KEY`, `GRIST_API_KEY`, `GRIST_DOC_ID`). The Discord bot defaults `ORG_ID` to `"orb"`.

No new env vars or config files needed for ORB to keep working.

### 3. `client_reference_id` Replaces `discord_message_id`

The field changed from `Optional[int]` to `Optional[str]` and was renamed for platform-agnostic use. The Discord bot now sends `str(message_id)`. The Slack bot sends a composite string `"channel:message_ts:response_ts"` that it parses back on callback.

### 4. `org_id` Defaults to `"default"`

If no `org_id` is sent in a request, it defaults to `"default"`, which resolves to the first org in the YAML file (or the env-var-based fallback). Existing clients that don't send `org_id` will keep working.

### 5. LLM Providers Use Lazy Imports

The factory in `agent/llm/factory.py` only imports the provider module when it's actually used. A Gemini-only deployment won't error if the `openai` package isn't installed (though it's in `requirements.txt` now).

### 6. Org Config is Cached

`load_org_configs()` caches the result in memory. Call `clear_org_configs()` in tests to reset state. In production, configs load once at first use and stay in memory for the process lifetime. Changing `orgs.yaml` requires restarting the agent.

---

## How to Set Up the Org Config

### Option A: YAML File (Recommended for Multi-Org)

Copy the example and fill in your values:

```bash
cd agent/
cp orgs.example.yaml orgs.yaml
```

Edit `orgs.yaml`:

```yaml
orgs:
  orb:
    name: "Oakland Review of Books"
    timezone: "America/Los_Angeles"

    llm:
      provider: "gemini"
      api_key: "${ORB_GEMINI_API_KEY}"
      model: "gemini-2.5-flash-lite"

    storage:
      backend: "grist"
      api_key: "${ORB_GRIST_API_KEY}"
      doc_id: "b2r9qYM2Lr9xJ2epHVV1K2"
      table_name: "Events"
      ui_host: "oaklog.getgrist.com"
      ui_page_name: "ORB-Events"

    chat:
      platform: "discord"
      channels: [1438314815901794364]
```

Secrets use `${VAR_NAME}` syntax — replaced with `os.environ` at load time. The YAML file itself is gitignored; the example file (`orgs.example.yaml`) is tracked.

### Option B: Environment Variables Only (Single-Org / Backward Compat)

If no `orgs.yaml` exists, the agent builds a default `"orb"` config from:
- `GEMINI_API_KEY`
- `GRIST_API_KEY`
- `GRIST_DOC_ID`

This is how ORB currently runs on Railway. No changes needed.

---

## How to Onboard a New Organization

### Step 1: Gather Info

You need from the new org:
- **LLM provider and credentials** — which model, API key, endpoint URL (if not Gemini)
- **Grist doc** — API key, doc ID, table name, host URL, page name
- **Chat platform** — Discord or Slack? What channels to monitor?
- **Timezone** — for date/time extraction in LLM prompts

### Step 2: Add Org to YAML Config

Add a new section to `agent/orgs.yaml`:

```yaml
orgs:
  orb:
    # ... existing ORB config ...

  neworg:
    name: "New Organization"
    timezone: "America/New_York"

    llm:
      provider: "openai_compatible"
      api_key: "${NEWORG_HF_API_KEY}"
      model: "PleIAs/pleias-large"
      endpoint_url: "https://api-inference.huggingface.co/v1"

    storage:
      backend: "grist"
      api_key: "${NEWORG_GRIST_API_KEY}"
      doc_id: "their-grist-doc-id"
      table_name: "Events"
      ui_host: "their-host.getgrist.com"
      ui_page_name: "Events"

    chat:
      platform: "slack"
      channels: ["C0123456789"]
```

### Step 3: Set Environment Variables

Add the new org's secrets to the deployment environment:

```bash
NEWORG_HF_API_KEY=hf_xxxxx
NEWORG_GRIST_API_KEY=xxxxx
```

### Step 4: Set Up Chat Bot

**For Slack:**

1. Create a Slack app at https://api.slack.com/apps
2. Enable Socket Mode (no public URL needed)
3. Add bot scopes: `channels:history`, `channels:read`, `chat:write`, `files:read`
4. Subscribe to events: `message.channels`
5. Install to workspace, get bot token (`xoxb-...`) and app token (`xapp-...`)
6. Configure `slack/.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_CHANNELS=C0123456789
   ORG_ID=neworg
   AGENT_API_URL=http://agent-service:8000/parse
   CALLBACK_URL=http://slack-bot:3001/callback
   ```
7. Deploy the Slack bot as a new service (Railway, Docker, etc.)

**For Discord:**

1. Deploy another Discord bot instance with `ORG_ID=neworg` in its `.env`
2. Set `DISCORD_CHANNELS` to the new org's channel IDs

### Step 5: Set Up Grist

1. Create a Grist document for the new org
2. Create an `Events` table with the same column schema (see CLAUDE.md for schema)
3. Generate an API key for the Grist document
4. Add the doc ID and API key to the org config

### Step 6: Test

```bash
# Verify the agent sees the new org
curl http://localhost:8000/health
# Should show: "orgs": {"orb": {"llm_provider": "gemini"}, "neworg": {"llm_provider": "openai_compatible"}}

# Test scraping with the new org's LLM
curl -X POST "http://localhost:8000/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lu.ma/some-event", "org_id": "neworg"}'
```

### Step 7: Deploy

1. Deploy the updated agent (with new `orgs.yaml` + env vars)
2. Deploy the new chat bot service
3. Existing services (ORB Discord bot) continue working unchanged

---

## Supported LLM Providers

| Provider | Config Value | Supports Images | Notes |
|----------|-------------|-----------------|-------|
| Google Gemini | `gemini` | Yes | Default for ORB. Uses `google-generativeai` SDK |
| OpenAI-Compatible | `openai_compatible` | No | Covers HuggingFace, vLLM, Replicate, etc. Requires `endpoint_url` |

The OpenAI-compatible extractor handles HuggingFace-specific issues:
- **503 model loading**: Retries with double-length waits for cold starts
- **JSON repair**: Strips markdown fences, fixes trailing commas, matches Gemini's logic
- **Image parsing**: Returns a not-supported message (most providers don't support vision via OpenAI API)

To add a new LLM provider, implement the `LLMExtractor` ABC (`agent/llm/base.py`) and add a case in `agent/llm/factory.py`.

---

## Future Work

### Remaining Plan Items (Unchecked)

These items from the implementation plan are not yet complete:

- **Pass org timezone to `validate_event()` and `_format_datetime()`** — Currently the prompt tells the LLM to use the org's timezone, but the validation/formatting code still defaults to Pacific. Low priority since the LLM output is already timezone-aware.
- **Slack SQLite request tracking** — The Slack bot doesn't persist request state across restarts. Follow the Discord bot's `database.py` pattern with a `platform` column.
- **Slack editorial replies** — Detect threaded replies to bot event messages and update Grist editorial field. Mirrors Discord's editorial reply feature.
- **Discord reads Grist credentials from org config** — Currently uses separate `GRIST_API_KEY` env var. Should read from org config for consistency.
- **Mock agent callback tests for Slack** — Test the webhook callback flow end-to-end.

### Longer-Term Enhancements

- **Duplicate detection** — Check if an event URL already exists in Grist before saving
- **Health endpoint per-org LLM health** — Ping each LLM provider to verify connectivity
- **One org's LLM outage doesn't affect others** — Already architecturally isolated, but could add circuit breakers
- **Admin API** — Manage orgs without editing YAML (reload config, add/remove orgs)
- **Shared SQLite for cross-platform tracking** — Unify Discord and Slack request tracking

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `agent/core/org_config.py` | Org config models, YAML loader, env var fallback |
| `agent/llm/factory.py` | Creates correct LLM extractor per org |
| `agent/llm/prompts.py` | Shared prompt templates (timezone-configurable) |
| `agent/llm/openai_compat.py` | OpenAI-compatible extractor (HuggingFace, etc.) |
| `agent/llm/gemini.py` | Gemini extractor (updated for shared prompts) |
| `agent/llm/base.py` | LLM extractor ABC |
| `agent/core/tasks.py` | Task runner with per-org LLM + Grist routing |
| `agent/core/schemas.py` | `org_id` + `client_reference_id` fields |
| `agent/orgs.example.yaml` | Example org config (tracked in git) |
| `slack/src/bot.py` | Slack bot — link detection, agent API calls |
| `slack/src/webhook.py` | Slack callback server (port 3001) |
| `slack/src/main.py` | Slack bot entry point (Socket Mode) |
| `slack/.env.example` | Slack bot config template |
