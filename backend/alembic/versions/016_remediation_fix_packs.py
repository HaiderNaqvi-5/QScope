"""Add durable remediation Fix Packs.

Revision ID: 016_remediation_fix_packs
Revises: 015_behavior_coverage
"""
from alembic import op
import sqlalchemy as sa

revision = "016_remediation_fix_packs"
down_revision = "015_behavior_coverage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remediation_fix_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False, index=True),
        sa.Column("scan_id", sa.String(36), nullable=False, index=True),
        sa.Column("root_cause_id", sa.String(128), nullable=False, index=True),
        sa.Column("finding_ids", sa.JSON(), nullable=False),
        sa.Column("correlation_confidence", sa.String(20), nullable=False),
        sa.Column("proposed_shared_correction", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(30), nullable=False),
        sa.Column("impact_radius", sa.JSON(), nullable=False),
        sa.Column("verification_scenarios", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="PROPOSED"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("remediation_fix_packs")
