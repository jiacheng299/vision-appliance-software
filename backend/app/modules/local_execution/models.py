"""Local inference owns its Run, Operation and Event persistence."""
from sqlalchemy import JSON, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ...shared.models import Base


class LocalRun(Base):
    __tablename__ = 'local_runs'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str] = mapped_column(String)
    channel_id: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    observation: Mapped[dict] = mapped_column(JSON, default=dict)
    predecessors: Mapped[list] = mapped_column(JSON, default=list)


class LocalOperation(Base):
    __tablename__ = 'local_operations'
    __table_args__ = (UniqueConstraint('agent_id','actor_id','command_key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str] = mapped_column(String)
    command_key: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)


class LocalEvent(Base):
    __tablename__ = 'local_events'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, unique=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str] = mapped_column(String)
    run_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    evidence_key: Mapped[str | None] = mapped_column(String, nullable=True)


class LocalAgentState(Base):
    __tablename__ = 'local_agent_states'
    __table_args__ = (UniqueConstraint('agent_id','actor_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String)
    actor_id: Mapped[str] = mapped_column(String)
    archived: Mapped[int] = mapped_column(Integer, default=0)
