"""Integration tests for the base memory schema (Phase A).

These tests have been updated for Phase B1 — Claim and MemoryGeneration now
require a workspace_id.  The semantic assertions are identical to the
original; only the fixture construction has been updated to supply the
required workspace owner.
"""

import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    Claim,
    ClaimVersion,
    GenerationClaimVersion,
    MemoryGeneration,
    MemoryWorkspace,
    Source,
)


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")

    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")

    if make_url(url).database != "memoryshield_test":
        raise RuntimeError("Integration tests require database memoryshield_test")

    engine = create_engine(url, pool_pre_ping=True)

    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT 1")

    # Use a transaction that rolls back at the end of each test.
    connection = engine.connect()
    transaction = connection.begin()

    try:
        with Session(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.integration
def test_claim_versions_preserve_history(db):
    ws = MemoryWorkspace(workspace_key="schema-history")
    db.add(ws)
    db.flush()

    source = Source(
        filename="supplier-record.txt",
        source_type="document",
        sha256="a" * 64,
        trust_status="verified",
    )
    claim = Claim(
        workspace_id=ws.id,
        subject_key="supplier-001",
        field_key="payment_terms",
    )

    db.add_all([source, claim])
    db.flush()

    version1 = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="Net 30",
        source_id=source.id,
        trust_status="verified",
    )
    version2 = ClaimVersion(
        claim_id=claim.id,
        version_number=2,
        value="Net 7",
        source_id=source.id,
        trust_status="disputed",
    )

    db.add_all([version1, version2])
    db.flush()

    versions = db.scalars(
        select(ClaimVersion)
        .where(ClaimVersion.claim_id == claim.id)
        .order_by(ClaimVersion.version_number)
    ).all()

    assert len(versions) == 2
    assert versions[0].value == "Net 30"
    assert versions[1].value == "Net 7"
    assert versions[0].id != versions[1].id


@pytest.mark.integration
def test_duplicate_claim_identity_is_rejected(db):
    ws = MemoryWorkspace(workspace_key="schema-dup")
    db.add(ws)
    db.flush()

    db.add(
        Claim(
            workspace_id=ws.id,
            subject_key="supplier-002",
            field_key="approval_status",
        )
    )
    db.flush()

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Claim(
                workspace_id=ws.id,
                subject_key="supplier-002",
                field_key="approval_status",
            )
        )
        db.flush()


@pytest.mark.integration
def test_memory_generation_references_version(db):
    ws = MemoryWorkspace(workspace_key="schema-gen")
    db.add(ws)
    db.flush()

    source = Source(
        filename="approved-record.txt",
        source_type="document",
        sha256="b" * 64,
        trust_status="verified",
    )
    claim = Claim(
        workspace_id=ws.id,
        subject_key="supplier-003",
        field_key="bank_account",
    )

    db.add_all([source, claim])
    db.flush()

    version = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="SYNTHETIC-ACCOUNT-A",
        source_id=source.id,
        trust_status="verified",
    )
    generation = MemoryGeneration(workspace_id=ws.id, state="active")

    db.add_all([version, generation])
    db.flush()

    db.add(
        GenerationClaimVersion(
            generation_id=generation.id,
            workspace_id=ws.id,
            claim_id=claim.id,
            version_id=version.id,
        )
    )

    ws.active_generation_id = generation.id
    ws.revision = 1
    db.flush()

    stored = db.scalar(
        select(GenerationClaimVersion).where(
            GenerationClaimVersion.generation_id == generation.id
        )
    )

    assert stored is not None
    assert stored.version_id == version.id
    assert stored.claim_id == claim.id
