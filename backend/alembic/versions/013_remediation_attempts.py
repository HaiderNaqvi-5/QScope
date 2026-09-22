"""Add durable remediation attempts.

Revision ID: 013_remediation_attempts
Revises: 012_manual_qa
"""
from alembic import op
import sqlalchemy as sa

revision = "013_remediation_attempts"
down_revision = "012_manual_qa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remediation_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("scan_id", sa.String(36), nullable=False, index=True),
        sa.Column("finding_id", sa.String(36), nullable=False, index=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mode", sa.String(30), nullable=False, server_default="ASSISTED"),
        sa.Column("status", sa.String(50), nullable=False, server_default="PLAN_VALIDATED"),
        sa.Column("risk", sa.String(30), nullable=False),
        sa.Column("finding_confidence", sa.String(20), nullable=False),
        sa.Column("fix_confidence", sa.String(20), nullable=False),
        sa.Column("reproduced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deterministic_static_evidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("impact_radius", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("eligibility", sa.JSON(), nullable=False),
        sa.Column("patch", sa.Text(), nullable=True),
        sa.Column("changed_files", sa.JSON(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("verification_plan", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("final_outcome", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("remediation_attempts")
