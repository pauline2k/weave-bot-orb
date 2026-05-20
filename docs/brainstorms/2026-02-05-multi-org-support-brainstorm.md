# Multi-Org Support Brainstorm

**Date:** 2026-02-05
**Status:** Decided — ready for planning

---

## What We're Building

Support a second organization on the same weave-bot-orb deployment, with different LLM (Plaias), chat platform (Slack), and potentially different storage — while keeping ORB's existing setup (Gemini + Discord + Grist) working unchanged.

## Why Now

- A second org has expressed interest in using the bot
- They want **Plaias** instead of Gemini (common crawl / ethical data sourcing concerns)
- They want **Slack** instead of Discord
- Storage is TBD but **Grist is probably fine** for now
- Timeline: next month or two — enough time to build it right

## Why This Approach (Middle Path)

We chose a middle path between full abstraction-first and quick-hack vertical slice:

1. **LLM abstraction is 80% done** — the `LLMExtractor` ABC exists with `extract_event()` and `extract_event_from_image()`. Adding a Plaias implementation is the natural next step.
2. **Slack adapter is bounded scope** — mirror the Discord bot's behavior (monitor channels for links, reply with parsed events, handle callbacks).
3. **Config-file-based org profiles** — avoid premature database complexity. A YAML/TOML file maps each org to their LLM provider, chat platform, storage backend, and channel IDs.
4. **Shared deployment** — one instance serves multiple orgs. Simpler to operate than separate deployments.

### What we rejected

- **Full abstraction first** — Over-engineering for 2 orgs. Build interfaces when we have 3+ consumers.
- **Quick vertical slice** — Would create tech debt that's harder to refactor than building the right seams now.

## Key Decisions

1. **LLM provider is per-org config**, not a global setting. ORB stays on Gemini, new org uses Plaias.
2. **Chat adapter pattern** — Slack bot mirrors Discord bot behavior. Shared webhook callback interface.
3. **Org config via file** (YAML or TOML), not a database. Can migrate to DB later if needed.
4. **Shared agent API** — both orgs hit the same `/scrape` and `/parse` endpoints. The org context determines which LLM to use.
5. **Storage stays Grist for now** — both orgs can use separate Grist docs. Abstract storage only when a third backend is needed.

## Implementation Order

1. **LLM abstraction + Plaias** — Complete the provider pattern, add Plaias extractor
2. **Org config system** — YAML-based org profiles that map org → LLM, chat, storage
3. **Slack adapter** — Bot that monitors Slack channels, sends to agent, formats replies
4. **Multi-org routing** — Agent API accepts org context, routes to correct LLM/storage

## Open Questions

- What is Plaias's API shape? Need to research their extraction API to understand how different it is from Gemini.
- Does the new org want the same event schema, or do they need different fields?
- How should org identity flow through the system? API key per org? Channel-based routing?
- Does the new org want Grist, or something else? If Grist, separate doc or shared doc with org column?
- Duplicate detection — should this be per-org or cross-org?

## Out of Scope (for now)

- Newsletter/template system (Phase 3 in the plan)
- Auth/onboarding UI (Phase 4)
- Per-field confidence scoring
- Event edit web form (Grist link works for now)
