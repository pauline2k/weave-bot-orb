# Platform Evolution Brainstorm

**Date:** 2026-02-05
**Status:** Explored
**Approach chosen:** Bottom-Up Quality (Approach C)

---

## What We're Building

Evolving weave-bot-orb from an ORB-specific event scraping tool into a multi-tenant hosted platform that any community (local newsletters, nonprofits, individual curators, developer friends) can use for event discovery and curation.

### Target Users
- Other local newsletters (like ORB in other cities)
- Community organizations (nonprofits, mutual aid)
- Individual curators maintaining event lists
- Developer friends who'd customize and extend

### Deployment Model
Hosted multi-tenant — one running instance, each org gets their own configuration for storage, AI provider, and chat integration.

---

## Why Bottom-Up Quality First

We chose to fix scraping quality and build abstractions incrementally rather than building a plugin architecture or web UI upfront. Rationale:

- **Trust is the product.** If scraped data is wrong, nothing else matters. Year/timezone bugs and missing fields erode confidence.
- **Each step ships independently.** Quality fixes benefit current ORB users immediately while laying groundwork for multi-tenancy.
- **Abstractions emerge from real needs.** Building storage/LLM interfaces after fixing quality means we understand what the interfaces actually need to support.
- **No wasted work.** Every improvement compounds — better scraping means less need for the edit UI, cleaner data means better newsletters.

---

## Key Decisions

### 1. Scraping Quality (First Priority)

**Year/timezone bugs:**
- Replace `datetime.now()` with timezone-aware `datetime.now(ZoneInfo("America/Los_Angeles"))` in LLM prompt generation
- Replace hardcoded `timedelta(hours=-8)` with `ZoneInfo` for proper DST handling
- Add a post-extraction validation layer that sanity-checks dates (not in past by >1 year, not >2 years in future, end > start)

**Missing fields:**
- Add a structured validation step after LLM extraction that flags low-confidence or empty required fields
- Consider a second LLM pass focused specifically on missing fields (targeted re-extraction)
- Improve content preprocessing — some fields are missed because the relevant content gets truncated or lost in HTML cleaning

**Wrong interpretation:**
- Add JSON-LD field-level overrides beyond just dates (venue, address, organizer when available in structured data)
- Consider confidence scoring per field, not just per event
- Add site-specific extraction hints (e.g., known CSS selectors for common platforms)

### 2. Abstraction Layer (Second Priority — All Four Together)

These are independent enough to work on in parallel as one milestone:

**Storage abstraction:**
- Create an `EventStore` interface with `save_event()`, `update_event()`, `list_events()`, `get_event()`
- Current Grist code becomes `GristEventStore`
- Consolidate the two separate Grist clients (agent + Discord bot) into one
- New backends: Airtable, Postgres, Notion as demand arises

**LLM abstraction:**
- Complete the `LLMExtractor` ABC (add `extract_event_from_image`)
- Make provider configurable via settings (`llm_provider: gemini | openai | anthropic`)
- Use dependency injection in orchestrator instead of hardcoded `GeminiExtractor()`
- Make `gemini_api_key` optional (only required if Gemini is selected)

**Event edit web form:**
- Simple web page per event (linked from chat message and storage)
- Shows all parsed fields in editable form
- Saves corrections back through the storage abstraction
- No auth needed initially (security through obscurity via unique URLs), add org-level auth later

**Chat adapter (Slack):**
- Rename `discord_message_id` to `client_reference_id` in schemas
- Create a chat adapter interface for sending/receiving messages
- Discord bot becomes `DiscordAdapter`
- Build `SlackAdapter` as the second implementation to prove the abstraction

### 3. Newsletter Templates (Third Priority)

- Per-org template configuration (grouping logic, visual style, tone)
- Web-based template builder/previewer
- Output formats: email HTML, markdown, plain text
- Builds on top of the storage abstraction (reads from EventStore)

---

## Open Questions

1. **Auth model for multi-tenancy:** How do orgs sign up? API keys? OAuth? Keep it simple with invite codes initially?
2. **Pricing:** Free tier + paid for high volume? Fully free/open source with hosted option?
3. **Event deduplication:** Multiple orgs in the same city will scrape the same events. Share data across orgs or keep isolated?
4. **Newsletter generation AI:** Use the same LLM abstraction as scraping, or a separate content-generation pipeline?
5. **Existing data migration:** How do current ORB events in Grist transition if/when storage backend changes?

---

## Incremental Roadmap

```
Phase 1: Scraping Quality
  - Fix timezone handling (ZoneInfo, DST-aware)
  - Fix year inference (validation layer, not just prompting)
  - Add post-extraction validation
  - Expand JSON-LD field overrides
  - Add confidence scoring per field

Phase 2: Multi-Tenant Foundation (parallel tracks)
  - Storage abstraction (EventStore interface)
  - LLM abstraction (complete ABC, DI, config-driven)
  - Event edit web form (per-event URL)
  - Chat adapter abstraction (Discord + Slack)

Phase 3: Content & Templates
  - Newsletter template system
  - Per-org template configuration
  - Template builder UI

Phase 4: Platform Polish
  - Org onboarding flow
  - Auth and access control
  - Event deduplication
  - Usage analytics
```

---

## Current Architecture Observations

**Good foundations:**
- Agent/Discord split is already sound — agent is a standalone API
- `LLMExtractor` ABC exists (needs completing)
- Callback pattern enables loose coupling between agent and consumers
- JSON-LD date override is a pragmatic quality pattern to extend

**Needs work:**
- Grist is hardcoded in 4+ files across both components (highest coupling)
- Two separate Grist API clients exist (agent + Discord bot)
- `GeminiExtractor` hardcoded in orchestrator constructor
- `datetime.now()` used without timezone awareness
- PST hardcoded as `-8` (wrong during DST)
- No post-extraction validation layer
- No test suite for the agent component
- `discord_message_id` in agent schemas leaks Discord-specific naming
