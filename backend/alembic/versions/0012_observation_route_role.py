"""Separate candidate shadow observations from active route evidence."""
from alembic import op
import sqlalchemy as sa

revision = '0012_observation_route_role'
down_revision = '0011_profile_events'
branch_labels = depends_on = None


def upgrade():
    op.add_column('observation_records',
                  sa.Column('route_role', sa.String, nullable=False, server_default='active'))


def downgrade():
    op.drop_column('observation_records', 'route_role')
