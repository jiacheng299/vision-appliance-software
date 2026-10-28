"""Persist real local monitoring without rewriting existing task/model records."""
from alembic import op
import sqlalchemy as sa

revision='0008_local_execution'
down_revision='0007_agent_templates'
branch_labels=depends_on=None


def upgrade():
    op.create_table('local_runs',sa.Column('id',sa.String,primary_key=True),
        sa.Column('agent_id',sa.String,nullable=False,index=True),sa.Column('actor_id',sa.String,nullable=False),
        sa.Column('channel_id',sa.String,nullable=False),sa.Column('source_id',sa.String,nullable=False),
        sa.Column('state',sa.String,nullable=False),sa.Column('payload',sa.JSON,nullable=False),
        sa.Column('observation',sa.JSON,nullable=False),sa.Column('predecessors',sa.JSON,nullable=False))
    op.create_table('local_operations',sa.Column('id',sa.String,primary_key=True),
        sa.Column('agent_id',sa.String,nullable=False,index=True),sa.Column('actor_id',sa.String,nullable=False),
        sa.Column('command_key',sa.String,nullable=False),sa.Column('request_hash',sa.String,nullable=False),
        sa.Column('payload',sa.JSON,nullable=False),sa.UniqueConstraint('agent_id','actor_id','command_key'))
    op.create_table('local_events',sa.Column('sequence',sa.Integer,primary_key=True,autoincrement=True),
        sa.Column('id',sa.String,nullable=False,unique=True),sa.Column('agent_id',sa.String,nullable=False,index=True),
        sa.Column('actor_id',sa.String,nullable=False),sa.Column('run_id',sa.String,nullable=False),
        sa.Column('payload',sa.JSON,nullable=False),sa.Column('evidence_key',sa.String,nullable=True),
        sqlite_autoincrement=True)
    op.create_table('local_agent_states',sa.Column('id',sa.String,primary_key=True),
        sa.Column('agent_id',sa.String,nullable=False),sa.Column('actor_id',sa.String,nullable=False),
        sa.Column('archived',sa.Integer,nullable=False),sa.UniqueConstraint('agent_id','actor_id'))


def downgrade():
    # Export local monitoring history before intentionally rolling back this feature.
    for table in ('local_agent_states','local_events','local_operations','local_runs'):
        op.drop_table(table)
