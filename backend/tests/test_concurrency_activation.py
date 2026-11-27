import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database.models import (
    ClaimVersion,
    MemoryGeneration,
    MemoryWorkspace,
    Source,
)
from app.memory.gateway import (
    MemoryGateway,
    PolicyDeniedError,
    StaleWorkspaceError,
)
from app.memory.policy import TrustLevel


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url or make_url(url).database != "memoryshield_test":
        pytest.fail("Must use memoryshield_test")

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


def setup_memory(db):
    gateway = MemoryGateway(db)
    ctx = gateway.get_or_create_workspace(f"b13-{uuid4()}")

    source = Source(
        filename="test.txt",
        source_type="document",
        sha256="a" * 64,
        trust_status="verified",
    )
    db.add(source)
    db.flush()

    claim = gateway.get_or_create_claim(ctx, f"subject-{uuid4()}", "status")

    version = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="Original verified value",
        source_id=source.id,
        trust_status="verified",
    )
    db.add(version)
    db.flush()

    return gateway, ctx, version


@pytest.mark.integration
def test_activation_increments_revision(db):
    gateway, ctx, version = setup_memory(db)

    candidate = gateway.create_candidate_generation(ctx, [version.id])

    assert candidate.base_revision == 0

    workspace = gateway.activate_generation(
        ctx,
        candidate.id,
        source_trust=TrustLevel.VERIFIED,
    )

    assert workspace.revision == 1
    assert workspace.active_generation_id == candidate.id
    assert candidate.state == "active"


@pytest.mark.integration
def test_stale_candidate_is_rejected(db):
    gateway, ctx, version = setup_memory(db)

    first = gateway.create_candidate_generation(ctx, [version.id])
    second = gateway.create_candidate_generation(ctx, [version.id])

    gateway.activate_generation(
        ctx,
        first.id,
        source_trust=TrustLevel.VERIFIED,
    )

    with pytest.raises(StaleWorkspaceError):
        gateway.activate_generation(
            ctx,
            second.id,
            source_trust=TrustLevel.VERIFIED,
        )

    workspace = db.get(MemoryWorkspace, ctx.workspace_id)
    assert workspace.active_generation_id == first.id
    assert workspace.revision == 1


@pytest.mark.integration
def test_quarantined_version_blocks_activation(db):
    gateway, ctx, version = setup_memory(db)

    candidate = gateway.create_candidate_generation(ctx, [version.id])

    version.visibility_status = "quarantined"
    db.flush()

    with pytest.raises(PolicyDeniedError):
        gateway.activate_generation(
            ctx,
            candidate.id,
            source_trust=TrustLevel.VERIFIED,
        )

    workspace = db.get(MemoryWorkspace, ctx.workspace_id)
    assert workspace.active_generation_id is None
    assert workspace.revision == 0


@pytest.mark.integration
def test_denied_policy_preserves_workspace_state(db):
    gateway, ctx, version = setup_memory(db)

    candidate = gateway.create_candidate_generation(ctx, [version.id])

    with pytest.raises(PolicyDeniedError):
        gateway.activate_generation(
            ctx,
            candidate.id,
            source_trust=TrustLevel.UNVERIFIED,
        )

    workspace = db.get(MemoryWorkspace, ctx.workspace_id)
    assert workspace.active_generation_id is None
    assert workspace.revision == 0
    assert candidate.state == "candidate"


@pytest.mark.integration
def test_repeated_activation_rejected(db):
    gateway, ctx, version = setup_memory(db)

    candidate = gateway.create_candidate_generation(ctx, [version.id])

    gateway.activate_generation(
        ctx,
        candidate.id,
        source_trust=TrustLevel.VERIFIED,
    )

    with pytest.raises(ValueError):
        gateway.activate_generation(
            ctx,
            candidate.id,
            source_trust=TrustLevel.VERIFIED,
        )

    workspace = db.scalar(
        select(MemoryWorkspace).where(MemoryWorkspace.id == ctx.workspace_id)
    )
    assert workspace.revision == 1


@pytest.mark.integration
def test_two_transactions_cannot_activate_stale_candidates():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import delete

    url = os.environ["TEST_DATABASE_URL"]
    if make_url(url).database != "memoryshield_test":
        raise RuntimeError("Unsafe database target")

    engine = create_engine(url, pool_size=3, max_overflow=0)

    workspace_id = None

    try:
        # Persist setup so independent connections can see the records.
        with Session(engine) as session, session.begin():
            gateway = MemoryGateway(session)
            ctx = gateway.get_or_create_workspace(f"b13-concurrent-{uuid4()}")
            workspace_id = ctx.workspace_id

            first = gateway.create_candidate_generation(ctx, [])
            second = gateway.create_candidate_generation(ctx, [])

            first_id = first.id
            second_id = second.id
            workspace_key = ctx.workspace_key

        barrier = Barrier(2)

        def activate(generation_id):
            with Session(engine) as session:
                gateway = MemoryGateway(session)
                ctx = gateway.resolve_workspace(workspace_key)

                barrier.wait(timeout=10)

                try:
                    with session.begin_nested():
                        gateway.activate_generation(
                            ctx,
                            generation_id,
                            source_trust=TrustLevel.VERIFIED,
                        )
                    session.commit()
                    return "activated"
                except StaleWorkspaceError:
                    session.rollback()
                    return "stale"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(activate, first_id),
                pool.submit(activate, second_id),
            ]
            outcomes = [f.result(timeout=20) for f in futures]

        assert sorted(outcomes) == ["activated", "stale"]

        with Session(engine) as session:
            workspace = session.get(MemoryWorkspace, workspace_id)

            assert workspace.revision == 1
            assert workspace.active_generation_id in {
                first_id,
                second_id,
            }

    finally:
        # Remove only the temporary workspace and generations
        # created by this test. Never touch application data.
        if workspace_id is not None:
            with Session(engine) as session, session.begin():
                workspace = session.get(MemoryWorkspace, workspace_id)
                if workspace is not None:
                    workspace.active_generation_id = None
                    session.flush()
                    session.execute(
                        delete(MemoryGeneration).where(
                            MemoryGeneration.workspace_id == workspace_id
                        )
                    )
                    session.delete(workspace)

        engine.dispose()
