"""Integration tests for workspace-scoped memory ownership (Phase B1).

These tests require a running PostgreSQL test database.  Run with:

    TEST_DATABASE_URL=postgresql+psycopg://...@localhost:5434/memoryshield_test \
        python -m pytest tests/test_workspace_isolation.py -v -m integration

All tests use rollback-based isolation — no rows persist between test cases.
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
from app.memory.gateway import (
    CrossWorkspaceError,
    MemoryGateway,
    PolicyDeniedError,
    WorkspaceNotFoundError,
)
from app.memory.policy import TrustLevel

# ---------------------------------------------------------------------------
# Shared fixture — rollback-isolated database session
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helper — create a minimal Source for FK satisfaction
# ---------------------------------------------------------------------------


def _make_source(db: Session, suffix: str = "") -> Source:
    source = Source(
        filename=f"doc{suffix}.txt",
        source_type="document",
        sha256=("a" * 63 + suffix[-1]) if suffix else "a" * 64,
        trust_status="verified",
    )
    db.add(source)
    db.flush()
    return source


# ===========================================================================
# Tests — directly via SQLAlchemy models
# ===========================================================================


@pytest.mark.integration
def test_two_workspaces_can_share_subject_and_field(db):
    """The same (subject_key, field_key) is allowed in two separate workspaces."""
    ws_a = MemoryWorkspace(workspace_key="ws-a")
    ws_b = MemoryWorkspace(workspace_key="ws-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    claim_a = Claim(
        workspace_id=ws_a.id,
        subject_key="supplier-001",
        field_key="bank_account",
    )
    claim_b = Claim(
        workspace_id=ws_b.id,
        subject_key="supplier-001",
        field_key="bank_account",
    )
    db.add_all([claim_a, claim_b])
    db.flush()

    # Both rows must exist and have different IDs.
    assert claim_a.id != claim_b.id
    assert claim_a.workspace_id == ws_a.id
    assert claim_b.workspace_id == ws_b.id


@pytest.mark.integration
def test_duplicate_claim_identity_within_workspace_is_rejected(db):
    """Duplicate (workspace_id, subject_key, field_key) violates uq_claim_identity."""
    ws = MemoryWorkspace(workspace_key="ws-dup")
    db.add(ws)
    db.flush()

    db.add(
        Claim(
            workspace_id=ws.id,
            subject_key="supplier-002",
            field_key="payment_terms",
        )
    )
    db.flush()

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Claim(
                workspace_id=ws.id,
                subject_key="supplier-002",
                field_key="payment_terms",
            )
        )
        db.flush()


@pytest.mark.integration
def test_workspace_a_cannot_read_workspace_b_claims(db):
    """Scoped query returns only the requesting workspace's claims."""
    ws_a = MemoryWorkspace(workspace_key="ws-reader-a")
    ws_b = MemoryWorkspace(workspace_key="ws-reader-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    db.add(
        Claim(
            workspace_id=ws_a.id,
            subject_key="supplier-003",
            field_key="contact_email",
        )
    )
    db.add(
        Claim(
            workspace_id=ws_b.id,
            subject_key="supplier-003",
            field_key="contact_email",
        )
    )
    db.flush()

    # Query scoped to ws_a — must not return ws_b's claim.
    claims_a = db.scalars(
        select(Claim).where(
            Claim.workspace_id == ws_a.id,
            Claim.subject_key == "supplier-003",
        )
    ).all()

    assert len(claims_a) == 1
    assert claims_a[0].workspace_id == ws_a.id


@pytest.mark.integration
def test_claim_versions_remain_associated_with_correct_workspace(db):
    """ClaimVersions inherit workspace scoping through their parent Claim FK."""
    ws_a = MemoryWorkspace(workspace_key="ws-ver-a")
    ws_b = MemoryWorkspace(workspace_key="ws-ver-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    source = _make_source(db, "1")

    claim_a = Claim(
        workspace_id=ws_a.id,
        subject_key="supplier-004",
        field_key="approved_vendor",
    )
    claim_b = Claim(
        workspace_id=ws_b.id,
        subject_key="supplier-004",
        field_key="approved_vendor",
    )
    db.add_all([claim_a, claim_b])
    db.flush()

    ver_a = ClaimVersion(
        claim_id=claim_a.id,
        version_number=1,
        value="true",
        source_id=source.id,
        trust_status="verified",
    )
    ver_b = ClaimVersion(
        claim_id=claim_b.id,
        version_number=1,
        value="false",
        source_id=source.id,
        trust_status="unverified",
    )
    db.add_all([ver_a, ver_b])
    db.flush()

    # Retrieve versions scoped to ws_a.
    versions_a = db.scalars(
        select(ClaimVersion)
        .join(Claim, ClaimVersion.claim_id == Claim.id)
        .where(Claim.workspace_id == ws_a.id)
    ).all()

    assert len(versions_a) == 1
    assert versions_a[0].id == ver_a.id
    assert versions_a[0].value == "true"


@pytest.mark.integration
def test_cross_workspace_generation_membership_fails(db):
    """A GenerationClaimVersion cannot link a generation to a claim from another workspace.

    The database FK on (version_id, claim_id) → claim_versions(id, claim_id)
    is not violated by cross-workspace membership directly, so this test
    verifies that the gateway refuses the cross-workspace write before it
    reaches the DB layer.
    """
    ws_a = MemoryWorkspace(workspace_key="ws-gen-a")
    ws_b = MemoryWorkspace(workspace_key="ws-gen-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    source = _make_source(db, "2")

    claim_b = Claim(
        workspace_id=ws_b.id,
        subject_key="supplier-005",
        field_key="address",
    )
    db.add(claim_b)
    db.flush()

    ver_b = ClaimVersion(
        claim_id=claim_b.id,
        version_number=1,
        value="123 Main St",
        source_id=source.id,
        trust_status="verified",
    )
    db.add(ver_b)
    db.flush()

    gw = MemoryGateway(db)
    ctx_a = gw.get_or_create_workspace("ws-gen-a")

    # Attempting to create a generation in ws_a using a version from ws_b
    # must raise CrossWorkspaceError.
    with pytest.raises(CrossWorkspaceError):
        gw.create_candidate_generation(ctx_a, [ver_b.id])


@pytest.mark.integration
def test_workspace_cannot_activate_another_workspaces_generation(db):
    """Gateway rejects activation when the generation belongs to a different workspace."""
    ws_a = MemoryWorkspace(workspace_key="ws-act-a")
    ws_b = MemoryWorkspace(workspace_key="ws-act-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    # Build a valid candidate generation owned by ws_b.
    source = _make_source(db, "3")
    claim_b = Claim(
        workspace_id=ws_b.id,
        subject_key="supplier-006",
        field_key="lead_time",
    )
    db.add(claim_b)
    db.flush()

    ver_b = ClaimVersion(
        claim_id=claim_b.id,
        version_number=1,
        value="14 days",
        source_id=source.id,
        trust_status="verified",
    )
    db.add(ver_b)
    db.flush()

    gen_b = MemoryGeneration(workspace_id=ws_b.id, state="candidate")
    db.add(gen_b)
    db.flush()

    db.add(
        GenerationClaimVersion(
            generation_id=gen_b.id,
            workspace_id=ws_b.id,
            claim_id=claim_b.id,
            version_id=ver_b.id,
        )
    )
    db.flush()

    gw = MemoryGateway(db)
    ctx_a = gw.get_or_create_workspace("ws-act-a")

    # ws_a trying to activate ws_b's generation must raise CrossWorkspaceError.
    with pytest.raises(CrossWorkspaceError):
        gw.activate_generation(
            ctx_a,
            gen_b.id,
            source_trust=TrustLevel.VERIFIED,
            authorized_approval=True,
        )


# ===========================================================================
# Tests — via gateway (workspace-key resolved, not raw DB IDs)
# ===========================================================================


@pytest.mark.integration
def test_gateway_resolves_workspace_by_key(db):
    """resolve_workspace returns a WorkspaceContext with the correct workspace_id."""
    ws = MemoryWorkspace(workspace_key="gw-resolve")
    db.add(ws)
    db.flush()

    gw = MemoryGateway(db)
    ctx = gw.resolve_workspace("gw-resolve")

    assert ctx.workspace_key == "gw-resolve"
    assert ctx.workspace_id == ws.id


@pytest.mark.integration
def test_gateway_raises_for_unknown_workspace_key(db):
    gw = MemoryGateway(db)
    with pytest.raises(WorkspaceNotFoundError):
        gw.resolve_workspace("does-not-exist")


@pytest.mark.integration
def test_gateway_get_or_create_workspace_creates_once(db):
    """get_or_create_workspace is idempotent — second call returns the same workspace."""
    gw = MemoryGateway(db)
    ctx1 = gw.get_or_create_workspace("gw-idempotent")
    ctx2 = gw.get_or_create_workspace("gw-idempotent")

    assert ctx1.workspace_id == ctx2.workspace_id


@pytest.mark.integration
def test_gateway_get_or_create_claim_scoped_to_workspace(db):
    """get_or_create_claim creates independent claims for different workspaces."""
    gw = MemoryGateway(db)
    ctx_a = gw.get_or_create_workspace("gw-claim-a")
    ctx_b = gw.get_or_create_workspace("gw-claim-b")

    claim_a = gw.get_or_create_claim(ctx_a, "supplier-007", "rating")
    claim_b = gw.get_or_create_claim(ctx_b, "supplier-007", "rating")

    assert claim_a.id != claim_b.id
    assert claim_a.workspace_id == ctx_a.workspace_id
    assert claim_b.workspace_id == ctx_b.workspace_id


@pytest.mark.integration
def test_gateway_get_or_create_claim_is_idempotent(db):
    """Calling get_or_create_claim twice returns the same Claim."""
    gw = MemoryGateway(db)
    ctx = gw.get_or_create_workspace("gw-idempotent-claim")

    c1 = gw.get_or_create_claim(ctx, "supplier-008", "contract_start")
    c2 = gw.get_or_create_claim(ctx, "supplier-008", "contract_start")

    assert c1.id == c2.id


@pytest.mark.integration
def test_gateway_eligible_versions_excludes_quarantined(db):
    """get_eligible_versions must not return quarantined or superseded versions."""
    gw = MemoryGateway(db)
    ctx = gw.get_or_create_workspace("gw-eligible")

    source = _make_source(db, "4")
    claim = gw.get_or_create_claim(ctx, "supplier-009", "terms")

    eligible_ver = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="Net 30",
        source_id=source.id,
        trust_status="verified",
        visibility_status="eligible",
    )
    quarantined_ver = ClaimVersion(
        claim_id=claim.id,
        version_number=2,
        value="Net 1 — POISONED",
        source_id=source.id,
        trust_status="disputed",
        visibility_status="quarantined",
    )
    db.add_all([eligible_ver, quarantined_ver])
    db.flush()

    versions = gw.get_eligible_versions(ctx, subject_key="supplier-009")

    ids = [v.id for v in versions]
    assert eligible_ver.id in ids
    assert quarantined_ver.id not in ids


@pytest.mark.integration
def test_gateway_eligible_versions_scoped_to_workspace(db):
    """get_eligible_versions does not return eligible versions from other workspaces."""
    gw = MemoryGateway(db)
    ctx_a = gw.get_or_create_workspace("gw-scope-a")
    ctx_b = gw.get_or_create_workspace("gw-scope-b")

    source = _make_source(db, "5")

    claim_a = gw.get_or_create_claim(ctx_a, "supplier-010", "country")
    claim_b = gw.get_or_create_claim(ctx_b, "supplier-010", "country")

    ver_a = ClaimVersion(
        claim_id=claim_a.id,
        version_number=1,
        value="Germany",
        source_id=source.id,
        trust_status="verified",
        visibility_status="eligible",
    )
    ver_b = ClaimVersion(
        claim_id=claim_b.id,
        version_number=1,
        value="France",
        source_id=source.id,
        trust_status="verified",
        visibility_status="eligible",
    )
    db.add_all([ver_a, ver_b])
    db.flush()

    versions_a = gw.get_eligible_versions(ctx_a)
    ids_a = [v.id for v in versions_a]

    assert ver_a.id in ids_a
    assert ver_b.id not in ids_a


@pytest.mark.integration
def test_gateway_create_and_activate_generation(db):
    """Full happy-path: create candidate generation and activate it."""
    gw = MemoryGateway(db)
    ctx = gw.get_or_create_workspace("gw-activate")

    source = _make_source(db, "6")
    claim = gw.get_or_create_claim(ctx, "supplier-011", "status")

    ver = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="approved",
        source_id=source.id,
        trust_status="verified",
        visibility_status="eligible",
    )
    db.add(ver)
    db.flush()

    gen = gw.create_candidate_generation(ctx, [ver.id])
    assert gen.state == "candidate"
    assert gen.workspace_id == ctx.workspace_id

    ws = gw.activate_generation(
        ctx,
        gen.id,
        source_trust=TrustLevel.VERIFIED,
        authorized_approval=True,
    )

    db.refresh(gen)
    assert gen.state == "active"
    assert ws.active_generation_id == gen.id
    assert ws.revision == 1


@pytest.mark.integration
def test_gateway_activation_retired_previous_active_generation(db):
    """Activating a new generation retires the previously active one."""
    gw = MemoryGateway(db)
    ctx = gw.get_or_create_workspace("gw-retire")

    source = _make_source(db, "7")
    claim = gw.get_or_create_claim(ctx, "supplier-012", "tier")

    ver1 = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="gold",
        source_id=source.id,
        trust_status="verified",
    )
    ver2 = ClaimVersion(
        claim_id=claim.id,
        version_number=2,
        value="platinum",
        source_id=source.id,
        trust_status="verified",
    )
    db.add_all([ver1, ver2])
    db.flush()

    gen1 = gw.create_candidate_generation(ctx, [ver1.id])
    gw.activate_generation(ctx, gen1.id, source_trust=TrustLevel.VERIFIED)

    gen2 = gw.create_candidate_generation(ctx, [ver2.id])
    gw.activate_generation(ctx, gen2.id, source_trust=TrustLevel.VERIFIED)

    db.refresh(gen1)
    db.refresh(gen2)
    assert gen1.state == "retired"
    assert gen2.state == "active"


@pytest.mark.integration
def test_gateway_activation_policy_denied_for_unverified(db):
    """Activation with unverified trust is denied by policy."""
    gw = MemoryGateway(db)
    ctx = gw.get_or_create_workspace("gw-policy-deny")

    source = _make_source(db, "8")
    claim = gw.get_or_create_claim(ctx, "supplier-013", "risk")

    ver = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="low",
        source_id=source.id,
        trust_status="unverified",
    )
    db.add(ver)
    db.flush()

    gen = gw.create_candidate_generation(ctx, [ver.id])

    with pytest.raises(PolicyDeniedError):
        gw.activate_generation(
            ctx, gen.id, source_trust=TrustLevel.UNVERIFIED
        )


# ===========================================================================
# Regression — existing schema tests must continue to pass
# ===========================================================================


@pytest.mark.integration
def test_claim_versions_preserve_history(db):
    """Regression: version history is preserved (workspace-scoped)."""
    ws = MemoryWorkspace(workspace_key="reg-history")
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
    """Regression: duplicate (workspace, subject, field) is still rejected."""
    ws = MemoryWorkspace(workspace_key="reg-dup")
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
    """Regression: generation-claim-version membership with workspace scoping."""
    ws = MemoryWorkspace(workspace_key="reg-gen")
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


# ===========================================================================
# Phase B1.1 — database-level cross-workspace constraint tests
# These tests probe the PostgreSQL constraints added in migration c2d3e4f5a6b7.
# ===========================================================================


@pytest.mark.integration
def test_db_rejects_generation_membership_from_different_workspace(db):
    """DB constraint fk_gcv_generation_workspace prevents a GCV row whose
    workspace_id does not match the generation's workspace_id."""
    ws_a = MemoryWorkspace(workspace_key="b11-gcv-gen-a")
    ws_b = MemoryWorkspace(workspace_key="b11-gcv-gen-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    source = _make_source(db, "b1")
    claim_a = Claim(
        workspace_id=ws_a.id, subject_key="s-b11-g", field_key="f1"
    )
    db.add(claim_a)
    db.flush()

    ver_a = ClaimVersion(
        claim_id=claim_a.id,
        version_number=1,
        value="v1",
        source_id=source.id,
        trust_status="verified",
    )
    gen_a = MemoryGeneration(workspace_id=ws_a.id, state="candidate")
    db.add_all([ver_a, gen_a])
    db.flush()

    # Attempt to insert a GCV row where workspace_id = ws_b.id but
    # generation belongs to ws_a.  The FK fk_gcv_generation_workspace must
    # reject this because (gen_a.id, ws_b.id) is not in memory_generations.
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            GenerationClaimVersion(
                generation_id=gen_a.id,
                workspace_id=ws_b.id,  # deliberate mismatch
                claim_id=claim_a.id,
                version_id=ver_a.id,
            )
        )
        db.flush()


@pytest.mark.integration
def test_db_rejects_claim_membership_from_different_workspace(db):
    """DB constraint fk_gcv_claim_workspace prevents a GCV row whose
    workspace_id does not match the claim's workspace_id."""
    ws_a = MemoryWorkspace(workspace_key="b11-gcv-claim-a")
    ws_b = MemoryWorkspace(workspace_key="b11-gcv-claim-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    source = _make_source(db, "b2")
    # claim belongs to ws_b
    claim_b = Claim(
        workspace_id=ws_b.id, subject_key="s-b11-c", field_key="f1"
    )
    db.add(claim_b)
    db.flush()

    ver_b = ClaimVersion(
        claim_id=claim_b.id,
        version_number=1,
        value="v1",
        source_id=source.id,
        trust_status="verified",
    )
    # generation belongs to ws_a
    gen_a = MemoryGeneration(workspace_id=ws_a.id, state="candidate")
    db.add_all([ver_b, gen_a])
    db.flush()

    # workspace_id=ws_a.id: generation matches, but claim does not.
    # fk_gcv_claim_workspace requires (claim_b.id, ws_a.id) to exist in
    # claims — it won't because claim_b is owned by ws_b.
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            GenerationClaimVersion(
                generation_id=gen_a.id,
                workspace_id=ws_a.id,
                claim_id=claim_b.id,  # belongs to ws_b, not ws_a
                version_id=ver_b.id,
            )
        )
        db.flush()


@pytest.mark.integration
def test_db_rejects_cross_workspace_activation(db):
    """DB constraint fk_workspace_active_generation_owned prevents setting
    active_generation_id to a generation owned by a different workspace."""
    ws_a = MemoryWorkspace(workspace_key="b11-act-a")
    ws_b = MemoryWorkspace(workspace_key="b11-act-b")
    db.add_all([ws_a, ws_b])
    db.flush()

    # generation owned by ws_b
    gen_b = MemoryGeneration(workspace_id=ws_b.id, state="active")
    db.add(gen_b)
    db.flush()

    # Attempt to point ws_a's active_generation_id at gen_b.
    # The FK (active_generation_id, id) → memory_generations(id, workspace_id)
    # requires (gen_b.id, ws_a.id) to exist in memory_generations — it won't.
    with pytest.raises(IntegrityError), db.begin_nested():
        ws_a.active_generation_id = gen_b.id
        db.flush()


@pytest.mark.integration
def test_db_allows_same_workspace_membership_and_activation(db):
    """Happy path: same-workspace generation membership and activation
    succeeds at the database layer."""
    ws = MemoryWorkspace(workspace_key="b11-happy")
    db.add(ws)
    db.flush()

    source = _make_source(db, "b3")
    claim = Claim(workspace_id=ws.id, subject_key="s-b11-h", field_key="f1")
    db.add(claim)
    db.flush()

    ver = ClaimVersion(
        claim_id=claim.id,
        version_number=1,
        value="ok",
        source_id=source.id,
        trust_status="verified",
    )
    gen = MemoryGeneration(workspace_id=ws.id, state="candidate")
    db.add_all([ver, gen])
    db.flush()

    # Membership row — all workspace_ids match.
    gcv = GenerationClaimVersion(
        generation_id=gen.id,
        workspace_id=ws.id,
        claim_id=claim.id,
        version_id=ver.id,
    )
    db.add(gcv)
    db.flush()

    # Activation — same workspace.
    gen.state = "active"
    ws.active_generation_id = gen.id
    ws.revision = 1
    db.flush()

    db.refresh(ws)
    assert ws.active_generation_id == gen.id
    assert ws.revision == 1
