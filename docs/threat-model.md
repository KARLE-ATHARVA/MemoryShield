# MemoryShield AI — Threat Model

Version: 1.0
Status: Frozen for Hackathon MVP

## 1. Protected Asset

The protected asset is an AI agent's external persistent
memory and the reliability of business decisions that
depend on that memory.

Protected components include:

- Structured supplier claims.
- Derived memory summaries.
- Active memory versions.
- Retrieval index references.
- Provenance and usage history.
- Recovery plans and verification evidence.

## 2. Threat Actor

The attacker can control or manipulate a lower-trust
document supplied to the procurement agent.

The attacker attempts to introduce false business facts
that persist and influence later agent behavior.

The attacker does not have:

- Direct PostgreSQL administrator access.
- Permission to alter immutable provenance logs.
- Control of authoritative supplier records.
- Permission to approve recovery actions.
- Control over the recovery verification system.

## 3. Primary Threat

Persistent memory contamination through untrusted
business documents.

The attack may influence:

- Extracted claims.
- Saved supplier knowledge.
- Derived summaries.
- Retrieval results.
- Later recommendations.

The primary concern is corruption that survives beyond
the originating interaction.

## 4. Trust Boundaries

Boundary A:
External document to document parser.

Boundary B:
Parsed text to LLM claim extraction.

Boundary C:
Extracted claim to persistent memory gateway.

Boundary D:
Persistent memory to agent retrieval context.

Boundary E:
Investigation results to recovery decisions.

Boundary F:
Candidate recovery state to active agent memory.

No lower-trust input automatically becomes authoritative
when it crosses these boundaries.

## 5. Source Authority

Sources have an explicit authority classification.

A file name, formatting, or an LLM-generated statement
does not establish authority.

Verified changes require independent supporting evidence
or an authorized human approval event.

The demonstration's vulnerable mode may temporarily
permit provisional data to become active.

That mode must remain isolated from real business systems.

## 6. Threat Scenarios

TM-01:
A lower-trust source creates an unauthorized supplier fact.

TM-02:
The compromised claim survives into another agent session.

TM-03:
A derived summary propagates the compromised information.

TM-04:
Removing the source leaves contaminated memory active.

TM-05:
Stale vector retrieval returns quarantined information.

TM-06:
A legitimate update is incorrectly classified as malicious.

TM-07:
A repair mistakenly removes unrelated trusted facts.

TM-08:
A recovery process fails partway through reconstruction.

TM-09:
No authoritative replacement information exists.

TM-10:
An LLM incorrectly interprets semantic relationships.

TM-11:
A historical recommendation already used compromised data.

TM-12:
A repeated recovery request attempts duplicate changes.

## 7. Security Invariants

INV-01:
Historical memory versions must be preserved.

INV-02:
Normal retrieval must exclude quarantined versions.

INV-03:
Source authority must be checked independently of the LLM.

INV-04:
Missing trusted evidence must not be replaced with a guess.

INV-05:
Recorded dependencies must be distinguishable from inferred
semantic associations.

INV-06:
Recovery must preserve unrelated valid knowledge.

INV-07:
Failed verification must prevent candidate activation.

INV-08:
Recovery operations must be idempotent.

INV-09:
Sensitive repairs require authorized approval.

INV-10:
Provenance history must remain inspectable after repair.

INV-11:
Historical decisions must not be falsely represented as
reversed or erased.

INV-12:
Every evaluation scenario must retain its ground truth
separately from the agent's working memory.

## 8. Recovery Safety

A recovered state cannot become active solely because
an LLM considers it correct.

Activation requires:

- Validated restoration evidence.
- Successful database integrity checks.
- Retrieval consistency checks.
- Required behavioral replay results.
- Approval where policy requires it.

When a condition fails, affected information remains
isolated and the incident remains unresolved.

## 9. What MemoryShield Can Establish

The system can establish:

- Which recorded source created a memory version.
- Which versions contributed to recorded derived artifacts.
- Which versions were returned during agent retrieval.
- Which decisions received related retrieved context.
- Which supported artifacts were successfully repaired.
- Whether controlled replay tests pass after recovery.

## 10. What MemoryShield Cannot Establish

The MVP cannot guarantee:

- Complete reconstruction of undocumented events.
- Full visibility into hidden LLM reasoning.
- Detection of every malicious document.
- Correctness of a supposedly authoritative source that
  has itself been compromised.
- Reversal of external business actions already executed.
- Safety of arbitrary unsupported agent integrations.
- Absence of all possible future contamination.

## 11. Security Testing Requirements

Tests must include:

- Valid and malicious supplier updates.
- Multiple dependent memories.
- Missing authoritative evidence.
- Repeated recovery requests.
- Interrupted recovery attempts.
- Retrieval attempts against quarantined versions.
- Preservation of unrelated memory.
- Source-to-decision forensic trace.
- Negative tests for unsafe activation.

## 12. Hackathon Safety Boundary

All suppliers, account numbers, documents, and business
decisions in the demo are synthetic.

No real financial transaction execution is permitted.

No production customer data is required.

The project is a security research prototype, not a
certified enterprise security control.
