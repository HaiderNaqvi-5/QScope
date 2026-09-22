"""Expand findings to the canonical PRD schema and add provenance/history."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    additions = (
        ("category", sa.String(100), "CODE_QUALITY"), ("subcategory", sa.String(100), None),
        ("description", sa.Text(), ""), ("confidence", sa.String(20), "0.75"), ("rule_id", sa.String(512), None),
        ("start_line", sa.Integer(), None), ("end_line", sa.Integer(), None), ("endpoint", sa.String(2048), None),
        ("evidence", sa.JSON(), "{}"), ("raw_artifact_id", sa.String(36), None), ("why_it_matters", sa.Text(), ""),
        ("recommendation", sa.Text(), ""), ("suggested_patch", sa.Text(), None), ("suggested_test", sa.Text(), None),
        ("sources", sa.JSON(), "[]"), ("correlation_key", sa.String(128), None),
    )
    for name, column_type, default in additions:
        op.add_column("findings", sa.Column(name, column_type, nullable=default is None, server_default=default))
    op.create_index("ix_findings_correlation_key", "findings", ["correlation_key"])
    op.create_table("finding_sources", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("finding_id", sa.String(36), nullable=False), sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("rule_id", sa.String(512)), sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("raw_artifact_id", sa.String(36)), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_finding_sources_finding_id", "finding_sources", ["finding_id"])
    op.create_table("finding_history", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("finding_id", sa.String(36), nullable=False), sa.Column("old_status", sa.String(30)),
        sa.Column("new_status", sa.String(30), nullable=False), sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_finding_history_finding_id", "finding_history", ["finding_id"])


def downgrade() -> None:
    op.drop_table("finding_history")
    op.drop_table("finding_sources")
    op.drop_index("ix_findings_correlation_key", table_name="findings")
    for name in ("correlation_key", "sources", "suggested_test", "suggested_patch", "recommendation", "why_it_matters",
                 "raw_artifact_id", "evidence", "endpoint", "end_line", "start_line", "rule_id", "confidence",
                 "description", "subcategory", "category"):
        op.drop_column("findings", name)
