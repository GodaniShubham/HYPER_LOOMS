from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class NodeRecord(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gpu: Mapped[str] = mapped_column(String(64), nullable=False)
    vram_total_gb: Mapped[float] = mapped_column(Float, nullable=False)
    vram_used_gb: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="healthy")
    trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    jobs_running: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms_avg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="us-east-1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    assigned_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    results: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    merged_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

