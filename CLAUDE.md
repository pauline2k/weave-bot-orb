# CLAUDE.md

## Project Overview

**weave-bot-orb** - Multi-org event discovery system. Originally built for Oakland Review of Books (ORB), now supports multiple organizations with different LLM providers, chat platforms, and storage backends.

Three components:

1. **agent/** - Event scraping API (Playwright + pluggable LLM). Supports Gemini and any OpenAI-compatible endpoint.
2. **discord/** - Discord bot for event display and submission (ORB)
3. **slack/** - Slack bot adapter for organizations using Slack

See `docs/multi-org-guide.md` for the full multi-org setup and onboarding guide.

## Quick Start

```bash
# Terminal 1: Start the agent API
cd ~/Symbols/Codes/weave-bot-orb
./agent/run.sh

# Terminal 2: Start the Discord bot (ORB)
cd ~/Symbols/Codes/weave-bot-orb/discord
uv run python src/main.py

# Terminal 3 (optional): Start the Slack bot (other org)
cd ~/Symbols/Codes/weave-bot-orb/slack
uv run python src/main.py

# Test agent health (shows configured orgs)
curl http://localhost:8000/health

# Test sync scrape (returns full result)
curl -X POST "http://localhost:8000/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lu.ma/example-event"}'

# Test sync scrape with specific org
curl -X POST "http://localhost:8000/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lu.ma/example-event", "org_id": "orb"}'

# Test async parse (returns request_id, sends callback when done)
curl -X POST "http://localhost:8000/parse" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://lu.ma/example-event",
    "callback_url": "http://localhost:3000/callback"
  }'
```

## Project Structure

```
weave-bot-orb/
├── agent/                      # Event scraping API
│   ├── main.py                 # FastAPI entry point
│   ├── run.sh                  # Start script
│   ├── .env                    # API keys (fallback when no orgs.yaml)
│   ├── orgs.example.yaml       # Example multi-org config (tracked)
│   ├── orgs.yaml               # Actual org config (gitignored)
│   ├── api/routes.py           # Endpoints: /scrape, /parse, /health
│   ├── core/
│   │   ├── config.py           # Settings from .env
│   │   ├── org_config.py       # Per-org config (YAML loader + env var fallback)
│   │   ├── schemas.py          # Pydantic models (Event, ParseRequest, etc.)
│   │   ├── callback.py         # Sends results to chat bot webhooks
│   │   └── tasks.py            # Background task runner + per-org Grist save
│   ├── integrations/
│   │   └── grist.py            # Grist API client for saving events
│   ├── scraper/
│   │   ├── browser.py          # Playwright (fault-tolerant)
│   │   ├── processor.py        # JSON-LD + trafilatura extraction
│   │   └── orchestrator.py     # Pipeline + date override
│   └── llm/
│       ├── base.py             # Abstract LLM interface (ABC)
│       ├── factory.py          # Creates extractor per org config
│       ├── prompts.py          # Shared prompt templates (timezone-configurable)
│       ├── gemini.py           # Gemini extractor
│       └── openai_compat.py    # OpenAI-compatible extractor (HuggingFace, etc.)
├── discord/                    # Discord bot (ORB)
│   ├── src/
│   │   ├── main.py             # Entry point (bot + webhook server)
│   │   ├── bot.py              # WeaveBotClient - message handling
│   │   ├── config.py           # Environment config loader
│   │   ├── database.py         # SQLite request tracking
│   │   ├── webhook.py          # aiohttp callback server (port 3000)
│   │   └── utils.py            # URL extraction utilities
│   ├── tests/
│   │   ├── mock_agent.py       # Mock agent for testing
│   │   └── test_callback.sh    # Callback test script
│   ├── .env                    # Discord token, channel IDs, ORG_ID
│   ├── pyproject.toml          # UV dependencies
│   └── railway.toml            # Railway deployment config
├── slack/                      # Slack bot (other orgs)
│   ├── src/
│   │   ├── main.py             # Entry point (Socket Mode)
│   │   ├── bot.py              # SlackEventBot - message/image handling
│   │   ├── config.py           # Environment config loader
│   │   ├── utils.py            # URL extraction, image filtering
│   │   └── webhook.py          # aiohttp callback server (port 3001)
│   ├── tests/
│   │   ├── test_bot.py         # Bot formatting tests
│   │   └── test_utils.py       # URL/image detection tests
│   ├── .env.example            # Slack config template
│   └── pyproject.toml          # UV dependencies
├── docs/
│   ├── multi-org-guide.md      # Multi-org setup and onboarding guide
│   ├── brainstorms/            # Design brainstorms
│   └── plans/                  # Implementation plans
└── CLAUDE.md                   # This file
```

---

## Integration Architecture

```
┌─────────────────┐                    ┌─────────────────┐     ┌──────────────────┐
│  Discord Bot    │                    │  Agent API      │     │  Slack Bot       │
│  (webhook:3000) │                    │  (api:8000)     │     │  (webhook:3001)  │
└────────┬────────┘                    └────────┬────────┘     └────────┬─────────┘
         │                                      │                      │
    1. User posts link                          │       1. User posts link
         │                                      │                      │
    2. POST /parse ────────────────────────────►│◄─────────────────────┤
       {url, callback_url,                      │  {url, callback_url, │
        client_reference_id,                    │   client_reference_id,
        org_id: "orb"}                          │   org_id: "org2"}    │
         │                                      │                      │
    3. Returns immediately ◄────────────────────│─────────────────────►│
       {"request_id": "uuid"}                   │                      │
         │                                      │                      │
         │         4. Background processing     │                      │
         │            - Load org config         │                      │
         │            - Select LLM per org      │                      │
         │            - Playwright fetch        │                      │
         │            - LLM extraction          │                      │
         │            - Save to org's Grist     │                      │
         │                                      │                      │
    5. POST /callback ◄─────────────────────────│─────────────────────►│
       {request_id, status, event, result_url}  │                      │
         │                                      │                      │
    6. Update message with event + Grist link   │     6. Update Slack  │
```

---

## Grist Integration

Events are automatically saved to the **ORB Events** Grist document.

### Grist Document

- **Org**: OakLog (`oaklog.getgrist.com`)
- **Document ID**: `b2r9qYM2Lr9xJ2epHVV1K2`
- **Table**: `Events`
- **View**: https://oaklog.getgrist.com/b2r9qYM2Lr9xJ2epHVV1K2/Events

### Events Table Schema

| Column          | Type     | Description             |
| --------------- | -------- | ----------------------- |
| Title           | Text     | Event name              |
| StartDatetime   | DateTime | Start time              |
| EndDatetime     | DateTime | End time                |
| Venue           | Text     | Venue name              |
| Address         | Text     | Street address          |
| City            | Text     | City                    |
| LocationType    | Choice   | physical/virtual/hybrid |
| Description     | Text     | Event description       |
| SourceURL       | Text     | Original event URL      |
| Price           | Text     | Ticket price            |
| Tags            | Text     | Comma-separated tags    |
| ImageURL        | Text     | Event image             |
| OrganizerName   | Text     | Organizer               |
| ConfidenceScore | Numeric  | LLM confidence (0-1)    |
| CreatedAt       | DateTime | When scraped            |

### Configuration

**agent/.env:**

```
GRIST_API_KEY=your_grist_api_key
GRIST_DOC_ID=b2r9qYM2Lr9xJ2epHVV1K2
```

---

## Agent Component

### API Endpoints

| Endpoint  | Method | Description                                         |
| --------- | ------ | --------------------------------------------------- |
| `/scrape` | POST   | Sync scrape - accepts `org_id`, returns full result  |
| `/parse`  | POST   | Async parse - accepts `org_id`, saves to org's Grist |
| `/health` | GET    | Health check with configured orgs and LLM providers  |
| `/docs`   | GET    | Swagger UI                                          |

### Async Parse Flow

1. Receive URL + callback_url + org_id
2. Validate org_id against config
3. Return `request_id` immediately
4. Background: load org config → create LLM → scrape → extract → save to org's Grist
5. POST callback with event data + Grist URL

### Configuration

**Option 1: `agent/orgs.yaml`** (multi-org, see `orgs.example.yaml`):

```yaml
orgs:
  orb:
    llm: { provider: "gemini", api_key: "${ORB_GEMINI_API_KEY}", model: "gemini-2.5-flash-lite" }
    storage: { api_key: "${ORB_GRIST_API_KEY}", doc_id: "b2r9qYM2Lr9xJ2epHVV1K2", ... }
```

**Option 2: `agent/.env`** (single-org fallback):

```
GEMINI_API_KEY=your_gemini_key
GRIST_API_KEY=your_grist_key
GRIST_DOC_ID=b2r9qYM2Lr9xJ2epHVV1K2
HEADLESS=true
BROWSER_TIMEOUT=30000
```

### Key Files

| File                      | Purpose                                         |
| ------------------------- | ----------------------------------------------- |
| `api/routes.py`           | `/scrape` (sync) and `/parse` (async) endpoints |
| `core/org_config.py`      | Per-org config loader (YAML + env var fallback)  |
| `core/tasks.py`           | Background task runner, per-org LLM + Grist      |
| `core/callback.py`        | Sends results to chat bot webhooks               |
| `llm/factory.py`          | Creates correct LLM extractor per org            |
| `llm/prompts.py`          | Shared prompt templates (timezone-configurable)  |
| `integrations/grist.py`   | Grist API client (per-org credentials)           |
| `scraper/orchestrator.py` | Main scraping pipeline                          |

---

## Discord Component

### Architecture

1. Bot monitors configured channels for links
2. On link detected: replies "Parsing...", sends to Agent
3. Agent returns `request_id` immediately
4. Bot stores request in SQLite (status: IN_PROGRESS)
5. Agent processes in background (2-20 seconds)
6. Agent saves to Grist, gets record URL
7. Agent POSTs callback to Bot's webhook server
8. Bot updates Discord with event details + Grist link

### Configuration

**discord/.env:**

```
DISCORD_TOKEN=your_bot_token
DISCORD_CHANNELS=channel_id_1,channel_id_2
ORG_ID=orb                              # Which org this bot represents
AGENT_API_URL=http://localhost:8000/parse
WEBHOOK_PORT=3000
WEBHOOK_HOST=0.0.0.0
DB_PATH=weave_bot.db
```

### Key Files

| File              | Purpose                                           |
| ----------------- | ------------------------------------------------- |
| `src/bot.py`      | Message handling, sends to agent, formats replies |
| `src/webhook.py`  | Receives callbacks from agent on port 3000        |
| `src/database.py` | SQLite tracking of parse requests                 |

---

## Slack Component

### Architecture

1. Bot monitors configured Slack channels via Socket Mode
2. On link detected: replies "Parsing...", sends to Agent with `org_id`
3. On image upload: downloads via Slack Files API, sends to Agent
4. Agent processes in background, POSTs callback to webhook (port 3001)
5. Bot updates the Slack message with event details + Grist link

### Configuration

**slack/.env:**

```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_CHANNELS=C0123456789
ORG_ID=org2                              # Which org this bot represents
AGENT_API_URL=http://localhost:8000/parse
WEBHOOK_PORT=3001
CALLBACK_URL=http://slack-bot:3001/callback
```

### Key Files

| File              | Purpose                                          |
| ----------------- | ------------------------------------------------ |
| `src/bot.py`      | Slack event handling, link/image detection        |
| `src/webhook.py`  | Receives callbacks from agent on port 3001       |
| `src/utils.py`    | URL extraction (handles Slack `<url|label>` format) |

---

## Tested Platforms

| Platform   | Score | Notes                      |
| ---------- | ----- | -------------------------- |
| Eventbrite | 0.95  | Excellent                  |
| Luma       | 0.90  | JSON-LD override critical  |
| BAMPFA     | 0.90  | Works                      |
| UCB Events | 0.95  | Works                      |
| Instagram  | 0.85  | Needs screenshot           |
| Meetup     | N/A   | Auth wall - requires login |

---

## Common Issues

### Agent Issues

**429 quota error**: Wait 1-2 min or disable screenshots

**Wrong dates**: Check JSON-LD override in `orchestrator.py`

**Import errors**: Run from weave-bot-orb root with `PYTHONPATH=$(pwd)`

**Browser timeout**: Increase `BROWSER_TIMEOUT` in .env

**Grist save failed**: Check `GRIST_API_KEY` in .env

### Discord Issues

**Bot not responding**: Check DISCORD_CHANNELS includes the channel ID

**Database locked**: Ensure only one bot instance running

**Callback not received**: Verify WEBHOOK_PORT is accessible from agent

---

## Future Enhancements

- **Multi-org remaining work**: See `docs/multi-org-guide.md` (Future Work section)
- **Duplicate detection**: Check if event URL already exists in Grist
- **Batch scraping**: Multiple URLs in one request
- **Event editing**: Allow users to correct parsed data via Discord/Slack
- **Scheduled scraping**: Auto-scrape known event sources
