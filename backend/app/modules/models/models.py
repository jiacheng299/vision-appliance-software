from sqlalchemy import String, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ...shared.models import Base, uid, now


class ModelFile(Base):
    __tablename__ = 'model_files'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    filename: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)


class ModelPair(Base):
    __tablename__ = 'model_pairs'
    __table_args__ = (UniqueConstraint('template_id', 'template_version'),)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, primary_key=True)
    template_id: Mapped[str] = mapped_column(String)
    template_version: Mapped[str] = mapped_column(String)
    file_id: Mapped[str] = mapped_column(ForeignKey('model_files.id'))
    definition: Mapped[dict] = mapped_column(JSON)
    validation: Mapped[str] = mapped_column(String, default='pending')
    validation_message: Mapped[str] = mapped_column(String, default='等待算法适配器校验。')
    status: Mapped[str] = mapped_column(String, default='available')
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    data_origin: Mapped[str] = mapped_column(String, default='real')
    created_at: Mapped[str] = mapped_column(String, default=now)
    updated_at: Mapped[str] = mapped_column(String, default=now)


class ModelCommand(Base):
    __tablename__ = 'model_commands'
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    response: Mapped[dict] = mapped_column(JSON)


class LLMSelection(Base):
    __tablename__ = 'llm_selections'
    usage: Mapped[str] = mapped_column(String, primary_key=True)
    deployment_id: Mapped[str] = mapped_column(String)
    row_version: Mapped[int] = mapped_column(Integer, default=1)


class RequirementPlan(Base):
    __tablename__ = 'requirement_plans'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    resolved_channel: Mapped[dict] = mapped_column(JSON)
    catalog_fingerprint: Mapped[str] = mapped_column(String)
    verdict: Mapped[str] = mapped_column(String)
    missing_conditions: Mapped[list] = mapped_column(JSON)
    limitations: Mapped[list] = mapped_column(JSON)
    data_origin: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)
