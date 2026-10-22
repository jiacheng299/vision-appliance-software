"""B-owned validation/confirmation records; never creates external Run/Event tables."""
from alembic import op
import sqlalchemy as sa
revision = '0003_agent_workflow'
down_revision = '0002_agents'
branch_labels = None
depends_on = None


def upgrade():
    for table, names in [('agents', ['archived_at', 'desired_revision_id']), ('agent_revisions', ['latest_validation_id', 'published_at', 'baseline_run_id'])]:
        for name in names:
            op.add_column(table, sa.Column(name, sa.String(), nullable=True))
    op.create_table('agent_validations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('revision_id', sa.String(), sa.ForeignKey('agent_revisions.id'), nullable=False),
        sa.Column('config_hash', sa.String(), nullable=False),
        sa.Column('source_hash', sa.String(), nullable=False),
        sa.Column('capability_fingerprint', sa.String(), nullable=False),
        sa.Column('verdict', sa.String(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('data_origin', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('expires_at', sa.String(), nullable=False))
    op.create_index('ix_agent_validations_revision_id', 'agent_validations', ['revision_id'])
    op.create_table('agent_confirmations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('revision_id', sa.String(), sa.ForeignKey('agent_revisions.id'), nullable=False, unique=True),
        sa.Column('validation_id', sa.String(), sa.ForeignKey('agent_validations.id'), nullable=False),
        sa.Column('actor_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('config_hash', sa.String(), nullable=False),
        sa.Column('limitations_acknowledged', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))


def downgrade():
    op.drop_table('agent_confirmations')
    op.drop_index('ix_agent_validations_revision_id', table_name='agent_validations')
    op.drop_table('agent_validations')
    for table, names in [('agent_revisions', ['baseline_run_id', 'published_at', 'latest_validation_id']), ('agents', ['desired_revision_id', 'archived_at'])]:
        for name in names:
            op.drop_column(table, name)
