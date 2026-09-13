"""Initial schema creation."""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Create initial tables."""
    op.create_table(
        'settings',
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.String(4096), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )
    op.create_index(op.f('ix_settings_key'), 'settings', ['key'], unique=False)

    op.create_table(
        'projects',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('root_path', sa.String(2048), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('root_path')
    )

    op.create_table(
        'scan_sessions',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'findings',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('scan_id', sa.String(36), nullable=False),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('severity', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'baselines',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('project_id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'reports',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('scan_id', sa.String(36), nullable=False),
        sa.Column('format', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('reports')
    op.drop_table('baselines')
    op.drop_table('findings')
    op.drop_table('scan_sessions')
    op.drop_table('projects')
    op.drop_index(op.f('ix_settings_key'), table_name='settings')
    op.drop_table('settings')
