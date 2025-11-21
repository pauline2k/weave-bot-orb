# Weave Discord Bot

A Discord bot that monitors specific channels for event links and sends them to an agent for parsing.

## Features

- Monitors configured Discord channels for messages containing links
- Sends links to an agent API for parsing
- Receives callbacks when parsing is complete
- Updates Discord messages with results
- SQLite database for tracking parse requests

## Setup

### Prerequisites

- Python 3.11+
- [UV](https://github.com/astral-sh/uv) for dependency management
- Discord bot token with MESSAGE_CONTENT intent enabled

### Installation

1. Install dependencies:
```bash
uv sync
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Edit `.env` with your configuration:
- `DISCORD_TOKEN`: Your Discord bot token
- `DISCORD_CHANNELS`: Comma-separated list of channel IDs to monitor
- `AGENT_API_URL`: URL of your agent API endpoint
- `WEBHOOK_PORT`: Port for the webhook server (default: 3000)

### Discord Bot Setup

1. Create a bot at https://discord.com/developers/applications
2. Enable the following intents:
   - MESSAGE CONTENT INTENT (required to read message content)
3. Add the bot to your server using this link (replace `YOUR_CLIENT_ID` with your application ID):

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=446676978752&scope=bot
```

Required permissions (446676978752):
- View Channels
- Send Messages
- Send Messages in Threads
- Manage Messages (to delete own messages)
- Read Message History

## Usage

Run the bot:
```bash
uv run python -m src.main
```

## Architecture

### Components

1. **Discord Bot** (`src/bot.py`)
   - Listens for messages in configured channels
   - Validates messages contain links
   - Sends links to agent API
   - Manages Discord message updates

2. **Webhook Server** (`src/webhook.py`)
   - Receives callbacks from agent when parsing completes
   - Runs on separate port (default: 3000)
   - Endpoints:
     - `POST /callback` - Agent completion callback
     - `GET /health` - Health check

3. **Database** (`src/database.py`)
   - SQLite database for tracking requests
   - Schema:
     - `discord_message_id`: Original message ID
     - `discord_response_id`: Bot's response message ID
     - `agent_request_id`: ID from agent API
     - `status`: pending, in_progress, completed, failed
     - `result_url`: Link to parsed result (optional)

### Flow

1. User posts a link in monitored channel
2. Bot replies with "🔄 Parsing event..."
3. Bot sends POST to agent API with URL
4. Agent API returns request ID
5. Bot stores request in database with status=in_progress
6. Agent processes link (2-20 seconds)
7. Agent sends POST to `/callback` webhook with result
8. Bot deletes "Parsing..." message
9. Bot replies to original message with result

### Agent API Contract

**Request to agent:**
```json
POST {AGENT_API_URL}
{
  "url": "https://example.com/event",
  "discord_message_id": 123456789
}
```

**Response from agent:**
```json
{
  "request_id": "unique-request-id"
}
```

**Callback from agent:**
```json
POST http://your-bot:3000/callback
{
  "request_id": "unique-request-id",
  "status": "completed",
  "result_url": "https://grist.example.com/..."
}
```

## Deployment

### Railway Deployment Guide

#### Quick Setup

1. **Create a new Railway project** from the Railway dashboard
2. **Connect your GitHub repository** (or deploy from CLI)
3. **Set environment variables** (see below)
4. **Deploy!** Railway will auto-detect Python and install dependencies

#### Important Considerations

**Port Configuration:**
- Railway automatically assigns a `PORT` environment variable
- Our webhook server uses `WEBHOOK_PORT` (default: 3000)
- Railway will expose this automatically - you don't need to configure anything special

**Database (SQLite):**
- SQLite data is **ephemeral** on Railway (resets on each deployment)
- This is fine for our use case since we only track temporary parse requests (2-20 seconds)
- If the bot restarts mid-parse, users can just retry posting the link
- For persistent storage needs, consider Railway's PostgreSQL addon

**Getting Your Railway URL:**
- After deployment, Railway provides a public URL (e.g., `https://your-app.railway.app`)
- Your webhook callback will be: `https://your-app.railway.app/callback`
- Copy this URL to configure your agent's callback URL

**SSL Certificates:**
- The `certifi` package is included and configured automatically
- No additional SSL setup needed on Railway

#### Environment Variables

Set these in Railway's environment variables settings:

```bash
DISCORD_TOKEN=your_bot_token_here
DISCORD_CHANNELS=1234567890,9876543210
AGENT_API_URL=http://your-agent-api.com/parse
WEBHOOK_PORT=3000
WEBHOOK_HOST=0.0.0.0
```

**Required:**
- `DISCORD_TOKEN` - Your Discord bot token from the Developer Portal
- `DISCORD_CHANNELS` - Comma-separated channel IDs to monitor (get these by enabling Developer Mode in Discord, right-click channel → Copy ID)
- `AGENT_API_URL` - The URL where your agent API is hosted

**Optional:**
- `WEBHOOK_PORT` - Defaults to 3000 (Railway handles port mapping automatically)
- `WEBHOOK_HOST` - Defaults to 0.0.0.0 (needed for Railway to route traffic)
- `DB_PATH` - SQLite database path (defaults to `weave_bot.db`)

#### Build Configuration

Railway will detect the Python project automatically. You can optionally add a `railway.toml`:

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uv run python -m src.main"
```

Or set the start command in Railway settings:
```bash
uv run python -m src.main
```

#### Testing Your Deployment

1. **Check the logs** in Railway dashboard to verify the bot connected:
   ```
   Bot logged in as YourBot#1234
   Monitoring channels: {1234567890, 9876543210}
   Webhook server started on 0.0.0.0:3000
   ```

2. **Test the webhook** health endpoint:
   ```bash
   curl https://your-app.railway.app/health
   # Should return: {"status":"ok"}
   ```

3. **Post a test link** in one of your monitored Discord channels

4. **Verify agent callback** works by checking Railway logs for callback receipts

#### Troubleshooting

**Bot won't connect:**
- Verify `DISCORD_TOKEN` is correct
- Check MESSAGE_CONTENT intent is enabled in Discord Developer Portal

**Not responding to messages:**
- Verify channel IDs in `DISCORD_CHANNELS` are correct
- Check bot has permissions in those channels
- Ensure MESSAGE_CONTENT intent is enabled

**Webhook not receiving callbacks:**
- Verify your agent is calling `https://your-app.railway.app/callback`
- Check Railway logs for incoming requests
- Test health endpoint: `curl https://your-app.railway.app/health`

**Database resets after deployment:**
- This is expected behavior with SQLite on Railway
- In-flight parse requests will be lost on redeploy (users can retry)
- For persistence, migrate to PostgreSQL (see below)

#### Upgrading to PostgreSQL (Optional)

For persistent storage across deployments:

1. Add PostgreSQL addon in Railway dashboard
2. Update `pyproject.toml`:
   ```toml
   dependencies = [
       "discord.py>=2.3.2",
       "aiohttp>=3.9.0",
       "python-dotenv>=1.0.0",
       "certifi>=2025.11.12",
       "asyncpg>=0.29.0",  # Add this
   ]
   ```
3. Modify `database.py` to use PostgreSQL connection
4. Railway will automatically set `DATABASE_URL` environment variable

## Development

Run in development:
```bash
uv run python -m src.main
```

The bot will:
- Connect to Discord
- Start webhook server on configured port
- Monitor configured channels
- Log all activity to console
