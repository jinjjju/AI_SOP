from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# SOP ↔ 참조 아티클 N:M (변경 감지 시 영향받는 SOP 역추적에 사용)
sop_articles = Table(
    "sop_articles",
    Base.metadata,
    Column("sop_id", ForeignKey("ai_sops.id", ondelete="CASCADE"), primary_key=True),
    Column("article_id", ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    zendesk_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, default="")
    section: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[str] = mapped_column(String(50), default="")
    body_hash: Mapped[str] = mapped_column(String(64), default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sops = relationship("AiSop", secondary=sop_articles, back_populates="articles")


class ChangeDetection(Base):
    __tablename__ = "change_detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    new_hash: Mapped[str] = mapped_column(String(64), default="")
    prev_body: Mapped[str] = mapped_column(Text, default="")
    diff_summary: Mapped[str] = mapped_column(Text, default="")
    # open → draft_created → applied / dismissed
    status: Mapped[str] = mapped_column(String(20), default="open")

    article = relationship("Article")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # generate: 신규 SOP 생성용 / revise: 아티클 변경 보완용
    purpose: Mapped[str] = mapped_column(String(20), default="generate")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    # 플레이스홀더: {scope}, {articles}, {current_sop}
    user_prompt_template: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # 단일 행(id=1)
    default_model: Mapped[str] = mapped_column(String(100), default="gemini-3.5-flash")
    default_generate_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prompt_templates.id"), nullable=True
    )
    default_revise_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prompt_templates.id"), nullable=True
    )
    usd_krw: Mapped[float] = mapped_column(Float, default=1400.0)  # 원화 환산 환율
    weekly_budget_usd: Mapped[float] = mapped_column(Float, default=10.0)  # 주간(최근 7일) 예산


class ModelPrice(Base):
    """모델별 단가 (USD / 100만 토큰). 어드민에서 수정하면 비용 계산에 즉시 반영된다."""

    __tablename__ = "model_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(100), unique=True)
    input_per_1m: Mapped[float] = mapped_column(Float, default=0.0)
    output_per_1m: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LlmUsage(Base):
    """LLM 호출 1건당 토큰 사용 기록. 비용은 저장하지 않고 조회 시점의 단가로 계산한다
    (단가를 수정하면 과거 표시 금액에도 자동 반영)."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(100), default="")
    purpose: Mapped[str] = mapped_column(String(20), default="")  # generate/revise/regenerate/test
    model: Mapped[str] = mapped_column(String(100), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    sop_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Manager(Base):
    """담당자 (MVP: 닉네임/팀명만 입력하는 간이 가입, 활동 이력의 주체).

    가입된 담당자만 SOP 생성·승인 등 변경 작업을 수행할 수 있다."""

    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    team: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ActivityLog(Base):
    """모든 주요 액션의 감사 이력 (누가/언제/무엇을)."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(100), default="")
    # sop_created / draft_created / version_applied / version_rejected /
    # status_changed / content_edited / sync_run / settings_updated / prompt_updated
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(30), default="")  # sop / change / settings
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiSop(Base):
    __tablename__ = "ai_sops"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    target_scope: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(100), default="")
    # draft → confirmed → published
    status: Mapped[str] = mapped_column(String(20), default="draft")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = relationship("Article", secondary=sop_articles, back_populates="sops")
    versions = relationship(
        "SopVersion", back_populates="sop", cascade="all, delete-orphan", order_by="SopVersion.version"
    )


class SopVersion(Base):
    __tablename__ = "sop_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    sop_id: Mapped[int] = mapped_column(ForeignKey("ai_sops.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    # new: 신규 생성 / revision: 변경 감지 보완 초안 / manual: 담당자 직접 수정
    source: Mapped[str] = mapped_column(String(20), default="new")
    change_detection_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("change_detections.id"), nullable=True
    )
    model_used: Mapped[str] = mapped_column(String(100), default="")
    created_by: Mapped[str] = mapped_column(String(100), default="")
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prompt_templates.id"), nullable=True)
    # pending_review → applied / rejected
    status: Mapped[str] = mapped_column(String(20), default="applied")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sop = relationship("AiSop", back_populates="versions")
