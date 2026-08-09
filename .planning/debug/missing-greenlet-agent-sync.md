---
status: awaiting_human_verify
trigger: "missing-greenlet-agent-sync (orchestrator-diagnosed, verify+fix)"
created: 2026-07-27T00:00:00Z
updated: 2026-07-27T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED. Orchestrator diagnosis was correct: three callers queried
HcpProfile without selectinload(HcpProfile.voice_live_instance) then called
sync_agent_for_profile, which triggered a lazy load of profile.voice_live_instance
inside resolve_voice_config() in an async context -> MissingGreenlet.
test: All three fixes applied and individually verified via revert-then-restore
cycle against real-DB (aiosqlite) regression tests. Full pytest subset (210 tests
across the 3 fixed service test files + test_agent_sync_service.py) passes. ruff
check/format show zero new violations introduced by this change (pre-existing
violations confirmed identical via git stash A/B diff).
expecting: N/A - fix complete and self-verified.
next_action: DONE from investigator side. Awaiting human confirmation that the
original issue (agent sync failing on first attempt via KB bind/unbind, skill
assignment, or bulk sync) is resolved in the real app before archiving this
session.

## Symptoms

expected: Saving an agent (or triggering an agent re-sync after knowledge base binding /
skill assignment / bulk sync) completes without error.
actual: First attempt raises `greenlet_spawn has not been called; can't call await_only()
here. Was IO attempted in an unexpected place? (Background on this error at:
https://sqlalche.me/e/20/xd2s)`. Retrying via the admin UI succeeds (that path eagerly
loads the relationship).
errors: sqlalchemy.exc.MissingGreenlet as above.
reproduction: Trigger agent sync through any caller that loads HcpProfile without
selectinload of voice_live_instance, e.g. bind/unbind a knowledge base, assign a skill to
a scenario HCP, or run bulk sync.
started: Latent since resolve_voice_config started reading profile.voice_live_instance
(D-10). Path-dependent, so appears intermittent.

## Eliminated

- hypothesis: A test that creates the VoiceLiveInstance and HcpProfile in the same
  db_session fixture, then calls _trigger_agent_resync(db_session, ...) on that same
  session, will reproduce MissingGreenlet when selectinload is missing.
  evidence: Verified with a standalone repro script (same pattern as the first version
  of the regression test): when the VoiceLiveInstance row was created earlier in the
  SAME session, SQLAlchemy's many-to-one LazyLoader "use_get" optimization satisfies
  `profile.voice_live_instance` directly from the session's identity map (by primary
  key) WITHOUT emitting a DB query -- so no IO occurs, and MissingGreenlet is never
  raised, regardless of whether `.options(selectinload(...))` is present. Confirmed by
  running the same test with the fix reverted: it still passed (false negative). A
  second repro script that creates the VoiceLiveInstance in one session (committed) and
  then queries HcpProfile in a genuinely FRESH session (or `session.expunge(vl)` on the
  same session before the query) reliably reproduces MissingGreenlet without the fix,
  and passes with it.
  timestamp: post-fix-verification

## Confirmed Regression-Test Pattern

To validly reproduce/guard this bug, the VoiceLiveInstance row must NOT already be in
the acting session's identity map when the caller's HcpProfile query executes. Use
`db_session.expunge(vl_instance)` after creating+flushing it (before invoking
_trigger_agent_resync / batch_sync_agents) to force a real lazy-load path, matching a
production request where the VL instance was never independently queried in that
session.

## Evidence

- timestamp: initial-read
  checked: backend/app/models/hcp_profile.py:58
  found: `voice_live_instance = relationship("VoiceLiveInstance", back_populates="hcp_profiles")`
  -- no `lazy=` kwarg, so SQLAlchemy default `lazy="select"` (lazy load) applies.
  implication: Confirms relationship is lazy by default; any bare attribute access outside
  a session context that already eager-loaded it will trigger implicit IO.

- timestamp: initial-read
  checked: backend/app/services/voice_live_instance_service.py:258-289 (resolve_voice_config)
  found: Synchronous function `def resolve_voice_config(profile: HcpProfile) -> dict` reads
  `inst = profile.voice_live_instance` directly (line 268) with no await / no
  session.refresh / no awaitable_attrs usage.
  implication: If voice_live_instance is not already loaded (not eagerly joined/selectin'd),
  this line performs a lazy DB load. In async SQLAlchemy, an un-awaited lazy load outside a
  greenlet_spawn context raises MissingGreenlet.

- timestamp: initial-read
  checked: backend/app/services/agent_sync_service.py:126-145 (build_voice_live_metadata)
  found: Calls `resolve_voice_config(profile)` at line 145 directly (not awaited, since
  resolve_voice_config is sync) from within async sync_agent_for_profile flow.
  implication: Confirms the call chain sync_agent_for_profile -> build_voice_live_metadata
  -> resolve_voice_config -> profile.voice_live_instance lazy load.

- timestamp: initial-read
  checked: backend/app/services/knowledge_base_service.py:590-629 (_trigger_agent_resync)
  found: `result = await db.execute(sa_select(HcpProfile).where(HcpProfile.id ==
  hcp_profile_id))` at line 606 -- no `.options(selectinload(...))`. Module only imports
  `from sqlalchemy import select` (line 23), no selectinload import anywhere in file.
  implication: Confirmed caller #1. Fix requires adding selectinload import + option.

- timestamp: initial-read
  checked: backend/app/services/scenario_service.py:61-75 (_trigger_agent_resync)
  found: `select(hcp_profile_service.HcpProfile).where(hcp_profile_service.HcpProfile.id
  == hcp_profile_id)` at lines 66-69 -- no `.options(selectinload(...))`. Note:
  `selectinload` and `HcpProfile` are already imported at module level (lines 8, 10), used
  elsewhere in `_reload_with_hcp` (line 82). The `except Exception: logger.warning` at line
  74-75 currently swallows the MissingGreenlet, so failures silently no-op (matches
  "retrying via admin UI succeeds" symptom - admin UI reload path uses `_reload_with_hcp`
  which does eager-load and re-triggers a working sync).
  implication: Confirmed caller #2. Fix is a one-line `.options()` addition using already-
  imported symbols.

- timestamp: initial-read
  checked: backend/app/services/hcp_profile_service.py:292-311 (batch_sync_agents)
  found: `select(HcpProfile).where((HcpProfile.agent_id == "") | ... )` at lines 304-309 --
  no `.options(selectinload(...))`. `selectinload` already imported at module level (line
  12) and used elsewhere (lines 104-105, 120-121, 164).
  implication: Confirmed caller #3. Fix is a one-line `.options()` addition using already-
  imported symbol.

- timestamp: test-pattern-review
  checked: backend/tests/test_knowledge_base.py:618-661
  (test_trigger_agent_resync_marks_synced_on_success /
  test_trigger_agent_resync_marks_failed_on_remote_tool_error) and
  backend/tests/test_agent_sync_service.py:425-490 (test_sync_agent_for_profile_creates_...)
  found: Existing tests for _trigger_agent_resync mock
  `app.services.agent_sync_service.sync_agent_for_profile` wholesale (AsyncMock), so they
  never exercise resolve_voice_config / the lazy-load path -- they would NOT have caught
  this bug. Existing sync_agent_for_profile tests use MagicMock profiles with
  `.voice_live_instance` pre-set as a plain attribute (no real relationship/lazy load), so
  they also don't exercise the real ORM lazy-load path.
  implication: New regression tests must use a REAL db_session-backed HcpProfile with a
  REAL assigned VoiceLiveInstance, calling through the actual query in each of the three
  caller functions (not mocking sync_agent_for_profile itself), mocking only the Azure SDK
  boundary (create_agent/update_agent/config_service.get_master_config/
  knowledge_base_service.get_knowledge_configs) so the lazy-load/eager-load behavior is
  genuinely exercised against aiosqlite (which will raise MissingGreenlet on unguarded lazy
  loads, same as production asyncpg).

## Resolution

root_cause: HcpProfile.voice_live_instance is a default lazy="select" relationship.
resolve_voice_config() (voice_live_instance_service.py:268) synchronously accesses
profile.voice_live_instance without awaiting, which is safe only if the relationship was
already eager-loaded. Three call sites that eventually invoke sync_agent_for_profile ->
build_voice_live_metadata -> resolve_voice_config load HcpProfile via a plain
select()/sa_select() with no `.options(selectinload(HcpProfile.voice_live_instance))`,
so the first access to profile.voice_live_instance triggers an implicit lazy DB load
inside an async context with no greenlet_spawn trampoline active, raising
sqlalchemy.exc.MissingGreenlet. The three callers are:
- backend/app/services/knowledge_base_service.py:606 (_trigger_agent_resync)
- backend/app/services/scenario_service.py:66-69 (_trigger_agent_resync)
- backend/app/services/hcp_profile_service.py:304-309 (batch_sync_agents)

fix: Added `.options(selectinload(HcpProfile.voice_live_instance))` to the three queries
above (added `from sqlalchemy.orm import selectinload` + `from app.models.hcp_profile
import HcpProfile` import to knowledge_base_service.py; scenario_service.py and
hcp_profile_service.py already had selectinload/HcpProfile imported). Did not change the
relationship's lazy strategy on the model itself (would over-eager-load in unrelated
queries). Did not change the `except Exception` swallow behavior in
scenario_service._trigger_agent_resync (out of scope; noted as a follow-up
observability gap since it currently hides sync failures from callers/logs at
warning-only level with no status field update, unlike the other two callers which set
agent_sync_status="failed").

verification: All three fixes were verified with a rigorous revert-then-restore
cycle: for each of the three files, the `.options(selectinload(...))` fix was
temporarily removed, the corresponding new regression test was run and confirmed to
fail with the EXACT production error (`greenlet_spawn has not been called; can't
call await_only() here...`, surfaced either as a raised exception or, for
batch_sync_agents/scenario_service which catch-and-record, as
agent_sync_status="failed" / agent_sync_error containing that exact string), then
the fix was restored and the test was confirmed to pass again. Full verification
sequence:
- knowledge_base_service.py::_trigger_agent_resync -- fails without fix (raises
  MissingGreenlet), passes with fix. Confirmed.
- scenario_service.py::_trigger_agent_resync -- fails without fix (logged as
  WARNING "Agent re-sync after skill assignment failed: greenlet_spawn has not been
  called..."), passes with fix. Confirmed.
- hcp_profile_service.py::batch_sync_agents -- fails without fix (profile row
  updated to agent_sync_status="failed", agent_sync_error="greenlet_spawn has not
  been called; can't call await_only() here...", summary["synced"]==0), passes with
  fix (summary["synced"]==1, agent_sync_status="synced", agent_id="asst_batch_1").
  Confirmed.
Full regression run: `pytest tests/test_knowledge_base.py tests/test_scenario_service.py
tests/test_hcp_profile_service.py tests/test_agent_sync_service.py` -- 210 passed,
0 failed, 6 pre-existing unrelated warnings (RuntimeWarning: coroutine
'AsyncMockMixin._execute_mock_call' was never awaited -- pre-existing in
unrelated tests, not touched by this fix).
`ruff check` / `ruff format --check` on the three fixed service files and three
test files: zero new violations introduced by this change. Pre-existing violations
(29 E501 in test_hcp_profile_service.py/test_skill_foundry_service.py, 1 E501 in
test_knowledge_base.py, format debt in test_hcp_profile_service.py/
test_knowledge_base.py) were confirmed via `git stash`/`git stash pop` A/B diff to
exist identically on the pre-fix baseline -- out of scope, not introduced by this
fix, left untouched.
files_changed:
  - backend/app/services/knowledge_base_service.py
  - backend/app/services/scenario_service.py
  - backend/app/services/hcp_profile_service.py
  - backend/tests/test_knowledge_base.py (new regression test)
  - backend/tests/test_scenario_service.py (new regression test)
  - backend/tests/test_hcp_profile_service.py (new regression test)
