# Phase 28 Security Audit — Skill AI Foundry Sync

**Phase:** 28 — sop-skill-ai-foundary-skill-hcp
**ASVS Level:** L1
**Audit date:** 2026-07-18
**Auditor:** gsd-security-auditor
**Verified against code state:** commit `5d3df47` (includes post-review fixes WR-01/WR-02/WR-03: `040f43c`, `f022dae`, `5d3df47`)

**Result: SECURED — 18/18 threats CLOSED.**

---

## Threat Verification

### Mitigate-disposition threats (verified by grep/inspection of cited code)

| Threat ID | Category | Component | Status | Evidence |
|-----------|----------|-----------|--------|----------|
| T-28-01 | Spoofing | `get_skills_client` | CLOSED | `backend/app/services/skill_foundry_service.py:80-112` — Entra-ID-only; module-level `_get_cached_credential()` singleton (line 77-90); `RuntimeError` raised on credential failure (no fallback, lines 104-110); confirmed **zero** matches for `AzureKeyCredential` in the file (`grep` exit 1) |
| T-28-02 | Tampering | ZIP upload via `create_from_files` | CLOSED | `backend/app/services/skill_foundry_service.py:138-140` — `validate_zip_security()` called and raises `ValueError` on any issue before every `create_from_files` call |
| T-28-03 | Info Disclosure | `foundry_sync_error` | CLOSED | Truncated at source: `skill_foundry_service.py:170` (`str(e)[:2000]`); exposed only via `require_role("admin")`-gated routes: `backend/app/api/skills.py:83-92` (list), `477-487` (detail), `557-578` (retry) |
| T-28-04 | DoS | Foundry API on publish | CLOSED | `skill_foundry_service.py:152-162` — `asyncio.wait_for(..., timeout=60)` around `create_from_files`; `sync_skill_to_foundry` never raises (try/except/finally, lines 130-173), no retry loop; `skill_service.py:317-320` confirms publish is non-blocking |
| T-28-05 | EoP | Foundry sync/delete triggers | ACCEPTED (see log below) | `skill_service.py:253` (`publish_skill`), `:361` (`archive_skill`), `:225` (`delete_skill`) — all reached only via `backend/app/api/skills.py` routes already gated by `Depends(require_role("admin"))` (lines 513-543, 502-510) |
| T-28-17 | Tampering | Foundry entity naming collision | CLOSED | `skill_foundry_service.py:54-70` — `_build_unique_foundry_name` suffixes `skill_id[:8]`, guaranteed unique per skill by construction; applied only on first sync (`skill_foundry_service.py:133`) |
| T-28-06 | Tampering | Cloud content → `focus_instruction` | CLOSED | Content round-trips own DB (`export_skill_zip` → Foundry → `download`); `validate_zip_security()` re-checked on every download: `backend/app/services/skill_consumption_service.py:228-236`; injected via unchanged Phase 24 `compose_focus_instruction` channel: `backend/app/services/session_service.py:50,55,89,118-119` |
| T-28-07 | Info Disclosure | Bearer token in `_try_mcp_fetch` | CLOSED | `skill_consumption_service.py:150-200` — token held only in local variable `token` (line 170-172), never logged (log calls at lines 185-190, 199 reference status codes/toolbox/skill names only); defensive `getattr` guards at lines 163-166, 173-174 |
| T-28-08 | DoS | mount/MCP probe/download at session+message time | CLOSED | `asyncio.to_thread` + explicit `timeout=30` in `_try_mcp_fetch` (line 181); `asyncio.to_thread` (SDK-timeout-bound) in `mount_skill_toolbox` (lines 119-137) and `download_and_extract_skill_content` (lines 219-225); no retry loops anywhere; TTL cache bounds cloud chain to once per `(skill.id, foundry_cloud_version)` per 600s (`_CONTENT_CACHE_TTL_SECONDS`, lines 53-73, cache-check at lines 284-321) |
| T-28-09 | Spoofing | `foundry_skill_name` references | ACCEPTED (see log below) | Set exclusively in `skill_foundry_service.py:164` (`sync_skill_to_foundry`) and reset in `:217` (`delete_skill_from_foundry`); never accepted as user input anywhere in `skills.py` or `skill_service.py` |
| T-28-10 | EoP | Toolbox mount / cloud fetch triggers | ACCEPTED (see log below) | `skill_consumption_service.py` functions reached only via `session_service.py:52,97` (`create_session`/`update_sop_progress`), which already enforce authenticated user + scenario ownership upstream (pre-existing, unmodified by Phase 28) |
| T-28-18 | Tampering | Version-pinned scenario drift | CLOSED | `skill_consumption_service.py:80-88` (`_scenario_pin_is_stale`) + `:278-283` (routes any scenario with `skill_version_id` set straight to `load_skill_for_scenario`, bypassing the cloud path unconditionally) |
| T-28-11 | Info Disclosure | `foundry_sync_error` in API responses | CLOSED | `backend/app/schemas/skill.py:85-88` exposes the field (inherited by `SkillOut`); 2000-char truncation at source (see T-28-03); all routes returning it are `require_role("admin")`-gated |
| T-28-12 | EoP | `POST /{id}/foundry-sync`, `GET /{id}/foundry-portal-url` | CLOSED | `backend/app/api/skills.py:561` and `:585` — both use `Depends(require_role("admin"))` identically to `publish`/`archive`/`restore` |
| T-28-14 | Tampering | `retry_foundry_sync` allowed statuses | CLOSED | `backend/app/api/skills.py:573-574` — guard is `if skill.status != "published":`, not a blocklist; archived skills (Foundry entity already deleted) cannot retry. **Post-review hardening confirmed:** commit `f022dae` (WR-02) additionally gates the frontend retry button on `isPublished` in `frontend/src/components/admin/skill-foundry-status-section.tsx:38,134,152-156`, and `frontend/e2e/skill-foundry-sync.spec.ts:220-259` adds an explicit E2E regression test ("retry button is hidden for a never-published (draft) skill") |

### Accept-disposition threats (verified against this document's Accepted Risks Log)

| Threat ID | Category | Component | Status | Rationale |
|-----------|----------|-----------|--------|-----------|
| T-28-05 | EoP | Foundry sync/delete triggers | CLOSED | See Accepted Risks Log #1 |
| T-28-09 | Spoofing | `foundry_skill_name` references | CLOSED | See Accepted Risks Log #2 |
| T-28-10 | EoP | Toolbox mount / cloud fetch triggers | CLOSED | See Accepted Risks Log #3 |
| T-28-13 | DoS | Admin repeatedly clicking retry-sync | CLOSED | See Accepted Risks Log #4 |
| T-28-15 | Info Disclosure | E2E mock fixtures | CLOSED | See Accepted Risks Log #5 |
| T-28-16 | Tampering | `page.route()` interception | CLOSED | See Accepted Risks Log #6 |

---

## Accepted Risks Log

This log is the authoritative record of `accept`-disposition threats for Phase 28. Presence of an entry here closes the corresponding threat for audit purposes.

1. **T-28-05 (EoP — Foundry sync/delete triggers).** Accepted: `sync_skill_to_foundry`/`delete_skill_from_foundry` are only reachable via `publish_skill`/`archive_skill`/`delete_skill` in `skill_service.py`, which are exclusively called from `backend/app/api/skills.py` routes already gated by `Depends(require_role("admin"))`. No new privilege surface is introduced by Phase 28; the existing admin gate is the sole control.

2. **T-28-09 (Spoofing — `foundry_skill_name` references).** Accepted: value is server-set exclusively by `skill_foundry_service.sync_skill_to_foundry` (collision-resistant per T-28-17's fix) and reset by `delete_skill_from_foundry`; never accepted as user input in any request schema (`backend/app/schemas/skill.py`) or route handler. No injection surface into the Toolbox/Skills API via this field.

3. **T-28-10 (EoP — Toolbox mount / cloud fetch triggers).** Accepted: `mount_skill_toolbox`/`_try_mcp_fetch`/`download_and_extract_skill_content` are only reachable via `get_skill_content_for_session`, called from `session_service.create_session`/`update_sop_progress`, both of which are gated by pre-existing (Phase 28-unmodified) authenticated-user + scenario-ownership checks. No new admin-only surface is introduced or bypassed.

4. **T-28-13 (DoS — Admin repeatedly clicking retry-sync).** Accepted: each retry re-runs the already non-blocking, 60s-bounded `sync_skill_to_foundry`; the frontend disables the retry button while a request is pending (`skill-foundry-status-section.tsx:139` — `disabled={retrySyncPending || foundryStatus === "pending"}`), bounding practical abuse to manual, rate-limited-by-UI admin action. No server-side rate limit added; residual risk is bounded by the existing admin-only gate (T-28-12) and the 60s per-call ceiling (T-28-04).

5. **T-28-15 (Info Disclosure — E2E mock fixtures).** Accepted: `frontend/e2e/skill-foundry-sync.spec.ts` is a test-only file never shipped to production; fixture values (`buildSkillFixture`, lines 39-71) are synthetic (e.g. `"e2e-mock-skill"`), not real Foundry identifiers or credentials.

6. **T-28-16 (Tampering — `page.route()` interception).** Accepted: standard Playwright client-side test-isolation mechanism, identical to the pre-existing pattern in `hcp-agent-sync.spec.ts` and `admin-dry-run.spec.ts`; no production request path or trust boundary is affected.

---

## Unregistered Flags

None. No `## Threat Flags` section was present in any of `28-01-SUMMARY.md`, `28-02-SUMMARY.md`, `28-03-SUMMARY.md`, or `28-04-SUMMARY.md` — the executors did not report new attack surface discovered during implementation beyond what PLAN.md's threat registers already covered.

---

## Post-Review Fix Commits Considered

Per audit instructions, the following post-review fix commits were verified as part of this audit (not just the SUMMARY.md narrative):

- `040f43c` (WR-01): extracts resource text at upload time so Foundry sync/ZIP export never ships placeholder stubs for direct PDF/DOCX/PPTX uploads — improves T-28-06 content-integrity assumption (uploaded resources now round-trip real text, not stub markers), `backend/app/api/skills.py:786-802`.
- `f022dae` (WR-02): frontend `isPublished` gate on the retry-sync button — hardens T-28-14's UI/API contract alignment (button is hidden, not just disabled-on-error, for non-published skills), `frontend/src/components/admin/skill-foundry-status-section.tsx:38,134,152-156`.
- `5d3df47` (WR-03): escalates non-404 Foundry-delete failures from `logger.warning` to `logger.error` — improves operational visibility for a potentially-orphaned cloud entity after T-28-05/T-28-17's delete path fails for a non-404 reason, `backend/app/services/skill_foundry_service.py:200-215`.

All three are consistent with, and reinforce, the mitigations already credited above; none introduce a new threat or contradict a disposition in the threat register.

---

SECURITY.md: `.planning/phases/28-sop-skill-ai-foundary-skill-hcp/28-SECURITY.md`
