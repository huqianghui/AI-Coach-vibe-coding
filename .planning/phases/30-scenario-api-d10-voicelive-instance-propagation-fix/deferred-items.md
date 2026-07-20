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
