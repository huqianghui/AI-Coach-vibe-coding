# Phase 30 Acceptance Evidence

## Authoritative status

Requirement 1 implementation and focused acceptance are verified. The 108 stale frontend failures
have been repaired and the complete non-coverage Vitest run is green. The user explicitly waived
the unrelated repository-wide branch coverage gate (77.62% against 82%) for this release; the
configured threshold was not changed. Explicit allowlist staging has not yet occurred, and no
Phase 30 commit or push has been made. Requirement 2 has not started.

## Scope

Requirement 1 only: Unified Training uses the exact session-pinned Microsoft Foundry HCP Prompt Agent version, and that exact version uses authenticated Foundry IQ MCP retrieval. Requirement 2 Skill temporary context is excluded.

## Baseline

- Branch: `feat/0616_shuning`
- Pre-release HEAD: `3a68cbe22c075d425fa63136e8f929537944b55d`
- Baseline matches `origin/main`.
- Phase 30 implementation is uncommitted until every gate below passes.

## Browser acceptance

- Spec: `frontend/e2e/unified-training-pinned-agent.spec.ts`
- Required assertions:
  - Session create body contains only `scenario_id` and `mode`.
  - Browser never submits Agent name/version, continuation state, Skill focus, or additional instructions.
  - Text SSE renders Agent output, key-message state, and coaching hints.
  - Existing session continues to expose its original Agent name/version after mutable HCP data changes.
  - Voice Live first WebSocket frame contains only trusted `session_id`.
- Status: passed again on 2026-07-28 with system Edge via the optional
  `PLAYWRIGHT_EXECUTABLE_PATH` override: 4 passed, 0 failed, 0 skipped.

## Real Azure Foundry IQ acceptance

- Test: `backend/tests/integration/test_unified_training_foundry_kb.py`
- The test is read-only for Azure resources and rolls back its local Session transaction.
- It resolves identity through production `create_session()`.
- It inspects exact `client.agents.get_version(agent_name, agent_version)` output.
- It requires an authenticated MCP project connection and allowed tools exactly `knowledge_base_retrieve`.
- It invokes production `chat_with_agent()` with the same pin and checks an operator-provided KB-exclusive marker.
- Target project: `ai-coach-demo` on `ai-coach-demo-resource`.
- Search service: `aicoach-demo-srch-iq`; Knowledge Base: `unified-training-iq-kb`.
- Authenticated RemoteTool connection: `kb-unified-training-iq-kb-0be101`.
- Exact Agent: `Dr-Chen-Jun` version `5`, restricted to
  `knowledge_base_retrieve`.
- Production Session creation snapshotted `Dr-Chen-Jun` version `5` from HCP
  `4f81e52b-8179-443e-9d14-fc35129565ac` and active F2F scenario
  `3474aa63-7d26-47c3-a126-281f02ff2bd0`.
- Latest release run on 2026-07-28: **1 passed, 0 skipped** in 15.65 seconds.
- Nonsecret evidence: MCP host `aicoach-demo-srch-iq.search.windows.net`, allowed tools
  exactly `knowledge_base_retrieve`, response ID
  `resp_00b5d61f36d80b8a006a68814df7048196868834bd3568fb72`, marker matched `true`,
  question SHA-256 `4430a5621b2c23925337a52ec412d029bcc45d615ef38cb678d86724b89c58e4`.

### Azure run history

| Order | Result | Response ID |
|---:|---|---|
| Earlier evidence run | 1 passed, 0 skipped | `resp_0f148e80612f9314006a686372af388193924460ab7fdd6a48` |
| Latest release rerun | 1 passed, 0 skipped | `resp_00b5d61f36d80b8a006a68814df7048196868834bd3568fb72` |

## Release gates

| Gate | Required result | Current result |
|---|---:|---|
| Disposable Alembic upgrade/downgrade/re-upgrade | pass | passed |
| Backend Ruff check and format check | pass | passed: 340 files formatted |
| Backend full pytest assertions | pass | 2554 passed, 153 skipped, 28 deselected, 0 failed |
| Backend global coverage | at least 89% | completed full run was 88.95%; 7 subsequently covered lines imply about 89.01%, but the user waived another 22-minute full rerun, so no final full-run artifact proves it |
| Final audio-transcoding focused closure | pass | 5 passed; service reached 100%, covering the final 7 lines |
| Changed Python code coverage | 100% | 187/187, 100% |
| Frontend TypeScript check | pass | passed |
| Frontend full Vitest | pass | 2422 passed, 0 failed after repairing 108 stale failures and test-infrastructure issues |
| Frontend global coverage | configured thresholds | statements 91.04%, functions 82.65%, lines 91.04% pass; branches 77.62% fail configured 82% threshold |
| Frontend production build | pass | passed |
| Changed TypeScript line coverage | 100% | 2/2 executable changed lines, 100% |
| Phase 30 Playwright | nonzero pass, zero fail/skip | 4 passed, 0 failed/skipped |
| Real Azure Foundry IQ | exactly 1 pass, zero skip | 1 passed, 0 skipped |
| Protected-path hash comparison | exact match | passed: all 6 manifest entries unchanged |
| Explicit allowlist staging audit | pass | pending |
| Single commit and push | remote SHA equals local SHA | pending |

## Integration correction discovered during acceptance

The backend session Voice Live path now correctly reports Agent mode. The existing Unified Training page still rejected any Agent-mode connection and disconnected it. The page and its unit test were corrected so a server-authorized Agent connection remains active. Focused result: 21 Unified Session tests passed and TypeScript compilation passed.

## Protected unrelated paths

The following paths must remain unmodified and unstaged throughout release:

- `.planning/debug/ci-backend-skill-injection.md`
- `.planning/debug/local-scenarios-missing.md`
- `.planning/debug/skill-sop-runtime-orchestration.md`
- `backend/storage/db-backups/`

The post-run comparison was performed before staging. All six entries matched byte-for-byte;
protected paths remain explicitly excluded from any future allowlist staging.

### Pre-release SHA-256 manifest

| Path | Bytes | SHA-256 |
|---|---:|---|
| `.planning/debug/ci-backend-skill-injection.md` | 8247 | `d328d5a6d11af3c91a78875fe80fe5844c835baf1809d8b154e99d4f2b213611` |
| `.planning/debug/local-scenarios-missing.md` | 9163 | `89cb3f22c81d4a6088bb5fabcc2dd6e96dbd9cea3961a3bba098b35ccc2838d2` |
| `.planning/debug/skill-sop-runtime-orchestration.md` | 11594 | `190604bb207d0705d18a282fd0a9d2825105e7e38453e7679d7bbade8824b5cf` |
| `backend/storage/db-backups/2026-07-16-scenario-recovery/ai_coach.db` | 2932736 | `3fc49345e3cdbc1ade8877e977b0900b00d2d7a8162246690611ac35d9802616` |
| `backend/storage/db-backups/2026-07-16-scenario-recovery/ai_coach.db-shm` | 32768 | `bc34ab4c2c0dcf1173c37dc7d941dc77344c31f58b4fca71868f45e664f596e0` |
| `backend/storage/db-backups/2026-07-16-scenario-recovery/ai_coach.db-wal` | 4054112 | `f08387a90700bbf8db74de915cc0869392c8d466338dbfd35ed01360a22c3a09` |

### Post-run SHA-256 comparison — 2026-07-28

| Path | Post-run SHA-256 | Comparison |
|---|---|---|
| `.planning/debug/ci-backend-skill-injection.md` | `d328d5a6d11af3c91a78875fe80fe5844c835baf1809d8b154e99d4f2b213611` | equal |
| `.planning/debug/local-scenarios-missing.md` | `89cb3f22c81d4a6088bb5fabcc2dd6e96dbd9cea3961a3bba098b35ccc2838d2` | equal |
| `.planning/debug/skill-sop-runtime-orchestration.md` | `190604bb207d0705d18a282fd0a9d2825105e7e38453e7679d7bbade8824b5cf` | equal |
| `backend/storage/db-backups/2026-07-16-scenario-recovery/ai_coach.db` | `3fc49345e3cdbc1ade8877e977b0900b00d2d7a8162246690611ac35d9802616` | equal |
| `backend/storage/db-backups/2026-07-16-scenario-recovery/ai_coach.db-shm` | `bc34ab4c2c0dcf1173c37dc7d941dc77344c31f58b4fca71868f45e664f596e0` | equal |
| `backend/storage/db-backups/2026-07-16-scenario-recovery/ai_coach.db-wal` | `f08387a90700bbf8db74de915cc0869392c8d466338dbfd35ed01360a22c3a09` | equal |

## Scope audit

- Text Session routing contains no generic adapter registry, `CoachRequest`, local prompt builder,
  `focus_instruction`, `additional_instructions`, or temporary Skill context.
- Session-bound Voice Live forces exact Agent mode, copies the Session-pinned name/version, and
  sets `instructions` to an empty string.
- `_compose_session_instructions()` remains only for standalone/non-session legacy behavior. The
  Unified Training Session branch does not call it.
- The `force_model_mode` argument used while loading Session configuration prevents mutable HCP
  Agent identity from being selected during that stage; the immediately following Session branch
  authoritatively replaces the result with exact Agent mode. It is not a model fallback.

## Git state — 2026-07-28

- Branch: `feat/0616_shuning`.
- Local HEAD: `3a68cbe22c075d425fa63136e8f929537944b55d`.
- Staged files: 0; `git diff --check` passed.
- Remote-tracking `origin/feat/0616_shuning`: `70d536573e8a5f2816910229c9d7b7d5c3315204`.
- No Phase 30 commit or push exists. Final local/remote SHA equality is therefore not applicable.
- Tracked root database sidecars were restored explicitly before staging. Protected debug
  documents and database backups remain untracked and must stay unstaged.
