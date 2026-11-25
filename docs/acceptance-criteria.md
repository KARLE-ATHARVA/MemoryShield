# MemoryShield AI — Acceptance Criteria

Version: 1.0
Status: Baseline Acceptance Specification

## 1. General Quality Gate

Every implemented feature must:

- Have documented inputs and expected outputs.
- Include meaningful automated tests.
- Handle invalid or missing inputs.
- Avoid hard-coded demonstration outcomes.
- Preserve defined security invariants.
- Record actual test results.

No unexecuted test may be reported as passing.

## 2. AC-01: Document Ingestion

Given a valid supported supplier document,
when it is uploaded,
then the system must:

- Register the document as a source.
- Preserve source identification metadata.
- Calculate a content hash.
- Extract readable content.
- Identify parse failures explicitly.

## 3. AC-02: AI Claim Extraction

Given extracted supplier content,
when claim extraction executes,
then the system must:

- Generate structured claim candidates.
- Validate output against a defined schema.
- Preserve source references.
- Identify unsupported or missing values.
- Avoid treating extracted content as automatically trusted.

## 4. AC-03: Versioned Persistent Memory

Given an existing stored claim,
when a new version is created,
then the system must:

- Preserve the earlier version.
- Save the new version separately.
- Record its supporting source.
- Apply the appropriate trust status.
- Enforce active-version rules.

## 5. AC-04: Cross-Session Recall

Given information stored during one agent session,
when the agent begins a later session,
then it must retrieve permitted persistent memory
without relying on the earlier chat context.

## 6. AC-05: Reproducible Contamination

Given an intentionally vulnerable sandbox policy,
when an attacker-controlled document is processed,
then the agent must be able to store a poisoned claim.

The test must demonstrate that the affected information
remains available in a later session.

The result must arise from normal system operations,
not a hard-coded response.

## 7. AC-06: Provenance Recording

Given a memory extraction, derivation, retrieval,
or decision event,
when the operation completes,
then the relevant source and version relationships
must be recorded.

The event history must identify actual operations
rather than inferred semantic similarity alone.

## 8. AC-07: Backward Tracing

Given a suspicious recorded decision,
when forensic tracing is initiated,
then the engine must identify its recorded upstream
retrieval, memory, and source relationships.

Multiple possible ancestors must be represented
without inventing a single unsupported cause.

## 9. AC-08: Forward Impact Analysis

Given a confirmed compromised memory version,
when forward analysis executes,
then the engine must identify recorded descendants.

Candidates must be marked as potentially affected
until further evidence confirms their status.

## 10. AC-09: Source Authority Validation

Given conflicting supplier information,
when restoration evidence is evaluated,
then the system must use independent source-authority
rules or authorized review.

An LLM-generated assertion alone must not establish
a replacement value as trusted.

## 11. AC-10: Recovery Plan

Given an investigated incident,
when the planner executes,
then the plan must identify:

- Exact suspect versions.
- Affected dependent artifacts.
- Intended quarantine operations.
- Trusted replacement evidence or unresolved state.
- Required regeneration operations.
- Verification steps.
- Approval requirements.

## 12. AC-11: Selective Repair

Given a confirmed compromised claim and verified
replacement evidence,
when recovery executes,
then the system must:

- Quarantine the compromised version.
- Preserve historical evidence.
- Create a corrected candidate version.
- Invalidate affected derived artifacts.
- Preserve unrelated legitimate claims.

The same code must work with changed supplier values.

## 13. AC-12: No Trusted Replacement

Given an incident without authoritative replacement
information,
when recovery is requested,
then the system must:

- Isolate unsupported information.
- Preserve the unresolved state.
- Request verification or review.
- Never fabricate a replacement value.

## 14. AC-13: Retrieval Reconstruction

Given a quarantined memory version,
when the recovery index is rebuilt,
then normal retrieval must exclude that version.

Corrected artifacts must be retrievable only after
the appropriate candidate state is validated.

## 15. AC-14: Behavioral Replay

Given a previously affected agent task,
when replay executes against candidate memory,
then the system must check expected output properties
against independent scenario ground truth.

A single plausible LLM response is insufficient
without the required integrity checks.

## 16. AC-15: Benign Memory Preservation

Given unrelated legitimate supplier claims,
when selective recovery completes,
then their content and permitted availability
must remain unchanged.

## 17. AC-16: Failed Recovery

Given an interrupted regeneration or failed
verification operation,
when recovery terminates,
then partially repaired memory must not become
the active verified generation.

## 18. AC-17: Idempotency

Given an already executed recovery operation,
when the same operation is requested again,
then the system must not create duplicate
active repairs or inconsistent versions.

## 19. AC-18: End-to-End UI

Given a reproducible incident,
a reviewer must be able to:

- Interact with ProcurePilot.
- Observe contaminated persistent memory.
- Inspect a forensic trace.
- View a recovery plan.
- Approve permitted recovery actions.
- Execute the recovery workflow.
- Inspect verification results.

The main demonstration must not depend on manual
database editing or terminal-only intervention.

## 20. AC-19: Generalization

Given a new fictional supplier and different
compromised values,
the same recovery implementation must work
without scenario-specific code changes.

At least one negative or unresolved scenario
must also be tested.

## 21. AC-20: Reproducible Evaluation

Each evaluation run must record:

- Scenario ID.
- Dataset or fixture version.
- Relevant model configuration.
- Ground-truth expected result.
- Observed result.
- Trace output.
- Recovery actions.
- Verification outcome.
- Execution time.
- Pass or fail status.

Metrics must report counts and denominators,
not unexplained percentages.

## 22. MVP Release Gate

The MVP can be considered complete only when:

- The primary scenario works from end to end.
- Recovery changes actual persistent state.
- Retrieval reconstruction succeeds.
- Behavioral replay succeeds.
- Legitimate knowledge remains available.
- Missing-evidence cases fail safely.
- Reproducible test results are saved.
- The demonstration is usable through the UI.

Passing these criteria demonstrates a working
hackathon prototype, not enterprise production readiness.
