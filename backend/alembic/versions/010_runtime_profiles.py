"""Add runtime profiles.

Revision ID: 010_runtime_profiles
Revises: 009_test_runs
"""
from alembic import op
import sqlalchemy as sa

revision = "010_runtime_profiles"
down_revision = "009_test_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("runtime_profiles",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("working_directory", sa.String(2048), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False), sa.Column("local_url", sa.String(2048), nullable=False),
        sa.Column("health_endpoint", sa.String(2048)), sa.Column("environment_file", sa.String(2048)),
        sa.Column("startup_timeout_seconds", sa.Integer(), nullable=False), sa.Column("trusted_default", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False), sa.Column("pid", sa.Integer()), sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_runtime_profiles_project_id", "runtime_profiles", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_runtime_profiles_project_id", table_name="runtime_profiles")
    op.drop_table("runtime_profiles")
