"""Add routing state and decision audit.

Pure addition: existing tables are untouched, so a rollback only drops the two
new routing tables.
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_route_state'
down_revision = '0009_semantic_observation'
branch_labels = depends_on = None


def upgrade():
    op.create_table('route_states',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('actor_id', sa.String, nullable=False),
        sa.Column('agent_id', sa.String, nullable=False, index=True),
        sa.Column('channel_id', sa.String, nullable=False),
        sa.Column('source_id', sa.String, nullable=False),
        sa.Column('rule', sa.String, nullable=False),
        sa.Column('active_members', sa.JSON, nullable=False),
        sa.Column('active_version', sa.String, nullable=False),
        sa.Column('active_since', sa.Float, nullable=False),
        sa.Column('mode', sa.String, nullable=False),
        sa.Column('candidate_members', sa.JSON, nullable=True),
        sa.Column('candidate_score', sa.Float, nullable=True),
        sa.Column('candidate_since', sa.Float, nullable=True),
        sa.Column('valid_windows', sa.Integer, nullable=False),
        sa.Column('hard_failure', sa.Integer, nullable=False),
        sa.Column('drift_cursor', sa.Float, nullable=True),
        sa.Column('attribute_labels', sa.JSON, nullable=False),
        sa.Column('updated_at', sa.String, nullable=False),
        sa.UniqueConstraint('actor_id', 'agent_id', 'channel_id', 'source_id'))
    op.create_table('route_decisions',
        sa.Column('sequence', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('id', sa.String, nullable=False, unique=True, index=True),
        sa.Column('route_state_id', sa.String, nullable=False, index=True),
        sa.Column('agent_id', sa.String, nullable=False, index=True),
        sa.Column('source_id', sa.String, nullable=False),
        sa.Column('channel_id', sa.String, nullable=False),
        sa.Column('kind', sa.String, nullable=False),
        sa.Column('action', sa.String, nullable=False),
        sa.Column('reason', sa.String, nullable=False),
        sa.Column('delta_j', sa.Float, nullable=True),
        sa.Column('route_version', sa.String, nullable=True),
        sa.Column('payload', sa.JSON, nullable=False),
        sa.Column('created_at', sa.String, nullable=False),
        sqlite_autoincrement=True)


def downgrade():
    for table in ('route_decisions', 'route_states'):
        op.drop_table(table)
