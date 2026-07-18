---
task: 260718-cy6
title: Agents API Skills/Toolbox POC — fix via Foundry-Features preview header + Entra ID
tags: [azure-ai-foundry, skills-api, toolbox, agents-api, azure-ai-projects, entra-id]
requires: [260717-x5f, 260718-b3q]
provides: [agents-api-skills-path-fixed, doc-10-section-12]
tech-stack:
  added: []
  upgraded: [azure-ai-projects@2.1.0 -> 2.3.0]
key-files:
  created: []
  modified:
    - docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py
    - backend/pyproject.toml
    - docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md
decisions:
  - "405 Method Not Allowed on the Agents API skills path was a missing Foundry-Features: Skills=V1Preview preview opt-in header, not a real Entra ID auth/RBAC rejection."
  - "azure-ai-projects 2.3.0's BetaOperations auto-injects the Foundry-Features header for beta.skills calls via an internal _OperationMethodHeaderProxy; toolboxes (now top-level, not under beta) still needs it attached manually."
  - "The YAML folded block scalar (description: >-) frontmatter parsing bug found on the Responses API path (quick task 260718-b3q) does NOT reproduce on the Agents API path — same real SKILL.md, ZIP upload succeeded on the first attempt."
  - "MCP endpoint discovery for toolboxes remains a genuine, unresolved API-shape gap (405 after supplying the required api-version query param) — recorded as a real FAIL, not softened."
metrics:
  duration: ~90m
  completed: 2026-07-18
---

# Quick Task 260718-cy6: Agents API Skills/Toolbox POC — Foundry-Features Header Fix Summary

Root-caused and fixed the Agents API Skills/Toolbox POC that was previously fully blocked (quick task 260717-x5f) by identifying a missing `Foundry-Features: Skills=V1Preview` preview opt-in header — not a real Entra ID authentication rejection as the earlier 405 suggested.

## What Was Built

**Task 1 — Script fix (`docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`, `backend/pyproject.toml`)**

- Upgraded `azure-ai-projects` from 2.1.0 to 2.3.0 in the real `backend/.venv` and updated the `pyproject.toml` floor constraint to `>=2.3.0`.
- Rewrote the POC script end-to-end against the real installed SDK 2.3.0 shapes, verified via live introspection (not blind trust in any single doc source):
  - `skills.create_from_package` was removed; replaced with `skills.create_from_files(name, CreateSkillVersionFromFilesBody(files=[...]))`.
  - Inline skill creation now requires `inline_content=SkillInlineContent(description=..., instructions=..., metadata=...)`.
  - `toolboxes` moved from `client.beta.toolboxes` to top-level `client.toolboxes`, and gained a typed `skills: Optional[list[ToolboxSkill]]` kwarg (used via `ToolboxSkillReference(name=...)`).
  - Manual `Foundry-Features: Skills=V1Preview` header attached to every beta.skills/toolboxes call, on top of the SDK's own automatic injection for `beta.skills` (confirmed via introspecting `azure.ai.projects.operations._patch`), to isolate the header-hypothesis variable.
  - Entra ID (`DefaultAzureCredential`) as the sole/primary auth path; one quick API-Key re-confirmation retained at the top of Test 3 (still 403 `AuthenticationTypeDisabled`, as expected).
  - Frontmatter A/B fallback logic for ZIP upload (never triggered — see below).
  - Real agent-consumes-skill acceptance test (Test 8) reusing the project's existing `agent_reference` invocation pattern from `backend/app/services/agent_chat_service.py`.
  - MCP endpoint discovery: SDK-object field inspection, then convention-based REST probing (iterated once to add the required `api-version` query param after a helpful 400 response), then JSON-RPC `resources/list`/`resources/read` (never reached — see Test 7 result below).
  - Cleanup in dependency order (Agent -> Toolbox Version -> Toolbox -> Skill(s)), each step wrapped in its own try/except; hardened to recognize the real observed cascading-delete-on-last-version 404 as expected, not a failure.

**Task 2 — Doc update (`docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md`)**

- Added new section 12 ("Agents API 路径修复后实测（Foundry-Features 预览头 + Entra ID）") documenting the real, verbatim script output: 11 subsections covering the hypothesis/root-cause, SDK version diff table, and per-test real PASS/FAIL results (Tests 3-8), full terminal output summary, and conclusion.
- Added an 8th bullet to the top 结论速查 list pointing to section 12's correction.
- `README.md`'s doc-10 index row was checked and left unchanged — its existing description is broad enough that it still accurately reflects doc 10's content after the fix.

## Real Test Results (final run against `avarda-demo-prj`)

```
Test 1: Validate Skill Frontmatter                  [PASS]
Test 2: Package Skill as ZIP                        [PASS]
Test 3: Foundry-Features Hypothesis + Inline Upload  [PASS]  405 gone, Entra ID + header works
Test 4: ZIP Upload (create_from_files)               [PASS]  succeeded on first attempt, no A/B fallback triggered
Test 5: Get/List/Download Roundtrip                  [PASS]
Test 6: Toolbox Version + Skill Mount                [PASS]  typed skills kwarg worked on first attempt
Test 7: MCP Endpoint Discovery                       [FAIL]  405 Method Not Allowed (real API-shape gap, not a script bug)
Test 8: Agent Consumes Skill (Acceptance)            [PASS]  real completion text confirms skill content reached the model

Total: 7 passed, 1 failed, 0 skipped
```

Post-run verification confirmed no orphaned POC resources remain in the Foundry project (`skills.list()`/`toolboxes.list()`/`agents.list()` all empty of POC names).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Script executed against the wrong (main repo) copy of the file on the first run attempt**
- **Found during:** First real script execution attempt
- **Issue:** Running `cd backend && .venv/bin/python3 ../docs/.../test_skill_foundry_upload.py` from the *main repo's* backend directory resolved the relative script path to the main repo's (old, un-rewritten) copy of the script, not the worktree's edited copy — producing output that didn't match the rewritten script's test names at all.
- **Fix:** Diagnosed via comparing printed test headers against the file's actual `print_header` calls; switched to invoking the worktree's script by absolute path while still using the main repo's `.venv` and pre-exported `backend/.env` variables (since `python-dotenv`'s `load_dotenv` does not override already-set env vars, this is safe regardless of which `backend_dir` the script resolves relative to its own `__file__`).
- **Files modified:** None (execution-invocation fix only)
- **Commit:** N/A (no file change)

**2. [Rule 1 - Bug] MCP endpoint probe missing required `api-version` query parameter**
- **Found during:** Test 7 (MCP endpoint discovery), first real run
- **Issue:** The first probe attempt (no query params) returned `400 BadRequest: Missing required query parameter: api-version`, meaning the probe itself was malformed, not that the endpoint was absent.
- **Fix:** Introspected `client.toolboxes._config.api_version` (`"v1"`) and added it as a query parameter to both candidate probe URLs. Re-ran; both candidates then returned `405 Method Not Allowed` (empty body) — a real, confirmed API-shape gap (the route prefix exists, since 400/405 rather than 404, but `GET .../mcp` is not the correct access pattern on this resource/SDK version). Iteration stopped here per plan instruction not to invent or soften results.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`
- **Commit:** a736920

**3. [Rule 1 - Bug] Cleanup reported a spurious FAIL for an expected cascading delete**
- **Found during:** Cleanup step, first real run
- **Issue:** `toolboxes.delete(name)` returned `404 not_found` immediately after `toolboxes.delete_version(name, version)` succeeded, because deleting the toolbox's only version appears to cascade-delete the toolbox itself on this resource. This is expected/benign behavior but was being reported as a `[FAIL]`.
- **Fix:** Updated `cleanup()` to detect a 404/not_found response on the toolbox delete step and log it as an informational "already removed via cascading delete" message instead of a failure.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`
- **Commit:** a736920

**4. [Rule 1 - Bug] Dead-code fragment in the single-line-description A/B helper**
- **Found during:** Pre-execution review of the previously-drafted script
- **Issue:** `_zip_bytes_root_layout_singleline` contained a confusing, dead `post.content_delimiter if False else ...` ternary left over from drafting (not a runtime bug — Python's lazy conditional evaluation meant `post.content_delimiter` was never accessed — but confusing for future readers).
- **Fix:** Simplified to `" ".join(post.metadata["description"].split())`.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`
- **Commit:** a736920

## Auth Gates

None — Entra ID (`DefaultAzureCredential`, existing `az login` session) worked throughout; the one API-Key re-confirmation attempt in Test 3 failed as expected (`403 AuthenticationTypeDisabled`), consistent with prior findings, and was not treated as a blocking gate.

## Known Stubs

None. All eight tests exercise real Azure API calls; no hardcoded/mocked data paths were introduced.

## Threat Flags

None. This is a POC test script exercising existing preview API surfaces (Skills, Toolboxes, Agents) already documented as in-scope in doc 08/10; no new production endpoints, auth paths, or schema changes were introduced.

## Self-Check: PASSED

- `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py` — FOUND (modified, committed at a736920)
- `backend/pyproject.toml` — FOUND (modified, committed at a736920)
- `docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md` — FOUND (modified, committed at 5380e05)
- Commit a736920 — FOUND (`git log --oneline` confirms)
- Commit 5380e05 — FOUND (`git log --oneline` confirms)
- No orphaned Foundry resources — CONFIRMED via post-run `list()` checks on skills/toolboxes/agents
