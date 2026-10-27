"""Separate reusable agent templates from runtime task instances."""
from alembic import op
import sqlalchemy as sa
import json
from uuid import uuid4

revision='0007_agent_templates'
down_revision='0006_requirement_plans'
branch_labels=depends_on=None

def upgrade():
    op.create_table('agent_templates',sa.Column('id',sa.String,primary_key=True),sa.Column('name',sa.String,nullable=False),
        sa.Column('description',sa.Text,nullable=False),sa.Column('row_version',sa.Integer,nullable=False),
        sa.Column('created_at',sa.String,nullable=False),sa.Column('updated_at',sa.String,nullable=False),
        sa.Column('archived_at',sa.String,nullable=True),sa.Column('imported_from_agent_id',sa.String,nullable=True,unique=True))
    op.create_table('agent_template_revisions',sa.Column('id',sa.String,primary_key=True),
        sa.Column('template_id',sa.String,sa.ForeignKey('agent_templates.id'),nullable=False,index=True),
        sa.Column('revision_no',sa.Integer,nullable=False),sa.Column('state',sa.String,nullable=False),
        sa.Column('config',sa.JSON,nullable=False),sa.Column('created_at',sa.String,nullable=False),
        sa.Column('published_at',sa.String,nullable=True),sa.UniqueConstraint('template_id','revision_no'))
    op.create_table('agent_template_tasks',sa.Column('agent_id',sa.String,sa.ForeignKey('agents.id'),primary_key=True),
        sa.Column('template_id',sa.String,sa.ForeignKey('agent_templates.id'),nullable=False,index=True),
        sa.Column('template_revision_id',sa.String,sa.ForeignKey('agent_template_revisions.id'),nullable=False),
        sa.Column('created_at',sa.String,nullable=False))
    # Register old definitions as editable template drafts. Do not rewrite any old revision/run.
    connection=op.get_bind()
    for agent in connection.execute(sa.text('SELECT * FROM agents')).mappings():
        row=connection.execute(sa.text('SELECT config FROM agent_revisions WHERE agent_id=:id ORDER BY revision_no DESC LIMIT 1'),{'id':agent['id']}).first()
        raw=json.loads(row[0]) if row and isinstance(row[0],str) else row[0] if row else {}
        channel=next(iter(raw.get('channels',[])),{})
        params=[{'key':k,'value':channel[k],'required':False} for k in ('target','rule','duration_seconds') if channel.get(k) not in (None,'')]
        identifier,rev=str(uuid4()),str(uuid4())
        connection.execute(sa.text('INSERT INTO agent_templates VALUES (:id,:name,:description,1,:created,:updated,:archived,:legacy)'),dict(id=identifier,name=agent['name'],description=agent['description'],created=agent['created_at'],updated=agent['updated_at'],archived=agent['archived_at'],legacy=agent['id']))
        connection.execute(sa.text('INSERT INTO agent_template_revisions VALUES (:id,:template,1,\'draft\',:config,:created,NULL)'),dict(id=rev,template=identifier,config=json.dumps({'model_ref':channel.get('capability_ref'),'parameters':params}),created=agent['created_at']))
        connection.execute(sa.text('INSERT INTO agent_template_tasks VALUES (:agent,:template,:revision,:created)'),dict(agent=agent['id'],template=identifier,revision=rev,created=agent['created_at']))

def downgrade():
    op.drop_table('agent_template_tasks')
    op.drop_table('agent_template_revisions')
    op.drop_table('agent_templates')
