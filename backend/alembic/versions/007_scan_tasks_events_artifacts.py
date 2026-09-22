"""Persist scan tasks, event history, and artifact metadata."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table("scan_tasks", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), nullable=False), sa.Column("task_key", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False), sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("adapter", sa.String(100), nullable=False), sa.Column("target", sa.String(2048), nullable=False),
        sa.Column("status", sa.String(50), nullable=False), sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False), sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()), sa.Column("exit_code", sa.Integer()), sa.Column("duration_ms", sa.Integer()),
        sa.Column("summary", sa.Text()))
    op.create_index("ix_scan_tasks_scan_id", "scan_tasks", ["scan_id"])
    op.create_table("scan_events", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), nullable=False), sa.Column("event", sa.String(100), nullable=False),
        sa.Column("task_id", sa.String(255)), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_scan_events_scan_id", "scan_events", ["scan_id"])
    op.create_index("ix_scan_events_created_at", "scan_events", ["created_at"])
    op.create_table("artifacts", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), nullable=False), sa.Column("task_id", sa.String(36)),
        sa.Column("kind", sa.String(30), nullable=False), sa.Column("relative_path", sa.String(2048), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_artifacts_scan_id", "artifacts", ["scan_id"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("scan_events")
    op.drop_table("scan_tasks")
