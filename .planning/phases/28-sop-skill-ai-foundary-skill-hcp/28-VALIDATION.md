---
phase: 28
slug: sop-skill-ai-foundary-skill-hcp
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed post-execution (State B) from PLAN/SUMMARY/VERIFICATION artifacts.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (backend) · Playwright 1.48+ (E2E) · tsc/ruff (static gates) |
| **Config file** | `backend/pyproject.toml` · `frontend/e2e/playwright.config.ts` |
| **Quick run command** | `cd backend && .venv/bin/pytest tests/test_skill_foundry_service.py tests/test_skill_consumption_service.py tests/test_skill_foundry_api.py -q` |
| **Full suite command** | `cd backend && .venv/bin/pytest -q` then `cd frontend && npx playwright test --config=e2e/playwright.config.ts e2e/skill-foundry-sync.spec.ts` |
| **Estimated runtime** | ~15s backend targeted · ~45s E2E (requires dev stack on :8000/:5173) |

---

## Sampling Rate

- **After every task commit:** Run quick command (targeted Foundry test files)
- **After every plan wave:** Run full backend suite + Foundry E2E spec
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 28-01-01 | 01 | 1 | D-01 (Foundry sync columns + migration) | T-28-01 | Sync metadata persisted, no secrets in columns | unit | `backend/.venv/bin/pytest tests/test_skill_foundry_service.py -q` | ✅ | ✅ green |
| 28-01-02 | 01 | 1 | D-01 (Entra-only client, collision-safe naming) | T-28-02 | Entra ID only — `AzureKeyCredential` absent (grep-verified) | unit | `backend/.venv/bin/pytest tests/test_skill_foundry_service.py -q` | ✅ | ✅ green |
| 28-01-03 | 01 | 1 | D-03 (publish/archive/delete lifecycle sync, 404-as-success) | T-28-03 | Delete treats 404 as success, resets tracking fields | unit | `backend/.venv/bin/pytest tests/test_skill_service.py -q -k foundry` | ✅ | ✅ green |
| 28-01-04 | 01 | 1 | D-03 (version-increment on re-publish, same name) | — | Same entity re-used, no duplicate skill created | unit (call-pattern) + live smoke | `backend/.venv/bin/pytest tests/test_skill_foundry_service.py -q` · live evidence in 28-HUMAN-UAT.md | ✅ | ✅ green |
| 28-02-01 | 02 | 2 | D-02 (Toolbox mount via skill_reference, non-blocking) | T-28-05 | Mount failure returns None, never raises into session creation | unit | `backend/.venv/bin/pytest tests/test_skill_consumption_service.py -q` | ✅ | ✅ green |
| 28-02-02 | 02 | 2 | D-04 (MCP probe → download → local degradation chain) | T-28-06 | 405-aware honest probe; fallback chain never fails session | unit | `backend/.venv/bin/pytest tests/test_skill_consumption_service.py -q` | ✅ | ✅ green |
| 28-02-03 | 02 | 2 | D-02/D-04 (TTL content cache keyed on (skill.id, cloud_version)) | — | Cloud calls fire at most once per TTL window | integration | `backend/.venv/bin/pytest tests/test_skill_consumption_service.py -q -k cache` | ✅ | ✅ green |
| 28-03-01 | 03 | 3 | D-05 (SkillContent → focus_instruction, text + Voice Live identical) | — | No Voice-Live-specific divergence (grep-verified) | integration | `backend/.venv/bin/pytest tests/test_session_service.py -q` | ✅ | ✅ green |
| 28-03-02 | 03 | 3 | D-06 (sync failure never blocks publish; unsynced skill degrades to local) | T-28-04 | try/except/finally, never re-raises | unit | `backend/.venv/bin/pytest tests/test_skill_service.py tests/test_skill_consumption_service.py -q` | ✅ | ✅ green |
| 28-04-01 | 04 | 4 | D-07 (API exposes foundry fields; retry-sync published-only; portal-url) | T-28-07 | Retry gated `status == "published"` (422 otherwise), admin-only routes | api | `backend/.venv/bin/pytest tests/test_skill_foundry_api.py -q` | ✅ | ✅ green |
| 28-04-02 | 04 | 4 | D-07 (Settings tab status badge/retry/portal link, i18n) | — | Retry button disabled for non-published skills (WR-02 fix) | e2e | `cd frontend && npx playwright test --config=e2e/playwright.config.ts e2e/skill-foundry-sync.spec.ts` | ✅ | ✅ green (7/7, re-run 2026-07-18) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Foundry server-side version increment on repeated `create_from_files` with same name | D-03 | Requires a live Azure AI Foundry project + Entra credentials — not CI-automatable | See 28-HUMAN-UAT.md. **Executed & PASSED 2026-07-18**: skill a7c5e171 sync #1 → version=1, sync #2 → version=2, same entity, no duplicate. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-18
