from datetime import datetime, timezone
import uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Float, JSON, Boolean

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def uid():
    return str(uuid.uuid4())

class Base(DeclarativeBase):
    pass

class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    observed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    media_key: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

class Upload(Base):
    __tablename__ = 'uploads'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    filename: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default='uploading')
    received_bytes: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer)
    chunks: Mapped[dict] = mapped_column(JSON, default=dict)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

class Setting(Base):
    __tablename__ = 'settings'
    section: Mapped[str] = mapped_column(String, primary_key=True)
    values: Mapped[dict] = mapped_column(JSON)
    row_version: Mapped[int] = mapped_column(Integer, default=1)

class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)
    upload_id: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str] = mapped_column(String, default='queued')
    created_at: Mapped[str] = mapped_column(String, default=now)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

class Worker(Base):
    __tablename__ = 'workers'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    heartbeat_at: Mapped[float] = mapped_column(Float)
    pid: Mapped[int] = mapped_column(Integer)

class Log(Base):
    __tablename__ = 'logs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    occurred_at: Mapped[str] = mapped_column(String, default=now)
    level: Mapped[str] = mapped_column(String)
    module: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)

class Notification(Base):
    __tablename__ = 'notifications'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, default=uid)
    type: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[str] = mapped_column(String, default=now)
    aggregate_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
