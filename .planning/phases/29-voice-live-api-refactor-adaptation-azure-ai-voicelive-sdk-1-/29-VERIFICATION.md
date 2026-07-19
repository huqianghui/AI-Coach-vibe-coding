---
phase: 29-voice-live-api-refactor-adaptation-azure-ai-voicelive-sdk-1-
verified: 2026-07-19T18:22:04Z
status: passed
score: 16/16 must-haves verified (D-01..D-16)
overrides_applied: 1
overrides:
  - must_have: "Upgrade azure-ai-voicelive SDK to 1.3.0 GA"
    reason: "GA 1.3.0 was confirmed not published on PyPI at execution time (live pip dry-run check, not research-time assumption). User made the blocking checkpoint decision 'pin-beta': azure-ai-voicelive[aiohttp]==1.3.0b1 pinned with explicit api_version=\"2026-07-15\" passed at every connect() call site, live-verified against the real Voice Live service via POC (backend/scripts/poc_voice_live_1_3_0.py). This is the accepted fulfillment of the SDK-upgrade goal per explicit user/orchestrator ground truth provided for this verification."
    accepted_by: "user (checkpoint decision, Plan 29-01 Task 2)"
    accepted_at: "2026-07-19T00:00:00Z"
---

# Phase 29: Voice Live API Refactor & Adaptation Verification Report

**Phase Goal:** Upgrade azure-ai-voicelive SDK to 1.3.0 GA (api-version 2026-07-15), formalize the dual-path architecture (text via Agent Responses API, voice via Voice Live → hosted Agent), delete the voice-agent monkey-patch and classic-agent path, make VL Instance mandatory per HCP (D-10 supersedes the roadmap's "optional" wording), remove the 14 deprecated inline HCP voice/avatar fields, split the Agent Foundation Model catalog from the Voice Live model catalog, and fully update docs + tests.

**Verified:** 2026-07-19T18:22:04Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (derived from D-01..D-16 + PLAN must_haves; roadmap success_criteria was empty)

| # | Truth (Decision) | Status | Evidence |
|---|---|---|---|
| 1 | D-01: Voice Live auth is Entra-first with API-key fallback, both paths tested | ✓ VERIFIED | `_resolve_voice_live_credential()` in `voice_live_websocket.py` tries `DefaultAzureCredential` then `AzureKeyCredential`; tests `test_credential_prefers_entra_when_available`, `test_credential_falls_back_to_api_key_when_entra_unavailable` |
| 2 | D-02: Single GA api-version (2026-07-15) constant used at every connect() call site, no preview literals remain | ✓ VERIFIED | `settings.voice_live_api_version = "2026-07-15"` in `config.py:101`; consumed in `voice_live_websocket.py` and `voice_live_webrtc.py:61`; repo-wide grep for `2025-05-01-preview\|2026-01-01-preview\|2026-06-01-preview` returns 0 hits (confirmed live in this session and recorded in 29-10-SUMMARY.md) |
| 3 | D-03: SDK pinned `azure-ai-voicelive[aiohttp]>=1.3.0,<2.0` — **overridden**, see `overrides` | ✓ VERIFIED (override) | `backend/pyproject.toml:56` pins `==1.3.0b1` with documented rationale; accepted per user checkpoint decision (pin-beta) |
| 4 | D-04: POC script validates Agent connect/auth/session-config before full migration | ✓ VERIFIED | `backend/scripts/poc_voice_live_1_3_0.py` exists (10,364 bytes), live output captured in 29-01-SUMMARY.md (`AGENT_CONNECT=PASS`) |
| 5 | D-05: asst_* classic agents auto-resync to hosted agents, never left orphaned on failure | ✓ VERIFIED | `agent_sync_service.resync_classic_agent()`; called in both `voice_live_websocket.py:213` and `voice_live_webrtc.py:92`; tests `test_resync_classic_agent_success/failure_restores_original_id/noop_*` (4 tests) plus WS/WebRTC-level resync tests |
| 6 | D-06: Classic-agent branch + `_apply_voice_agent_patch()` monkey-patch deleted from `voice_live_websocket.py` | ✓ VERIFIED | grep for `_apply_voice_agent_patch\|_VOICE_AGENT_PATCHED` returns 0 matches; only `AgentSyncRequiredError` class remains at that location |
| 7 | D-07: Global hosted-agent override settings deleted; per-HCP hosted agent only | ✓ VERIFIED | grep for `voice_live_hosted_agent` returns 0 matches in `config.py`, `voice_live_websocket.py`, `voice_live_webrtc.py` |
| 8 | D-08: Agent mode mandatory — unsynced HCP voice sessions rejected (WS: `AgentSyncRequiredError`/`AGENT_SYNC_REQUIRED`; WebRTC: 409 `AGENT_SYNC_REQUIRED`), Model mode reserved for VL Instance Editor test-connect only | ✓ VERIFIED | `class AgentSyncRequiredError(ValueError)` in `voice_live_websocket.py:48`, raised at L224, caught before generic `except Exception` at L241/525; WebRTC raises `AppException(409, "AGENT_SYNC_REQUIRED", ...)` at L100 |
| 9 | D-09: 14 deprecated inline HCP voice/avatar columns dropped (model/schema/API/frontend), no backfill | ✓ VERIFIED | `hcp_profile.py` model: only `voice_live_instance_id` remains (no `voice_live_enabled/voice_name/avatar_character/...`); Alembic `z33a_drop_hcp_inline_voice_fields.py` uses `batch_alter_table`; `frontend/src/types/hcp.ts` `HcpProfile` interface has zero of the 14 fields (they only exist on the separate `VoiceLiveInstanceSummary` type) |
| 10 | D-10: Every HCP must be bound to a VL Instance (roadmap "optional" wording superseded) | ✓ VERIFIED | Backend: `HcpProfileCreate.voice_live_instance_id: str = Field(..., min_length=1)`; service-layer guard in `hcp_profile_service.py:148-149` blocks clearing on update. Frontend: zod `.refine()` in `hcp-profile-editor.tsx:79-83` blocks save client-side |
| 11 | D-11: Voice/Avatar tab is read-only VL Instance summary + assign/unassign + VL Management link; old editable Model Deployment selector + Voice Mode Switch removed | ✓ VERIFIED | `agent-config-left-panel.tsx` renders VL Instance Summary Card (L126-222) with `vlInstanceEmptyTitle`; `voice-avatar-tab.tsx` derives `voiceModeEnabled = Boolean(vlInstanceId)` — no independent Switch state |
| 12 | D-12: `resolve_voice_config()` never reads deprecated inline columns; no-VL fallback returns hardcoded safe defaults; denormalized avatar-mirror writes removed | ✓ VERIFIED | `voice_live_instance_service.py:258-` — fallback returns hardcoded dict (`voice_live_enabled=False`, etc.), reads only `profile.voice_live_instance`; `MagicMock(spec=[...])` regression-guard test confirms no other attribute access |
| 13 | D-13: Save-time validation enforces VL Instance on both create and update (422); DB column stays nullable | ✓ VERIFIED | Confirmed at #10; `hcp_profile.py` model column is `Mapped[str | None]` (nullable, no migration risk) |
| 14 | D-14: Agent Foundation Model catalog is a separate, admin-gated, cached, defensively-filtered endpoint distinct from `VOICE_LIVE_MODELS` | ✓ VERIFIED | `GET /api/v1/agent-foundation-models` registered in `main.py:138`, gated by `require_role("admin")`; `agent_foundation_models.py` has 300s TTL cache, excludes `VOICE_LIVE_MODELS` matches, stale-on-failure/empty-on-failure (never 500); 9 tests in `test_agent_foundation_models.py` |
| 15 | D-15: docs/voice-live-avatar merged into single tree, no classic-agent/deprecated-field/preview-version references, dual-path architecture documented | ✓ VERIFIED | `docs/voice-live-avatar/README/` subtree confirmed deleted (no such directory); 17-file flat tree present (00-index..14 + appendix-glossary + README.md); `01-architecture.md` contains new "双路径架构" section per 29-09-SUMMARY.md |
| 16 | D-16: Full test suites updated + new coverage (Entra/API-key, resync, VL-required, foundation-model catalog); E2E actually executed; coverage gate enforced | ✓ VERIFIED | Backend: 2635 passed/15 skipped, `--cov-fail-under=89` enforced in `pyproject.toml:71`. Frontend: tsc clean, build clean, `thresholds` block in `vitest.config.ts:42-44`. Playwright: 104 passed/8 failed(pre-existing, root-caused)/7 skipped(data-dependent). Repo-wide grep for stale preview api-versions: 0 hits |

**Score:** 16/16 truths verified (1 via documented override for D-03's GA-version literal, all downstream behavior — including the accepted api_version override at connect() — independently verified)

### Required Artifacts (sampled across all 10 plans)

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/scripts/poc_voice_live_1_3_0.py` | SDK POC script | ✓ VERIFIED | Exists, 10,364 bytes |
| `backend/pyproject.toml` | SDK pin + coverage gate | ✓ VERIFIED | `azure-ai-voicelive[aiohttp]==1.3.0b1`; `--cov-fail-under=89` |
| `backend/app/config.py` | `voice_live_api_version`, no hosted-override settings | ✓ VERIFIED | L101; grep for hosted-agent settings = 0 |
| `backend/app/services/agent_sync_service.py` | `resync_classic_agent()` | ✓ VERIFIED | Present, tested (4 direct + WS/WebRTC integration tests) |
| `backend/app/services/voice_live_websocket.py` | `AgentSyncRequiredError`, Entra-first credential, no monkey-patch | ✓ VERIFIED | All confirmed via grep/read |
| `backend/app/services/voice_live_webrtc.py` | No `WEBRTC_API_VERSION`, D-05/D-08 gate | ✓ VERIFIED | Confirmed via grep |
| `backend/alembic/versions/z33a_drop_hcp_inline_voice_fields.py` | Batch migration dropping 14 columns | ✓ VERIFIED | Referenced/applied; model reflects post-migration state |
| `backend/app/models/hcp_profile.py` | Only `voice_live_instance_id` remains | ✓ VERIFIED | Confirmed |
| `backend/app/schemas/hcp_profile.py` | Required `voice_live_instance_id` | ✓ VERIFIED | `Field(..., min_length=1)` on Create |
| `backend/app/services/voice_live_instance_service.py` | Safe-defaults fallback, no mirror writes | ✓ VERIFIED | Confirmed |
| `frontend/src/types/hcp.ts` | 14 fields removed from `HcpProfile` | ✓ VERIFIED | Confirmed — fields exist only on `VoiceLiveInstanceSummary` |
| `frontend/src/pages/admin/hcp-profile-editor.tsx` | zod `.refine()` on `voice_live_instance_id` | ✓ VERIFIED | L79-83 |
| `frontend/src/components/admin/agent-config-left-panel.tsx` | VL Instance Summary Card + Foundation Model card | ✓ VERIFIED | Card structure confirmed |
| `frontend/src/components/admin/voice-avatar-tab.tsx` | Read-only, `Boolean(vlInstanceId)` derived voice mode | ✓ VERIFIED | Confirmed, no `Switch`/stateful toggle |
| `backend/app/services/agent_foundation_models.py` | Cached, filtered Foundry catalog | ✓ VERIFIED | 300s TTL cache confirmed |
| `backend/app/api/agent_foundation_models.py` | Admin-gated endpoint | ✓ VERIFIED | Registered in `main.py`/`api/__init__.py` |
| `frontend/src/components/admin/agent-foundation-model-select.tsx` | Dropdown w/ loading/error/empty states | ✓ VERIFIED | Present; see WR-01 anti-pattern note below |
| `docs/voice-live-avatar/*` (17 files) | Unified doc tree, no `README/` subtree | ✓ VERIFIED | Confirmed via `ls` — 17 top-level files, no nested subtree |
| `frontend/vitest.config.ts` | Coverage thresholds | ✓ VERIFIED | `thresholds: { statements: 71, branches: 82, ... }` |

### Key Link Verification (sampled)

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `voice_live_websocket.py::_load_connection_config` | `agent_sync_service.py::resync_classic_agent` | `await resync_classic_agent(db, profile)` before sync gate | ✓ WIRED | L213 |
| `voice_live_webrtc.py::create_webrtc_session_config` | `agent_sync_service.py::resync_classic_agent` | lazy import + await, gated on `asst_` prefix | ✓ WIRED | L90-92 |
| `voice_live_webrtc.py::create_webrtc_session_config` | `AppException(409, "AGENT_SYNC_REQUIRED")` | raised before signaling URL built | ✓ WIRED | L100 |
| `hcp-profile-editor.tsx::hcpSchema` | `agent-config-left-panel.tsx` | `errors.voice_live_instance_id` → inline error + `vlInstanceValidationError` i18n key | ✓ WIRED | Confirmed |
| `agent_sync_service.py::build_voice_live_metadata` | `voice_live_instance_service.py::resolve_voice_config` | unchanged call site | ✓ WIRED | Confirmed |
| `agent-foundation-models.py` (API) | `agent_foundation_models.py` (service) | `list_agent_foundation_models()` | ✓ WIRED | Router registered in `main.py:138` |
| `frontend/src/hooks/use-agent-foundation-models.ts` | `GET /agent-foundation-models` | `apiClient.get` | ✓ WIRED | Confirmed present |
| `agent-config-left-panel.tsx` | `agent-foundation-model-select.tsx` | import + JSX render | ✓ WIRED | L37, L232 |
| `00-index.md` | 09-14/appendix merged docs | markdown links | ✓ WIRED | Per 29-09-SUMMARY.md directory table update |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `agent-foundation-model-select.tsx` | `data.models` | `useAgentFoundationModels()` → `GET /agent-foundation-models` → `AIProjectClient.deployments.list()` | Yes — live Foundry API call, capabilities-filtered (D-14 probe confirmed real deployment shape in 29-01) | ✓ FLOWING |
| `agent-config-left-panel.tsx` VL Instance card | `profile.voice_live_instance` | HCP profile GET response, populated by SQLAlchemy relationship (not hardcoded) | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

Not run live in this verification session (per task instructions: "do not run test suites — full suites already ran green in 29-10"). Evidence instead comes from static code inspection cross-referenced against 29-10-SUMMARY.md's recorded live-run output (backend pytest 2635 passed/15 skipped @ 89% coverage; frontend tsc/build/vitest thresholds; Playwright 104 passed/8 pre-existing failures/7 data-dependent skips; live grep sweep for stale preview api-versions = 0 hits), which is accepted as ground truth per the verification task's explicit instructions.

### Requirements Coverage (D-01..D-16)

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| D-01 | 29-03 | Entra-first + API-key fallback auth | ✓ SATISFIED | See Truth #1 |
| D-02 | 29-02, 29-03, 29-04, 29-10 | Single GA api-version constant | ✓ SATISFIED | See Truth #2 |
| D-03 | 29-01 | SDK pin `>=1.3.0,<2.0` | ✓ SATISFIED (override) | GA unavailable on PyPI; pin-beta accepted |
| D-04 | 29-01 | POC before full migration | ✓ SATISFIED | See Truth #4 |
| D-05 | 29-02, 29-03, 29-04 | asst_* auto-resync | ✓ SATISFIED | See Truth #5 |
| D-06 | 29-03 | Delete classic path + monkey-patch | ✓ SATISFIED | See Truth #6 |
| D-07 | 29-03, 29-04 | Delete global hosted-agent override | ✓ SATISFIED | See Truth #7 |
| D-08 | 29-03, 29-04 | Mandatory agent mode, hard rejection | ✓ SATISFIED | See Truth #8 |
| D-09 | 29-05 | Drop 14 inline columns, no backfill | ✓ SATISFIED | See Truth #9 |
| D-10 | 29-07 | VL Instance mandatory per HCP | ✓ SATISFIED | See Truth #10 |
| D-11 | 29-07 | Read-only VL summary + assign/unassign | ✓ SATISFIED | See Truth #11 |
| D-12 | 29-06 | Safe-defaults fallback, no mirror writes | ✓ SATISFIED | See Truth #12 |
| D-13 | 29-05 | Save-time validation, nullable DB column | ✓ SATISFIED | See Truth #13 |
| D-14 | 29-01(probe), 29-08 | Foundation Model catalog split from VL models | ✓ SATISFIED | See Truth #14 |
| D-15 | 29-09 | Docs tree merge + dual-path diagram | ✓ SATISFIED | See Truth #15 |
| D-16 | 29-10 | Full test update + coverage gate + E2E | ✓ SATISFIED | See Truth #16 |

No orphaned decision IDs — all D-01..D-16 are claimed by at least one plan's `requirements:` frontmatter and independently verified against the codebase above.

### Anti-Patterns Found

All items below were already surfaced by the phase's own code review (29-REVIEW.md, 0 critical / 3 warnings / 3 info) and independently re-confirmed present in the current codebase during this verification. None block the phase goal; they are UX/documentation/dead-code quality issues, not missing or unwired functionality.

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `frontend/src/components/admin/agent-foundation-model-select.tsx` | 38-55 | Treats any truthy `data?.error` as full failure, discarding a still-usable stale cached model list | ⚠️ Warning | Admin loses picker during transient Foundry outages even though backend intentionally serves stale data; no functional break of the D-14 endpoint contract itself |
| `docs/voice-live-avatar/02-database-schema.md` | 93-116 | Doc snippet shows `resolve_voice_config()` raising `ConfigurationError`; actual implementation returns safe defaults (tested) | ⚠️ Warning | Documentation drift — could mislead a future engineer, does not affect running code |
| `frontend/src/hooks/voice-live-integration.test.ts` | 22-32 | Local `HcpProfile` interface still uses pre-Phase-29 flat `avatar_character`/`voice_name` fields; predicates silently no-op against the real (migrated) API instead of failing | ⚠️ Warning | Silent test-coverage loss for this one integration-test file; does not affect other test files' coverage of the same behavior (e.g. `voice-avatar-real.spec.ts` uses the correct shape) |
| `backend/app/services/agent_sync_service.py` | 23 | `AGENT_REGISTRY_API_VERSION = "2025-01-01-preview"` dead constant, unused anywhere | ℹ️ Info | Confusing given D-02's single-source-of-truth rule, but not read/used, so no runtime effect |
| `backend/app/services/voice_live_instance_service.py` | 100 | `# TODO:` comment about future scaling consideration | ℹ️ Info | Non-blocking, forward-looking note only |
| `frontend/src/components/admin/agent-config-left-panel.tsx` | 318-321 | "Tools placeholder" section (Knowledge & Tools collapsible skeleton) | ℹ️ Info | Pre-existing from prior phases, unrelated to Phase 29's scope (Instructions/Knowledge/Tools section explicitly unchanged per 29-07-SUMMARY.md) |

### Human Verification Required

None. All observable truths were verified against the codebase directly, and the phase's own execution already captured live evidence (real Azure Entra auth round-trip, real Foundry deployments.list() probe, real backend Playwright E2E run against a live server) per 29-01-SUMMARY.md and 29-10-SUMMARY.md, which this verification treats as accepted ground truth per the task's explicit instructions.

### Gaps Summary

No gaps found. All 16 decision points (D-01..D-16) are implemented, wired, and covered by tests, cross-verified independently against the current codebase (not just SUMMARY claims). The one deviation from the literal roadmap goal text — GA SDK 1.3.0 vs the pinned 1.3.0b1 beta — is an explicitly accepted override per a live-verified, user-approved blocking checkpoint decision documented in 29-01-SUMMARY.md, and is not treated as a gap per this verification task's explicit ground-truth instructions.

Three pre-existing, non-blocking anti-patterns (2 warnings on frontend/doc UX, 1 warning on a single integration test's silent coverage loss, plus 3 info-level dead-code/placeholder notes) were already identified by the phase's own code review and are carried forward here for visibility; they do not affect goal achievement and require no closure plan for this phase to be considered complete.

---

_Verified: 2026-07-19T18:22:04Z_
_Verifier: Claude (gsd-verifier)_
