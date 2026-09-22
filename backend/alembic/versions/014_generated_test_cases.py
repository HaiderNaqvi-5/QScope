"""Add deterministic schema-derived test cases."""
from alembic import op
import sqlalchemy as sa

revision = "014_generated_test_cases"
down_revision = "013_remediation_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_test_cases", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False), sa.Column("scan_id", sa.String(36)),
        sa.Column("category", sa.String(30), nullable=False), sa.Column("title", sa.String(512), nullable=False),
        sa.Column("method", sa.String(16), nullable=False), sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("actor", sa.String(255)), sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("source_path", sa.String(2048), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_generated_test_cases_project_id", "generated_test_cases", ["project_id"])
    op.create_index("ix_generated_test_cases_category", "generated_test_cases", ["category"])
    op.create_index("ix_generated_test_cases_fingerprint", "generated_test_cases", ["fingerprint"], unique=True)


def downgrade() -> None:
    op.drop_table("generated_test_cases")
