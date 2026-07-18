---
phase: 28
status: partial
source: 28-VERIFICATION.md
created: 2026-07-18
tests_total: 1
tests_passed: 0
tests_failed: 0
tests_pending: 1
---

# Phase 28 Human UAT — SOP Skill → AI Foundry Skill → HCP Consumption

Automated verification covered 17/18 must-haves. The following item requires a
live Azure AI Foundry project + Entra ID credentials and must be verified by a human.

## Test Items

### 1. D-03 — Foundry version-increment smoke test

**Status:** pending

**What to verify:** Repeated `create_from_files` calls with the same skill name
cause Azure AI Foundry to increment the skill version server-side (the code in
`backend/app/services/skill_foundry_service.py` assumes this semantics when
re-publishing an updated skill).

**Steps:**
1. Ensure `.env` has valid Foundry project endpoint + Entra ID credentials
   (`az login` or service principal).
2. Publish a SOP skill from the admin skill editor (or call
   `POST /api/v1/skills/{id}/publish`).
3. Confirm in the Foundry portal (Settings tab → "View in Foundry portal" link)
   that the skill appears with version 1 and `foundry_cloud_version=1` is stored.
4. Edit the skill content, re-publish.
5. **Expected:** Foundry shows the same skill name with version incremented
   (2), and the skill row's `foundry_cloud_version` reflects the new version.
   No duplicate skill entity is created.

**Result:** _(fill in: pass / fail + notes)_
