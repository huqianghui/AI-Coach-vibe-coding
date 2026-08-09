# Phase 31 Final Execution Authority

**Status:** AUTHORITATIVE PLANNING SET — IMPLEMENTATION NOT YET EXECUTED
**Effective:** 2026-08-05

This file and the `*.final.md` plans listed below supersede all earlier Phase 31 production plans and status/validation/research assumptions. Earlier files remain immutable history. Capability evidence remains evidence only.

## Proven and disproven contracts

| Surface | Final contract |
|---|---|
| Skill-bound text | Enabled only through one server-owned Foundry Conversation per application Session; append a `developer` Conversation item immediately before each user item; create the Response with exact Session `agent_reference` |
| Continuation | The explicit Conversation is the only continuation mechanism; `previous_response_id` is prohibited on this path unless a separately executed service-contract test later proves compatibility and Phase 31 is replanned |
| Top-level instructions | DISPROVEN; never send with an Agent |
| Response-input developer/system | DISPROVEN for this integration; never use |
| Native IQ | Preserved; no tools/tool_choice replacement; acceptance requires two response-correlated successful `knowledge_base_retrieve` lifecycles |
| Voice/avatar | Unavailable, endpoint 404; fail closed before exchange and never fall back |
| WebRTC | Fail closed before token/signaling/media exchange |
| Browser authority | Browser owns user text/media intents only; no Conversation ID, context, pin, tools, instructions, response creation, continuation, or idempotency authority |

## Plan identity and dependency authority

The exact dependency IDs are the filenames below. Executors MUST resolve `depends_on` as exact filenames, not aliases such as `31-03R`.

1. `31-03-PLAN.final.md` depends on completed capability artifact `31-02-PLAN.revised.md`.
2. `31-04-PLAN.final.md` depends on `31-03-PLAN.final.md`.
3. `31-05-PLAN.final.md` depends on `31-04-PLAN.final.md`.
4. `31-06-PLAN.final.md` depends on `31-05-PLAN.final.md`.
5. `31-07-PLAN.final.md` depends on `31-06-PLAN.final.md`.
6. `31-08-PLAN.final.md` depends on `31-07-PLAN.final.md`.
7. `31-09-PLAN.final.md` depends on `31-08-PLAN.final.md`.

Execution is strictly sequential, one requirement at a time. Each plan must complete unit tests, changed statement/branch coverage, and its E2E obligations before the next begins. Plans 03–08 must not commit or push. Plan 09 permits exactly one allowlisted commit and one push attempt only after every gate passes.

Plan 08 creates, self-tests, and changed-branch-covers the integrity/release scripts and reviewed Python/frontend executable manifests. Plan 09 creates no executable source; it only runs frozen gates and writes evidence/receipts.

Because Plans 03–08 make no intermediate commits, each plan freezes a non-overwritable start snapshot before edits and computes its exact changed-executable manifest against that snapshot rather than `HEAD`. Plan 03 uses the recorded Phase baseline. Application/library code requires 100% changed statements/branches; Playwright specs follow the explicit test-infrastructure policy and machine-parsed zero-skip execution rather than a false V8-source claim.

Plan 08 also authors, fake-provider executes, and changed-branch-covers the production live harness and both release executables. The final freeze includes a machine-readable exception manifest allowing only the post-push receipt and final summary; all other worktree paths/hashes remain immutable after freeze.

## Durable correctness policy

- A mutable turn aggregate/outbox tracks orchestration. Immutable attempt rows record request-start facts; separate immutable attempt-event rows append every later dispatch/outcome/reconciliation/winner/duplicate fact. Neither history row type is updated.
- The provider contract cannot guarantee exactly-once side effects. Therefore the system promises **at-most-one committed application result**, not exactly-one provider execution.
- Unknown provider outcomes remain reconcilable and block blind resend. Winner selection is transactional; late/duplicate responses are audited and ignored for application state.
- One server-owned Conversation is durably created/reused, retained while active, and cleanup is retryable at end/delete/expiry plus startup and periodic maintenance.
- Immutable `focus_instruction` is reference-only. The final developer item ends with the highest-precedence current-step directive explicitly superseding stale progress in all prior context.

## Protected and release constraints

Never modify/stage `.planning/debug/**`, `backend/storage/db-backups/**`, database files/sidecars, or Phase 30 acceptance/summary artifacts. Never use broad add, clean, reset, or stash. Final release must prove protected hashes, forbidden sweep, zero live skips, exact staging allowlist, exactly one commit from baseline, exactly one push attempt receipt, remote SHA equality, and a truthful uncommitted post-push receipt.

## Authority boundaries

- `31-RESEARCH-STATUS.final.md` contains findings/status only and no executable instructions.
- `31-VALIDATION.final.md` defines gates only and no implementation assumptions.
- `31-PLAN-CHECK.revised.md` records checker resolution as **PENDING RECHECK**, never self-PASS.
- Only `31-03-PLAN.final.md` through `31-09-PLAN.final.md` are executable production plans.

## Operator-authorized offline release exception — 2026-08-10

The operator explicitly selected an offline-verified release because they do not want to
configure Azure Foundry or disposable PostgreSQL live inputs for this push. This exception
does **not** convert missing live evidence into a pass and does not authorize any claim that
Plan 09 production live acceptance or PostgreSQL migration/concurrency acceptance ran.

Evidence available before the release decision:

- Full backend branch-aware suite: 2754 passed, 67 skipped, 31 deselected, 89.59% total.
- Skill snapshot, Session service, turn orchestrator, and acceptance harness: 82 passed,
  zero failed, zero skipped.
- Unified Training Skill-context Playwright story: 5 passed, zero unexpected, zero skipped.
- Frontend branch coverage: 87.90% against the 82% gate.
- Ruff check/format and frontend production build passed.

The release remains constrained to one exact-path commit and one push attempt. Generated
coverage/JUnit/Playwright reports, protected debug/database/Phase 30 artifacts, and unrelated
worktree files remain excluded. Real Azure/PostgreSQL acceptance stays pending for a future
environment-backed verification.
