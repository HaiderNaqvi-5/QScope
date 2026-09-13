"""Store the canonical discovered project model."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("projects", sa.Column("project_model", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("projects", "project_model")
