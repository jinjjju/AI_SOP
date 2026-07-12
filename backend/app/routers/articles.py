from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Article
from ..services import detector, generator
from ..services.audit import get_actor, log
from ..services.zendesk import zendesk_usage_today

router = APIRouter(prefix="/api", tags=["articles"])


@router.post("/sync", response_model=schemas.SyncResult)
def sync(mode: str = "auto", db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Zendesk 아티클 동기화 + 변경 감지 실행.

    mode=auto(기본): 마지막 동기화 이후 변경분만 인크리멘털 수집 (최초엔 전체)
    mode=full: 전체 재수집 — 정합성 맞추기용 (호출 수 많음, 주 1회 권장)"""
    result = detector.sync_articles(db, mode=mode, actor=actor)
    log(
        db, actor, "sync_run", "sync", None,
        f"아티클 {result['synced']}건 동기화({result['mode']}) · 변경 {result['new_detections']}건 · "
        f"신규 후보 {result['new_article_candidates']}건 · 자동 초안 {result['drafts_created']}건"
        + (" · ⚠ 호출 상한 도달" if result["budget_exhausted"] else ""),
    )
    db.commit()
    return result


@router.get("/zendesk-usage", response_model=schemas.ZendeskUsageOut)
def zendesk_usage():
    """오늘의 Zendesk API 호출 수 / 자체 상한 (설정에서 조정 가능)."""
    return zendesk_usage_today()


@router.get("/articles", response_model=list[schemas.ArticleOut])
def list_articles(query: str = "", db: Session = Depends(get_db)):
    if query.strip():
        return generator.search_articles(db, query, limit=20)
    return db.query(Article).order_by(Article.title).all()


@router.get("/articles/{article_id}", response_model=schemas.ArticleDetailOut)
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "아티클을 찾을 수 없습니다.")
    return article
