from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database.models import (
    ClaimVersion,
    MemorySecurityAudit,
    MemoryWorkspace,
    Source,
)
from app.memory.gateway import MemoryGateway, PolicyDeniedError
from app.memory.security import (
    ActorRole,
    AuthorizationContext,
    AuthorizationDeniedError,
)


@pytest.fixture
def db():
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    url = os.environ.get("TEST_DATABASE_URL")
    if not url or make_url(url).database != "memoryshield_test":
        pytest.fail("Tests require memoryshield_test.")

    engine = create_engine(url)
    connection = engine.connect()
    transaction = connection.begin()

    try:
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def memory(db):
    gateway = MemoryGateway(db)
    ctx = gateway.get_or_create_workspace(f"security-{uuid4()}")
    source = Source(
        filename="review.txt",
        source_type="document",
        sha256="c" * 64,
        trust_status="verified",
    )
    db.add(source)
    db.flush()

    claim = gateway.get_or_create_claim(ctx, f"supplier-{uuid4()}", "bank_account")
    version = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="123456",
        source_id=source.id,
        trust_status="verified",
    )
    db.add(version)
    db.flush()

    reviewer = AuthorizationContext(
        actor_id="test-reviewer",
        role=ActorRole.REVIEWER,
        workspace_id=ctx.workspace_id,
    )
    agent = AuthorizationContext(
        actor_id="test-agent",
        role=ActorRole.AGENT,
        workspace_id=ctx.workspace_id,
    )
    return gateway, ctx, source, version, reviewer, agent


def test_agent_cannot_quarantine(db, memory):
    gateway, ctx, _, version, _, agent = memory

    with pytest.raises(AuthorizationDeniedError):
        gateway.set_claim_visibility(
            ctx,
            version.id,
            "quarantined",
            agent,
            "Agent requested quarantine",
        )

    assert version.visibility_status == "eligible"


def test_reviewer_can_quarantine_and_audit(db, memory):
    gateway, ctx, _, version, reviewer, _ = memory

    gateway.set_claim_visibility(
        ctx,
        version.id,
        "quarantined",
        reviewer,
        "Suspicious supplier document",
    )

    assert version.visibility_status == "quarantined"

    audit = db.scalar(
        select(MemorySecurityAudit).where(
            MemorySecurityAudit.workspace_id == ctx.workspace_id
        )
    )
    assert audit is not None
    assert audit.actor_id == "test-reviewer"
    assert audit.policy_version == "b1.4-v1"

    ws = db.get(MemoryWorkspace, ctx.workspace_id)
    assert ws.revision == 1


def test_wrong_workspace_actor_denied(db, memory):
    gateway, ctx, _, version, _, _ = memory

    attacker = AuthorizationContext(
        actor_id="other-reviewer",
        role=ActorRole.REVIEWER,
        workspace_id="different-workspace",
    )

    with pytest.raises(AuthorizationDeniedError):
        gateway.set_claim_visibility(
            ctx,
            version.id,
            "quarantined",
            attacker,
            "Unauthorized attempt",
        )


def test_release_requires_verified_evidence(db, memory):
    gateway, ctx, source, version, reviewer, _ = memory

    gateway.set_claim_visibility(
        ctx,
        version.id,
        "quarantined",
        reviewer,
        "Initial quarantine",
    )

    source.trust_status = "disputed"
    db.flush()

    with pytest.raises(PolicyDeniedError):
        gateway.set_claim_visibility(
            ctx,
            version.id,
            "eligible",
            reviewer,
            "Attempted restoration",
        )


def test_review_disputes_source_and_quarantines_versions(db, memory):
    gateway, ctx, source, version, reviewer, _ = memory

    gateway.review_source_trust(
        ctx,
        source.id,
        "disputed",
        reviewer,
        "Independent review found inconsistency",
        "review-case-001",
    )

    assert source.trust_status == "disputed"
    assert version.visibility_status == "quarantined"

    ws = db.get(MemoryWorkspace, ctx.workspace_id)
    assert ws.revision == 1


def test_security_audit_cannot_be_rewritten(db, memory):
    gateway, ctx, _, version, reviewer, _ = memory

    gateway.set_claim_visibility(
        ctx,
        version.id,
        "quarantined",
        reviewer,
        "Forensic hold",
    )

    audit = db.scalar(select(MemorySecurityAudit))
    assert audit is not None

    with (
        pytest.raises(IntegrityError),
        db.begin_nested(),
    ):
        db.execute(
            text(
                "UPDATE memory_security_audit SET actor_id = 'tampered' WHERE id = :id"
            ),
            {"id": audit.id},
        )


def test_quarantine_retires_active_generation(db, memory):
    from app.memory.policy import TrustLevel

    gateway, ctx, _, version, reviewer, _ = memory

    candidate = gateway.create_candidate_generation(ctx, [version.id])
    gateway.activate_generation(
        ctx,
        candidate.id,
        source_trust=TrustLevel.VERIFIED,
    )

    gateway.set_claim_visibility(
        ctx,
        version.id,
        "quarantined",
        reviewer,
        "Potential contamination",
    )

    ws = db.get(MemoryWorkspace, ctx.workspace_id)

    assert ws.active_generation_id is None
    assert ws.revision == 2
    assert candidate.state == "retired"


def test_reviewer_can_release_verified_quarantine(db, memory):
    gateway, ctx, _, version, reviewer, _ = memory

    gateway.set_claim_visibility(
        ctx,
        version.id,
        "quarantined",
        reviewer,
        "Temporary hold",
    )

    gateway.set_claim_visibility(
        ctx,
        version.id,
        "eligible",
        reviewer,
        "Reviewed verified evidence",
    )

    assert version.visibility_status == "eligible"
    assert db.get(MemoryWorkspace, ctx.workspace_id).revision == 2


def test_shared_source_cannot_be_globally_reviewed(db, memory):
    gateway, ctx, source, _, reviewer, _ = memory

    other = gateway.get_or_create_workspace(f"other-{uuid4()}")
    other_claim = gateway.get_or_create_claim(
        other, f"other-supplier-{uuid4()}", "status"
    )

    db.add(
        ClaimVersion(
            claim_id=other_claim.id,
            version_number=1,
            value="Other workspace value",
            source_id=source.id,
            trust_status="unverified",
        )
    )
    db.flush()

    with pytest.raises(AuthorizationDeniedError):
        gateway.review_source_trust(
            ctx,
            source.id,
            "disputed",
            reviewer,
            "Requested review",
            "review-case-002",
        )
