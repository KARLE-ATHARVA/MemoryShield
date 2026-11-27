"""Record the workspace revision used to build each candidate.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "memory_generations",
        sa.Column("base_revision", sa.Integer(), nullable=True),
    )

    op.create_check_constraint(
        "ck_generation_base_revision_nonnegative",
        "memory_generations",
        "base_revision IS NULL OR base_revision >= 0",
    )


def downgrade():
    op.drop_constraint(
        "ck_generation_base_revision_nonnegative",
        "memory_generations",
        type_="check",
    )
    op.drop_column("memory_generations", "base_revision")
