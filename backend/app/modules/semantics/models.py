"""Semantic profile, time-decayed attributes and valid-observation records."""
from sqlalchemy import JSON, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ...shared.models import Base, now, uid


class SemanticProfile(Base):
    """One profile per camera and view version; never shared across sources."""
    __tablename__ = 'semantic_profiles'
    __table_args__ = (UniqueConstraint('source_id','view_version'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(String, index=True)
    view_version: Mapped[str] = mapped_column(String, default='v1')
    intrinsic: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class ProfileAttribute(Base):
    """Dynamic attribute bound to its source frame, ROI, time and validity."""
    __tablename__ = 'profile_attributes'
    __table_args__ = (UniqueConstraint('profile_id','key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    profile_id: Mapped[str] = mapped_column(String, index=True)
    key: Mapped[str] = mapped_column(String)
    value: Mapped[dict] = mapped_column(JSON)
    source_kind: Mapped[str] = mapped_column(String)
    source_frame_ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    roi: Mapped[list] = mapped_column(JSON, default=list)
    observed_at: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    tau_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    hard_expiry_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str] = mapped_column(String, default='valid')
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class ObservationRecord(Base):
    """A window-level verdict bound to task, ROI, route version and model version."""
    __tablename__ = 'observation_records'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, unique=True, index=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str] = mapped_column(String)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    task_key: Mapped[str] = mapped_column(String)
    roi: Mapped[list] = mapped_column(JSON, default=list)
    window_start: Mapped[float] = mapped_column(Float)
    window_end: Mapped[float] = mapped_column(Float)
    route_version: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    path_id: Mapped[str | None] = mapped_column(String, nullable=True)
    verdict: Mapped[str] = mapped_column(String, index=True)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    gates: Mapped[list] = mapped_column(JSON, default=list)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String, default=now)
