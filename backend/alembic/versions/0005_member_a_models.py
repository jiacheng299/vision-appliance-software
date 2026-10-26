"""Member A model/template versions, import receipts and LLM selection."""
from alembic import op
import sqlalchemy as sa
revision = '0005_member_a_models'
down_revision = '0004_workspace_actors'
branch_labels = depends_on = None


def upgrade():
    op.create_table('model_files', sa.Column('id', sa.String, primary_key=True), sa.Column('filename', sa.String, nullable=False), sa.Column('size_bytes', sa.Integer, nullable=False), sa.Column('checksum', sa.String, nullable=False), sa.Column('created_at', sa.String, nullable=False))
    op.create_table('model_pairs', sa.Column('model_id', sa.String, primary_key=True), sa.Column('version', sa.String, primary_key=True), sa.Column('template_id', sa.String, nullable=False), sa.Column('template_version', sa.String, nullable=False), sa.Column('file_id', sa.String, sa.ForeignKey('model_files.id'), nullable=False), sa.Column('definition', sa.JSON, nullable=False), sa.Column('validation', sa.String, nullable=False), sa.Column('validation_message', sa.String, nullable=False), sa.Column('status', sa.String, nullable=False), sa.Column('row_version', sa.Integer, nullable=False), sa.Column('data_origin', sa.String, nullable=False), sa.Column('created_at', sa.String, nullable=False), sa.Column('updated_at', sa.String, nullable=False), sa.UniqueConstraint('template_id', 'template_version'))
    op.create_table('model_commands', sa.Column('key', sa.String, primary_key=True), sa.Column('request_hash', sa.String, nullable=False), sa.Column('response', sa.JSON, nullable=False))
    op.create_table('llm_selections', sa.Column('usage', sa.String, primary_key=True), sa.Column('deployment_id', sa.String, nullable=False), sa.Column('row_version', sa.Integer, nullable=False))


def downgrade():
    for name in ('llm_selections', 'model_commands', 'model_pairs', 'model_files'):
        op.drop_table(name)
