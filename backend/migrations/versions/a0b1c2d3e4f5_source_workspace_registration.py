"""Add workspace ownership and content deduplication for new sources.

Revision ID: a0b1c2d3e4f5
Revises: f5a6b7c8d9e0
"""

import sqlalchemy as sa
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sources",
        sa.Column("workspace_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_source_workspace",
        "sources",
        "memory_workspaces",
        ["workspace_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_source_workspace_sha256",
        "sources",
        ["workspace_id", "sha256"],
    )


def downgrade():
    op.drop_constraint(
        "uq_source_workspace_sha256",
        "sources",
        type_="unique",
    )
    op.drop_constraint(
        "fk_source_workspace",
        "sources",
        type_="foreignkey",
    )
    op.drop_column("sources", "workspace_id")
