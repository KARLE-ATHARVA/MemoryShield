# ADR-0001: MemoryShield Core Architecture

Status: Accepted for Hackathon MVP
Decision date: 2026-11-25

## Context

MemoryShield requires a reproducible recovery pipeline
for compromised external AI-agent memory.

The implementation must be achievable by two developers,
support local AI inference, preserve provenance evidence,
and demonstrate safe restoration and verification.

## Decision 1: Modular Monolith

Use a Python/FastAPI modular monolith rather than
multiple independent backend microservices.

Rationale:

- Easier integration and testing.
- Lower deployment complexity.
- Simpler database transaction boundaries.
- Appropriate scale for the hackathon.
- Modules can be separated later if needed.

## Decision 2: PostgreSQL

Use PostgreSQL for structured claims, immutable versions,
source references, recorded dependencies, and recovery jobs.

Rationale:

- Transaction support.
- Relational integrity.
- Version and provenance queries.
- Familiar development ecosystem.
- Supports pgvector as an extension.

## Decision 3: Versioned Claim-Based Memory

Store individual business claims as versioned records,
while also preserving natural-language artifacts.

Rationale:

- Enables precise repairs.
- Preserves unaffected information.
- Supports source-based validation.
- Provides a stronger recovery unit than entire documents.

## Decision 4: Explicit Provenance

Record dependencies during memory operations.

Rationale:

- Evidence-based trace-back.
- Forward impact analysis.
- Reproducible recovery.
- Avoids inventing causal links after an incident.

## Decision 5: Hybrid AI and Deterministic Recovery

Use an LLM for semantic tasks.

Use deterministic services for:
- Source-authority policy.
- Recovery authorization.
- Dependency traversal.
- Quarantine.
- Version activation.
- Integrity checks.

Rationale:

Semantic reasoning is useful, but security-critical
decisions must remain controllable and testable.

## Decision 6: Recovery Candidate Generations

Build and verify a repaired memory generation
before activating it.

Rationale:

- Avoid partial exposure of repaired state.
- Support validation before release.
- Preserve historical versions.
- Improve failure handling.

## Decision 7: Local-First AI

Prefer a suitable IBM Granite model via Ollama,
after local feasibility tests.

Rationale:

- Avoid paid inference APIs.
- Support repeatable development.
- Demonstrate genuine AI functionality.
- Maintain compatibility with hackathon constraints.

Exact model selection is deferred to local benchmarking.

## Decision 8: No Mandatory Heavy Agent Framework

Begin with a controlled tool-using agent workflow.

Introduce LangGraph only if workflow complexity
justifies the additional dependency.

Rationale:

- Faster development.
- Fewer integration risks.
- Clear memory-control boundaries.
- Easier testing.

## Decision 9: Reference Business Domain

Use a synthetic procurement supplier-knowledge agent.

Rationale:

- Clear business impact.
- Objective source-of-truth comparisons.
- Understandable demonstration.
- Multiple recovery scenarios.
- No real payment execution required.

## Decision 10: Production-Minded Prototype

Implement meaningful engineering safeguards without
claiming enterprise production certification.

Rationale:

- Deliver a complete functioning product.
- Maintain realistic security boundaries.
- Prioritize demonstrable correctness.
- Defer enterprise-only operational complexity.

## Consequences

Benefits:
- Focused development.
- Clear component boundaries.
- Testable recovery operations.
- Explainable forensic history.
- Strong technical demonstration.

Tradeoffs:
- Requires instrumented memory operations.
- Does not automatically support all agent frameworks.
- Does not reconstruct hidden or unlogged reasoning.
- Local LLM performance depends on hardware.
- Production-scale security requires additional work.

## Revisit Conditions

Reconsider the architecture if:

- Local model validation fails.
- Database performance becomes a demonstrated bottleneck.
- Required recovery guarantees cannot be implemented.
- Integration tests reveal a fundamental design conflict.

Any change requires a new ADR or explicit revision.
