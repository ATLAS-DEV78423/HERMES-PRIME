# Failure Class: Intent & Consent Drift

This directory codifies the failure postures, containment mechanisms, and recovery procedures for authorization breaches, user rejections, and consent fatigue.

---

## F7. Intent Root Verification Failure

*   **Class:** `CRITICAL`
*   **Symptom:** A privileged action proposal reaches Sentinel lacking a verifiable user Intent Root signature, or the proposed scope exceeds the Intent Root scope boundaries.
*   **Why concerning:** This indicates that Hermes is attempting to take unauthorized initiative, has drifted from its core task, or has been compromised by a prompt injection attempting privilege escalation.
*   **Containment:** Sentinel immediately rejects the capability request; the action is blocked before reaching Forge.
*   **Recovery:**
    1. Quarantine the active session.
    2. Write a secure entry into the tamper-evident audit log.
    3. Notify the user of the scope violation and prompt for explicit intent signature re-authentication.
*   **Telemetry:** `sentinel.intent_root_violations` (triggers immediate CRITICAL pager alarm).

---

## F8. Consent Fatigue Click-Throughs

*   **Class:** `DEGRADED`
*   **Symptom:** User decision latency on consent prompts falls below the human-deliberation threshold (e.g. click-through in <500ms).
*   **Why concerning:** The operator is approving actions reflexively, neutralizing the safety gates.
*   **Containment:** Sentinel introduces mandatory cooldown windows and rate-limits prompt delivery. High-stake irreversible actions bypass simple click-throughs.
*   **Recovery:**
    1. Batch low-risk notifications to reduce alert volume.
    2. Elevate verification checks: require a second-factor (2FA/WebAuthn hardware token) or manual type-in confirmations for critical-path mutations.
*   **Telemetry:** `consent.median_decision_latency`, `consent.prompts_per_session` (alarms on sustained low decision latency).

---

## F9. Repeated Capability Denials

*   **Class:** `EXPECTED` to `DEGRADED`
*   **Symptom:** Hermes repeatedly requests capabilities that are outside its token scope, resulting in multiple rejections.
*   **Why concerning:** Normal noise in isolated events, but repeated occurrences indicate the model is stuck in a planning loop or is drifting from the core task.
*   **Containment:** Sentinel logs each rejection. Rejections beyond a specific count trigger session-level throttling.
*   **Recovery:**
    1. Pause planning execution.
    2. Prompt the operator: "Hermes is repeatedly attempting actions beyond its active scope. Would you like to extend its Intent Root or restart the plan?"
*   **Telemetry:** `sentinel.capability_rejections`.
