"""Add persisted behavior coverage model."""
from alembic import op
import sqlalchemy as sa

revision = "015_behavior_coverage"
down_revision = "014_generated_test_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("behavior_coverage", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False), sa.Column("scan_id", sa.String(36)),
        sa.Column("capability_key", sa.String(512), nullable=False), sa.Column("category", sa.String(50), nullable=False),
        sa.Column("title", sa.String(512), nullable=False), sa.Column("criticality", sa.String(30), nullable=False),
        sa.Column("coverage_status", sa.String(30), nullable=False), sa.Column("source", sa.String(50), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_behavior_coverage_project_id", "behavior_coverage", ["project_id"])
    op.create_index("ix_behavior_coverage_scan_id", "behavior_coverage", ["scan_id"])
    op.create_index("ix_behavior_coverage_fingerprint", "behavior_coverage", ["fingerprint"], unique=True)


def downgrade() -> None:
    op.drop_table("behavior_coverage")
