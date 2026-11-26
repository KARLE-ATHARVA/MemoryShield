import pytest

from app.memory.policy import (
    MemoryPolicyContext,
    MemoryTrustPolicy,
    Operation,
    TrustLevel,
)


@pytest.mark.parametrize("trust", list(TrustLevel))
def test_ingestion_records_any_trust_level(trust):
    decision = MemoryTrustPolicy().evaluate(
        MemoryPolicyContext(
            operation=Operation.INGEST,
            source_trust=trust,
        )
    )

    assert decision.allowed


def test_unverified_source_cannot_be_activated():
    decision = MemoryTrustPolicy().evaluate(
        MemoryPolicyContext(
            operation=Operation.ACTIVATE,
            source_trust=TrustLevel.UNVERIFIED,
        )
    )

    assert not decision.allowed


def test_verified_source_can_be_activated():
    decision = MemoryTrustPolicy().evaluate(
        MemoryPolicyContext(
            operation=Operation.ACTIVATE,
            source_trust=TrustLevel.VERIFIED,
        )
    )

    assert decision.allowed


def test_provisional_activation_requires_sandbox():
    policy = MemoryTrustPolicy()

    production = policy.evaluate(
        MemoryPolicyContext(
            operation=Operation.ACTIVATE,
            source_trust=TrustLevel.PROVISIONAL,
        )
    )

    sandbox = policy.evaluate(
        MemoryPolicyContext(
            operation=Operation.ACTIVATE,
            source_trust=TrustLevel.PROVISIONAL,
            sandbox_mode=True,
        )
    )

    assert not production.allowed
    assert sandbox.allowed


def test_restore_requires_authorized_approval():
    policy = MemoryTrustPolicy()

    without_approval = policy.evaluate(
        MemoryPolicyContext(
            operation=Operation.RESTORE,
            source_trust=TrustLevel.VERIFIED,
        )
    )

    with_approval = policy.evaluate(
        MemoryPolicyContext(
            operation=Operation.RESTORE,
            source_trust=TrustLevel.VERIFIED,
            authorized_approval=True,
        )
    )

    assert not without_approval.allowed
    assert with_approval.allowed


def test_unverified_evidence_cannot_restore():
    decision = MemoryTrustPolicy().evaluate(
        MemoryPolicyContext(
            operation=Operation.RESTORE,
            source_trust=TrustLevel.UNVERIFIED,
            authorized_approval=True,
        )
    )

    assert not decision.allowed


def test_disputed_source_cannot_restore():
    decision = MemoryTrustPolicy().evaluate(
        MemoryPolicyContext(
            operation=Operation.RESTORE,
            source_trust=TrustLevel.DISPUTED,
            authorized_approval=True,
        )
    )

    assert not decision.allowed
