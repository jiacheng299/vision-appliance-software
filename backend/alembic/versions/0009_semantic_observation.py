"""Add the time-decayed profile and valid-observation records.

Purely additive: no existing table is altered, so rolling back only drops the
new tables and leaves runs, events and models untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_semantic_observation'
down_revision = '0008_local_execution'
branch_labels = depends_on = None


def upgrade():
    op.create_table('semantic_profiles',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('source_id', sa.String, nullable=False, index=True),
        sa.Column('view_version', sa.String, nullable=False),
        sa.Column('intrinsic', sa.JSON, nullable=False),
        sa.Column('runtime', sa.JSON, nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('created_at', sa.String, nullable=False),
        sa.Column('updated_at', sa.String, nullable=False),
        sa.UniqueConstraint('source_id', 'view_version'))
    op.create_table('profile_attributes',
        sa.Column('id', sa.String, primary_key=True),
        sa.Column('profile_id', sa.String, nullable=False, index=True),
        sa.Column('key', sa.String, nullable=False),
        sa.Column('value', sa.JSON, nullable=False),
        sa.Column('source_kind', sa.String, nullable=False),
        sa.Column('source_frame_ts', sa.Float, nullable=True),
        sa.Column('roi', sa.JSON, nullable=False),
        sa.Column('observed_at', sa.Float, nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('tau_seconds', sa.Float, nullable=True),
        sa.Column('hard_expiry_at', sa.Float, nullable=True),
        sa.Column('state', sa.String, nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('updated_at', sa.String, nullable=False),
        sa.UniqueConstraint('profile_id', 'key'))
    op.create_table('observation_records',
        sa.Column('sequence', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('id', sa.String, nullable=False, unique=True, index=True),
        sa.Column('agent_id', sa.String, nullable=False, index=True),
        sa.Column('actor_id', sa.String, nullable=False),
        sa.Column('run_id', sa.String, nullable=True),
        sa.Column('source_id', sa.String, nullable=False, index=True),
        sa.Column('task_key', sa.String, nullable=False),
        sa.Column('roi', sa.JSON, nullable=False),
        sa.Column('window_start', sa.Float, nullable=False),
        sa.Column('window_end', sa.Float, nullable=False),
        sa.Column('route_version', sa.String, nullable=True),
        sa.Column('profile_version', sa.Integer, nullable=True),
        sa.Column('model_version', sa.String, nullable=True),
        sa.Column('path_id', sa.String, nullable=True),
        sa.Column('verdict', sa.String, nullable=False, index=True),
        sa.Column('detection_count', sa.Integer, nullable=False),
        sa.Column('metrics', sa.JSON, nullable=False),
        sa.Column('thresholds', sa.JSON, nullable=False),
        sa.Column('gates', sa.JSON, nullable=False),
        sa.Column('reasons', sa.JSON, nullable=False),
        sa.Column('created_at', sa.String, nullable=False),
        sqlite_autoincrement=True)


def downgrade():
    for table in ('observation_records', 'profile_attributes', 'semantic_profiles'):
        op.drop_table(table)
