# Phase 30 Deferred Items

## Plan 30-01

- `frontend/src/pages/user/session-history.test.tsx` has two pre-existing chart-rendering test failures: `renders the performance radar` cannot find `performance-radar`, and `renders the trend chart` cannot find `line-chart`. The other 44 tests pass. These failures are unrelated to the four session fixtures updated with Agent audit pins and are outside Plan 30-01 scope.

## Plan 30-06 final frontend baseline

- The initial repository-wide `npm run test:coverage` run ended with 108 failures outside
	Requirement 1. Those stale failures were subsequently repaired.
- Representative categories are stale i18n mocks returning keys instead of expected English text,
	obsolete navigation expectations such as `/user/scenarios` instead of `/user/training`, outdated
	chart/UI identifiers such as `line-Overall` instead of `line-avgScore`, and one voice timeout.
- Requirement 1 focused evidence remains green: API client suite 20 passed, Unified Session suite
	21 passed, TypeScript compilation passed, production build passed, and Playwright 4 passed.
- Repairs covered current i18n resources, Router context, Radix pointer-capture support, stale API
	and navigation contracts, chart identifiers, hook mocks, and full-suite timeout contention.
- Final non-coverage result: 2422 passed, 0 failed. Changed TypeScript line coverage: 2/2, 100%.
- Global branch coverage remains a separate historical gap: 77.62% against the configured 82%
	threshold. The threshold was not lowered. The user explicitly waived this unrelated global gate
	for the Requirement 1 release; closing the historical branch gap remains deferred work.
