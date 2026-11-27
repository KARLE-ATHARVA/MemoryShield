"""Integration test: activation versus quarantine concurrency."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
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
from app.memory.security import (
    ActorRole,
    AuthorizationContext,
)


@pytest.mark.integration
def test_concurrent_activation_and_quarantine_is_safe():
    url = os.environ.get("TEST_DATABASE_URL")

    if not url or make_url(url).database != "memoryshield_test":
        pytest.fail("Must use isolated memoryshield_test database.")

    engine = create_engine(
        url,
        pool_size=4,
        max_overflow=0,
        pool_timeout=10,
    )

    workspace_key = f"race-test-{uuid4()}"

    try:
        # Both workers need committed records visible to
        # independent PostgreSQL connections.
        with Session(engine) as session, session.begin():
            gateway = MemoryGateway(session)
            ctx = gateway.get_or_create_workspace(workspace_key)

            source = Source(
                filename="race-test.txt",
                source_type="document",
                sha256="d" * 64,
                trust_status="verified",
            )
            session.add(source)
            session.flush()

            claim = gateway.get_or_create_claim(
                ctx,
                f"race-supplier-{uuid4()}",
                "bank_account",
            )

            version = ClaimVersion(
                claim_id=claim.id,
                version_number=1,
                value="123456",
                source_id=source.id,
                trust_status="verified",
            )
            session.add(version)
            session.flush()

            candidate = gateway.create_candidate_generation(
                ctx,
                [version.id],
            )

            workspace_id = ctx.workspace_id
            version_id = version.id
            candidate_id = candidate.id

        barrier = Barrier(2, timeout=15)

        def activate():
            with Session(engine) as session:
                gateway = MemoryGateway(session)
                ctx = gateway.resolve_workspace(workspace_key)

                barrier.wait()

                try:
                    gateway.activate_generation(
                        ctx,
                        candidate_id,
                        source_trust=TrustLevel.VERIFIED,
                    )
                    session.commit()
                    return "activated"

                except (StaleWorkspaceError, PolicyDeniedError):
                    session.rollback()
                    return "rejected"

        def quarantine():
            with Session(engine) as session:
                gateway = MemoryGateway(session)
                ctx = gateway.resolve_workspace(workspace_key)

                reviewer = AuthorizationContext(
                    actor_id="integration-test-reviewer",
                    role=ActorRole.REVIEWER,
                    workspace_id=ctx.workspace_id,
                )

                barrier.wait()

                gateway.set_claim_visibility(
                    ctx,
                    version_id,
                    "quarantined",
                    reviewer,
                    "Concurrent security investigation",
                )
                session.commit()

                return "quarantined"

        with ThreadPoolExecutor(max_workers=2) as pool:
            activation_future = pool.submit(activate)
            quarantine_future = pool.submit(quarantine)

            activation_result = activation_future.result(timeout=30)
            quarantine_result = quarantine_future.result(timeout=30)

        assert activation_result in {"activated", "rejected"}
        assert quarantine_result == "quarantined"

        # Read the final committed database state, not an ORM cache.
        with Session(engine) as session:
            workspace = session.get(MemoryWorkspace, workspace_id)
            version = session.get(ClaimVersion, version_id)
            generation = session.get(MemoryGeneration, candidate_id)

            assert workspace is not None
            assert version is not None
            assert generation is not None

            assert version.visibility_status == "quarantined"
            assert workspace.active_generation_id is None
            assert generation.state != "active"

            if activation_result == "activated":
                assert workspace.revision == 2
                assert generation.state == "retired"
            else:
                assert workspace.revision == 1
                assert generation.state == "candidate"

    finally:
        engine.dispose()
