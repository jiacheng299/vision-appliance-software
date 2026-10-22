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
    archived_at: Mapped[str | None] = mapped_column(String, nullable=True)
    desired_revision_id: Mapped[str | None] = mapped_column(String, nullable=True)


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
    latest_validation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)
    baseline_run_id: Mapped[str | None] = mapped_column(String, nullable=True)


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


class AgentValidation(Base):
    __tablename__ = 'agent_validations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    revision_id: Mapped[str] = mapped_column(ForeignKey('agent_revisions.id'), index=True)
    config_hash: Mapped[str] = mapped_column(String)
    source_hash: Mapped[str] = mapped_column(String)
    capability_fingerprint: Mapped[str] = mapped_column(String)
    verdict: Mapped[str] = mapped_column(String)
    result: Mapped[dict] = mapped_column(JSON)
    data_origin: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
    expires_at: Mapped[str] = mapped_column(String)


class AgentConfirmation(Base):
    __tablename__ = 'agent_confirmations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    revision_id: Mapped[str] = mapped_column(ForeignKey('agent_revisions.id'), unique=True)
    validation_id: Mapped[str] = mapped_column(ForeignKey('agent_validations.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    config_hash: Mapped[str] = mapped_column(String)
    limitations_acknowledged: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(String, default=now)
