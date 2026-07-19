---
phase: 29
slug: voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥8.3.0 + pytest-asyncio ≥0.24.0 (backend) · vitest ^3.2.4 (frontend) · Playwright ≥1.48.0 (E2E) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` · `frontend/vite.config.ts` · `frontend/playwright.config.ts` (must pass `--config=e2e/playwright.config.ts` — CLAUDE.md Gotcha #5) |
| **Quick run command** | `cd backend && .venv/bin/pytest tests/test_voice_live_websocket.py tests/test_voice_live_webrtc.py -x` |
| **Full suite command** | `cd backend && .venv/bin/pytest -v` then `cd frontend && npm run test && npx playwright test --config=e2e/playwright.config.ts` |
| **Estimated runtime** | ~90 seconds (backend quick) / several minutes (full) |

---

## Sampling Rate

- **After every task commit:** Run targeted quick-run command for the file(s) touched
- **After every plan wave:** Run full backend + frontend + Playwright suite
- **Before `/gsd-verify-work`:** Full suite must be green (95% coverage + "E2E must actually run" project standard)
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

> Task IDs to be filled by planner. Mapping follows the 16 locked decisions (no formal REQ-IDs for this phase).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | D-01 Entra-first connect + API-key fallback | — | Entra used when creds available; fallback covered | unit | `pytest tests/test_voice_live_websocket.py -k "entra or api_key" -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | D-02 single GA api-version constant (WS + WebRTC) | — | No preview-version literals remain | unit | `pytest tests/test_voice_live_websocket.py tests/test_voice_live_webrtc.py -k api_version -x` | ✅ (update assertions at `test_voice_live_websocket.py:786-787,1326,1366`, `test_voice_live_webrtc.py:80`) | ⬜ pending |
| TBD | — | — | D-05 asst_* HCP auto-resync | T-29-01 | Resync runs before classic branch deleted | unit + integration | `pytest tests/ -k asst_resync -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | D-06/D-08 classic branch removed; unsynced HCP rejected | T-29-02 | Rejection enforced server-side (WS; WebRTC gap = Open Q#3) | unit | `pytest tests/test_voice_live_websocket.py -k agent_forced_reject -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | D-09/D-13 HCP save without VL instance rejected | — | API-level required validation (create + update) | unit | `pytest tests/ -k vl_required -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | D-14 foundation model catalog endpoint | T-29-03 | Admin-scoped; returns only dropdown fields | unit | `pytest tests/test_agent_foundation_models.py -x` | ❌ W0 | ⬜ pending |
| TBD | — | — | D-16 E2E full HCP voice training session post-refactor | — | N/A | e2e | `npx playwright test --config=e2e/playwright.config.ts` (confirm exact spec) | locate existing spec | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Confirm exact existing test file names for HCP profile API tests, agent sync tests, and the voice-live E2E spec
- [ ] New test file: `backend/tests/test_agent_foundation_models.py` — D-14 endpoint
- [ ] New test cases in `test_voice_live_websocket.py` — D-01 Entra/API-key dual-path coverage
- [ ] New test cases — D-05 asst_* auto-resync trigger
- [ ] New test cases — D-13 VL-required save-time validation (create + update)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SDK 1.3.0 GA availability on PyPI | D-03/D-04 | External registry state; GA not yet published (only 1.3.0b1 as of 2026-07-19) | POC pre-flight: `pip index versions azure-ai-voicelive` before migration begins |
| Live `ModelDeployment.capabilities` shape for chat-model filtering | D-14 | Untested against live Foundry project | Run POC script against real AI Foundry project; inspect `capabilities` dict keys |
| Live Voice Live Agent connect with 1.3.0 GA | D-04 | Requires real Azure credentials + Entra | Run POC script (pattern: `docs/microsoft-agent-framework/tests/test_agent_auth_v2.py`) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
