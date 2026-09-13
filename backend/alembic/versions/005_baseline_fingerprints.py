"""Persist baseline finding fingerprints."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("baselines", sa.Column("fingerprints", sa.JSON(), nullable=True, server_default="[]"))


def downgrade() -> None:
    op.drop_column("baselines", "fingerprints")
