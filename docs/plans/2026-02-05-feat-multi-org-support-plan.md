---
title: "feat: Multi-Org Support"
type: feat
date: 2026-02-05
---

# Multi-Org Support

## Overview

Add support for a second organization on the same weave-bot-orb deployment. Org #2 needs Slack (instead of Discord), Pleias LLM via HuggingFace Inference API (instead of Gemini), and their own Grist doc. ORB's existing setup must continue working unchanged.

## Problem Statement

The system is hardcoded to a single org (ORB) at multiple levels: Gemini is the only LLM, Discord is the only chat platform, and Grist doc/credentials are global singletons. A second org cannot use the system without running a completely separate deployment.

## Proposed Solution

Build org-aware routing through the existing pipeline using config-file-based org profiles. Add an OpenAI-compatible LLM extractor (covers Pleias via HuggingFace and any other OpenAI-compatible provider). Build a Slack adapter that mirrors the Discord bot's behavior.

### Design Decisions (from brainstorm)

1. **Org identity**: Explicit `org_id` field on `ParseRequest`, defaulting to `"default"` for backward compatibility
2. **LLM routing**: Per-org config selects provider + credentials. OpenAI-compatible client covers HuggingFace, Replicate, etc.
3. **Config format**: YAML file with env var substitution for secrets (`${VAR_NAME}`)
4. **Chat adapters**: Separate processes per platform (Discord bot, Slack bot), each hitting the shared Agent API
5. **Storage**: Both orgs use Grist with different docs. Abstract storage only when a non-Grist backend is needed.
6. **Rename**: `discord_message_id` -> `client_reference_id` across agent schemas

---

## Technical Approach

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
         │  POST /parse       │                     │
         │  {org_id: "orb"}   │  POST /parse        │
         ├───────────────────►│◄────────────────────┤
         │                    │  {org_id: "org2"}   │
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
         │                    │                     │
         │  POST /callback    │  POST /callback     │
         │◄───────────────────┤────────────────────►│
         │                    │                     │
```

### Org Config Schema

```yaml
# orgs.yaml
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

  org2:
    name: "Second Org"
    timezone: "America/Los_Angeles"

    llm:
      provider: "openai_compatible"
      api_key: "${ORG2_HF_API_KEY}"
      model: "PleIAs/pleias-large"
      endpoint_url: "https://api-inference.huggingface.co/v1"

    storage:
      backend: "grist"
      api_key: "${ORG2_GRIST_API_KEY}"
      doc_id: "their-grist-doc-id"
      table_name: "Events"
      ui_host: "their-host.getgrist.com"
      ui_page_name: "Events"

    chat:
      platform: "slack"
      channels: ["C0123456789"]
```

---

## Implementation Phases

### Phase 1: Agent Core — Org Config + LLM Routing

Foundation work in the agent. No new chat adapters yet — testable via `/scrape` endpoint.

#### 1a. Org config system

- [x] Create `agent/core/org_config.py` with `OrgConfig` pydantic model and YAML loader
- [x] Env var substitution (`${VAR}` -> `os.environ[VAR]`) at load time
- [x] `get_org_config(org_id: str) -> OrgConfig` lookup function
- [x] Default org (`"default"` maps to first org or `ORB_` env vars) for backward compat
- [x] Validate config on startup (required fields, API keys present)

#### 1b. OpenAI-compatible LLM extractor

- [x] Create `agent/llm/openai_compat.py` implementing `LLMExtractor` ABC
- [x] Use `openai` Python SDK (works with any OpenAI-compatible endpoint via `base_url`)
- [x] Accept `api_key`, `model`, `endpoint_url` in constructor
- [x] Reuse prompt templates from Gemini (extract shared prompt builder)
- [x] Handle HuggingFace-specific errors (503 model loading, cold start delays)
- [x] `extract_event_from_image()`: raise `NotImplementedError` if provider doesn't support multimodal (log warning, return low-confidence text-only extraction)

#### 1c. LLM factory + per-org timezone

- [x] Create `agent/llm/factory.py` with `create_extractor(org_config) -> LLMExtractor`
- [x] Pass org timezone to prompt builder (replace hardcoded Pacific)
- [ ] Pass org timezone to `validate_event()` and `_format_datetime()`

#### 1d. Wire org_id through the pipeline

- [x] Rename `discord_message_id` -> `client_reference_id` in `schemas.py`, `callback.py`, `tasks.py`, `routes.py`
- [x] Add `org_id: str = "default"` to `ParseRequest`, `ScrapeRequest`, `ParseTask`, `CallbackPayload`
- [x] In `_run_task()`: load `OrgConfig`, create correct LLM extractor, pass Grist credentials
- [x] In `/scrape` endpoint: accept `org_id`, use correct LLM
- [ ] Update Discord bot to send `client_reference_id` and `org_id: "orb"`

#### Tests

- [x] Unit tests for org config loading (valid YAML, missing fields, env var substitution)
- [x] Unit tests for OpenAI-compatible extractor (mock httpx responses)
- [x] Unit tests for LLM factory (returns correct extractor per provider)
- [x] Integration test: `/scrape` with `org_id` routes to correct LLM

### Phase 2: Slack Adapter

New `slack/` directory, parallel to `discord/`.

#### 2a. Slack bot core

- [x] Create `slack/` directory with `src/main.py`, `src/bot.py`, `src/config.py`
- [x] Use `slack-bolt` library with Socket Mode (no public URL needed)
- [x] Monitor configured channels for links (same URL detection logic)
- [x] Monitor for image uploads (download via Slack Files API with auth)
- [x] Send to Agent API `/parse` with `org_id` from channel->org mapping
- [x] Format event replies using Slack Block Kit (not Discord embeds)

#### 2b. Callback handling

- [x] Webhook server on configurable port (default 3001, separate from Discord's 3000)
- [x] Receive agent callbacks, update Slack messages (edit, not delete+recreate)
- [ ] Track requests in SQLite (reuse schema pattern from Discord, with `platform` column)

#### 2c. Editorial replies

- [ ] Detect threaded replies to bot event messages
- [ ] Update Grist editorial field via org-specific Grist credentials
- [ ] Confirm update with reaction or reply

#### Tests

- [x] Unit tests for Slack message formatting (Block Kit output)
- [x] Unit tests for URL/image detection in Slack messages
- [ ] Mock agent callback tests

### Phase 3: Discord Bot Updates

Minimal changes to keep ORB working with the new org-aware agent.

- [x] Update Discord bot to send `org_id: "orb"` and `client_reference_id` (was `discord_message_id`)
- [ ] Read org config to get Grist credentials (stop using separate `GRIST_API_KEY` env var)
- [x] Verify all existing functionality unchanged (editorial replies, calendar export)
- [x] Calendar export stays ORB-only for now

---

## Acceptance Criteria

### Functional

- [ ] ORB Discord bot continues working identically (no behavior changes)
- [ ] Org #2 can post links in Slack and receive parsed events
- [ ] Events save to the correct org's Grist doc
- [ ] Grist record URLs point to the correct org's doc
- [ ] Agent `/health` shows configured orgs and their LLM provider status
- [ ] Agent `/scrape` accepts `org_id` and uses the correct LLM
- [ ] Config file validates on startup; clear errors for missing fields

### Non-Functional

- [ ] One org's LLM outage does not affect the other org
- [ ] Secrets are stored as env var references, not plaintext in YAML
- [ ] Adding a third org requires only a new YAML section + env vars (no code changes)

---

## Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Pleias model may not support structured JSON output reliably | OpenAI-compatible extractor includes JSON repair logic; fall back to lower confidence |
| HuggingFace cold starts (30+ sec for some models) | Longer timeout + retry for 503s; document warm-up requirements |
| Slack API rate limits on message updates | Use ephemeral "Parsing..." message, single edit for results |
| `discord_message_id` rename breaks deployed Discord bot | Deploy agent + Discord bot together; field defaults to backward-compat |
| Org config YAML accidentally committed with secrets | `.gitignore` the config file; env var substitution pattern |

## Open Questions (to resolve during implementation)

1. What specific Pleias/HuggingFace model and endpoint URL will Org #2 use?
2. Does Org #2 need image parsing? (If not, skip multimodal for OpenAI-compatible extractor)
3. Does Org #2 want the same Grist table schema, or different column names?
4. What Slack workspace and channels will Org #2 use?

## References

- Brainstorm: `docs/brainstorms/2026-02-05-multi-org-support-brainstorm.md`
- Platform evolution brainstorm: `docs/brainstorms/2026-02-05-platform-evolution-brainstorm.md`
- Existing plan (Phase 0-1 complete): `docs/plans/2026-02-05-feat-multi-tenant-platform-evolution-plan.md`
- LLM ABC: `agent/llm/base.py`
- Orchestrator DI point: `agent/scraper/orchestrator.py:14-16`
- Grist per-call overrides: `agent/integrations/grist.py:80-98`
- discord_message_id locations: `agent/core/schemas.py:94,137`, `agent/core/callback.py:12,19,39,47`
- Pleias on HuggingFace: https://huggingface.co/PleIAs
- Slack Bolt Python: https://slack.dev/bolt-python/
