# Phase 31 Validation Strategy

**Nyquist status:** Enabled
**Current executable scope:** Plan 31-01 capability gate only
**Implementation validation:** Must be regenerated after the capability verdict

## Wave 0 — Capability Gate Validation

| Gate | Automated evidence | Blocking rule |
|---|---|---|
| Sanitized preflight | Probe preflight test/report enumerates HCP/scenario/session IDs, Foundry project/endpoint presence, IQ input presence, Voice Live endpoint/credential source/API version, avatar config, SDK versions, frontend/backend reachability, Chromium/media capability | Missing prerequisite blocks that probe; no successful skip |
| Static no-write guard | AST/text scan of capability code and imported helper surface for Agent create/update/delete/publish/version-write methods | Any reachable write symbol/call fails before live calls |
| Runtime no-write guard | Read client wrapped so all Agent write methods raise and increment a violation counter | Counter must remain zero |
| Agent immutability | Before/after canonical exact Agent definition+tool SHA-256 and sorted version inventory SHA-256 | Every fingerprint byte-identical |
| Text initial/continuation | Live Responses call with exact pin and changed temporary directives | Behavioral proof on both turns, same chain, no tool override |
| IQ invocation | Correlated successful `response.mcp_call.*` lifecycle or exposed final `mcp_call` item naming exactly `knowledge_base_retrieve` | Marker/configuration alone fails |
| Voice WS/avatar | Typed SDK event timeline, `create_response=False`, one backend response, context behavior, transcript/output correlation, IQ call | Any auto/duplicate/uncorrelated response fails |
| WebRTC browser authority | Separate Playwright run on actual Unified Training path with hostile data-channel `response.create` | Missing harness/browser, ambiguity, or bypass => `FAIL-CLOSED`; only rejection/prevention + one response => `PROVEN` |
| Protected work | Before/after SHA-256 and forbidden-path status sweep | Any protected mutation fails |

### Probe deadlines

Each connection, first event, behavior response, MCP terminal event, avatar readiness, SDP/data-channel open, bypass observation, and cleanup has a named independent timeout. A global timeout may cap the suite but cannot replace probe-specific diagnostics. Evidence records which deadline expired without secrets/raw context.

### Live no-skip and tee semantics

The explicit capability command must convert missing prerequisites into a failing/blocking preflight or an explicit WebRTC `FAIL-CLOSED` verdict. It must report zero pytest skips for required text/WS probes. When piping through `Tee-Object`, capture and return the native pytest exit code immediately; grepping log text is supplemental and may not replace process status.

## Post-Verdict Regeneration Requirements

Plans 31-02+ must be generated from the approved evidence and include the following validation work. None is executable from this file.

### Database and audit

- Alembic migration tests for immutable structured SOP snapshot and append-only per-turn context audit.
- Upgrade/downgrade coverage on SQLite test DB and migration-head validation.
- Unique `(session_id, turn_key)` replay/idempotency test.
- Parent retention/delete semantics test.
- ORM/package export import test.
- DB round-trip proof for exact pin, Skill/version, snapshot/focus/context digests, applied step, response ID, MCP correlation, progression outcome, and timestamps.
- No update/delete business API for audit rows; mutation attempt tests fail.
- Historical Skill-bound Session lacking structured SOP snapshot fails closed before provider calls.

### API compatibility

- Keep standalone `chat_with_agent()` contract and Phase 30/HCP playground tests unchanged; test a separate Session wrapper requiring typed context.
- Keep `detect_sop_step()` callers green; test new typed progression API or update all callers/tests atomically.
- Verify initial/continued Session calls carry `instructions`, exact `agent_reference`, and continuation ID without tools overrides.

### WS and Unified Training contract

- Text-over-WS `conversation.item.create` is accepted as input intent; browser cannot send response/instruction/tool/identity authority.
- Final audio transcript is authoritative for persistence/progression; partial transcript and browser callback text are not.
- Backend persists user transcript, assistant output, append-only audit, and progression after successful terminal response.
- Include `frontend/src/pages/user/unified-session.tsx`, hook/page tests, and an actual Unified Training Playwright route.
- Browser callbacks remain display-only and exactly one response is created.

### WebRTC verdict

Generate one actual implementation plan only:

- **FAIL-CLOSED:** Session-bound endpoint rejects before token/signaling with structured unsupported error; no fallback; actual Unified Training UI test confirms no connection/transport substitution.
- **PROVEN:** Plan names the exact proven endpoint/lifecycle, server control ownership, data-channel rejection mechanism, event correlations, timeout/cleanup behavior, and browser contract. No conditional branch remains.

## Coverage Gates

- Current known frontend branch coverage: **77.62%**.
- Required threshold: **82%**.
- Thresholds/exclusions may not be lowered or broadened.
- Regenerated plans must first produce an uncovered-branch report and add targeted tests until the full gate is green. If closure scope cannot be bounded, insert a blocking user decision checkpoint before release.
- Changed executable Python requires 100% diff/changed-code coverage.
- Changed executable TS/TSX requires executable changed-code coverage using LCOV/diff tooling that supports TS/TSX mappings; `tsc` is not coverage.
- Full backend configured coverage, full frontend statements/branches/functions/lines, TypeScript, build, and Playwright all remain mandatory.

## Final Release Gate Contract

1. Record branch, baseline HEAD, origin SHA, worktree status, and baseline count for the single Requirement 2 commit.
2. Hash protected debug files, DB backups, DB files/sidecars, and Phase 30 acceptance/summary before release.
3. Run full Ruff check/format, backend pytest coverage, changed Python coverage, full frontend coverage including branch closure, changed TS/TSX coverage, TypeScript, build, full Playwright, focused actual Unified Training E2E, strict live no-skip, and Phase 30 native IQ regression.
4. Run automated forbidden sweep for Agent writes, mutable-latest/model/generic fallback, browser instructions/tools/pin/context, Session bare `response.create`, broad git add, and protected paths.
5. Recompute protected hashes before staging.
6. Stage explicit allowlisted paths only; inspect cached names/diff and run cached diff check.
7. Prove exactly one commit relative to recorded baseline, then push once.
8. Verify remote SHA equals local SHA and protected hashes remain equal.
9. Record the **pre-release receipt** before commit. Record the **post-push receipt** after push and explicitly mark it as post-commit evidence; do not amend or create a second commit to include it.

## Nyquist Sign-Off

Plan 31-01 may complete only when all capability artifacts are generated with deterministic verdicts and no resource mutation. Phase 31 implementation may not be called planned, executable, or releasable until plans are regenerated and every validation item above is assigned to concrete tasks with automated commands.
