"""Agent definitions and draft revisions; existing foundation data is preserved."""
from alembic import op
import sqlalchemy as sa

revision = '0002_agents'
down_revision = '0001_foundation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agents',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('owner_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('row_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False))
    op.create_table('agent_revisions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('agent_id', sa.String(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('revision_no', sa.Integer(), nullable=False),
        sa.Column('base_revision_id', sa.String(), sa.ForeignKey('agent_revisions.id'), nullable=True),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('row_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.UniqueConstraint('agent_id', 'revision_no'))
    op.create_index('ix_agent_revisions_agent_id', 'agent_revisions', ['agent_id'])
    op.create_table('agent_commands',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('actor_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('command_key', sa.String(), nullable=False),
        sa.Column('request_hash', sa.String(), nullable=False),
        sa.Column('response', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('actor_id', 'command_key'))


def downgrade():
    op.drop_table('agent_commands')
    op.drop_index('ix_agent_revisions_agent_id', table_name='agent_revisions')
    op.drop_table('agent_revisions')
    op.drop_table('agents')
