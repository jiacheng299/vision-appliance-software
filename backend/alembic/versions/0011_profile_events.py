"""Record every profile version bump so the shared timeline can show it.

Pure addition: a new append-only table. Rolling back only drops it.
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_profile_events'
down_revision = '0010_route_state'
branch_labels = depends_on = None


def upgrade():
    op.create_table('profile_events',
        sa.Column('sequence', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('id', sa.String, nullable=False, unique=True, index=True),
        sa.Column('source_id', sa.String, nullable=False, index=True),
        sa.Column('profile_id', sa.String, nullable=False, index=True),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('kind', sa.String, nullable=False),
        sa.Column('attribute', sa.String, nullable=True),
        sa.Column('previous', sa.String, nullable=True),
        sa.Column('current', sa.String, nullable=True),
        sa.Column('summary', sa.String, nullable=False),
        sa.Column('actor', sa.String, nullable=False),
        sa.Column('created_at', sa.String, nullable=False),
        sqlite_autoincrement=True)


def downgrade():
    op.drop_table('profile_events')
