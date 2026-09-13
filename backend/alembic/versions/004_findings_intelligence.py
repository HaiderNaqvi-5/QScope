"""Add normalized finding fields."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    for name, column in (
        ("tool", sa.String(100),), ("stage", sa.String(100),),
        ("file_path", sa.String(2048),), ("line", sa.String(30),),
        ("message", sa.Text(),), ("fingerprint", sa.String(128),),
        ("status", sa.String(30),),
    ):
        op.add_column("findings", sa.Column(name, column, nullable=True))


def downgrade() -> None:
    for name in ("status", "fingerprint", "message", "line", "file_path", "stage", "tool"):
        op.drop_column("findings", name)
