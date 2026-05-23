# Failure Class: Recursive Expansion & Probabilistic DoS

This directory codifies the failure postures, containment mechanisms, and recovery procedures for runaway miner loops, graph traversals, and context amplification attacks.

---

## F10. Runaway Subagent & Miner Loops

*   **Class:** `EXPECTED` to `DEGRADED`
*   **Symptom:** Hermes is stuck in a loop repeatedly dispatching file or grep miners, generating excessive read operations.
*   **Containment:** The **Max Miner ceiling (I18)** caps dispatches at 20 runs per Intent Root. 
*   **Recovery:**
    1. Suspend the active dispatch thread once the count ceiling is breached.
    2. Inform Hermes: `MINER_DISPATCH_LIMIT_EXCEEDED`.
    3. Require the model to replan using existing cached references, or escalate to the operator for a ceiling reset.
*   **Telemetry:** `fabric.dispatches.per_session`.

---

## F11. Graph Traversal Storms

*   **Class:** `DEGRADED` to `CRITICAL`
*   **Symptom:** Atlas executes a highly recursive graph search that queries a massive number of nodes and relationship jumps (e.g. attempting to traverse the entire workspace index).
*   **Why concerning:** This consumes high CPU/memory, locking up the Epistemic Store and causing a denial of service on query pipelines.
*   **Containment:** The **Graph Traversal ceiling (I18)** limits relationship jumps to a maximum depth of 100 jumps.
*   **Recovery:**
    1. Terminate the active graph query immediately at jump 100.
    2. Return the partial, verified node set compiled up to that point.
    3. Flag the query pattern for behavioral anomaly analysis.
*   **Telemetry:** `atlas.graph.traversal_depth` (triggers DEGRADED warning).

---

## F12. Context Size Amplification Loop

*   **Class:** `CRITICAL`
*   **Symptom:** The active reasoning prompt grows exponentially (e.g., trying to read 10 huge files at once, exceeding token constraints).
*   **Why concerning:** Explodes token costs, degrades model reasoning accuracy, and crashes API boundaries.
*   **Containment:** Sentinel enforces a strict **Max Context Size ceiling of 64K tokens** on outbound model payloads.
*   **Recovery:**
    1. Intercept and block the payload before sending it to the model provider.
    2. Enforce prompt compaction: instruct the Retrieval Fabric to return signature-only structures or 1-paragraph summarizations (summarizer class) instead of raw files.
    3. Re-evaluate the prompt size before routing.
*   **Telemetry:** `sentinel.ceiling.context_size`.
