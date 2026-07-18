---
phase: quick
plan: 01
subsystem: docs/microsoft-agent-framework
tags: [azure-openai, responses-api, skills-api, foundry, poc]
dependency-graph:
  requires: []
  provides:
    - "Empirical POC test script for the Azure OpenAI Responses API skills path (openai/v1, client.skills)"
    - "Doc 10 section 11 comparing Responses API path vs Agents API (beta.skills) path"
  affects:
    - "docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md"
    - "docs/microsoft-agent-framework/README.md"
tech-stack:
  added: []
  patterns:
    - "Plain openai SDK client construction against Azure via base_url={ENDPOINT}/openai/v1/, api_key=API Key then Entra ID (DefaultAzureCredential) fallback"
key-files:
  created:
    - docs/microsoft-agent-framework/tests/test_skill_responses_api.py
  modified:
    - docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md
    - docs/microsoft-agent-framework/README.md
decisions:
  - "Documented (did not fix) the server-side YAML folded-block-scalar frontmatter parsing limitation in containers.create() inline skills, since fixing it would require changing the production mr-training-creator/SKILL.md, which is out of scope for this POC task"
metrics:
  duration: "~35min"
  completed: "2026-07-18"
---

# Phase quick Plan 01: Responses API Skills Path POC Summary

Empirically tested the Azure OpenAI Responses API skills surface (`openai/v1`, plain `openai` SDK, `client.skills`) against the real `ai-foundary-hu-sweden-central2` Foundry resource and found it partially bypasses the `AuthenticationTypeDisabled` block that fully blocks the previously-documented Agents API (`beta.skills`) path — Entra ID succeeds for skill upload/version management here, while shell-tool mounting and inline base64 skills each hit independent, non-auth limitations.

## What Was Built

**Task 1 — POC script (`docs/microsoft-agent-framework/tests/test_skill_responses_api.py`)**

Following the exact style of `test_skill_foundry_upload.py` (print_header/print_result/print_info helpers, module-level constants, script-style `test_N_*()` functions, cached auth-mode client, `cleanup()` in `main()`'s `finally`), the script implements 6 tests:

1. `test_1_sdk_surface_discovery` — confirms `openai==2.29.0` exposes `client.skills`, `client.skills.versions`, `client.skills.content`, `client.containers`, and that `containers.create()` has a `skills` kwarg (all local, no network).
2. `test_2_package_skill_zip` — packages `mr-training-creator/` into an in-memory ZIP with a **single top-level folder** (`mr-training-creator/SKILL.md`), explicitly different from the ZIP-root layout used by the Agents API path, and checks the documented size/file-count/per-file-size limits.
3. `test_3_upload_skill` — `client.skills.create(files=...)`, API Key first, Entra ID fallback on 401/403.
4. `test_4_version_management` — `client.skills.versions.create()` for a second version, asserts `latest_version` increments.
5. `test_5_responses_shell_tool_mount` — `client.responses.create()` with a `shell` tool + `container_auto` environment + `skill_reference` pointing at the uploaded skill.
6. `test_6_inline_base64_skill` — `client.containers.create()` with an `inline` base64-ZIP skill, using name/description read from the real SKILL.md frontmatter (independent of whether test 3 succeeded).
7. `cleanup()` — deletes any created skill versions and skills in dependency order, each in its own try/except.

**Task 2 — Documentation (doc 10 section 11 + README.md)**

Added a full new section 11 「Responses API 路径（openai/v1）」to `10-agent-skills-foundry-upload-and-toolbox.md` with: overview/endpoint differences, SDK construction snippet, SDK-surface-discovery table, skill-upload table, version-management table, shell-tool-mount result with verbatim error, inline-skill result with verbatim error plus a root-cause investigation note, a limits table (including the "single top-level folder" vs "ZIP root" structural difference), a two-path comparison table, and a conclusion. Also corrected the top-of-doc "结论速查"/"概述" sections to clarify those earlier conclusions apply only to the Agents API path, and updated README.md's doc-10 index row description to mention the Responses API path.

## Real Test Results (actual run against `ai-foundary-hu-sweden-central2` / `avarda-demo-prj`, model `gpt-4o-mini`)

| Test | Result | Finding |
|------|--------|---------|
| 1. SDK Surface Discovery | PASS | `openai==2.29.0` exposes all expected resources locally |
| 2. Package Skill ZIP (single top-level folder) | PASS | 4633 bytes, 4 entries, well within limits |
| 3. Upload Skill | PASS (via Entra ID) | API Key → `403 AuthenticationTypeDisabled`; Entra ID (`DefaultAzureCredential`) → **success**, `skill_id=skill_6a5ac5436eb08190af323aba375ba68e01c5a41f271b146c`, `default_version=1`, `latest_version=1` |
| 4. Version Management | PASS | Second version upload via `skills.versions.create()` → `latest_version` went `1 → 2` |
| 5. Responses Shell Tool Mount | FAIL | `400`: `"Tool 'shell' is not supported with gpt-4o-mini-2024-07-18."` — a **model-deployment limitation**, not an auth/API limitation |
| 6. Inline Base64 ZIP Skill | FAIL | `400`: `"Inline skill name/description must match the values in SKILL.md/Skills.md front matter."` — root-caused (via a same-resource side probe, not counted as a numbered test) to the server-side frontmatter parser not handling the YAML folded block scalar `description: >-` used in the real `mr-training-creator/SKILL.md`; a minimal SKILL.md with a single-line plain-scalar description succeeded immediately |

**Total: 4 passed, 2 failed, 0 skipped (exit code 1 — genuine, documented findings, not script bugs).**

`cleanup()` deleted the created skill version and skill; verified via a follow-up `client.skills.list()` call that no orphaned skills remain in the Foundry project.

### Key finding for the user's specific question

**Yes, the Responses API path partially bypasses the 403 `AuthenticationTypeDisabled` seen on `beta.skills`** — but not via API Key (API Key is rejected identically, `403 AuthenticationTypeDisabled`, on both paths). The bypass is specifically that **Entra ID (`DefaultAzureCredential`) succeeds** on the Responses API's `client.skills.create()`/`client.skills.versions.create()`, whereas the same Entra ID fallback on the Agents API's `beta.skills.create()` failed with `405 Method Not Allowed` (a different failure mode entirely, per doc 10 section 8). So: skill upload + version management is a viable alternative on this resource via Entra ID; the two "consumption" sub-paths (shell-tool mount, inline base64 skill) each hit separate, independent, non-auth blockers (model deployment capability, and server-side YAML parsing, respectively).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed inline skill name/description mismatch in Task 6's initial implementation**
- **Found during:** Task 1, first script run
- **Issue:** Initial `test_6_inline_base64_skill()` used the POC-specific `INLINE_CONTAINER_NAME` as both the container name and the inline skill's `name`/`description`, which do not match the real SKILL.md frontmatter — this is required by the server per plan interfaces (`InlineSkillParam: {type: "inline", name: str, description: str, source: ...}`).
- **Fix:** Changed the inline skill's `name`/`description` to be read from the real `mr-training-creator/SKILL.md` frontmatter via `frontmatter.load()` (matching the pattern already used in `test_skill_foundry_upload.py`), while keeping the container's own `name` as the distinct POC-suffixed value.
- **Result:** The fix did not fully resolve the failure — a genuine, deeper server-side limitation was uncovered instead (see Known Findings below) and recorded honestly as a FAIL with root-cause investigation, per the plan's "record whatever actually happens" instruction.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_skill_responses_api.py`
- **Commit:** `54b729d` (folded into the Task 1 commit; the script was fixed and re-run before that commit was made, so the committed script already contains the fix)

## Known Findings (not stubs, but worth flagging for future work)

- **Test 5 (shell tool)**: Not usable with the currently deployed `gpt-4o-mini` model. A future POC should retry with a model deployment documented by Microsoft as supporting the `shell` tool (not yet identified/verified in this project).
- **Test 6 (inline base64 skill)**: Not usable with the real `mr-training-creator/SKILL.md` as-is, due to its YAML folded block scalar `description: >-` field. No production file was changed to work around this — doc 10 §11.7/§11.8 record the limitation explicitly so a future task can decide whether to reformat SKILL.md descriptions project-wide or avoid the inline-skill sub-path.

## Threat Flags

None — the new test script talks to the same Azure OpenAI `openai/v1` endpoint (network egress to an already-trusted Foundry resource) using the same class of credentials (`AZURE_FOUNDRY_API_KEY` from `backend/.env`, Entra ID via `DefaultAzureCredential`) as the existing `test_skill_foundry_upload.py`, and introduces no new endpoints, auth paths, or schema changes beyond what the plan's `<threat_model>` already covers (T-quick-01 through T-quick-04).

## Self-Check

- `docs/microsoft-agent-framework/tests/test_skill_responses_api.py` exists: **FOUND**
- `docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md` contains section 11: **FOUND** (verified via `grep -q "Responses API 路径"`)
- `docs/microsoft-agent-framework/README.md` mentions "Responses API": **FOUND** (verified via `grep -q "Responses API"`)
- Commit `54b729d` (Task 1, test script): **FOUND** in `git log`
- Commit `dc4eba0` (Task 2, docs): **FOUND** in `git log`
- No orphaned Foundry resources: **VERIFIED** — `client.skills.list()` returned `[]` after the script's own cleanup ran

## Self-Check: PASSED
