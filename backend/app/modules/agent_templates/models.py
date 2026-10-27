from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ...shared.models import Base, now, uid

class AgentTemplate(Base):
    __tablename__='agent_templates'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    name:Mapped[str]=mapped_column(String)
    description:Mapped[str]=mapped_column(Text,default='')
    row_version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[str]=mapped_column(String,default=now)
    updated_at:Mapped[str]=mapped_column(String,default=now)
    archived_at:Mapped[str|None]=mapped_column(String,nullable=True)
    imported_from_agent_id:Mapped[str|None]=mapped_column(String,nullable=True,unique=True)

class AgentTemplateRevision(Base):
    __tablename__='agent_template_revisions'
    __table_args__=(UniqueConstraint('template_id','revision_no'),)
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    template_id:Mapped[str]=mapped_column(ForeignKey('agent_templates.id'),index=True)
    revision_no:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String,default='draft')
    config:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[str]=mapped_column(String,default=now)
    published_at:Mapped[str|None]=mapped_column(String,nullable=True)

class TemplateTaskLink(Base):
    __tablename__='agent_template_tasks'
    agent_id:Mapped[str]=mapped_column(ForeignKey('agents.id'),primary_key=True)
    template_id:Mapped[str]=mapped_column(ForeignKey('agent_templates.id'),index=True)
    template_revision_id:Mapped[str]=mapped_column(ForeignKey('agent_template_revisions.id'))
    created_at:Mapped[str]=mapped_column(String,default=now)
