---
phase: quick
plan: 01
subsystem: docs/microsoft-agent-framework
tags: [azure-ai-foundry, skills-api, toolbox, empirical-test, agent-framework]
dependency-graph:
  requires: []
  provides:
    - "docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py"
    - "docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md"
  affects:
    - "docs/microsoft-agent-framework/README.md"
tech-stack:
  added: []
  patterns:
    - "Script-style POC test (test_N_* functions, print_header/print_result/print_info helpers, main() summary table) mirroring test_agent_with_skills.py"
    - "Dual-auth-mode fallback: API Key attempted first, Entra ID (DefaultAzureCredential) attempted as fallback when API Key is rejected, both outcomes recorded verbatim"
key-files:
  created:
    - "docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py"
    - "docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md"
  modified:
    - "docs/microsoft-agent-framework/README.md"
decisions:
  - "Added an Entra ID (DefaultAzureCredential) fallback attempt for beta.skills/beta.toolboxes/agents calls beyond what the plan's interfaces block specified, since az login was trivially available in this environment -- both auth modes' real outcomes are recorded in doc 10 rather than assuming API-key alone"
  - "Did not fabricate PASS results for Toolbox skill_reference mounting or Agent-consumes-Toolbox tests -- both are reported as SKIP because the upstream Skill upload step never succeeded against the real Foundry resource"
metrics:
  duration: "~35min"
  completed: "2026-07-18"
---

# Quick Task 260717-x5f: Agent Skills Foundry Upload + Toolbox Mount POC Summary

**One-liner:** Wrote and ran a real POC script against Azure AI Foundry's `project.beta.skills`/`project.beta.toolboxes` API; both API-Key (403) and Entra ID (405) auth were empirically rejected for Skill upload, blocking Toolbox/Agent verification, and doc 10 records this exact empirical outcome.

## What was done

### Task 1 — `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`

Created a script-style POC test file (mirroring `test_agent_with_skills.py`'s conventions: `print_header`/`print_result`/`print_info` helpers, `test_N_*()` functions returning `True`/`False`/`None`, module-level `ENDPOINT`/`API_KEY`/`PROJECT_NAME`/`MODEL` loaded via `dotenv.load_dotenv(backend_dir / ".env")`, `cleanup()` in `try/finally`, PASS/FAIL/SKIP summary table).

Covers:
- **Test 1** — validates `mr-training-creator/SKILL.md` frontmatter (name regex `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, `<=64` chars, no `--`, description `<=1024` chars, body `>100` chars). **PASS**
- **Test 2** — packages the Skill directory into an in-memory ZIP with `SKILL.md` at the ZIP root (not nested), verifies round-trip frontmatter parsing. **PASS**
- **Test 3** — `client.beta.skills.create()` inline upload; tries API Key auth first, falls back to Entra ID (`DefaultAzureCredential`) if API Key is rejected with 401/403. **FAIL** (both auth modes)
- **Test 4** — `client.beta.skills.create_from_package()` ZIP upload, reusing whichever auth mode Test 3 found working (none did, so defaults to API Key). **FAIL**
- **Test 5** — get/list/download roundtrip for created skills. **SKIP** (no skills were created upstream)
- **Test 6** — `client.beta.toolboxes.create_version()` with raw-dict `skills: [{"type": "skill_reference", "name": "mr-training-creator"}]` body, inspects `as_dict()` on both the create and get_version responses for echo. **SKIP** (upstream skill missing)
- **Test 7** — attempts Agent-consumes-Toolbox via raw dict tool `{"type": "toolbox", ...}`, falls back to metadata-only reference if rejected, explicitly tracks `toolbox_bound_as_tool` vs metadata-only fallback. **SKIP** (upstream toolbox missing)
- **`cleanup()`** — deletes agents → toolbox versions → toolbox → skills in dependency order, each in its own try/except, called unconditionally in `main()`'s `finally` block.

### Real run results (executed against the live `avarda-demo-prj` Foundry project in `backend/.env`)

```
Test 1: Validate Skill Frontmatter        [PASS]
Test 2: Package Skill as ZIP              [PASS]
Test 3: Create Skill Inline               [FAIL]  403 AuthenticationTypeDisabled (api-key) / 405 Method Not Allowed (entra-id fallback)
Test 4: Create Skill From Package         [FAIL]  403 AuthenticationTypeDisabled (api-key)
Test 5: Get/List/Download Roundtrip       [SKIP]  no skills created upstream
Test 6: Toolbox Version + skill_reference [SKIP]  no skill to reference upstream
Test 7: Agent Uses Toolbox                [SKIP]  no toolbox version upstream

Total: 2 passed, 2 failed, 3 skipped
Exit code: 1
```

Cleanup ran (via `try/finally`) but was a genuine no-op — since `_created_skills`, `_created_toolboxes`, `_created_agents` were all empty (nothing was ever created on the Azure side), `cleanup()`'s guard clause returned immediately without any API calls or log output. **No orphaned resources were left in the Foundry project.**

**Key empirical finding**: the Foundry resource `avarda-demo-prj` has **API-Key authentication disabled at the resource level** for the Skills preview endpoint (`403 AuthenticationTypeDisabled`, verbatim server message: "Key based authentication is disabled for this resource."). This does not contradict this project's earlier "API Key + Agent 模式 = 可行" conclusion (docs 01/02/README), because that finding was about the Voice Live API's `AgentSessionConfig` connection path via `azure-ai-voicelive`, a different service surface from `azure-ai-projects`'s `beta.skills`/`beta.toolboxes` preview endpoints tested here.

As a deviation beyond the plan's literal instructions (see below), I also attempted an Entra ID (`DefaultAzureCredential`) fallback since `az login` was already active in this environment — it failed with a different error (`405 Method Not Allowed`), which is also recorded verbatim in doc 10 rather than assumed to work.

### Task 2 — `docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md` + README.md

Wrote doc 10 in Chinese, matching the empirical-first "实测结论" style of docs 01/02/08, with all 11 required sections: 概述, 前置条件与环境, Inline 上传实测, ZIP 包上传实测, Get/List/Download 往返实测, Toolbox Version + skill_reference 挂载实测, Agent 消费 Toolbox 实测, 认证模式对照, 命名规则提醒, 清理与建议顺序, and a 结论速查 summary at the top. Every "实测结果"/PASS/FAIL/SKIP claim in the doc corresponds directly to the real script output above — no hypothetical results.

Updated `README.md`'s 文档索引 table by appending one new row for doc 10 at the end of the table, exactly as specified in the plan, without renumbering or otherwise altering the existing (pre-existing duplicate-numbered) rows.

## Deviations from Plan

### Auto-fixed / Extended (within Rule 1-3 scope)

**1. [Rule 3 - blocking issue] Added Entra ID (DefaultAzureCredential) fallback attempt for Skills/Toolbox/Agent calls**
- **Found during:** Task 1, Test 3
- **Issue:** API Key auth was rejected by the Skills endpoint with `403 AuthenticationTypeDisabled`. The plan's `<interfaces>` block only specified API Key auth construction, and instructed "do NOT silently retry with a different auth mode unless `azure.identity.DefaultAzureCredential` is trivially available; if you do try a fallback, clearly label which auth mode produced which result."
- **Fix:** Verified `az login` session was already active (`az account show` succeeded) and `azure-identity` was installed, making the Entra ID fallback "trivially available" per the plan's own carve-out. Added `_get_project_client_entra()` and a `_get_beta_client()` cache that records which auth mode (if any) succeeds, used consistently for `beta.skills`, `beta.toolboxes`, and `agents.create_version` calls in Tests 4/5/6/7 and `cleanup()`. Both auth modes' real outcomes are labeled explicitly (`[api-key]` / `[entra-id]`) in the script's printed output and in doc 10.
- **Files modified:** `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py`
- **Commit:** `dcac7b0`

No architectural changes were needed; no Rule 4 checkpoints were triggered.

## Known Stubs

None. This is a documentation/POC-script quick task with no application UI or data-flow stubs.

## Threat Flags

None beyond what the plan's `<threat_model>` already anticipated (T-quick-01 through T-quick-04, all `mitigate`/`accept` and addressed as specified: API key never printed in full, POC-suffixed names used, per-resource try/except in cleanup, printed PASS/FAIL log as audit trail).

## Branch and Commits

**Branch:** `worktree-agent-aaf9dba41a956672a`

| Task | Commit | Message |
|------|--------|---------|
| 1 | `dcac7b0` | `test(quick-260717-x5f): add Skills API + Toolbox upload POC script` |
| 2 | `347fcc5` | `docs(quick-260717-x5f): document Skills Foundry upload + Toolbox mount empirical results` |

## Self-Check

- `docs/microsoft-agent-framework/tests/test_skill_foundry_upload.py` — FOUND
- `docs/microsoft-agent-framework/10-agent-skills-foundry-upload-and-toolbox.md` — FOUND
- `docs/microsoft-agent-framework/README.md` contains link to doc 10 — FOUND
- Commit `dcac7b0` — FOUND in `git log`
- Commit `347fcc5` — FOUND in `git log`

## Self-Check: PASSED
