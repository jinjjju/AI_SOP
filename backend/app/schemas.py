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
    inquiry_type_name: str = ""  # 연결된 문의유형명 (없으면 "")


class ChangeDetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    detected_at: datetime
    diff_summary: str
    kind: str = "updated"  # updated / new_article
    triage_json: str = ""  # 신규 아티클 자동 분류(LLM) 결과 JSON
    status: str
    article: ArticleOut
    affected_sops: list[SopSummaryOut] = []


class SopVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sop_id: int
    version: int
    content: str
    verification_json: str = ""  # 근거 검증 결과 JSON
    test_report_json: str = ""  # 골든 질문 자동 테스트 결과 JSON
    source: str
    change_detection_id: Optional[int]
    model_used: str
    created_by: str = ""
    status: str
    created_at: datetime


class GoldenQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sop_id: int
    question: str
    expected_points: str
    created_by: str = ""


class GoldenQuestionIn(BaseModel):
    question: str
    expected_points: str = ""


class SopDetailOut(SopSummaryOut):
    content: str
    content_en: str = ""
    articles: list[ArticleOut] = []
    versions: list[SopVersionOut] = []
    golden_questions: list[GoldenQuestionOut] = []


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
    light_model: str
    default_generate_template_id: Optional[int]
    default_revise_template_id: Optional[int]
    usd_krw: float
    weekly_budget_usd: float
    zendesk_daily_call_limit: int
    auto_draft_on_sync: bool
    auto_sync_enabled: bool
    sync_hour: int
    last_sync_at: Optional[datetime] = None


class SettingsIn(BaseModel):
    default_model: Optional[str] = None
    light_model: Optional[str] = None
    default_generate_template_id: Optional[int] = None
    default_revise_template_id: Optional[int] = None
    usd_krw: Optional[float] = None
    weekly_budget_usd: Optional[float] = None
    zendesk_daily_call_limit: Optional[int] = None
    auto_draft_on_sync: Optional[bool] = None
    auto_sync_enabled: Optional[bool] = None
    sync_hour: Optional[int] = None


class ModelPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model: str
    input_per_1m: float
    output_per_1m: float


class ModelPriceIn(BaseModel):
    input_per_1m: float
    output_per_1m: float


class UsageRow(BaseModel):
    actor: str
    calls: int
    input_tokens: int
    output_tokens: int
    usd: float
    krw: float
    week_usd: float


class UsageSummary(BaseModel):
    total_usd: float
    total_krw: float
    week_usd: float
    week_krw: float
    weekly_budget_usd: float
    over_budget: bool
    usd_krw: float
    by_actor: list[UsageRow]
    by_model: list[dict]
    recent: list[dict]


class BudgetStatus(BaseModel):
    week_usd: float
    weekly_budget_usd: float
    over_budget: bool


class QualityOut(BaseModel):
    """LLM 정확도 실측 지표 — 무수정 승인율 95%+가 목표."""

    revision_total: int
    pending: int
    applied: int
    rejected: int
    clean_applied: int  # 수정 없이 승인된 초안
    clean_apply_rate: Optional[float]  # 결정된 건 대비 (표본 없으면 None)
    target_rate: float
    verified: int  # 근거 검증이 실행된 초안 수
    warned: int  # 검증 경고가 1건 이상 나온 초안 수
    tested: int  # 골든 테스트 실행된 초안 수
    test_failed: int  # 골든 테스트 실패 항목이 있던 초안 수


class GenerateIn(BaseModel):
    scope: str
    article_ids: Optional[list[int]] = None  # None이면 스코프 기반 자동 검색
    inquiry_type_id: Optional[int] = None  # 연결할 문의유형 (선택)


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
    mode: str = "full"  # incremental / full
    synced: int
    created: int
    updated: int
    new_detections: int
    new_article_candidates: int = 0  # 신규 아티클 감지 건수
    drafts_created: int = 0  # 자동 생성된 보완 초안 수
    skipped: int = 0  # 수집 필터로 제외된 신규 아티클 수
    budget_exhausted: bool = False  # 일일 호출 상한 도달로 중단됨
    slack_notified: bool = False
    message: str = ""


class ZendeskUsageOut(BaseModel):
    date: str
    calls: int
    limit: int


class InquiryTypeIn(BaseModel):
    name: str
    condition: str = ""


class InquiryTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    condition: str
    articles: list[ArticleOut] = []
    sop_count: int = 0


class ArticleLinkIn(BaseModel):
    url: str  # Zendesk 아티클 URL 또는 아티클 ID


class TriageIn(BaseModel):
    url: str
    inquiry_type_id: int


class TriageOut(BaseModel):
    article: ArticleOut
    suitable: bool
    reason: str
    action: str  # revise | create | none
    candidate_sops: list[SopSummaryOut] = []  # action=revise일 때 보완 대상 후보


class FiltersModel(BaseModel):
    in_scope_prefixes: list[str] = []
    exclusion_keywords: list[str] = []
    out_scope_prefixes: list[str] = []


class ReviseIn(BaseModel):
    article_id: int
    change_id: Optional[int] = None  # 신규 아티클 감지 건에서 넘어온 경우 해당 감지 건과 연결


class SopImportIn(BaseModel):
    """이미 만들어진 SOP 완성본 등록 (LLM 생성 없이)."""

    title: str = ""  # 비우면 content 첫 헤딩에서 추출
    target_scope: str
    content: str
    inquiry_type_id: Optional[int] = None
    article_ids: Optional[list[int]] = None  # 관련 아티클 연결 (변경 감지 역추적에 필요)
    status: str = "draft"  # draft / confirmed / published


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
    content_en: str = ""  # 영문본 (챗봇 반영 개발자용)
    version: int
    updated_at: datetime
    source_articles: list[dict]
