# Memory Invariants

This document codifies the safety invariants governing epistemic beliefs, vector/graph mappings (Atlas), and validator model selection.

---

## I6. Memory provenance is mandatory

*   **ID:** `I6`
*   **Statement:** No fact may be promoted from quarantine to authoritative Atlas tier without a verifiable source, an ingestion timestamp, and at least one corroborating reference or explicit user confirmation.
*   **Rationale:** Doctrine §4. Memory without provenance is a hallucination accumulator.
*   **Enforcement:** Atlas write path rejects promotions lacking provenance metadata. Quarantine tier facts are excluded from authoritative retrieval.
*   **Detection:** Metric on promotion path: `atlas.promotion.missing_provenance`. Audit log records every promotion.
*   **Response:** Promotion blocked. Fact remains in quarantine. If pattern repeats, source is marked untrusted.
*   **Test:** Integration tests cover promotion paths with and without provenance; assert behavior in both cases.

---

## I11. Diversity on critical-path validation

*   **ID:** `I11`
*   **Statement:** When a critical-path decision is validated by an independent probabilistic check, the validator and the primary must use different model families and different retrieval/embedding paths.
*   **Rationale:** Doctrine P6. Correlated failure defeats defense-in-depth.
*   **Enforcement:** Router configuration declares family tags. Validator dispatch refuses to use a validator from the same family as the primary.
*   **Detection:** Startup validation. Runtime metric on validator/primary family pairing.
*   **Response:** Validation fails closed; action blocked pending operator review.
*   **Test:** Configuration test ensures critical-path entries always have a diverse validator declared.
