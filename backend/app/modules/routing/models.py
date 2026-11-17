"""路由状态与决策审计（M7/M9）：当前组合、候选组合与切换历史。"""
from sqlalchemy import Float, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...shared.models import Base, now, uid


class RouteState(Base):
    """One routing state per task channel and video source."""
    __tablename__ = 'route_states'
    __table_args__ = (UniqueConstraint('actor_id', 'agent_id', 'channel_id', 'source_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    channel_id: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    rule: Mapped[str] = mapped_column(String)
    active_members: Mapped[list] = mapped_column(JSON, default=list)
    active_version: Mapped[str] = mapped_column(String, default='route-v0')
    active_since: Mapped[float] = mapped_column(Float, default=0.0)
    mode: Mapped[str] = mapped_column(String, default='stable')
    candidate_members: Mapped[list | None] = mapped_column(JSON, nullable=True)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_since: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_windows: Mapped[int] = mapped_column(Integer, default=0)
    hard_failure: Mapped[int] = mapped_column(Integer, default=0)
    drift_cursor: Mapped[float | None] = mapped_column(Float, nullable=True)
    attribute_labels: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class RouteDecision(Base):
    """Append-only audit of every enter, cancel and switch."""
    __tablename__ = 'route_decisions'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, unique=True, index=True)
    route_state_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String)
    channel_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    delta_j: Mapped[float | None] = mapped_column(Float, nullable=True)
    route_version: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String, default=now)
