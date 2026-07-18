---
task: 260718-eha
title: Fix 17 failing voice_live backend tests (az login decoupling + Entra bearer + stale assertions)
tags: [pytest, voice-live, azure-entra-id, defaultazurecredential, test-hygiene]
requires: []
provides: [voice-live-tests-green-local]
tech-stack:
  added: []
  upgraded: []
key-files:
  created: []
  modified:
    - backend/tests/test_voice_live.py
    - backend/tests/test_voice_live_service.py
    - backend/tests/test_voice_live_websocket.py
decisions:
  - "All fixes are test-side only — zero production code changes (git diff backend/app/ empty). The production DefaultAzureCredential fallback and bearer-mode-when-no-key designs are intentional and were left untouched."
  - "Category 1 (2 tests): patch the Entra fallback helper (_get_bearer_token → None) so connection-tester no-key tests are deterministic regardless of the local az login session."
  - "Category 2 (8 real tests): direct-SDK wss tests swapped from api-key to DefaultAzureCredential (resource ai-foundary-hu-sweden-central2 has key auth disabled by policy); handler-level tests redirected to no-key DB seeding to drive the existing keyless/bearer fallback; the dead STS key-exchange test now asserts the real 403 AuthenticationTypeDisabled policy response instead of a bearer token."
  - "Category 3 (7 tests): assertions updated to the post-22866fd service design (no-key = bearer mode with masked token, endpoint-alone availability, agent-mode connect flow); mock_sdk fixture gained an azure.identity.aio stub which let classic agent-mode tests actually reach connect() again."
metrics:
  duration: ~55m (executor) + on-main re-verification
  completed: 2026-07-18
---

# Quick Task 260718-eha: Fix 17 Failing voice_live Tests Summary

Fixed all 17 locally-failing voice_live tests across three files. Root causes were pre-diagnosed by the orchestrator (none related to the azure-ai-projects 2.3.0 upgrade): 2 tests coupled to the local `az login` session, 8 real-Azure tests using api-key auth against a resource with key auth disabled (`AuthenticationTypeDisabled`), and 7 credential-gated tests with assertions stale against the June-3 (`22866fd`) service redesign (no-key = bearer mode, token always masked).

## Commits

- `f6021bd` fix(quick-260718-eha): make connection_tester no-key tests deterministic
- `adc2f1d` fix(quick-260718-eha): correct stale assertions and real STS 403 expectation
- `fb121fa` fix(quick-260718-eha): fix mock_sdk azure.identity stub and Category-2 credential swaps
- Merged to main at `f0783b1`.

## Real Test Results (verbatim)

Executor (worktree, real .env + az login):
- Three target files together: **152 passed, 0 failed** (baseline: 135 passed / 17 failed)
- Full backend suite: `1 failed, 2551 passed, 14 skipped, 27 deselected in 765.68s` — the 1 failure (`test_real_connect_model_mode_session_config_accepted`, live-Azure network test) re-verified passing in isolation (`1 passed in 4.91s`) and in the combined 152/152 run immediately after → transient real-network flakiness, not a regression. Count math checks: baseline 2535+17=2552 = post-fix 2551+1.
- `ruff check` / `ruff format --check`: clean
- `git diff --stat backend/app/`: empty — zero production changes

Orchestrator re-verification on merged main (`f0783b1`):
- `pytest tests/test_voice_live.py tests/test_voice_live_service.py tests/test_voice_live_websocket.py` → **152 passed in 107.83s**
- Full-suite regression run on main: see final orchestrator report (run after this SUMMARY was written).

## Deviations from Plan

**1. [Rule 1 - Bug] 3 stale `project_name == "default"` assertions surfaced only after the mock_sdk fixture fix**
- Once the `azure.identity.aio` stub let agent-mode `connect()` actually execute for the first time, three assertions comparing against `"default"` failed; corrected to `REAL_FOUNDRY_PROJECT` matching the existing convention in the same file.

**2. [Process] Worktree branch was based on `e43b86c` instead of expected `da366500`**
- EnterWorktree created the branch from a stale ref (known issue). Executor flagged it and did not reset (work was already committed). Orchestrator reviewed: the missing commits (260718-cy6 docs + pyproject floor bump) do not overlap the three test files; merge to main was clean (ort strategy, no conflicts).

**3. [Process] SUMMARY.md was lost with worktree removal and reconstructed by the orchestrator**
- Per constraints the executor left SUMMARY.md uncommitted; the forced worktree cleanup deleted it. This file is a faithful reconstruction from the executor's verbatim final report plus orchestrator re-verification.

## Known Stubs

None in production code. Test-side: `mock_sdk` fixture now stubs `azure.identity.aio` (test infrastructure, clearly scoped to tests).

## Self-Check

- backend/tests/test_voice_live.py — modified, on main (f0783b1)
- backend/tests/test_voice_live_service.py — modified, on main (f0783b1)
- backend/tests/test_voice_live_websocket.py — modified, on main (f0783b1)
- Commits f6021bd / adc2f1d / fb121fa — in `git log`
- 152/152 re-verified on main: PASSED
