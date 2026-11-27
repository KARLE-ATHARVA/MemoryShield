import os

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    AgentDecision,
    Claim,
    ClaimVersion,
    DependencyEdge,
    MemoryArtifact,
    MemoryWorkspace,
    RetrievalEvent,
    Source,
)


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")

    if not url:
        pytest.fail("TEST_DATABASE_URL is required")

    if make_url(url).database != "memoryshield_test":
        raise RuntimeError(
            "Refusing to run against a non-test database"
        )

    engine = create_engine(url, pool_pre_ping=True)
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
def evidence(db):
    workspace = MemoryWorkspace(
        workspace_key="immutability-test-workspace"
    )
    source = Source(
        filename="original.txt",
        source_type="document",
        sha256="a" * 64,
        trust_status="verified",
    )

    db.add_all([workspace, source])
    db.flush()

    claim = Claim(
        workspace_id=workspace.id,
        subject_key="immutability-subject",
        field_key="status",
    )

    db.add(claim)
    db.flush()

    version = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="Original verified value",
        source_id=source.id,
        trust_status="verified",
    )

    artifact = MemoryArtifact(
        artifact_type="summary",
        content="Original memory summary",
    )

    event = RetrievalEvent(
        run_id="immutability-test-run",
        query="Find verified information",
        retrieved_version_ids=[],
    )

    db.add_all([version, artifact, event])
    db.flush()

    edge = DependencyEdge(
        parent_type="source",
        parent_id=source.id,
        child_type="claim_version",
        child_id=version.id,
        relationship_type="extracted_from",
    )

    decision = AgentDecision(
        run_id="immutability-test-run",
        retrieval_event_id=event.id,
        output="Original agent output",
    )

    db.add_all([edge, decision])
    db.flush()

    return {
        "sources": source.id,
        "claims": claim.id,
        "claim_versions": version.id,
        "memory_artifacts": artifact.id,
        "dependency_edges": edge.id,
        "retrieval_events": event.id,
        "agent_decisions": decision.id,
        "source": source,
        "claim": claim,
        "version": version,
        "artifact": artifact,
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    ("table", "column", "replacement"),
    [
        ("sources", "sha256", "b" * 64),
        ("claims", "subject_key", "modified-subject"),
        ("claim_versions", "value", "Tampered value"),
        ("claim_versions", "source_id", "invalid-source-id"),
        ("memory_artifacts", "content", "Tampered summary"),
        ("dependency_edges", "relationship_type", "tampered"),
        ("retrieval_events", "query", "Tampered query"),
        ("agent_decisions", "output", "Tampered output"),
    ],
)
def test_direct_sql_cannot_modify_historical_evidence(
    db, evidence, table, column, replacement
):
    with pytest.raises(
        IntegrityError,
        match="Historical evidence is append-only",
    ), db.begin_nested():
        db.execute(
            text(
                f"UPDATE {table} SET {column} = :replacement "
                "WHERE id = :record_id"
            ),
            {
                "replacement": replacement,
                "record_id": evidence[table],
            },
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "table",
    [
        "sources",
        "claims",
        "claim_versions",
        "memory_artifacts",
        "dependency_edges",
        "retrieval_events",
        "agent_decisions",
    ],
)
def test_direct_sql_cannot_delete_historical_evidence(
    db, evidence, table
):
    with pytest.raises(
        IntegrityError,
        match="Historical evidence is append-only",
    ), db.begin_nested():
        db.execute(
            text(f"DELETE FROM {table} WHERE id = :record_id"),
            {"record_id": evidence[table]},
        )


@pytest.mark.integration
def test_quarantine_claim_version_is_permitted(db, evidence):
    version_id = evidence["claim_versions"]

    db.execute(
        text(
            "UPDATE claim_versions "
            "SET visibility_status = 'quarantined' "
            "WHERE id = :version_id"
        ),
        {"version_id": version_id},
    )

    db.expire_all()
    version = db.get(ClaimVersion, version_id)

    assert version.visibility_status == "quarantined"
    assert version.value == "Original verified value"


@pytest.mark.integration
def test_quarantine_memory_artifact_is_permitted(db, evidence):
    artifact_id = evidence["memory_artifacts"]

    db.execute(
        text(
            "UPDATE memory_artifacts "
            "SET visibility_status = 'quarantined' "
            "WHERE id = :artifact_id"
        ),
        {"artifact_id": artifact_id},
    )

    db.expire_all()
    artifact = db.get(MemoryArtifact, artifact_id)

    assert artifact.visibility_status == "quarantined"
    assert artifact.content == "Original memory summary"


@pytest.mark.integration
def test_corrected_claim_creates_new_version(db, evidence):
    original = evidence["version"]

    corrected = ClaimVersion(
        claim_id=original.claim_id,
        version_number=2,
        value="Corrected value",
        source_id=original.source_id,
        trust_status="verified",
    )

    db.add(corrected)
    db.flush()

    versions = db.scalars(
        select(ClaimVersion)
        .where(ClaimVersion.claim_id == original.claim_id)
        .order_by(ClaimVersion.version_number)
    ).all()

    assert len(versions) == 2
    assert versions[0].value == "Original verified value"
    assert versions[1].value == "Corrected value"
    assert versions[0].id != versions[1].id


@pytest.mark.integration
def test_source_trust_status_can_change_without_rewriting_evidence(
    db, evidence
):
    source_id = evidence["sources"]

    db.execute(
        text(
            "UPDATE sources "
            "SET trust_status = 'disputed' "
            "WHERE id = :source_id"
        ),
        {"source_id": source_id},
    )

    db.expire_all()
    source = db.get(Source, source_id)

    assert source.trust_status == "disputed"
    assert source.sha256 == "a" * 64
