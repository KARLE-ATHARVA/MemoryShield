"""database-level cross-workspace ownership constraints

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
Create Date: 2026-11-26 23:30:00.000000

Phase B1.1 — database-level cross-workspace ownership constraints.

Changes
-------
1. Add ``uq_generation_id_workspace`` on ``memory_generations(id, workspace_id)``.
   Required as the target of composite FKs that prove workspace ownership.

2. Add ``uq_claim_id_workspace`` on ``claims(id, workspace_id)``.
   Required as the target of the composite FK on ``generation_claim_versions``.

3. Add ``workspace_id`` column to ``generation_claim_versions``.
   Backfill from the parent generation's ``workspace_id``.
   Add composite FKs:
     - ``(generation_id, workspace_id) → memory_generations(id, workspace_id)``
     - ``(claim_id, workspace_id) → claims(id, workspace_id)``
   Together these force both the generation and the claim to share the same
   workspace in the membership row — enforced at the database layer.

4. Replace the simple ``active_generation_id → memory_generations.id`` FK on
   ``memory_workspaces`` with a composite FK
   ``(active_generation_id, id) → memory_generations(id, workspace_id)``.
   This forces the activated generation to belong to the same workspace as
   the workspace row itself — again enforced at the database layer.

Migration safety
----------------
Step 3 backfills ``workspace_id`` from the existing generation row.  If any
``generation_claim_versions`` row references a generation that no longer
exists (data corruption), the upgrade aborts with an explicit error.

Step 4 checks for ``active_generation_id`` values that point to a generation
belonging to a different workspace.  If any are found the upgrade aborts.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection


# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    conn: Connection = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Unique index on memory_generations(id, workspace_id).
    #    id is already the PK so this index is narrow; it exists solely
    #    to serve as the FK target for composite references.
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_generation_id_workspace",
        "memory_generations",
        ["id", "workspace_id"],
    )

    # ------------------------------------------------------------------
    # 2. Unique index on claims(id, workspace_id).
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_claim_id_workspace",
        "claims",
        ["id", "workspace_id"],
    )

    # ------------------------------------------------------------------
    # 3. generation_claim_versions — add workspace_id column.
    # ------------------------------------------------------------------

    # 3a. Add nullable column.
    op.add_column(
        "generation_claim_versions",
        sa.Column("workspace_id", sa.String(36), nullable=True),
    )

    # 3b. Backfill from the parent generation row.
    conn.execute(
        sa.text(
            """
            UPDATE generation_claim_versions gcv
            SET workspace_id = mg.workspace_id
            FROM memory_generations mg
            WHERE gcv.generation_id = mg.id
            """
        )
    )

    # 3c. Abort if any rows could not be backfilled (orphaned membership).
    orphan_gcv = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM generation_claim_versions WHERE workspace_id IS NULL"
        )
    ).scalar()
    if orphan_gcv:
        raise RuntimeError(
            f"Migration c2d3e4f5a6b7: {orphan_gcv} row(s) in "
            "'generation_claim_versions' could not be backfilled — "
            "their generation_id references a non-existent memory_generation. "
            "Resolve the data inconsistency and re-run the migration."
        )

    # 3d. Make NOT NULL.
    op.alter_column("generation_claim_versions", "workspace_id", nullable=False)

    # 3e. Add composite FK: generation_id + workspace_id → memory_generations.
    op.create_foreign_key(
        "fk_gcv_generation_workspace",
        "generation_claim_versions",
        "memory_generations",
        ["generation_id", "workspace_id"],
        ["id", "workspace_id"],
    )

    # 3f. Verify that every claim row also belongs to the same workspace before
    #     adding the claim composite FK.
    cross_claim = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM generation_claim_versions gcv
            JOIN claims c ON c.id = gcv.claim_id
            WHERE c.workspace_id != gcv.workspace_id
            """
        )
    ).scalar()
    if cross_claim:
        raise RuntimeError(
            f"Migration c2d3e4f5a6b7: {cross_claim} row(s) in "
            "'generation_claim_versions' reference a claim from a different "
            "workspace than the generation.  Resolve the inconsistency and "
            "re-run the migration."
        )

    # 3g. Add composite FK: claim_id + workspace_id → claims.
    op.create_foreign_key(
        "fk_gcv_claim_workspace",
        "generation_claim_versions",
        "claims",
        ["claim_id", "workspace_id"],
        ["id", "workspace_id"],
    )

    # ------------------------------------------------------------------
    # 4. memory_workspaces — replace simple active_generation_id FK with
    #    a composite FK that also enforces workspace ownership.
    # ------------------------------------------------------------------

    # 4a. Abort if any workspace references a generation from a different workspace.
    cross_activation = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM memory_workspaces mw
            JOIN memory_generations mg ON mg.id = mw.active_generation_id
            WHERE mg.workspace_id != mw.id
            """
        )
    ).scalar()
    if cross_activation:
        raise RuntimeError(
            f"Migration c2d3e4f5a6b7: {cross_activation} workspace row(s) have "
            "active_generation_id pointing to a generation owned by a different "
            "workspace.  Correct the data and re-run the migration."
        )

    # 4b. Drop the existing simple FK on active_generation_id.
    op.drop_constraint(
        "memory_workspaces_active_generation_id_fkey",
        "memory_workspaces",
        type_="foreignkey",
    )

    # 4c. Add composite FK (active_generation_id, id) → (id, workspace_id).
    #     use_alter is not available in create_foreign_key; we emit raw DDL.
    #     The circular dependency (workspace references generation, generation
    #     references workspace) is broken by the use_alter flag in the ORM
    #     model but here we simply add the constraint after both tables exist.
    op.create_foreign_key(
        "fk_workspace_active_generation_owned",
        "memory_workspaces",
        "memory_generations",
        ["active_generation_id", "id"],
        ["id", "workspace_id"],
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 4. Restore simple FK on active_generation_id.
    op.drop_constraint(
        "fk_workspace_active_generation_owned",
        "memory_workspaces",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "memory_workspaces_active_generation_id_fkey",
        "memory_workspaces",
        "memory_generations",
        ["active_generation_id"],
        ["id"],
    )

    # 3. Remove workspace_id from generation_claim_versions.
    op.drop_constraint(
        "fk_gcv_claim_workspace", "generation_claim_versions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_gcv_generation_workspace", "generation_claim_versions", type_="foreignkey"
    )
    op.drop_column("generation_claim_versions", "workspace_id")

    # 2. Drop claim unique index.
    op.drop_constraint("uq_claim_id_workspace", "claims", type_="unique")

    # 1. Drop generation unique index.
    op.drop_constraint(
        "uq_generation_id_workspace", "memory_generations", type_="unique"
    )
