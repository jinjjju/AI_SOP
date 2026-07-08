from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    zendesk_id: int
    title: str
    section: str
    updated_at: str
    synced_at: datetime


class ArticleDetailOut(ArticleOut):
    body: str


class SopSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    target_scope: str
    status: str
    current_version: int
    created_by: str = ""
    created_at: datetime
    updated_at: datetime
    has_pending: bool = False  # 검토 대기 중인 보완 초안 존재 여부
    pending_since: Optional[datetime] = None  # 보완 초안(감지 케이스) 생성 일시


class ChangeDetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    detected_at: datetime
    diff_summary: str
    status: str
    article: ArticleOut
    affected_sops: list[SopSummaryOut] = []


class SopVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sop_id: int
    version: int
    content: str
    source: str
    change_detection_id: Optional[int]
    model_used: str
    created_by: str = ""
    status: str
    created_at: datetime


class SopDetailOut(SopSummaryOut):
    content: str
    articles: list[ArticleOut] = []
    versions: list[SopVersionOut] = []


class PromptTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    purpose: str
    system_prompt: str
    user_prompt_template: str


class PromptTemplateIn(BaseModel):
    name: str
    purpose: str = "generate"
    system_prompt: str = ""
    user_prompt_template: str = ""


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_model: str
    default_generate_template_id: Optional[int]
    default_revise_template_id: Optional[int]


class SettingsIn(BaseModel):
    default_model: Optional[str] = None
    default_generate_template_id: Optional[int] = None
    default_revise_template_id: Optional[int] = None


class GenerateIn(BaseModel):
    scope: str
    article_ids: Optional[list[int]] = None  # None이면 스코프 기반 자동 검색


class RegenerateIn(BaseModel):
    article_ids: list[int]


class SopUpdateIn(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    target_scope: Optional[str] = None


class StatusIn(BaseModel):
    status: str  # draft / confirmed / published


class TestIn(BaseModel):
    question: str


class TestOut(BaseModel):
    question: str
    answer: str
    model_used: str


class SyncResult(BaseModel):
    synced: int
    created: int
    updated: int
    new_detections: int


class ManagerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    team: str


class ManagerIn(BaseModel):
    name: str
    team: str = ""


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: Optional[int]
    detail: str
    created_at: datetime


class PublishedSopOut(BaseModel):
    id: int
    title: str
    target_scope: str
    content: str
    version: int
    updated_at: datetime
    source_articles: list[dict]
