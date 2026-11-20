"""Throttle automatic route evaluations to a fixed cadence."""
from alembic import op
import sqlalchemy as sa

revision = '0013_route_eval_cadence'
down_revision = '0012_observation_route_role'
branch_labels = depends_on = None


def upgrade():
    op.add_column('route_states',
                  sa.Column('last_eval_at', sa.Float, nullable=True))


def downgrade():
    op.drop_column('route_states', 'last_eval_at')
