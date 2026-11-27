"""Protect historical memory evidence against mutation.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7

Historical records are append-only. Selected operational status
fields may be updated without changing historical evidence.
"""

from collections.abc import Sequence

from alembic import op  # isort:skip


revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FUNCTION_NAME = "memoryshield_guard_historical_evidence"

PROTECTED_TABLES = (
    ("sources", "trust_status"),
    ("claims", None),
    ("claim_versions", "visibility_status"),
    ("memory_artifacts", "visibility_status"),
    ("dependency_edges", None),
    ("retrieval_events", None),
    ("agent_decisions", None),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION memoryshield_guard_historical_evidence()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION
                    'Historical evidence is append-only: % DELETE blocked',
                    TG_TABLE_NAME
                    USING ERRCODE = '23514';
            END IF;

            IF (
                to_jsonb(NEW) - COALESCE(TG_ARGV[0], '')
            ) IS DISTINCT FROM (
                to_jsonb(OLD) - COALESCE(TG_ARGV[0], '')
            ) THEN
                RAISE EXCEPTION
                    'Historical evidence is append-only: % UPDATE blocked',
                    TG_TABLE_NAME
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )

    for table_name, mutable_column in PROTECTED_TABLES:
        trigger_name = f"trg_{table_name}_immutable"

        argument = (
            f"'{mutable_column}'"
            if mutable_column is not None
            else ""
        )

        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OR DELETE
            ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION {FUNCTION_NAME}({argument});
            """
        )


def downgrade() -> None:
    for table_name, _ in reversed(PROTECTED_TABLES):
        trigger_name = f"trg_{table_name}_immutable"

        op.execute(
            f"DROP TRIGGER IF EXISTS {trigger_name} "
            f"ON {table_name};"
        )

    op.execute(
        f"DROP FUNCTION IF EXISTS {FUNCTION_NAME}();"
    )
