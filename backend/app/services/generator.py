"""AI SOP 생성 파이프라인.

- 신규 생성: 스코프 → 관련 아티클 자동 검색 → 기본(generate) 프롬프트 + 기본 모델로 생성
- 보완 초안: 변경 감지 건 → 기본(revise) 프롬프트로 기존 SOP 보완 → pending_review 버전
담당자는 스코프만 입력하면 되고, 모델/프롬프트는 AppSettings의 기본값이 자동 적용된다.
"""
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AiSop, AppSettings, Article, ChangeDetection, PromptTemplate, SopVersion
from .audit import log
from .llm import get_llm_provider

MAX_SEARCH_RESULTS = 8
ARTICLE_BODY_LIMIT = 4000  # 프롬프트에 넣을 아티클 본문 길이 제한


def get_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        raise HTTPException(500, "app_settings가 없습니다. seed.py를 먼저 실행하세요.")
    return settings


def _get_template(db: Session, template_id: Optional[int], purpose: str) -> PromptTemplate:
    template = db.get(PromptTemplate, template_id) if template_id else None
    if template is None:
        template = db.query(PromptTemplate).filter(PromptTemplate.purpose == purpose).first()
    if template is None:
        raise HTTPException(500, f"'{purpose}' 프롬프트 템플릿이 없습니다. 설정을 확인하세요.")
    return template


def next_version(db: Session, sop_id: int) -> int:
    """거절된 버전 포함 전체 이력 기준으로 다음 버전 번호를 채번 (중복 방지)."""
    latest = db.query(func.max(SopVersion.version)).filter(SopVersion.sop_id == sop_id).scalar()
    return (latest or 0) + 1


def search_articles(db: Session, scope: str, limit: int = MAX_SEARCH_RESULTS) -> list[Article]:
    """스코프 키워드 매칭 점수 기반의 단순 검색 (MVP). 제목 매칭에 가중치."""
    tokens = [t for t in re.split(r"[\s,./·]+", scope) if len(t) >= 2]
    if not tokens:
        return []
    scored: list[tuple[int, Article]] = []
    for article in db.query(Article).all():
        score = 0
        for token in tokens:
            if token in article.title:
                score += 3
            score += min(article.body.count(token), 5)
        if score > 0:
            scored.append((score, article))
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:limit]]


def _format_articles(articles: list[Article]) -> str:
    blocks = []
    for a in articles:
        body = a.body[:ARTICLE_BODY_LIMIT]
        blocks.append(f"### {a.title}\n(섹션: {a.section} / Zendesk ID: {a.zendesk_id})\n\n{body}")
    return "\n\n---\n\n".join(blocks) or "(참조 아티클 없음)"


def _fill(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:200]
    return fallback[:200]


def generate_new_sop(
    db: Session, scope: str, article_ids: Optional[list[int]] = None, actor: str = ""
) -> AiSop:
    settings = get_settings(db)
    template = _get_template(db, settings.default_generate_template_id, "generate")

    if article_ids:
        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
    else:
        articles = search_articles(db, scope)

    user_prompt = _fill(
        template.user_prompt_template,
        scope=scope,
        articles=_format_articles(articles),
    )
    content = get_llm_provider().generate(settings.default_model, template.system_prompt, user_prompt)

    sop = AiSop(
        title=_extract_title(content, scope),
        target_scope=scope,
        content=content,
        status="draft",
        current_version=1,
        created_by=actor,
        articles=articles,
    )
    db.add(sop)
    db.flush()
    db.add(
        SopVersion(
            sop_id=sop.id,
            version=1,
            content=content,
            source="new",
            model_used=settings.default_model,
            created_by=actor,
            template_id=template.id,
            status="applied",
        )
    )
    log(db, actor, "sop_created", "sop", sop.id, f"'{sop.title}' 신규 생성 ({settings.default_model})")
    db.commit()
    db.refresh(sop)
    return sop


def regenerate_sop(db: Session, sop: AiSop, article_ids: list[int], actor: str = "") -> AiSop:
    """담당자가 참조 아티클을 조정해 다시 생성 (draft 내용을 새 버전으로 교체)."""
    settings = get_settings(db)
    template = _get_template(db, settings.default_generate_template_id, "generate")
    articles = db.query(Article).filter(Article.id.in_(article_ids)).all()

    user_prompt = _fill(
        template.user_prompt_template,
        scope=sop.target_scope,
        articles=_format_articles(articles),
    )
    content = get_llm_provider().generate(settings.default_model, template.system_prompt, user_prompt)

    sop.articles = articles
    sop.content = content
    sop.current_version = next_version(db, sop.id)
    db.add(
        SopVersion(
            sop_id=sop.id,
            version=sop.current_version,
            content=content,
            source="new",
            model_used=settings.default_model,
            created_by=actor,
            template_id=template.id,
            status="applied",
        )
    )
    log(db, actor, "sop_regenerated", "sop", sop.id, f"'{sop.title}' 아티클 조정 후 재생성 (v{sop.current_version})")
    db.commit()
    db.refresh(sop)
    return sop


def create_revision_draft(
    db: Session, change: ChangeDetection, sop: AiSop, actor: str = ""
) -> SopVersion:
    """변경된 아티클 기준으로 기존 SOP 보완 초안을 생성해 pending_review 버전으로 저장."""
    settings = get_settings(db)
    template = _get_template(db, settings.default_revise_template_id, "revise")

    user_prompt = _fill(
        template.user_prompt_template,
        scope=sop.target_scope,
        current_sop=sop.content,
        articles=_format_articles([change.article]) + f"\n\n[변경 diff]\n{change.diff_summary}",
    )
    content = get_llm_provider().generate(settings.default_model, template.system_prompt, user_prompt)

    version = SopVersion(
        sop_id=sop.id,
        version=next_version(db, sop.id),
        content=content,
        source="revision",
        change_detection_id=change.id,
        model_used=settings.default_model,
        created_by=actor,
        template_id=template.id,
        status="pending_review",
    )
    db.add(version)
    change.status = "draft_created"
    log(
        db, actor, "draft_created", "sop", sop.id,
        f"'{sop.title}' 보완 초안 v{version.version} 생성 (아티클 '{change.article.title}' 변경 감지 #{change.id})",
    )
    db.commit()
    db.refresh(version)
    return version


def test_sop(db: Session, sop: AiSop, question: str) -> dict:
    """SOP를 시스템 프롬프트로 넣고 고객 질문을 시뮬레이션."""
    settings = get_settings(db)
    system_prompt = (
        "너는 고객센터 AI 챗봇이다. 아래 AI SOP에 정의된 절차와 안내 문구만 근거로 답변한다. "
        "SOP에 없는 정책은 안내하지 말고 상담사 연결을 권한다.\n\n[AI SOP]\n" + sop.content
    )
    answer = get_llm_provider().generate(
        settings.default_model, system_prompt, f"[고객 질문]\n{question}"
    )
    return {"question": question, "answer": answer, "model_used": settings.default_model}
