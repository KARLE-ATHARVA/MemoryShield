"""Integration tests for gateway.register_source (Phase B1.4).

These tests cover:
- Server-side SHA-256 computation and deduplication.
- Workspace scoping of source records.
- Input validation guards.
- Idempotent re-registration within a workspace.
- Cross-workspace source independence (same content → different rows).

All tests use the rollback-based isolation fixture so no rows persist.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.memory.gateway import MemoryGateway, WorkspaceNotFoundError


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url or make_url(url).database != "memoryshield_test":
        pytest.fail("Must use TEST_DATABASE_URL pointing at memoryshield_test")

    engine = create_engine(url, pool_pre_ping=True)
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
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CONTENT = b"Synthetic supplier document content for testing."
SAMPLE_FILENAME = "supplier-record.txt"


def _make_workspace(db, key: str):
    gw = MemoryGateway(db)
    return gw.get_or_create_workspace(key), gw


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_register_source_returns_source_with_correct_digest(db):
    ctx, gw = _make_workspace(db, "reg-src-digest")

    import hashlib

    expected = hashlib.sha256(SAMPLE_CONTENT).hexdigest()
    source = gw.register_source(ctx, SAMPLE_FILENAME, "document", SAMPLE_CONTENT)

    assert source.sha256 == expected
    assert source.filename == SAMPLE_FILENAME
    assert source.source_type == "document"
    assert source.trust_status == "unverified"
    assert source.workspace_id == ctx.workspace_id


@pytest.mark.integration
def test_register_source_is_idempotent_within_workspace(db):
    ctx, gw = _make_workspace(db, "reg-src-idem")

    s1 = gw.register_source(ctx, SAMPLE_FILENAME, "document", SAMPLE_CONTENT)
    s2 = gw.register_source(ctx, SAMPLE_FILENAME, "document", SAMPLE_CONTENT)

    # Same content → same row returned; no duplicate inserted.
    assert s1.id == s2.id


@pytest.mark.integration
def test_same_content_in_different_workspaces_produces_separate_rows(db):
    ctx_a, gw = _make_workspace(db, "reg-src-sep-a")
    ctx_b, _ = _make_workspace(db, "reg-src-sep-b")

    gw2 = MemoryGateway(db)

    s_a = gw.register_source(ctx_a, SAMPLE_FILENAME, "document", SAMPLE_CONTENT)
    s_b = gw2.register_source(ctx_b, SAMPLE_FILENAME, "document", SAMPLE_CONTENT)

    assert s_a.id != s_b.id
    assert s_a.workspace_id == ctx_a.workspace_id
    assert s_b.workspace_id == ctx_b.workspace_id
    # Both have the same SHA-256 — deduplication is per-workspace.
    assert s_a.sha256 == s_b.sha256


@pytest.mark.integration
def test_register_observation_source_type(db):
    ctx, gw = _make_workspace(db, "reg-src-obs")
    content = b"Observed event data."

    source = gw.register_source(ctx, "observation.txt", "observation", content)

    assert source.source_type == "observation"


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_register_source_rejects_non_bytes(db):
    ctx, gw = _make_workspace(db, "reg-src-val-bytes")

    with pytest.raises(TypeError, match="bytes"):
        gw.register_source(ctx, SAMPLE_FILENAME, "document", "not bytes")  # type: ignore[arg-type]


@pytest.mark.integration
def test_register_source_rejects_empty_content(db):
    ctx, gw = _make_workspace(db, "reg-src-val-empty")

    with pytest.raises(ValueError, match="empty"):
        gw.register_source(ctx, SAMPLE_FILENAME, "document", b"")


@pytest.mark.integration
def test_register_source_rejects_oversized_content(db):
    ctx, gw = _make_workspace(db, "reg-src-val-size")
    oversized = b"x" * (5 * 1024 * 1024 + 1)

    with pytest.raises(ValueError, match="5 MiB"):
        gw.register_source(ctx, SAMPLE_FILENAME, "document", oversized)


@pytest.mark.integration
def test_register_source_rejects_path_traversal_filename(db):
    ctx, gw = _make_workspace(db, "reg-src-val-path")

    with pytest.raises(ValueError, match="Invalid"):
        gw.register_source(ctx, "../etc/passwd", "document", SAMPLE_CONTENT)


@pytest.mark.integration
def test_register_source_rejects_backslash_filename(db):
    ctx, gw = _make_workspace(db, "reg-src-val-bs")

    with pytest.raises(ValueError, match="Invalid"):
        gw.register_source(ctx, "dir\\file.txt", "document", SAMPLE_CONTENT)


@pytest.mark.integration
def test_register_source_rejects_empty_filename(db):
    ctx, gw = _make_workspace(db, "reg-src-val-fname")

    with pytest.raises(ValueError, match="Invalid"):
        gw.register_source(ctx, "", "document", SAMPLE_CONTENT)


@pytest.mark.integration
def test_register_source_rejects_unsupported_type(db):
    ctx, gw = _make_workspace(db, "reg-src-val-type")

    with pytest.raises(ValueError, match="Unsupported source type"):
        gw.register_source(ctx, SAMPLE_FILENAME, "image", SAMPLE_CONTENT)


@pytest.mark.integration
def test_register_source_rejects_invalid_workspace_context(db):
    """Gateway rejects a WorkspaceContext that doesn't match the database."""
    from app.memory.gateway import WorkspaceContext

    ctx, gw = _make_workspace(db, "reg-src-val-ctx")

    # Craft a context with a mismatched workspace_key.
    bad_ctx = WorkspaceContext(
        workspace_key="nonexistent-key",
        workspace_id=ctx.workspace_id,
    )

    with pytest.raises(WorkspaceNotFoundError):
        gw.register_source(bad_ctx, SAMPLE_FILENAME, "document", SAMPLE_CONTENT)
