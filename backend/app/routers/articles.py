from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Article
from ..services import detector, generator
from ..services.audit import get_actor, log

router = APIRouter(prefix="/api", tags=["articles"])


@router.post("/sync", response_model=schemas.SyncResult)
def sync(db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Zendesk 아티클 동기화 + 변경 감지 실행."""
    result = detector.sync_articles(db)
    log(
        db, actor, "sync_run", "sync", None,
        f"아티클 {result['synced']}건 동기화 · 변경 {result['new_detections']}건 감지",
    )
    db.commit()
    return result


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
