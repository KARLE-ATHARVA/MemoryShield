# MemoryShield AI — Implementation Contract

Version: 1.0
Status: Frozen for Hackathon MVP
Track: IBM AI Builders Challenge — AI for Business

## 1. Product Identity

Product: MemoryShield AI
Tagline: Trace the contamination. Repair the knowledge. Restore trust.

MemoryShield AI is an AI-assisted forensic recovery system
for compromised external persistent memory used by AI agents.

It investigates suspicious knowledge, traces recorded
dependencies, selectively repairs affected information,
reconstructs retrieval state, and verifies recovery through
controlled agent-task replay.

MemoryShield is a recovery product, not merely a detector.

## 2. Business Context

The demonstration application is ProcurePilot, an AI-powered
procurement and supplier knowledge assistant.

ProcurePilot can:
- Ingest synthetic supplier documents.
- Extract structured supplier information.
- Maintain persistent knowledge across sessions.
- Retrieve supplier facts and derived summaries.
- Answer supplier-related questions.
- Produce procurement recommendations.

ProcurePilot does not:
- Transfer money.
- Execute real purchases.
- Modify production ERP systems.
- Process live customer information.

MemoryShield is the core product.
ProcurePilot is the reference application demonstrating it.

## 3. MVP Scope

The MVP must support:

FR-01: Document ingestion and source registration.
FR-02: AI-powered structured claim extraction.
FR-03: Persistent versioned claim storage.
FR-04: Agent memory retrieval across sessions.
FR-05: Recorded source and memory dependencies.
FR-06: Retrieval and agent-output event recording.
FR-07: Reproducible memory contamination.
FR-08: Backward forensic tracing.
FR-09: Forward impact analysis.
FR-10: Source-authority validation.
FR-11: Reviewable recovery plan generation.
FR-12: Quarantine of compromised memory versions.
FR-13: Restoration from verified evidence.
FR-14: Regeneration of affected derived summaries.
FR-15: Safe invalidation of stale retrieval entries.
FR-16: Behavioral replay and regression verification.
FR-17: Controlled activation of repaired memory.
FR-18: Simple investigation and recovery interface.
FR-19: Reproducible evaluation and metrics reporting.

## 4. Primary Demonstration Scenario

The primary case is unauthorized modification of
supplier payment information.

A lower-trust document introduces incorrect information
into ProcurePilot's working memory in a controlled,
intentionally permissive demonstration configuration.

The agent persists the information, creates dependent
knowledge, and uses it in a later session.

An independently verified source or authorized incident
report subsequently establishes the compromise.

MemoryShield traces the recorded propagation, quarantines
compromised versions, restores verified values when
available, rebuilds affected retrieval artifacts, and
verifies corrected agent behavior.

The demonstration must not hard-code supplier identities,
account values, or expected recovery results.

## 5. Secondary Test Scenarios

If implementation time permits:

- Changed contract payment terms.
- Incorrect supplier approval status.
- Legitimate updates that must not be quarantined.
- Missing trusted replacement information.
- Multiple derived artifacts affected by one compromised
  memory version.

The main recovery algorithm must be reusable across
these variations.

## 6. Memory Representation

Memory consists of:

1. Source documents and extracted evidence.
2. Structured claims representing individual facts.
3. Immutable claim versions.
4. Derived memory artifacts, such as summaries.
5. Recorded dependency relationships.
6. Retrieval and decision events.
7. Active memory generations.

A claim is identified by its subject and field.

Each version records:
- Its logical claim identity.
- Its value.
- Its source evidence.
- Its trust and lifecycle status.
- Its creation timestamp.
- Its lineage where applicable.

Historical versions remain available for audit.

## 7. Trust and Authority

The system distinguishes:

- Verified authoritative evidence.
- Approved or provisionally accepted evidence.
- Unverified lower-trust content.
- AI-generated derived information.
- Unresolved or disputed information.

AI-generated content is never independently authoritative.

A historical value is not automatically trustworthy.

Sensitive business values require independent authoritative
evidence or authorized human verification before
MemoryShield can restore them as verified.

When no trusted replacement exists, the information
remains quarantined or unresolved.

## 8. Controlled Contamination Model

MemoryShield is designed for post-compromise recovery.

The demonstration permits lower-trust information to become
active only in an explicitly identified vulnerable sandbox.

This permissive behavior is not the recommended production
security policy.

Source provenance must still be recorded during the
vulnerable run so later forensic tracing is possible.

The normal guarded policy must distinguish provisionally
accepted and verified information.

## 9. Provenance Requirements

Every supported persistent memory operation passes through
the MemoryShield gateway.

The system records relevant relationships between:

- Source document and extracted claim.
- Claim version and derived memory artifact.
- Memory artifact and retrieval event.
- Retrieval event and agent response or decision.

Recorded relationships provide evidence of data exposure
and derivation, not direct proof of the model's hidden
internal reasoning.

AI-inferred semantic associations must be labeled as
hypotheses and never presented as logged causal facts.

## 10. Recovery Pipeline

The pipeline is:

1. Open incident.
2. Preserve relevant evidence.
3. Identify suspicious records.
4. Trace upstream source relationships.
5. Identify potentially affected descendants.
6. Validate authoritative replacement evidence.
7. Generate recovery plan.
8. Obtain approval for sensitive changes.
9. Quarantine compromised versions.
10. Create corrected candidate versions.
11. Rebuild affected derived artifacts.
12. Exclude stale retrieval entries.
13. Run verification tests.
14. Activate the candidate only after required tests pass.

Historical external business actions cannot be undone
simply by changing agent memory.

Affected historical decisions are flagged for review.

## 11. Recovery Consistency

Recovery operations must be idempotent.

A quarantined version must not be available to normal
agent retrieval.

A failed repair must never expose partially rebuilt
memory as a successfully recovered state.

Candidate memory generations are verified before they
become active.

Database state transitions require transaction-safe
handling.

External index updates require reliable retry and
consistency checks.

## 12. AI Responsibilities

A locally runnable LLM may perform:

- Document claim extraction.
- Structured semantic interpretation.
- Investigation assistance.
- Grounded summary generation.
- Natural-language procurement assistance.

The LLM must not independently:

- Decide source authority.
- Invent missing financial values.
- Authorize sensitive recovery operations.
- Bypass quarantine.
- Activate unverified recovered memory.

## 13. Technology Decisions

Frontend:
React, TypeScript, Tailwind CSS.

Backend:
Python, FastAPI, Pydantic.

Database:
PostgreSQL with Alembic migrations.

Retrieval:
Structured queries first, then pgvector and local
embeddings when integrated.

LLM:
Local IBM Granite model through Ollama, subject to
practical model and hardware validation.

Document extraction:
PyMuPDF initially.

Provenance:
PostgreSQL dependency tables and Python graph traversal.

Recovery:
Python services with transactional PostgreSQL operations.

Testing:
Pytest, integration tests, agent-task replay.

Development:
IBM Bob is the primary AI-assisted development tool.
ChatGPT, Codex, and Claude support architecture,
independent review, testing, and debugging.

Deployment:
Docker Compose, initially local.

Optional frameworks such as LangGraph and Docling may
be added only if a demonstrated requirement justifies them.

## 14. Explicit Non-Goals

The hackathon MVP will not provide:

- Editing of knowledge inside LLM model weights.
- Universal compatibility with all agent frameworks.
- Unlogged historical dependency reconstruction.
- General-purpose malware removal.
- Live banking integrations.
- Real financial transaction execution.
- Enterprise multi-tenancy.
- Guaranteed detection of all memory attacks.
- Autonomous restoration without trustworthy evidence.
- Production security certification.

## 15. Evaluation Principles

Compare:

A. Clean baseline.
B. Contaminated memory.
C. Repaired memory.

Where relevant, also compare against:

D. Source deletion only.
E. Whole-memory rollback.

Record:

- Recovery success.
- Trace coverage.
- Benign-memory preservation.
- False quarantine rate.
- Stale retrieval rate.
- Behavioral replay success.
- Recovery execution time.

All reported metrics must come from actual test runs.

Results must state scenario counts, configurations,
and measurement methodology.

## 16. Definition of MVP Completion

The project is functionally complete when:

- The agent uses real persistent memory.
- Contamination survives across sessions.
- Recorded provenance identifies the source.
- Forward tracing identifies affected descendants.
- The system generates a reviewable repair plan.
- Compromised versions are excluded from retrieval.
- Verified information is selectively restored.
- Dependent memory artifacts are rebuilt.
- The original affected agent task is replayed.
- Legitimate unrelated knowledge is preserved.
- Required verification checks pass.
- The end-to-end workflow is accessible through the UI.
- Evaluation results are saved reproducibly.

## 17. Change Control

This contract is the primary scope reference.

Any material change must document:

- Reason for change.
- Affected requirements.
- Impact on architecture.
- Impact on tests.
- Impact on hackathon timeline.

Changes must not silently contradict the HLD, LLD,
architecture, evaluation plan, or system flow.
