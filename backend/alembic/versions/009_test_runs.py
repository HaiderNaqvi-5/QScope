"""Persist normalized native test-run summaries."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table("test_runs", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), nullable=False), sa.Column("task_id", sa.String(36)),
        sa.Column("suite_name", sa.String(512), nullable=False), sa.Column("framework", sa.String(100), nullable=False),
        sa.Column("discovered", sa.Integer(), nullable=False), sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False), sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer()), sa.Column("coverage_percent", sa.String(20)),
        sa.Column("status", sa.String(50), nullable=False), sa.Column("raw_artifact_id", sa.String(36)),
        sa.Column("details", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_test_runs_scan_id", "test_runs", ["scan_id"])


def downgrade() -> None:
    op.drop_table("test_runs")
