---
phase: 30
slug: scenario-api-d10-voicelive-instance-propagation-fix
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-20
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (backend) / vitest (frontend unit) / Playwright (E2E) |
| **Config file** | `backend/pyproject.toml` / `frontend/vitest.config.ts` / `frontend/e2e/playwright.config.ts` |
| **Quick run command** | `cd backend && pytest tests/ -k scenario -q` and `cd frontend && npx vitest run --reporter=dot` |
| **Full suite command** | `cd backend && pytest -v` then `cd frontend && npx tsc -b && npx vitest run && npx playwright test --config=e2e/playwright.config.ts` |
| **Estimated runtime** | ~120 seconds (quick) / ~600 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | — | — | D-10 propagation | — | No sensitive VoiceLive credentials leak into scenario API response | unit/integration/e2e | see plans | ⬜ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_scenario_avatar_fields.py` — rewrite: currently asserts the buggy flat shape as correct
- [ ] Frontend fixtures in `training.test.tsx`, `scenario-card.test.tsx`, `scenario-panel.test.tsx`, `scenario-table.test.tsx`, `unified-session.test.tsx` — update to nested `voice_live_instance` shape

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Voice/digital-human mode buttons appear for scenario-driven sessions | D-10 propagation | Visual gating confirmation in real browser | Start dev servers, open training page with a scenario whose HCP has a VoiceLive instance, confirm voice + avatar modes offered and avatar character/style resolve |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
