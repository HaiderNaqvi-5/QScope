"""Add manual QA cases and evidence."""
from alembic import op
import sqlalchemy as sa

revision = "012_manual_qa"
down_revision = "011_scan_release_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("manual_test_cases",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("module", sa.String(255), nullable=False), sa.Column("feature", sa.String(255)),
        sa.Column("preconditions", sa.JSON(), nullable=False), sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False), sa.Column("actual_result", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("severity", sa.String(30)),
        sa.Column("notes", sa.Text()), sa.Column("source", sa.String(40), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_manual_test_cases_project_id", "manual_test_cases", ["project_id"])
    op.create_table("manual_test_evidence",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("test_id", sa.String(36), nullable=False),
        sa.Column("relative_path", sa.String(2048), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False), sa.Column("original_name", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.create_index("ix_manual_test_evidence_test_id", "manual_test_evidence", ["test_id"])


def downgrade() -> None:
    op.drop_index("ix_manual_test_evidence_test_id", table_name="manual_test_evidence"); op.drop_table("manual_test_evidence")
    op.drop_index("ix_manual_test_cases_project_id", table_name="manual_test_cases"); op.drop_table("manual_test_cases")
