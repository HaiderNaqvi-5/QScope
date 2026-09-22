"""Add scan release and reproducibility metadata."""
from alembic import op
import sqlalchemy as sa

revision = "011_scan_release_metadata"
down_revision = "010_runtime_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column in (
        ("git_commit", sa.Column("git_commit", sa.String(64))),
        ("git_branch", sa.Column("git_branch", sa.String(512))),
        ("project_fingerprint", sa.Column("project_fingerprint", sa.String(64))),
        ("overall_score", sa.Column("overall_score", sa.Integer())),
        ("is_complete_audit", sa.Column("is_complete_audit", sa.Boolean())),
        ("release_readiness", sa.Column("release_readiness", sa.String(50))),
        ("release_blockers", sa.Column("release_blockers", sa.JSON(), nullable=False, server_default="[]")),
    ):
        op.add_column("scan_sessions", column)


def downgrade() -> None:
    for name in ("release_blockers", "release_readiness", "is_complete_audit", "overall_score",
                 "project_fingerprint", "git_branch", "git_commit"):
        op.drop_column("scan_sessions", name)
