---
phase: 27-prompt-optimizer-unified-prompt-management
plan: 02
subsystem: api
tags: [mcp, prompt-optimizer, docker, fastapi, azure-openai, streamable-http]

requires:
  - phase: 27-prompt-optimizer-unified-prompt-management
    provides: "Plan 27-01 prompt registry (defaults + get_prompt)"
provides:
  - prompt-optimizer sidecar in docker-compose (internal-only, Azure /v1 custom provider)
  - optimize_prompt() MCP Streamable-HTTP client (system|user|iterate)
  - stateless POST /api/v1/prompts/optimize endpoint (admin-only, no DB writes)
affects: [27-04, 27-05, 27-06]

tech-stack:
  added: [mcp>=1.0, "linshen/prompt-optimizer:2.11.7 sidecar"]
  patterns:
    - "Optimizer reached via MCP streamablehttp_client + ClientSession (initialize -> call_tool)"
    - "Stateless optimize endpoint: returns optimized text, persistence deferred to 27-04"
    - "Upstream MCP failures wrapped as AppException(502), never leaked as 500 stacktraces"

key-files:
  created:
    - backend/app/services/prompt_optimizer_client.py
    - backend/app/api/prompts.py
    - backend/tests/test_prompt_optimizer_client.py
    - backend/tests/test_prompts_optimize_api.py
  modified:
    - docker-compose.yml
    - backend/pyproject.toml
    - backend/app/config.py
    - backend/app/api/__init__.py
    - backend/app/main.py

key-decisions:
  - "Endpoint strategy: direct Azure OpenAI /v1 (custom provider) approved at checkpoint (approved: direct-v1)"
  - "Sidecar is internal-only (expose, no published port); AGPL image used unmodified as a separate network service"
  - "optimize endpoint takes no db dependency at all to guarantee no persistence"

patterns-established:
  - "MCP mode->tool map: system->optimize-system-prompt, user->optimize-user-prompt, iterate->iterate-prompt"
  - "PromptOptimizerError raised by client; converted to AppException(502, PROMPT_OPTIMIZER_ERROR) at the API boundary"

requirements-completed: [PROMPT-01, PROMPT-03]

duration: ~25min
completed: 2026-07-01
---

# Phase 27 Plan 02: Prompt Optimizer Integration Summary

**prompt-optimizer sidecar + MCP client and a stateless admin-only `POST /api/v1/prompts/optimize` endpoint (system/user/iterate), validated against Azure OpenAI `/v1`.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 auto + 1 checkpoint (approved: direct-v1)
- **Files created:** 4
- **Files modified:** 5

## Accomplishments
- Internal-only `prompt-optimizer` sidecar in docker-compose (pinned `2.11.7`, `/healthz` healthcheck, Azure `/v1` custom provider from env)
- `optimize_prompt()` MCP Streamable-HTTP client mapping the three optimize modes to optimizer tools, with structured error handling
- Stateless `POST /api/v1/prompts/optimize` endpoint (admin-only) returning optimized text with **no DB writes**
- Checkpoint validated: Azure `/v1` direct connectivity approved
- 15 unit tests, 100% coverage on `prompt_optimizer_client.py` + `prompts.py`

## Task Commits

1. **Task 1: Sidecar + MCP client** - `20022d1` (feat)
2. **Checkpoint: Azure /v1 connectivity + AGPL sign-off** - approved `direct-v1` (no commit)
3. **Task 2 RED: failing tests** - `c08b37b` (test)
4. **Task 2 GREEN: optimize endpoint + registration** - `235b2b7` (feat)

## Files Created/Modified
- `backend/app/services/prompt_optimizer_client.py` - `optimize_prompt()` MCP client + `PromptOptimizerError`
- `backend/app/api/prompts.py` - `POST /prompts/optimize` (admin-only, stateless)
- `backend/app/api/__init__.py` - export `prompts_router`
- `backend/app/main.py` - import + register `prompts_router`
- `docker-compose.yml` - internal `prompt-optimizer` sidecar
- `backend/pyproject.toml` - add `mcp>=1.0`
- `backend/app/config.py` - `PROMPT_OPTIMIZER_MCP_URL` + timeout
- `backend/tests/test_prompt_optimizer_client.py` - 8 client tests
- `backend/tests/test_prompts_optimize_api.py` - 7 endpoint tests

## Decisions Made
- **Endpoint strategy = direct Azure `/v1`** (approved at checkpoint). LiteLLM proxy remains the documented fallback in `27-RESEARCH.md` if a region's Azure `/v1` support lags.
- Endpoint deliberately omits any `db` dependency so it cannot persist.

## Deviations from Plan
None - plan executed as written (Task 1 auto, checkpoint approved, Task 2 TDD RED→GREEN).

## Issues Encountered
- One test file needed `ruff format` after the RED commit; reformatted in the GREEN commit. No behavior change.

## User Setup Required
Running the optimizer requires environment configuration (only needed to actually execute optimizations):
- `AZURE_OPENAI_API_KEY`, `AOAI_DEPLOYMENT`, and `VITE_CUSTOM_API_BASE_URL` (an Azure OpenAI `/v1` endpoint) exported before `docker compose up -d prompt-optimizer`.

## Next Phase Readiness
- `optimize_prompt()` and the optimize endpoint are ready for 27-04 to record optimization runs (`PromptOptimizationRun`) and adopt results as new versions.
- **Circular-import reminder (for 27-03):** modules that will call `get_prompt` (scoring_engine, skill_conversion_service, dry_run_engine) must import it lazily inside functions.

## Self-Check: PASSED

All 5 claimed files exist; commits 20022d1, c08b37b, 235b2b7 exist in git history.
