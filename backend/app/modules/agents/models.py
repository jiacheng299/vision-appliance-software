from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ...shared.models import Base, now, uid


class Agent(Base):
    __tablename__ = 'agents'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default='')
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class AgentRevision(Base):
    __tablename__ = 'agent_revisions'
    __table_args__ = (UniqueConstraint('agent_id', 'revision_no'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    agent_id: Mapped[str] = mapped_column(ForeignKey('agents.id'), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    base_revision_id: Mapped[str | None] = mapped_column(ForeignKey('agent_revisions.id'), nullable=True)
    state: Mapped[str] = mapped_column(String, default='draft')
    config: Mapped[dict] = mapped_column(JSON)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class AgentCommand(Base):
    """Persist a retry receipt in the same transaction as the resource creation."""
    __tablename__ = 'agent_commands'
    __table_args__ = (UniqueConstraint('actor_id', 'command_key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    command_key: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String, default=now)
