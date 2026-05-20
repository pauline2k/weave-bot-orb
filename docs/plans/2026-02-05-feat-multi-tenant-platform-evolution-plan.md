---
title: "Scraping Quality & Bug Fixes"
type: feat
date: 2026-02-05
brainstorm: docs/brainstorms/2026-02-05-platform-evolution-brainstorm.md
approach: Bottom-Up Quality (Approach C) — Phase 0 + Phase 1 only
reviewed_by: DHH reviewer, Kieran Python reviewer, Code Simplicity reviewer
---

# Scraping Quality & Bug Fixes

Fix production bugs and make scraped event data trustworthy. Every change benefits ORB users immediately.

## Overview

The event scraping system works but has data quality issues (timezone bugs, year inference errors, incomplete field extraction) and a production data-loss bug (SQLite on ephemeral storage). This plan fixes what's broken and improves extraction quality — nothing speculative, nothing that requires demand that doesn't exist yet.

---

## Problem Statement

**Production bugs:**
- SQLite on Railway ephemeral storage — parse request tracking lost on every redeploy (`discord/src/database.py`)
- `datetime.now()` without timezone in 4 locations across 3 files — wrong during DST
- Hardcoded `timezone(timedelta(hours=-8))` in Grist formatting — wrong March through November (`agent/integrations/grist.py:63`)

**Quality gaps:**
- JSON-LD override only covers dates — misses authoritative venue/address/organizer data (`agent/scraper/orchestrator.py:17-46`)
- No post-extraction validation — obviously wrong dates (past events, end before start) are saved silently
- ORB-specific constants hardcoded in source files instead of config (`oaklog.getgrist.com`, `ORB-Events`, doc IDs)
- Zero automated tests — changes can't be verified without manual testing
- `GeminiExtractor` hardcoded in orchestrator constructor — one-line fix (`agent/scraper/orchestrator.py:14`)

**What works well (preserve these):**
- Agent/Discord split via HTTP + async callback
- Pydantic schemas with clear data contracts
- Fault-tolerant browser scraping (continues on timeout)
- JSON-LD date override pattern (extend it, don't replace it)
- LLM retry with exponential backoff

---

## Technical Approach

### Phase 0: Fix Production Bugs

#### 0.1 Fix SQLite Ephemeral Storage

Railway uses ephemeral filesystem by default. The Discord bot's SQLite database (`weave_bot.db`) is lost on every deploy, silently breaking editorial reply tracking.

- [x] Investigate Railway persistent volumes for SQLite
- [x] Add volume mount instructions to railway.toml
- [x] Add runtime warning when DB is not on persistent volume
- [ ] Verify `parse_requests` data survives redeploys (requires Railway deploy)
- [ ] Verify editorial reply feature works after redeploy (requires Railway deploy)

**Success criteria:** Database persists across Railway deploys.
**Files:** `discord/src/database.py`

#### 0.2 Add Minimal Test Infrastructure

Just enough to catch regressions during Phase 1 changes. Not a comprehensive suite.

- [x] Add pytest to agent dependencies (`agent/requirements.txt`)
- [x] Create `agent/tests/conftest.py` with:
  - Mock `LLMExtractor` returning canned `Event` data (makes the existing ABC useful for testing)
  - Lazy/injectable `Settings` so tests don't need `.env` — wrap `settings = Settings()` in `@lru_cache` function (`agent/core/config.py:39`)
- [x] Write unit tests for pure functions:
  - `_apply_json_ld_dates()` with known JSON-LD input → correct datetime output
  - `_format_datetime()` and `_event_to_grist_fields()` with known Event → correct Grist payload
- [x] Write one integration test: POST to `/scrape` with mock extractor, validate response matches `ScrapeResponse` schema
- [x] Create `agent/core/time_utils.py` with `get_current_time() -> datetime` returning timezone-aware Pacific time — makes time injectable for deterministic tests

**Success criteria:** `pytest agent/tests/` passes. Pure function tests cover the code being changed in Phase 1.
**Files:** `agent/tests/conftest.py`, `agent/tests/test_json_ld.py`, `agent/tests/test_grist_fields.py`, `agent/tests/test_scrape.py`, `agent/core/config.py`, `agent/core/time_utils.py`

---

### Phase 1: Scraping Quality

#### 1.1 Timezone Handling (ZoneInfo, DST-aware)

Replace all hardcoded timezone offsets with `ZoneInfo("America/Los_Angeles")` for automatic DST handling.

- [x] Replace `datetime.now()` with `get_current_time()` (from 0.2) in LLM prompt generation (`agent/llm/gemini.py:35-36`, `agent/llm/gemini.py:238-239`)
- [x] Replace `timezone(timedelta(hours=-8))` with `get_current_time()` in Grist CreatedAt formatting (`agent/integrations/grist.py:63`)
- [x] Update LLM prompt to derive the correct offset from `get_pacific_offset_str()` — PDT `-07:00` (Mar-Nov) or PST `-08:00` (Nov-Mar)
- [x] Test: `test_time_utils.py` verifies offset format is -07:00 or -08:00

**Success criteria:** Events scraped during PDT months show correct times. `CreatedAt` in Grist is always Pacific Time regardless of DST.
**Files:** `agent/llm/gemini.py`, `agent/integrations/grist.py`, `agent/core/time_utils.py`

#### 1.2 Post-Extraction Date Validation

Add a validation step after JSON-LD override in the orchestrator pipeline. Validation warns but never rejects — lowers confidence and adds extraction notes.

- [x] Add `validate_event()` function in `agent/core/validation.py`
- [x] Validation rules:
  - `start_datetime` not more than 1 year in the past
  - `start_datetime` not more than 2 years in the future
  - `end_datetime > start_datetime` (if both present)
  - If `end_datetime < start_datetime`: null out `end_datetime`, add extraction note
  - If `title` is empty or "Extraction Failed": flag, lower confidence
- [x] Call validation after JSON-LD override in orchestrator pipeline
- [x] Test: 10 validation tests covering all rules, edge cases, and confidence floor

**Success criteria:** No events saved with obviously wrong years. Validation warnings visible in `extraction_notes`.
**Files:** `agent/scraper/orchestrator.py` (or `agent/core/validation.py`)

#### 1.3 Expand JSON-LD Field Overrides

Currently only dates are overridden from JSON-LD structured data. Extend to venue, address, and organizer — the same fields Eventbrite and Luma provide reliably.

- [x] Rename `_apply_json_ld_dates()` to `_apply_json_ld_overrides()` in `agent/scraper/orchestrator.py:17-46`
- [x] Add venue override: if JSON-LD `location.name` exists and is not empty/generic, override `event.location.venue`
- [x] Add address override: parse JSON-LD `location.address` — handle both plain string and `PostalAddress` object with `streetAddress`, `addressLocality`, etc.
- [x] Add organizer override: if JSON-LD `organizer.name` exists, override `event.organizer.name`
- [x] Only override when JSON-LD value is substantive (not empty, not just the org/site name)
- [x] Add extraction note when override happens: e.g., "Venue overridden from JSON-LD structured data"
- [x] Test: Eventbrite page gets correct venue/address from JSON-LD; site without JSON-LD is unaffected

**Success criteria:** Events from Eventbrite and Luma get authoritative venue/address from JSON-LD. No regressions on sites without JSON-LD.
**Files:** `agent/scraper/orchestrator.py`, `agent/scraper/processor.py`

---

### Cleanup: Config Hygiene

Small changes that reduce coupling without introducing abstractions.

- [x] Move ORB-specific constants to `.env` config instead of hardcoded in source:
  - `oaklog.getgrist.com` → `GRIST_UI_HOST` in `agent/integrations/grist.py:18`
  - `ORB-Events` → `GRIST_UI_PAGE_NAME` in `agent/integrations/grist.py:19`
  - `b2r9qYM2Lr9x` (UI doc ID) → `GRIST_UI_DOC_ID` in `agent/integrations/grist.py:17`
- [x] Pass `LLMExtractor` as constructor parameter to `ScrapingOrchestrator` instead of hardcoding `GeminiExtractor()` at `agent/scraper/orchestrator.py:14` — one-line change, makes testing easier
- [x] Deduplicate the retry/JSON-repair logic between `extract_event()` and `extract_event_from_image()` in `agent/llm/gemini.py` — extract shared logic into private methods on `GeminiExtractor`

**Files:** `agent/integrations/grist.py`, `agent/core/config.py`, `agent/scraper/orchestrator.py`, `agent/llm/gemini.py`

---

## Acceptance Criteria

- [ ] SQLite database persists across Railway deploys (requires Railway deploy to verify)
- [x] `pytest agent/tests/` passes with unit + integration tests (47 tests)
- [x] Events scraped during PDT months show correct Pacific times
- [x] Events near year boundaries (Dec→Jan) infer the correct year
- [x] Post-extraction validation catches bad dates without rejecting events
- [x] JSON-LD overrides venue/address/organizer from Eventbrite and Luma
- [ ] All existing ORB Discord bot features work unchanged (requires manual testing)
- [ ] No regressions on tested platforms (requires live scrape testing)
- [x] ORB-specific constants configurable via `.env`, not hardcoded

---

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Timezone change breaks correct behavior during PST months | Medium | Transition logging comparing old vs new offset. Test DST boundaries before removing old code. |
| Validation too strict, rejects previously-accepted events | Medium | Validation only lowers confidence + adds notes. Never rejects. Test against real scrape results. |
| JSON-LD override uses generic org address instead of event venue | Medium | Only override when value is substantive and different from site/org name. Log overrides. |
| SQLite → Postgres migration breaks request tracking | Medium | Back up existing SQLite before migration. Test editorial reply flow after migration. |
| Changing `datetime.now()` calls affects prompt wording | Low | `get_current_time()` returns the same data, just timezone-aware. Compare prompt output before/after. |

---

## What This Plan Does NOT Include (and Why)

Based on review feedback from DHH, Kieran, and Simplicity reviewers, the following items from the original brainstorm are **deferred until there is real demand:**

| Deferred Item | Trigger to Revisit |
|---------------|-------------------|
| `EventStore` ABC / storage abstraction | A second org needs a non-Grist backend |
| LLM provider config (OpenAI, Claude) | You want to try a different LLM provider |
| Event edit web form | Users report they can't edit events (Grist link already works) |
| Chat adapter abstraction / Slack | A Slack user asks for integration |
| `discord_message_id` → `client_reference_id` rename | A second chat platform is being built |
| Newsletter template engine | A second org with different formatting needs appears |
| Per-field confidence scoring | A concrete use case for per-field data emerges |
| Org onboarding / auth / analytics | 3+ orgs are using the system and manual setup is painful |

The brainstorm at `docs/brainstorms/2026-02-05-platform-evolution-brainstorm.md` preserves the full vision. This plan executes only what is needed now.

---

## References

### Files Being Modified

| File | Changes |
|------|---------|
| `discord/src/database.py` | Persistence fix (volume or Postgres migration) |
| `agent/core/config.py` | Add Grist UI config vars, make Settings injectable |
| `agent/core/time_utils.py` | New: `get_current_time()` utility |
| `agent/llm/gemini.py` | Use `get_current_time()`, deduplicate retry logic |
| `agent/integrations/grist.py` | ZoneInfo for CreatedAt, move constants to config |
| `agent/scraper/orchestrator.py` | Expand JSON-LD overrides, add validation step, accept extractor param |
| `agent/scraper/processor.py` | Potentially expose more JSON-LD fields |
| `agent/tests/*` | New: test infrastructure |

### Relevant Commits

- `ce0ce47` — Use Pacific Time for CreatedAt field in Grist
- `d26ba40` — Strip timezone from datetimes sent to Grist
- `9a3f5fd` — Fix year inference and timezone handling in LLM prompts
- `0e3fac7` — Fix Grist URL section ID (s1 -> s4)
- `f5c5b6f` — Add image parsing support for event posters and flyers

### Platform Compatibility (test targets)

| Platform   | Score | JSON-LD | Notes |
|------------|-------|---------|-------|
| Eventbrite | 0.95  | Yes     | Excellent structured data |
| Luma       | 0.90  | Yes     | JSON-LD override critical for dates |
| BAMPFA     | 0.90  | Varies  | Works well |
| UCB Events | 0.95  | Yes     | Works well |
| Instagram  | 0.85  | No      | Needs screenshot/image parsing |
| Meetup     | N/A   | N/A     | Auth wall — requires login |
