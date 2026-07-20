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
