# Deferred Items — Phase 27

Out-of-scope discoveries logged during execution. NOT fixed (unrelated to Phase 27 changes).

## Pre-existing full-suite failures (discovered during 27-01 regression gate)

Full backend `pytest -q` on `10096ff0a0af`: **2259 passed, 9 failed, 149 skipped**.
All 9 failures are pre-existing/environmental and unrelated to the prompt registry
(none touch `prompt_defaults`, `prompt_registry`, or `startup_seed`).

| Test | Category | Likely cause |
| ---- | -------- | ------------ |
| `test_coverage_boost_2.py::TestConnectionTester::test_ai_foundry_endpoint_no_key` | Azure ConnectionTester | Environment: expects specific no-key behavior |
| `test_coverage_boost_2.py::TestConnectionTester::test_azure_voice_live_no_key` | Azure ConnectionTester | Environment: expects specific no-key behavior |
| `test_voice_live.py::TestConnectionTester::test_connection_tester_voice_live_no_key` | Azure ConnectionTester | Environment: expects specific no-key behavior |
| `test_voice_live.py::TestConnectionTester::test_connection_tester_dispatch_voice_live` | Azure ConnectionTester | Environment: dispatch expectation |
| `test_skill_text_extractor.py::TestExtractTextFromDocx::test_docx_with_paragraphs` | docx extraction | python-docx / lib version behavior |
| `test_skill_text_extractor.py::TestExtractTextFromDocx::test_docx_with_table` | docx extraction | python-docx / lib version behavior |
| `test_skill_text_extractor.py::TestExtractTextFromDocx::test_docx_with_empty_paragraphs_skipped` | docx extraction | python-docx / lib version behavior |
| `test_skill_text_extractor.py::TestExtractTextFromDocx::test_docx_empty_document` | docx extraction | python-docx / lib version behavior |
| `test_skill_text_extractor.py::TestExtractTextFromDocx::test_docx_table_with_empty_cells` | docx extraction | python-docx / lib version behavior |

**Disposition:** Not fixed — outside Phase 27 scope (Scope Boundary rule). Prompt registry
changes are additive (new models/tables/service + try/except seed hook) and do not affect
these subsystems.

---

## Merged from former Phase 28 (now plans 27-07 / 27-08)

### (was Phase 28) Deferred Items

Out-of-scope discoveries logged during execution. NOT fixed (unrelated to the
prompt create / version-content work).

## Pre-existing test failures (environment-related)

Discovered while running the full backend suite (`pytest -q`) as a pre-commit
gate for Plan 28-01. None of these touch `prompt_registry`, `app/api/prompts`,
or `app/schemas/prompt`, and all Phase 28 tests pass (48/48, 100% coverage on
the changed prompt modules).

- `tests/test_voice_live.py::TestConnectionTester::test_connection_tester_voice_live_no_key`
- `tests/test_voice_live.py::TestConnectionTester::test_connection_tester_dispatch_voice_live`
- `tests/test_coverage_boost_2.py::TestConnectionTester::test_ai_foundry_endpoint_no_key`
- `tests/test_coverage_boost_2.py::TestConnectionTester::test_azure_voice_live_no_key`
  - **Cause:** The dev host has an active `az login`. `DefaultAzureCredential`
    acquires a real token even in the "no_key" path, so the tester makes a live
    HTTP call instead of the expected short-circuit. Environmental, not a code
    regression.

- `tests/test_skill_text_extractor.py::TestExtractTextFromDocx::*` (5 tests)
  - **Cause:** python-docx extraction behavior in this environment; unrelated to
    prompt management.

## Pre-existing formatting drift (out of scope)

`ruff format --check app tests` reports two files needing reformat that are NOT
part of Phase 28:

- `app/services/scenario_service.py`
- `tests/test_scenarios_api.py`
