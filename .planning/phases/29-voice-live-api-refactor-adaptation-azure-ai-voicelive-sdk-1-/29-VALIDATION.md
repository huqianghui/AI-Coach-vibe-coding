---
phase: 29
slug: voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1
status: approved
nyquist_compliant: true
wave_0_complete: true
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

> Backfilled 2026-07-19 against the final 10-plan set (29-01..29-10). Mapping follows the 16 locked decisions (no formal REQ-IDs for this phase).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 29-03 T2 | 29-03 | 2 | D-01 Entra-first connect + API-key fallback | — | Entra used when creds available; fallback covered | unit | `pytest tests/test_voice_live_websocket.py -k "entra or api_key" -x` | ❌ W0 (added by 29-03 T3) | ⬜ pending |
| 29-02 T1 / 29-03 T2 / 29-04 T1 | 29-02, 29-03, 29-04 | 2 | D-02 single GA api-version constant (WS + WebRTC) | — | No preview-version literals remain | unit | `pytest tests/test_voice_live_websocket.py tests/test_voice_live_webrtc.py -k api_version -x` | ✅ (update assertions at `test_voice_live_websocket.py:786-787,1326,1366`, `test_voice_live_webrtc.py:80`) | ⬜ pending |
| 29-02 T2 | 29-02 | 2 | D-05 asst_* HCP auto-resync | T-29-01 | Resync runs before classic branch deleted | unit + integration | `pytest tests/ -k asst_resync -x` | ❌ W0 (added by 29-02 T2, TDD) | ⬜ pending |
| 29-03 T1/T2 | 29-03 | 2 | D-06/D-08 classic branch removed; unsynced HCP rejected | T-29-02 | Rejection enforced server-side (WS + WebRTC via 29-04 T1) | unit | `pytest tests/test_voice_live_websocket.py -k agent_forced_reject -x` | ❌ W0 (added by 29-03 T3) | ⬜ pending |
| 29-05 T2 | 29-05 | 2 | D-09/D-13 HCP save without VL instance rejected | — | API-level required validation (create + update) | unit | `pytest tests/ -k vl_required -x` | ❌ W0 (added by 29-05 T2, TDD) | ⬜ pending |
| 29-08 T1 | 29-08 | 4 | D-14 foundation model catalog endpoint | T-29-03 | Admin-scoped; returns only dropdown fields | unit | `pytest tests/test_agent_foundation_models.py -x` | ❌ W0 (added by 29-08 T1, TDD) | ⬜ pending |
| 29-07 T1-T3 | 29-07 | 3 | D-10/D-11 frontend VL-required validation + read-only Voice/Avatar tab | — | Save blocked in UI without VL instance | unit (vitest) | `cd frontend && npx vitest run src/components/admin src/pages/admin` | ❌ W0 (added by 29-07 tasks) | ⬜ pending |
| 29-10 T3 | 29-10 | 5 | D-16 E2E full HCP voice training session post-refactor | — | N/A | e2e | `npx playwright test --config=e2e/playwright.config.ts` (actual execution required) | ✅ existing voice/HCP/agent-sync specs | ⬜ pending |

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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (missing test files created by owning plans' TDD tasks)
- [x] No watch-mode flags
- [x] Feedback latency < 120s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-19 (plan-checker pass: 0 blockers, warnings resolved)
