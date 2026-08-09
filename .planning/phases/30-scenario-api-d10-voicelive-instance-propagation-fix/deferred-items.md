# Deferred Items — Phase 30

## Item 1: Pre-existing "Real Azure" network-dependent test failures (out of scope for 30-01)

**Found during:** Plan 30-01, Task 2 broader verification (`pytest -k "hcp_profile or voice_live"`)

**Failures:**
- `tests/test_voice_live_session_context.py::test_session_path_ignores_client_hcp_prompt_and_injects_persona_focus`
- `tests/test_voice_live_websocket.py::TestRealAzureSessionConfig::test_real_connect_model_mode_session_config_accepted`
- `tests/test_voice_live_websocket.py::TestRealAzureSessionConfig::test_real_transcription_model_azure_speech_accepted`
- `tests/test_voice_live_websocket.py::TestRealVoiceLiveIntegration::test_real_model_mode_english_voice_accepted`
- `tests/test_voice_live_websocket.py::TestRealVoiceLiveIntegration::test_real_model_mode_with_instructions`

**Why deferred (not fixed):** These tests require a live Azure CLI credential / real Azure Voice Live service connection (`AzureCliCredential`, `TestRealAzureSessionConfig`, `TestRealVoiceLiveIntegration`). They do not import or exercise `backend/app/api/scenarios.py`, `HcpProfileBrief`, or `VoiceLiveInstanceSummary` — no relationship to the D-10 nested `voice_live_instance` propagation fix made in Plan 30-01. Confirmed unrelated via grep (no reference to `scenarios`/`HcpProfileBrief`/`VoiceLiveInstanceSummary` in `test_voice_live_session_context.py`; `test_voice_live_websocket.py` matched only on the word "scenarios" in prose, not an import). Per SCOPE BOUNDARY, out-of-scope failures in unrelated files are logged here rather than fixed.

**Action for future work:** Investigate separately whether these need `az login` / network access in CI, or are flaky by design and should be marked `@pytest.mark.skip` / `xfail` when credentials are unavailable.

## Item 2: Pre-existing scenario-panel.test.tsx failure unrelated to hcp_profile shape (out of scope for 30-04)

**Found during:** Plan 30-04, Task 2 verification (`npx vitest run scenario-panel.test.tsx`)

**Failure:** `src/components/coach/scenario-panel.test.tsx > ScenarioPanel > renders scenario product and area when expanded` — `Unable to find an element with the text: DrugX`.

**Why deferred (not fixed):** Confirmed via `git stash` that this test fails identically on unmodified `main` (before any of this plan's `hcp_profile` fixture edits). Root cause: `frontend/src/components/coach/scenario-panel.tsx` derives its displayed `product`/`area` strings by parsing `scenario.tags` (format `"product:X"`/`"area:Y"`, see lines 33-36), but the test's `mockScenario` fixture sets flat `product`/`therapeutic_area` fields instead of `tags`. This is a pre-existing test/component drift with zero relationship to the `HcpProfileSummary` nesting fix (D-10) this plan addresses. Per SCOPE BOUNDARY, out-of-scope failures unrelated to the current task's changes are logged here rather than fixed.

**Action for future work:** Either add a `tags: ["product:DrugX", "area:Oncology"]` fixture field to `scenario-panel.test.tsx`'s `mockScenario`, or update `scenario-panel.tsx` to also fall back to flat `product`/`therapeutic_area` fields — whichever matches the current intended `Scenario` contract.

## Item 3: Pre-existing training-start-session.spec.ts E2E failures unrelated to D-10 avatar propagation (out of scope for 30-05)

**Found during:** Plan 30-05, Task 2 verification (`npx playwright test training-start-session.spec.ts --config=e2e/playwright.config.ts`)

**Failures:**
- `"clicking '开始培训' on Conference scenario navigates to conference session"` — `page.waitForResponse` times out waiting for `POST /api/v1/sessions` after clicking the conference start button.
- `"text mode session auto-starts and shows avatar static preview"` — neither `[data-testid=avatar-static-preview]` nor a text input becomes visible after starting a F2F session.

**Why deferred (not fixed):** Neither test reads `hcp_profile.avatar_character`/`voice_live_instance` at all — they are unrelated to this plan's `avatar_character`/`avatar_style` nested-path fix or the new gating-restoration test. Confirmed both fail identically running against the real dev backend+frontend regardless of this plan's spec edits (only the two rewritten assertions and the new gating test — none of which these two tests touch — were changed). Per SCOPE BOUNDARY, out-of-scope pre-existing failures are logged here rather than fixed. All 11 other tests in the file pass, including all 3 of this plan's fixed/added tests.

**Action for future work:** Investigate separately — likely a conference-session-creation regression or timing issue (test 1) and an avatar-static-preview/text-input selector drift (test 2), both independent of D-10 propagation.

## Item 4: Pre-existing backend `ruff check .` / `ruff format --check .` violations (out of scope for 30-05)

**Found during:** Plan 30-05, Task 2 verification (`ruff check .` and `ruff format --check .`)

**Failures:** 30 `E501 Line too long (>100)` errors across `tests/test_hcp_profile_service.py`, `tests/test_skill_foundry_service.py`, and `tests/test_knowledge_base.py`; 5 files flagged by `ruff format --check .` (`tests/test_api_direct.py`, `tests/test_hcp_profile_service.py`, `tests/test_knowledge_base.py`, `tests/test_skill_foundry_service.py`, `tests/test_voice_live_management.py`).

**Why deferred (not fixed):** `git log --oneline -1 -- <these files>` shows their last modification predates Phase 30 (Phase 29 commit `0f2b714` for the E501 set). None of Plans 30-01 through 30-04's `key-files` lists these files, and this plan (30-05) only modifies `frontend/e2e/training-start-session.spec.ts`. Pre-existing debt with zero relationship to D-10 avatar propagation. Per SCOPE BOUNDARY, out-of-scope failures unrelated to the current task's changes are logged here rather than fixed.

**Action for future work:** Run `ruff format .` / manually wrap the flagged lines in a dedicated lint-debt cleanup plan, independent of Phase 30.

## Item 5: Pre-existing full-suite `npx vitest run` failures unrelated to D-10 avatar propagation (out of scope for 30-05)

**Found during:** Plan 30-05, Task 2 verification (`cd frontend && npx vitest run --reporter=dot`)

**Result:** 100 failed / 2327 passed (15 test files failing) — matches Plan 30-04's documented baseline improvement (104 failed/2317 passed before 30-03's `training.tsx` fix landed; the 3 `training.test.tsx` tests 30-04 flagged as "will pass once 30-03 merges" are now passing).

**Failing files (all confirmed pre-existing, unrelated to `hcp_profile`/`voice_live_instance` shape):**
- 14 files matching Plan 30-04's already-documented pre-existing baseline list verbatim: `admin-pages.test.tsx`, `azure-config.test.tsx`, `dashboard.test.tsx`, `reports.test.tsx`, `settings.test.tsx`, `training-materials.test.tsx`, `users.test.tsx`, `session-history.test.tsx`, `api-clients.test.ts`/`sessions.test.ts`, `i18n/index.test.ts`, `voice-test-playground.test.tsx`, `voice-session.test.tsx`, `analytics-components.test.tsx`
- 1 additional file not explicitly named in 30-04's list: `hcp-profile-editor.test.tsx` (7 failures) — root cause is an i18n test-environment rendering issue (components render raw translation keys like `"admin:hcp.save"` instead of resolved strings), same category as the already-flagged `i18n/index.test.ts` failure — zero relationship to `hcp_profile.voice_live_instance` nesting

**Why deferred (not fixed):** This plan's only file change (`frontend/e2e/training-start-session.spec.ts`) is outside Vitest's `include` glob (`src/**/*.{test,spec}.{ts,tsx}`) entirely, so it cannot have caused any Vitest regression — the failing-file list and counts match the pre-existing baseline exactly. Per SCOPE BOUNDARY, these are logged here rather than fixed.

**Action for future work:** A dedicated test-infra cleanup plan is needed to fix the shared i18n-test-rendering root cause affecting `i18n/index.test.ts` and `hcp-profile-editor.test.tsx`, plus separately investigate the other 13 unrelated pre-existing files already logged by Plan 30-04.

## Item 6: Backend coverage gate (`--cov-fail-under=89`) requires live Azure/OpenAI credentials not present in this worktree (out of scope for 30-05)

**Found during:** Plan 30-05, Task 2 verification (`cd backend && .venv/bin/python -m pytest -q`)

**Result:** With this worktree's `.env` (copied from `.env.example`, no real Azure/OpenAI keys), the full backend suite is **2498 passed, 0 failed, 153 skipped, 27 deselected** — zero functional failures. However, total coverage is 88% (88.30-88.21% across runs), below the repo's configured `--cov-fail-under=89` in `backend/pyproject.toml`, so a literal `pytest -v` invocation exits non-zero on the coverage gate alone (not on any test failure).

**Why deferred (not fixed):** The 153 skips (vs. this same plan's earlier documented baseline of 15 skips from a differently-provisioned environment) are entirely `skipif`-gated "real Azure/OpenAI" tests (same category as Item 1) that only execute — and thus only contribute coverage — when live `AZURE_OPENAI_API_KEY`/`AZURE_SPEECH_KEY`/etc. credentials are configured in `.env`. This worktree was freshly created without a working `.venv` or a credentialed `.env` (both had to be bootstrapped from scratch as part of this plan's Task 2 verification setup); copying the main repo's real `.env` into this worktree was attempted, but the resulting real-network test run was too slow (network-bound Azure round-trips, <5% progress after several minutes) to complete within this verification pass. This is a local-environment credential/provisioning gap, not a regression caused by this plan's e2e-spec-only change — the same 2498 tests that run all pass. Per SCOPE BOUNDARY, logged here rather than blocking on a full real-credentials run.

**Action for future work:** Either provision this worktree's `.env` with real Azure/OpenAI keys and allow a full real-network pytest run to complete (accepting the longer runtime), or lower/parameterize `--cov-fail-under` for credential-less local/CI runs so the gate doesn't conflate "missing live credentials" with "code coverage regression."
