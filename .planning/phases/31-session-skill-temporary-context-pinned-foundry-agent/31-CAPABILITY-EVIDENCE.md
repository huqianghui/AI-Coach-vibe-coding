# Phase 31 Capability Evidence

> Alternative text-only Requirement 2 gate. Directives, IQ question/marker, secrets, tokens, policy text, and tokenized URLs are excluded.

## Deterministic verdicts

- Text Responses verdict: PROVEN: CONVERSATION_ITEM_DEVELOPER
- Voice WS verdict: BLOCKED: ENDPOINT 404
- Avatar verdict: BLOCKED: ENDPOINT 404
- WebRTC verdict: FAIL-CLOSED

## Sanitized preflight

- Timestamp (UTC): 2026-08-04T15:52:17+00:00
- Project: ai-coach-demo
- Session ID: 1705a6e4-71bb-44a9-a0e4-4cc30d8cd4b7
- HCP ID: 4f81e52b-8179-443e-9d14-fc35129565ac
- Scenario ID: 3474aa63-7d26-47c3-a126-281f02ff2bd0
- Exact Agent pin: Dr-Chen-Jun/5
- Foundry endpoint host present: True
- Credential source: database-api-key
- IQ question present: True
- IQ marker present: True
- SDK versions: {"azure-ai-projects": "2.4.0", "azure-identity": "1.25.3", "openai": "2.38.0", "python": "3.11.9"}
- Exact candidate order: RESPONSE_INPUT_DEVELOPER -> RESPONSE_INPUT_SYSTEM -> CONVERSATION_ITEM_DEVELOPER -> CONVERSATION_ITEM_SYSTEM -> SERVER_PREFIXED_USER
- Historical top-level instructions result: REJECTED 400 invalid_payload; not retried
- Request tools/tool_choice supplied: false

## Candidate matrix

### RESPONSE_INPUT_DEVELOPER

- Status: REJECTED
- A response ID: none
- B response ID: none
- Continuation mechanism: previous_response_id
- Disposable Conversation ID: none
- A correlated call IDs: []
- B correlated call IDs: []
- A correlated successful knowledge_base_retrieve: False
- B correlated successful knowledge_base_retrieve: False
- Accepted event types: []
- Sanitized reason: Error code: 400 - {'error': {'message': "Invalid value: ''. Supported values are: 'additional_tools', 'apply_patch_call', 'apply_patch_call_output', 'code_interpreter_call', 'compaction', 'compaction_trigger', 'computer_call', 'computer_call_output', 'custom_tool_call', 'custom_tool_call_output', 'file_search_call', 'function_call', 'function_call_output', 'image_generation_call', 'item_reference', 'local_shell_call', 'local_shell_call_output', 'mcp_approval_request', 'mcp_approval_response', 'm

### RESPONSE_INPUT_SYSTEM

- Status: REJECTED
- A response ID: none
- B response ID: none
- Continuation mechanism: previous_response_id
- Disposable Conversation ID: none
- A correlated call IDs: []
- B correlated call IDs: []
- A correlated successful knowledge_base_retrieve: False
- B correlated successful knowledge_base_retrieve: False
- Accepted event types: []
- Sanitized reason: Error code: 400 - {'error': {'message': "Invalid value: ''. Supported values are: 'additional_tools', 'apply_patch_call', 'apply_patch_call_output', 'code_interpreter_call', 'compaction', 'compaction_trigger', 'computer_call', 'computer_call_output', 'custom_tool_call', 'custom_tool_call_output', 'file_search_call', 'function_call', 'function_call_output', 'image_generation_call', 'item_reference', 'local_shell_call', 'local_shell_call_output', 'mcp_approval_request', 'mcp_approval_response', 'm

### CONVERSATION_ITEM_DEVELOPER

- Status: PROVEN
- A response ID: resp_97e947baca26390d006a720abe47808190a807acbd53863b39
- B response ID: resp_97e947baca26390d006a720ac71f1c8190bb265969d2629c96
- Continuation mechanism: same Conversation
- Disposable Conversation ID: conv_97e947baca26390d00i53zgOy7rRREMZAWrpNhyCMdTbZx3PUe
- A correlated call IDs: ["mcp_97e947baca26390d006a720ac2088c8190b19f1a15170ababd"]
- B correlated call IDs: ["mcp_97e947baca26390d006a720ac918d88190862d67c419f2238e"]
- A correlated successful knowledge_base_retrieve: True
- B correlated successful knowledge_base_retrieve: True
- Accepted event types: ["response.completed", "response.content_part.added", "response.content_part.done", "response.created", "response.in_progress", "response.mcp_call.completed", "response.mcp_call.in_progress", "response.mcp_call_arguments.delta", "response.mcp_call_arguments.done", "response.mcp_list_tools.completed", "response.mcp_list_tools.in_progress", "response.output_item.added", "response.output_item.done", "response.output_text.annotation.added", "response.output_text.delta", "response.output_text.done"]

### CONVERSATION_ITEM_SYSTEM

- Status: NOT ATTEMPTED: FIRST VIABLE SURFACE FOUND
- A response ID: none
- B response ID: none
- Continuation mechanism: none
- Disposable Conversation ID: none
- A correlated call IDs: []
- B correlated call IDs: []
- A correlated successful knowledge_base_retrieve: False
- B correlated successful knowledge_base_retrieve: False
- Accepted event types: []

### SERVER_PREFIXED_USER

- Status: NOT ATTEMPTED: FIRST VIABLE SURFACE FOUND
- A response ID: none
- B response ID: none
- Continuation mechanism: none
- Disposable Conversation ID: none
- A correlated call IDs: []
- B correlated call IDs: []
- A correlated successful knowledge_base_retrieve: False
- B correlated successful knowledge_base_retrieve: False
- Accepted event types: []

## Immutability and trust controls

- Static Agent write guard: CLEAN
- Agent resource writes: 0
- Definition/tool fingerprint before: ce612fcaedef0ba8e52433e4ecf510415913fac53d652911a33ce6d6db961b24
- Definition/tool fingerprint after: ce612fcaedef0ba8e52433e4ecf510415913fac53d652911a33ce6d6db961b24
- Definition/tool fingerprint: MATCH
- Version inventory fingerprint before: 639ccbbd6bc6cf52a8c69fa00f11680c3a706182179d9fc04a22f7d3f84f775b
- Version inventory fingerprint after: 639ccbbd6bc6cf52a8c69fa00f11680c3a706182179d9fc04a22f7d3f84f775b
- Version inventory fingerprint: MATCH
- Protected hash manifest: MATCH
- Disposable Conversation cleanup: CONFIRMED
- Database writes: 0 (read-only Session lookup; explicit rollback; no create fallback)

## Blockers

- None

## Authorization boundary

This verdict authorizes only subsequent GSD replanning. Production code/tests, schema/migrations, databases, commit, and push are not authorized.
Withdrawn Plans 31-02 through 31-07 remain non-executable.
Text evidence does not prove Voice, avatar, or WebRTC capability.
