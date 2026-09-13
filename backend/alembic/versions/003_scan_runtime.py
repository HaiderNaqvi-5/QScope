"""Persist scan plans and runtime results."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("scan_sessions", sa.Column("mode", sa.String(20), nullable=True, server_default="STANDARD"))
    op.add_column("scan_sessions", sa.Column("plan", sa.JSON(), nullable=True, server_default="[]"))
    op.add_column("scan_sessions", sa.Column("results", sa.JSON(), nullable=True, server_default="[]"))
    op.add_column("scan_sessions", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("scan_sessions", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("scan_sessions", sa.Column("completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for column in ("completed_at", "started_at", "error", "results", "plan", "mode"):
        op.drop_column("scan_sessions", column)
