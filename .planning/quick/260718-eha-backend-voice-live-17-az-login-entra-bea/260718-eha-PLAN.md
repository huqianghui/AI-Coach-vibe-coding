---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/tests/test_voice_live.py
  - backend/tests/test_voice_live_service.py
  - backend/tests/test_voice_live_websocket.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Running `pytest backend/tests/test_voice_live.py backend/tests/test_voice_live_service.py backend/tests/test_voice_live_websocket.py -v` with a real `.env` + `az login` locally reports 0 failed (down from 17), with no test count decreasing (no tests silently skipped/deleted to make this pass) versus the pre-fix collection count"
    - "Category 1 (2 tests): `_get_bearer_token` is deterministically mocked so the local `az login` Entra fallback can never make these two `no_key` tests non-deterministic; production `connection_tester.py` code is untouched"
    - "Category 2 (8 real Azure integration tests): every direct-SDK real test that currently does `AzureKeyCredential(REAL_FOUNDRY_API_KEY)` now uses `DefaultAzureCredential()` from `azure.identity.aio`, since the Foundry resource has key-based auth permanently disabled by policy (`AuthenticationTypeDisabled`, confirmed via real 403); production `voice_live_websocket.py` credential-selection logic is untouched -- the 2 handler-level real tests are redirected onto the app's EXISTING keyless/bearer fallback path via DB seeding (empty master API key), not a new code path"
    - "`test_real_exchange_returns_bearer_token` is converted to assert the real, documented 403 `AuthenticationTypeDisabled` policy response from the STS endpoint (via `pytest.raises(httpx.HTTPStatusError)` + status code assertion) instead of expecting a bearer token -- it is never faked to pass and never skipped"
    - "Category 3 (7 tests): stale assertions are corrected to match the actual current behavior of `voice_live_service.py` (no-key -> bearer mode, not an exception; `avatar_available`/`avatar_enabled` reflect the real always-on avatar-in-VoiceLive-session semantics) and `voice_live_websocket.py` (`avatar_enabled` defaults `True`; classic agent connect includes `api_version=\"2025-05-01-preview\"`); no production code in either file is modified to make these pass"
    - "`ruff check backend/tests/test_voice_live.py backend/tests/test_voice_live_service.py backend/tests/test_voice_live_websocket.py` and `ruff format --check` on the same three files report clean"
    - "The full existing backend suite still passes at its prior pass count outside these 3 files (no regression introduced by the `mock_sdk` fixture change, since it restores `sys.modules` exactly as before plus the new `azure.identity`/`azure.identity.aio` stub keys)"
  artifacts:
    - path: "backend/tests/test_voice_live.py"
      provides: "Deterministic Category-1 fix: `_get_bearer_token` patched to return None in the 2 no-key connection-tester tests"
    - path: "backend/tests/test_voice_live_service.py"
      provides: "Corrected stale assertions (no-key -> bearer mode; avatar semantics) + real 403-policy assertion for the STS bearer-token-exchange test"
    - path: "backend/tests/test_voice_live_websocket.py"
      provides: "mock_sdk fixture stubs `azure.identity`/`azure.identity.aio` (fixes 3 classic-agent tests never calling connect()); corrected avatar_enabled/api_version assertions; real Category-2 tests swapped to DefaultAzureCredential or redirected to the keyless DB-seeding path"
  key_links:
    - from: "backend/tests/test_voice_live.py::TestConnectionTester (no_key tests)"
      to: "app.services.connection_tester._get_bearer_token"
      via: "unittest.mock.patch returning None, eliminating the az-login-dependent non-determinism"
      pattern: "patch\\(.*_get_bearer_token"
    - from: "backend/tests/test_voice_live_websocket.py::mock_sdk fixture"
      to: "azure.identity.aio.DefaultAzureCredential (as used by the classic-agent code path in voice_live_websocket.py)"
      via: "sys.modules pre-population with a stub module exposing an async-context-manager-free FakeCredential (get_token/close)"
      pattern: "sys\\.modules\\[.azure\\.identity"
    - from: "backend/tests/test_voice_live_websocket.py (Category 2 real handler tests)"
      to: "app.services.voice_live_websocket.handle_voice_live_websocket credential selection (api_key empty -> DefaultAzureCredential)"
      via: "DB seeding with an empty master api_key_encrypted, driving the existing production keyless fallback"
      pattern: "api_key_encrypted=\"\""
---

<objective>
Fix all 17 currently-failing backend Voice Live tests across `test_voice_live.py`, `test_voice_live_service.py`, and `test_voice_live_websocket.py` using test-side-only changes. A prior diagnosis (already completed and provided below) traced every failure to one of three root causes: (1) local `az login` making a keyless fallback non-deterministic in 2 connection-tester tests, (2) the shared Azure AI Foundry resource having key-based auth permanently disabled by policy, breaking 8 real-Azure integration tests that use `AzureKeyCredential`, and (3) 7 tests with stale assertions left over from a service redesign (no-key now means bearer mode, not an error; avatar defaults on; classic-agent connect passes `api_version`) plus a `mock_sdk` test fixture missing an `azure.identity.aio` stub that silently prevents `connect()` from ever being called.

Purpose: Restore a fully green backend test suite without weakening any production security/auth behavior, and without faking or skipping any real-Azure integration test that can still genuinely run against the live resource.
Output: 3 test files fixed; 0 failed across all Voice Live tests; ruff clean; no regressions elsewhere.
</objective>

<execution_context>
@/Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/.claude/get-shit-done/workflows/execute-plan.md
@/Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@backend/tests/test_voice_live.py
@backend/tests/test_voice_live_service.py
@backend/tests/test_voice_live_websocket.py
@backend/app/services/voice_live_service.py
@backend/app/services/voice_live_websocket.py
@backend/app/services/connection_tester.py
@backend/app/services/config_service.py
</context>

<interfaces>
<!-- Confirmed by live diagnosis: exact failure modes, exact line numbers, exact current code behavior.
     Do not re-diagnose -- these are empirically confirmed, not guessed. -->

```
Category 1 -- backend/tests/test_voice_live.py
  Line 147-154 test_connection_tester_voice_live_no_key
  Line 192-202 test_connection_tester_dispatch_voice_live
  Root cause: app.services.connection_tester._get_bearer_token() (lines 142-151) calls the REAL
  azure.identity.aio.DefaultAzureCredential locally, and with `az login` active this succeeds,
  making test_azure_voice_live() return success instead of "API key is required". Non-deterministic
  across machines/CI. FIX: patch _get_bearer_token to return None so the assertion is deterministic.
  DO NOT touch connection_tester.py -- production behavior (real keyless fallback) must remain.

Category 2 -- 8 real Azure integration tests, wss/STS 403 (AuthenticationTypeDisabled policy)
  Confirmed via live test runs: the Foundry resource `ai-foundary-hu-sweden-central2` has key-based
  auth DISABLED by policy. Both the STS token-exchange endpoint AND the wss connect endpoint reject
  AzureKeyCredential/API-key auth with 403. DefaultAzureCredential (Entra, via az login) is the only
  auth path that works on this resource. The SDK's connect() accepts
  Union[AzureKeyCredential, AsyncTokenCredential] (confirmed via azure/ai/voicelive/aio/_patch.py
  line 674) with default credential_scopes=["https://ai.azure.com/.default"] (line 686) when no
  credential_scopes kwarg is passed -- this default scope is what the app's own model-mode connect
  call already uses successfully, so no credential_scopes override is needed for the swap below.

  5 direct-SDK real tests in test_voice_live_websocket.py, ALL do:
    credential = AzureKeyCredential(REAL_FOUNDRY_API_KEY)
    async with connect(endpoint=REAL_FOUNDRY_ENDPOINT, credential=credential, model=model) as azure_conn:
  FIX: swap to `from azure.identity.aio import DefaultAzureCredential` + `credential = DefaultAzureCredential()`.
  No credential_scopes kwarg needed (default already works). Locations:
    - TestRealAzureSessionConfig.test_real_connect_model_mode_session_config_accepted (line 2417)
    - TestRealAzureSessionConfig.test_real_transcription_model_azure_speech_accepted (line 2459)
    - TestRealVoiceLiveIntegration.test_real_model_mode_full_session_config_accepted (line 2622)
    - TestRealVoiceLiveIntegration.test_real_model_mode_english_voice_accepted (line 2673)
    - TestRealVoiceLiveIntegration.test_real_model_mode_with_instructions (line 2717)

  2 handler-level real tests in test_voice_live_websocket.py call handle_voice_live_websocket()
  through the real seeded_db fixture, which seeds a REAL API key on the master config -- the
  production code (voice_live_websocket.py lines 595-601) picks AzureKeyCredential whenever
  cfg["api_key"] is non-empty, so these hit the same 403. FIX: do NOT change production credential
  selection. Instead seed a DB variant with an EMPTY master api_key_encrypted, which makes
  config_service.get_effective_key() resolve to "" (confirmed in config_service.py lines 218-233:
  falls back to master key only if master has one; empty encrypted value -> empty secret), driving
  the app's EXISTING keyless DefaultAzureCredential fallback (voice_live_websocket.py line 599-601)
  for real. This is the SAME already-working production code path used by Category 1's fix target
  and by every other currently-green real test on this resource -- no new production code needed.
    - test_real_handler_model_mode_proxy_connected (line 3055, uses `seeded_db`)
    - test_real_handler_vl_instance_model_mode (line 3146, uses `vl_instance_standalone` which
      itself depends on `seeded_db` -- do NOT modify the shared `seeded_db`/`vl_instance_standalone`
      fixtures since other passing tests, including mocked ones, depend on their real-key behavior;
      instead give each of these 2 tests its own no-key DB setup)

  1 real test in test_voice_live_service.py exercises a dead endpoint on this resource:
    TestRealTokenExchange.test_real_exchange_returns_bearer_token (line 456)
  Confirmed via live run: raises httpx.HTTPStatusError 403 Forbidden calling
  .../sts/v1.0/issueToken. This endpoint is API-key-only by design (STS token exchange takes an
  Ocp-Apim-Subscription-Key header, there is no Entra equivalent) and is permanently blocked by the
  same resource policy. FIX: convert the test to assert this real, documented policy behavior --
  pytest.raises(httpx.HTTPStatusError) and assert the real response status_code == 403 -- instead of
  asserting success. This keeps the test real (it still makes a live call and asserts on the live,
  reproducible outcome) without faking success or skipping it.

Category 3 -- stale assertions from service redesign (commit 22866fd) + missing mock_sdk stub

  backend/tests/test_voice_live_service.py:
    - test_raises_when_api_key_missing (TestGetVoiceLiveTokenErrors) currently does
      `with pytest.raises(ValueError, match="API key not set"): await get_voice_live_token(db_session)`
      but get_voice_live_token() (voice_live_service.py) no longer raises for a missing key -- it
      returns successfully with auth_type="bearer", token="***configured***". FIX: replace the
      pytest.raises block with a direct await + assert result.auth_type == "bearer" and
      result.token == "***configured***".
    - test_status_both_available (TestGetVoiceLiveStatus; asserts avatar_available is False) --
      confirmed via code trace that get_voice_live_status() computes avatar_available from
      vl_endpoint (Voice Live's OWN effective endpoint resolution), NOT from azure_avatar.is_active,
      so with the seeded_db fixture (voice_live is_active=True with an inherited real endpoint via
      master fallback) avatar_available is actually True. FIX: change assertion to
      `assert result.avatar_available is True` and update the docstring/comment to explain avatar
      availability piggybacks on Voice Live's own endpoint resolution, not the separate
      azure_avatar config row.

  backend/tests/test_voice_live_websocket.py:
    - mock_sdk fixture / _install_mock_sdk() (lines 577-639): stubs azure.ai.voicelive.aio,
      azure.ai.voicelive.models, azure.core.credentials, and parent packages azure/azure.ai/
      azure.ai.voicelive/azure.core -- but does NOT stub azure.identity.aio. The classic-agent
      connect path in voice_live_websocket.py (lines 757-764) does
      `from azure.identity.aio import DefaultAzureCredential as _DAC` -- with no azure.identity.aio
      in sys.modules and `azure` replaced by a bare types.ModuleType with no __path__, this raises
      ModuleNotFoundError: No module named 'azure.identity'; 'azure' is not a package, which is
      swallowed by the handler's broader try/except around the connect block, silently resulting in
      connect() never being called (call count 0) for every classic-agent (asst_* agent_id) test.
      FIX: inside _install_mock_sdk(), add a stub `azure.identity` and `azure.identity.aio` module
      exposing a fake async DefaultAzureCredential class with async get_token(*scopes) returning an
      object with a `.token` attribute, and an async close(). Register both into sys.modules
      alongside the existing entries (mirroring how azure.core parent + azure.core.credentials are
      already both registered). No need to change the function's return tuple signature -- no test
      currently destructures a 4th/5th value; just add the two new sys.modules keys inside
      _install_mock_sdk(). Confirmed working via a standalone verification script (sys.modules
      pre-population is sufficient without azure.identity needing __path__, because Python's import
      system resolves an exact dotted name already present in sys.modules directly without needing
      parent-package machinery).
    - test_agent_mode_connect_uses_agent_parameters (line 1259-1316): after the mock_sdk fix above,
      connect() WILL be called, but its existing assertion `assert "api_version" not in call_kwargs`
      (line 1304) will fail because the classic-agent code path actually always passes
      api_version="2025-05-01-preview". FIX: replace that line with
      `assert call_kwargs["api_version"] == "2025-05-01-preview"`.
    - test_agent_mode_failure_no_fallback (line 1358-1413) and
      test_agent_mode_does_not_require_agent_session_config (line 2320-2362): only need the mock_sdk
      fixture fix above -- their existing assertions do not check api_version and remain correct
      once connect() is actually invoked.
    - test_avatar_disabled_when_inactive (line 355-359): asserts
      `cfg["avatar_enabled"] is False` when azure_avatar is inactive, but
      _load_connection_config() (voice_live_websocket.py) sets result["avatar_enabled"] = True
      unconditionally (only avatar_character is conditionally overridden by an active azure_avatar
      row) -- this is intentional per that file's own comment: "avatar is a Voice Live session
      modality and does not require a separate azure_avatar config row." FIX: rename the test to
      test_avatar_enabled_even_when_avatar_config_inactive and change the assertion to
      `assert cfg["avatar_enabled"] is True`, updating the docstring to explain the real semantics.
    - test_sends_proxy_connected_on_success (line 678-709): line 706
      `assert msg["avatar_enabled"] is False` -- same root cause, FIX to
      `assert msg["avatar_enabled"] is True`.
    - test_real_handler_model_mode_proxy_connected (line 3055-3085): line 3083
      `assert msg["avatar_enabled"] is False` -- same root cause AND needs the Category-2 no-key DB
      fix from above in the same edit pass; FIX both together.
```
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Fix Category 1 non-determinism in test_voice_live.py</name>
  <files>backend/tests/test_voice_live.py</files>
  <action>
    In `TestConnectionTester`, fix the two tests that are non-deterministic locally because
    `app.services.connection_tester._get_bearer_token()` succeeds via the real `DefaultAzureCredential`
    when `az login` is active:

    1. `test_connection_tester_voice_live_no_key` (around line 147): wrap the body in
       `@patch("app.services.connection_tester._get_bearer_token", new_callable=AsyncMock, return_value=None)`
       (add the decorator above the method, add the mock as the method's first parameter after `self`,
       e.g. `async def test_connection_tester_voice_live_no_key(self, mock_get_bearer):`). Keep the
       existing call to `_test_azure_voice_live(...)` and existing assertions unchanged -- they become
       deterministic once the bearer fallback always returns None in this test.
    2. `test_connection_tester_dispatch_voice_live` (around line 192): apply the identical
       `@patch("app.services.connection_tester._get_bearer_token", new_callable=AsyncMock, return_value=None)`
       decorator and parameter, keep the existing `_test_service_connection(...)` call and assertions.

    Do not modify `app/services/connection_tester.py` -- the real keyless fallback behavior must remain
    intact for production and for the other passing tests in this file that rely on it implicitly.
    `unittest.mock.patch` and `AsyncMock` are already imported at the top of this file (line 5) --
    no new imports needed.
  </action>
  <verify>
    <automated>cd /Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/backend && .venv/bin/python3 -m pytest tests/test_voice_live.py -v 2>&1 | tail -40</automated>
  </verify>
  <done>
    `test_connection_tester_voice_live_no_key` and `test_connection_tester_dispatch_voice_live` pass
    deterministically regardless of local `az login` state. All other tests in `test_voice_live.py`
    remain green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Fix stale assertions and convert one dead-endpoint real test in test_voice_live_service.py</name>
  <files>backend/tests/test_voice_live_service.py</files>
  <action>
    1. `test_raises_when_api_key_missing` (`TestGetVoiceLiveTokenErrors`): replace the
       `with pytest.raises(ValueError, match="API key not set"): await get_voice_live_token(db_session)`
       block with a direct call and assertions matching current behavior (no-key means bearer mode,
       not an exception):
       ```python
       result = await get_voice_live_token(db_session)
       assert result.auth_type == "bearer"
       assert result.token == "***configured***"
       ```
       Update the docstring from "raises ValueError when API key is not set" to
       "returns bearer auth_type when API key is not set (no exception)".

    2. `test_status_both_available` (`TestGetVoiceLiveStatus`): change
       `assert result.avatar_available is False` to `assert result.avatar_available is True`.
       Update the docstring/comment to explain that `avatar_available` is derived from Voice Live's
       own effective endpoint resolution (which resolves via master fallback in `seeded_db`), not from
       the separate `azure_avatar` config row's `is_active` flag -- so it is True here even though
       `azure_avatar` itself is seeded inactive.

    3. `TestRealTokenExchange.test_real_exchange_returns_bearer_token`: replace the current body
       (which expects a JWT string) with an assertion of the real, confirmed 403 policy response.
       `httpx` and `pytest` are already imported in this module (used elsewhere in this same test
       class). Replace:
       ```python
       token = await _exchange_api_key_for_bearer_token(cog_endpoint, REAL_FOUNDRY_API_KEY)
       assert isinstance(token, str)
       assert len(token) > 0
       parts = token.split(".")
       assert len(parts) == 3, f"Expected JWT with 3 parts, got {len(parts)}"
       ```
       with:
       ```python
       import httpx

       with pytest.raises(httpx.HTTPStatusError) as exc_info:
           await _exchange_api_key_for_bearer_token(cog_endpoint, REAL_FOUNDRY_API_KEY)
       assert exc_info.value.response.status_code == 403
       ```
       (place the `import httpx` at the top of the test method body if `httpx` is not already imported
       module-wide in this test class -- check first and avoid a duplicate import if it already is).
       Update the docstring to: "Real STS call is rejected with 403 because this Foundry resource has
       key-based auth disabled by policy (AuthenticationTypeDisabled) -- this endpoint has no Entra
       equivalent, so 403 is the correct, permanent, real outcome for this resource, not a bug."
       Do NOT change `test_real_exchange_invalid_key_raises` (already expects HTTPStatusError, still
       correct) or `test_real_get_voice_live_token_returns_config` (not in the failing set, no network
       call, leave untouched).

    Do not modify `app/services/voice_live_service.py` -- every fix here reflects the real, current,
    intentional behavior of that file.
  </action>
  <verify>
    <automated>cd /Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/backend && .venv/bin/python3 -m pytest tests/test_voice_live_service.py -v 2>&1 | tail -60</automated>
  </verify>
  <done>
    `test_raises_when_api_key_missing`, `test_status_both_available`, and
    `test_real_exchange_returns_bearer_token` pass. `test_real_exchange_invalid_key_raises` and
    `test_real_get_voice_live_token_returns_config` remain unchanged and green. No production code in
    `app/services/voice_live_service.py` was modified.
  </done>
</task>

<task type="auto">
  <name>Task 3: Fix mock_sdk fixture, stale assertions, and Category-2 credential swaps in test_voice_live_websocket.py</name>
  <files>backend/tests/test_voice_live_websocket.py</files>
  <action>
    1. Fix the `mock_sdk` fixture root cause (`_install_mock_sdk()`, lines 577-639): add stub
       `azure.identity` and `azure.identity.aio` modules alongside the existing stubbed packages, so
       the classic-agent code path's `from azure.identity.aio import DefaultAzureCredential as _DAC`
       resolves instead of raising `ModuleNotFoundError`. Add this inside `_install_mock_sdk()`,
       following the same pattern as the existing `azure.core`/`azure.core.credentials` pair:
       ```python
       # --- azure.identity.aio module (stub for classic-agent DefaultAzureCredential path) ---
       identity_aio_mod = types.ModuleType("azure.identity.aio")

       class _FakeDefaultAzureCredential:
           async def get_token(self, *scopes):
               class _FakeToken:
                   token = "fake-mock-sdk-token"

               return _FakeToken()

           async def close(self):
               pass

       identity_aio_mod.DefaultAzureCredential = _FakeDefaultAzureCredential

       azure_identity = types.ModuleType("azure.identity")

       sys.modules["azure.identity"] = azure_identity
       sys.modules["azure.identity.aio"] = identity_aio_mod
       ```
       Place the `azure.identity`/`azure.identity.aio` construction near the other module
       constructions (before the "Install into sys.modules" block) and add
       `sys.modules["azure.identity"] = azure_identity` and
       `sys.modules["azure.identity.aio"] = identity_aio_mod` inside the existing
       "Install into sys.modules" block alongside the other `sys.modules[...] = ...` lines. Do not
       change the function's return statement/signature.

    2. `test_agent_mode_connect_uses_agent_parameters` (line ~1259-1316): replace
       `assert "api_version" not in call_kwargs` (line ~1304) with
       `assert call_kwargs["api_version"] == "2025-05-01-preview"`.

    3. `test_agent_mode_failure_no_fallback` (line ~1358-1413) and
       `test_agent_mode_does_not_require_agent_session_config` (line ~2320-2362): no assertion
       changes needed -- they pass once fix #1 makes `connect()` actually get called.

    4. `test_avatar_disabled_when_inactive` (line ~355-359, in `TestLoadConnectionConfig`): rename to
       `test_avatar_enabled_even_when_avatar_config_inactive`, update the docstring to
       "Avatar stays enabled even when azure_avatar config is inactive -- avatar is a Voice Live
       session modality, not gated by the separate azure_avatar config row", and change
       `assert cfg["avatar_enabled"] is False` to `assert cfg["avatar_enabled"] is True`.

    5. `test_sends_proxy_connected_on_success` (line ~678-709): change
       `assert msg["avatar_enabled"] is False` (line ~706) to `assert msg["avatar_enabled"] is True`.

    6. Category 2 direct-SDK real tests -- in each of the 5 locations below, replace the
       `from azure.core.credentials import AzureKeyCredential` + `credential = AzureKeyCredential(REAL_FOUNDRY_API_KEY)`
       pair with `from azure.identity.aio import DefaultAzureCredential` +
       `credential = DefaultAzureCredential()`. Leave every other line (connect() call, session_config,
       assertions) unchanged in each:
       - `TestRealAzureSessionConfig.test_real_connect_model_mode_session_config_accepted` (~line 2417)
       - `TestRealAzureSessionConfig.test_real_transcription_model_azure_speech_accepted` (~line 2459)
       - `TestRealVoiceLiveIntegration.test_real_model_mode_full_session_config_accepted` (~line 2622)
       - `TestRealVoiceLiveIntegration.test_real_model_mode_english_voice_accepted` (~line 2673)
       - `TestRealVoiceLiveIntegration.test_real_model_mode_with_instructions` (~line 2717)
       Do not add a `credential_scopes` kwarg to `connect()` in any of these -- the SDK's default
       `["https://ai.azure.com/.default"]` scope already works for this app's model-mode path.

    7. Category 2 handler-level real tests -- give each of these 2 tests its own no-key DB setup
       instead of relying on the shared `seeded_db`/`vl_instance_standalone` fixtures (which other
       passing tests still need with a real key):
       - `test_real_handler_model_mode_proxy_connected` (~line 3055, currently takes `seeded_db` as a
         fixture arg): stop taking the `seeded_db` fixture; instead take `db_session` directly and
         seed the same three `ServiceConfig` rows inline (master `ai_foundry`, `azure_voice_live`,
         `azure_avatar`) exactly as `seeded_db` does, EXCEPT set the master's
         `api_key_encrypted=""` (empty, not `encrypt_value(REAL_FOUNDRY_API_KEY)`) so
         `config_service.get_effective_key()` resolves to `""` and the handler takes its existing
         `DefaultAzureCredential` fallback path for real. Also fix the stale assertion on this test:
         change `assert msg["avatar_enabled"] is False` to `assert msg["avatar_enabled"] is True`
         (same Category 3 root cause as task items 4/5 above).
       - `test_real_handler_vl_instance_model_mode` (~line 3146, currently takes
         `vl_instance_standalone` as a fixture arg): stop taking that fixture; instead take
         `db_session` directly, seed the same no-key master/voice_live/avatar rows inline (as above),
         then create a `VoiceLiveInstance` row identical to the one built inside the
         `vl_instance_standalone` fixture (name, voice_live_model="gpt-4o", voice_name, voice_type,
         avatar_character, avatar_style, avatar_enabled=False, model_instruction, created_by), flush,
         refresh, and use its `.id` in the `session.update` payload exactly as the current test body
         does. `VoiceLiveInstance` is already imported at the top of this file (line 28).
       Do not modify the shared `seeded_db` or `vl_instance_standalone` fixtures themselves -- other
       tests (including mocked ones and `test_real_config_resolution_vl_instance_model_mode`, which is
       not in the failing set) still depend on their real-key behavior.

    Do not modify `app/services/voice_live_websocket.py` or `app/services/config_service.py` -- every
    fix here is test-side, exercising existing production behavior (the keyless DefaultAzureCredential
    fallback, the always-on avatar_enabled default, and the classic-agent api_version parameter) rather
    than introducing new production code paths.
  </action>
  <verify>
    <automated>cd /Users/huqianghui/Downloads/1.github/AI-Coach-vibe-coding/backend && .venv/bin/python3 -m pytest tests/test_voice_live_websocket.py -v 2>&1 | tail -100</automated>
  </verify>
  <done>
    All previously-failing tests in `test_voice_live_websocket.py` pass: the 3 classic-agent mock
    tests now actually invoke `connect()` with the real `api_version` kwarg asserted, the 2 stale
    `avatar_enabled` assertions (mock + real-handler) now expect `True`, and the 7 Category-2 real
    tests (5 direct-SDK + 2 handler-level) connect successfully via `DefaultAzureCredential`/the
    keyless DB-seeded path instead of hitting a 403. No production code in
    `app/services/voice_live_websocket.py` was modified.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|--------------|
| Test process -> real Azure AI Foundry resource (STS + wss) | Real integration tests in this plan send a live Entra ID bearer token (via `az login`/`DefaultAzureCredential`) over the network to the same Foundry resource the application uses in production, to open real Voice Live WebSocket sessions |
| `mock_sdk` fixture -> `sys.modules` | Test fixture temporarily replaces `azure.*` entries in the process-wide `sys.modules` dict with fake stub modules for the duration of each mocked test, then restores the real entries |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Tampering | `mock_sdk` fixture's `sys.modules` patching (new `azure.identity`/`azure.identity.aio` stub keys) | mitigate | Fixture already saves and restores ALL `azure.*` sys.modules entries in a `yield`-wrapped fixture with cleanup after every test (existing pattern, unchanged) -- the new stub keys are added to the same save/restore set, so no mocked state can leak into subsequent tests, including the adjacent real-SDK test classes which additionally call `_ensure_real_azure_modules()` as a second safety net |
| T-quick-02 | Information Disclosure | Real bearer tokens/API keys in test output | accept | No test in this plan prints the raw bearer token or API key value; `_exchange_api_key_for_bearer_token`'s converted-to-403 test only asserts on `status_code`, never on response body content that could contain sensitive data |
| T-quick-03 | Denial of Service / Elevation of Privilege | Real WebSocket connections opened against the shared Foundry resource by CI/local test runs | accept | Pre-existing behavior for all real tests in this suite (gated behind `skipif` on `.env` credentials, already the case before this plan); this plan does not add new real network calls, it only swaps the credential type used by existing real calls and fixes assertions on existing real/mocked calls |
| T-quick-04 | Repudiation | No production code changed, so no new attack surface introduced by this plan | accept | This plan is test-file-only; the STRIDE register for the production `voice_live_websocket.py`/`voice_live_service.py`/`connection_tester.py` surfaces was already established when those files were last planned/reviewed and is unaffected here |
</threat_model>

<verification>
- `cd backend && .venv/bin/python3 -m pytest tests/test_voice_live.py tests/test_voice_live_service.py tests/test_voice_live_websocket.py -v` reports 0 failed
- `cd backend && ruff check tests/test_voice_live.py tests/test_voice_live_service.py tests/test_voice_live_websocket.py` reports clean
- `cd backend && ruff format --check tests/test_voice_live.py tests/test_voice_live_service.py tests/test_voice_live_websocket.py` reports clean
- `cd backend && .venv/bin/python3 -m pytest -q 2>&1 | tail -20` shows no new failures introduced in the rest of the suite (compare total pass count against the pre-fix baseline of 2535 passing + 17 failing)
- `git diff --stat backend/app/` shows no changes to production code (only files under `backend/tests/` are modified)
</verification>

<success_criteria>
- 0 failed across all 17 previously-failing Voice Live tests; no test was skipped, deleted, or faked to reach this result
- All 8 real-Azure integration tests among the 17 either connect successfully via Entra ID (`DefaultAzureCredential`) or, for the one genuinely dead API-key-only STS endpoint, assert the real, documented 403 policy response
- No production code in `voice_live_service.py`, `voice_live_websocket.py`, or `connection_tester.py` was modified
- `ruff check` and `ruff format --check` are clean on all 3 modified test files
- No regression in the rest of the backend test suite
</success_criteria>

<output>
After completion, create `.planning/quick/260718-eha-backend-voice-live-17-az-login-entra-bea/260718-eha-SUMMARY.md`
</output>
