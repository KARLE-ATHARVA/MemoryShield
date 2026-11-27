"""Add immutable security audit records.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
"""

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_security_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("memory_workspaces.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(150), nullable=False),
        sa.Column("actor_role", sa.String(40), nullable=False),
        sa.Column("operation", sa.String(60), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("old_status", sa.String(40), nullable=False),
        sa.Column("new_status", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_security_audit_workspace_created",
        "memory_security_audit",
        ["workspace_id", "created_at"],
    )

    op.execute(
        """
        CREATE TRIGGER trg_memory_security_audit_immutable
        BEFORE UPDATE OR DELETE
        ON memory_security_audit
        FOR EACH ROW
        EXECUTE FUNCTION memoryshield_guard_historical_evidence();
        """
    )


def downgrade():
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_memory_security_audit_immutable "
        "ON memory_security_audit;"
    )
    op.drop_index(
        "ix_security_audit_workspace_created",
        table_name="memory_security_audit",
    )
    op.drop_table("memory_security_audit")
