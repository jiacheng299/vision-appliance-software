"""Versioned template-first / multimodal task planning receipts owned by A."""
from alembic import op
import sqlalchemy as sa
revision = '0006_requirement_plans'
down_revision = '0005_member_a_models'
branch_labels = depends_on = None


def upgrade():
    op.create_table('requirement_plans', sa.Column('id', sa.String, primary_key=True),
        sa.Column('resolved_channel', sa.JSON, nullable=False), sa.Column('catalog_fingerprint', sa.String, nullable=False),
        sa.Column('verdict', sa.String, nullable=False), sa.Column('missing_conditions', sa.JSON, nullable=False),
        sa.Column('limitations', sa.JSON, nullable=False), sa.Column('data_origin', sa.String, nullable=False),
        sa.Column('expires_at', sa.String, nullable=False))


def downgrade():
    op.drop_table('requirement_plans')
