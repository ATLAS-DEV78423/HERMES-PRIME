# Failure Class: Hallucination

This directory codifies the failure postures, containment mechanisms, and recovery procedures for probabilistic plan and tool hallucinations.

---

## F1. Hallucinated Plan Steps

*   **Class:** `EXPECTED`
*   **Symptom:** Hermes proposes a planning step that references a nonexistent tool, capability, file, or API.
*   **Containment:** The **Capability Registry (I9)** intercepts all Forge calls. Any proposed action that does not match an active registry entry is blocked at lookup.
*   **Recovery:** 
    1. Reject the execution step with a structured error `FORGE_CAPABILITY_NOT_FOUND`.
    2. Feed the registry schema catalog back to the planner context.
    3. Instruct the planner to re-route or re-plan using valid capabilities.
*   **Telemetry:** `forge.unknown_action_attempts` (alarm if spikes > 5 within a session, which indicates potential planning loop).

---

## F2. Malformed Tool Calls

*   **Class:** `EXPECTED`
*   **Symptom:** Hermes calls a real tool but passes wrong argument types, invalid values, or misses required schema fields.
*   **Containment:** The **Schema Validation Layer (doctrine §5.3)** intercepts all Forge parameters and parses them against the strict tool schema before dispatching to the sandbox.
*   **Recovery:**
    1. Terminate execution immediately.
    2. Return a detailed schema violation JSON block containing the exact field failures and type requirements back to the model context.
    3. Force the planner to regenerate the parameters.
*   **Telemetry:** `forge.schema_violations`.

---

## F3. Tool Output Schema Mismatch

*   **Class:** `DEGRADED`
*   **Symptom:** A sandboxed tool executes successfully, but the returned output data fails to conform to the registered tool output schema.
*   **Why concerning:** This indicates an un-notified API change in the underlying workspace tool, or that the tool environment has been compromised/impersonated.
*   **Containment:** Sentinel quarantines the output payload; it is blocked from entering the active prompt memory or downstream vector storage.
*   **Recovery:**
    1. Fall back to safe mode. Tell Hermes the tool execution failed due to an environmental format mismatch.
    2. Write a critical telemetry alert to page the operator.
    3. Require the operator to review the API integration before the tool is re-enabled.
*   **Telemetry:** `forge.tool_output_schema_failures` (triggers immediate DEGRADED status alarm).
