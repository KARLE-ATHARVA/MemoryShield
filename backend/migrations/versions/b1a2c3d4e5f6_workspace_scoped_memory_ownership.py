"""workspace-scoped memory ownership

Revision ID: b1a2c3d4e5f6
Revises: 663278400431
Create Date: 2026-11-26 23:15:00.000000

Phase B1 — workspace isolation.

Changes
-------
1. Add ``created_at`` to ``memory_workspaces``.
2. Add ``workspace_id`` (NOT NULL FK → memory_workspaces.id) to ``claims``.
   Replace global ``uq_claim_identity(subject_key, field_key)`` with the
   workspace-scoped ``uq_claim_identity(workspace_id, subject_key, field_key)``.
3. Add ``workspace_id`` (NOT NULL FK → memory_workspaces.id) to
   ``memory_generations``.
4. Add ``workspace_id`` (NOT NULL FK → memory_workspaces.id) to
   ``incidents``.

Migration safety
----------------
If existing rows are present in ``claims``, ``memory_generations``, or
``incidents`` **without** an identifiable workspace, the upgrade step will
raise an explicit error rather than silently assigning records to an
arbitrary workspace.  For a fresh development database the NOT NULL columns
are added directly.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection


# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "663278400431"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helper — abort if orphaned rows exist so we never silently corrupt data.
# ---------------------------------------------------------------------------


def _assert_empty(conn: Connection, table: str) -> None:
    result = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
    count = result.scalar()
    if count:
        raise RuntimeError(
            f"Migration b1a2c3d4e5f6 requires '{table}' to be empty or fully "
            f"backfilled before workspace_id can be made NOT NULL.  "
            f"Found {count} row(s) without workspace_id.  "
            "Backfill workspace ownership manually and re-run the migration."
        )


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Add created_at to memory_workspaces (new audit column).
    #    Use server_default so any pre-existing rows get a sensible value.
    # ------------------------------------------------------------------
    op.add_column(
        "memory_workspaces",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Remove the server_default after backfill so future rows use the ORM default.
    op.alter_column("memory_workspaces", "created_at", server_default=None)

    # ------------------------------------------------------------------
    # 2. claims — add workspace_id.
    # ------------------------------------------------------------------

    # 2a. Add nullable first so the column can be populated without constraint
    #     errors on any pre-existing rows.
    op.add_column(
        "claims",
        sa.Column("workspace_id", sa.String(36), nullable=True),
    )

    # 2b. Safety check: if any claim rows exist they must already have been
    #     backfilled by the operator.  For an empty DB this is a no-op.
    orphan_claims = conn.execute(
        sa.text("SELECT COUNT(*) FROM claims WHERE workspace_id IS NULL")
    ).scalar()
    if orphan_claims:
        raise RuntimeError(
            f"Migration b1a2c3d4e5f6: {orphan_claims} row(s) in 'claims' have "
            "NULL workspace_id.  Assign workspace ownership manually before "
            "re-running this migration."
        )

    # 2c. Apply NOT NULL constraint and FK.
    op.alter_column("claims", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_claim_workspace",
        "claims",
        "memory_workspaces",
        ["workspace_id"],
        ["id"],
    )

    # 2d. Replace global uniqueness with workspace-scoped uniqueness.
    op.drop_constraint("uq_claim_identity", "claims", type_="unique")
    op.create_unique_constraint(
        "uq_claim_identity",
        "claims",
        ["workspace_id", "subject_key", "field_key"],
    )

    # ------------------------------------------------------------------
    # 3. memory_generations — add workspace_id.
    # ------------------------------------------------------------------

    op.add_column(
        "memory_generations",
        sa.Column("workspace_id", sa.String(36), nullable=True),
    )

    orphan_gens = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM memory_generations WHERE workspace_id IS NULL"
        )
    ).scalar()
    if orphan_gens:
        raise RuntimeError(
            f"Migration b1a2c3d4e5f6: {orphan_gens} row(s) in 'memory_generations' "
            "have NULL workspace_id.  Assign workspace ownership manually before "
            "re-running this migration."
        )

    op.alter_column("memory_generations", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_generation_workspace",
        "memory_generations",
        "memory_workspaces",
        ["workspace_id"],
        ["id"],
    )

    # ------------------------------------------------------------------
    # 4. incidents — add workspace_id.
    # ------------------------------------------------------------------

    op.add_column(
        "incidents",
        sa.Column("workspace_id", sa.String(36), nullable=True),
    )

    orphan_incidents = conn.execute(
        sa.text("SELECT COUNT(*) FROM incidents WHERE workspace_id IS NULL")
    ).scalar()
    if orphan_incidents:
        raise RuntimeError(
            f"Migration b1a2c3d4e5f6: {orphan_incidents} row(s) in 'incidents' "
            "have NULL workspace_id.  Assign workspace ownership manually before "
            "re-running this migration."
        )

    op.alter_column("incidents", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_incident_workspace",
        "incidents",
        "memory_workspaces",
        ["workspace_id"],
        ["id"],
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Reverse in the opposite order of upgrade.

    # 4. incidents
    op.drop_constraint("fk_incident_workspace", "incidents", type_="foreignkey")
    op.drop_column("incidents", "workspace_id")

    # 3. memory_generations
    op.drop_constraint(
        "fk_generation_workspace", "memory_generations", type_="foreignkey"
    )
    op.drop_column("memory_generations", "workspace_id")

    # 2. claims
    op.drop_constraint("uq_claim_identity", "claims", type_="unique")
    op.create_unique_constraint(
        "uq_claim_identity",
        "claims",
        ["subject_key", "field_key"],
    )
    op.drop_constraint("fk_claim_workspace", "claims", type_="foreignkey")
    op.drop_column("claims", "workspace_id")

    # 1. memory_workspaces
    op.drop_column("memory_workspaces", "created_at")
