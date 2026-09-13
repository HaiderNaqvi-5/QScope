"""Persist scan approval state."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("scan_sessions", sa.Column("approved", sa.String(10), nullable=True, server_default="false"))


def downgrade() -> None:
    op.drop_column("scan_sessions", "approved")
