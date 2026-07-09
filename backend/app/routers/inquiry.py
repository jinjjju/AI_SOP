"""문의유형 관리 + 수동 아티클 링크 검수(triage)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import AiSop, Article, InquiryType
from ..services import generator
from ..services.audit import get_actor, log, require_manager
from ..services.detector import _hash
from ..services.zendesk import get_zendesk_client

router = APIRouter(prefix="/api", tags=["inquiry"])


def _serialize(itype: InquiryType, db: Session) -> dict:
    return {
        "id": itype.id,
        "name": itype.name,
        "condition": itype.condition,
        "articles": itype.articles,
        "sop_count": db.query(AiSop).filter(AiSop.inquiry_type_id == itype.id).count(),
    }


def _get_type(db: Session, type_id: int) -> InquiryType:
    itype = db.get(InquiryType, type_id)
    if itype is None:
        raise HTTPException(404, "문의유형을 찾을 수 없습니다.")
    return itype


def _resolve_article(db: Session, url: str) -> Article:
    """Zendesk 아티클 URL(또는 ID)에서 아티클을 확보한다 — DB에 없으면 fetch 후 저장."""
    match = re.search(r"articles/(\d+)", url) or re.fullmatch(r"\s*(\d+)\s*", url)
    if match is None:
        raise HTTPException(400, "아티클 URL에서 ID를 찾을 수 없습니다. (…/articles/{id} 형식 또는 숫자 ID)")
    zendesk_id = int(match.group(1))

    article = db.query(Article).filter(Article.zendesk_id == zendesk_id).first()
    if article is None:
        remote = get_zendesk_client().get_article(zendesk_id)
        if remote is None:
            raise HTTPException(404, f"Zendesk에서 아티클 {zendesk_id}을(를) 찾을 수 없습니다.")
        article = Article(
            zendesk_id=remote["zendesk_id"],
            title=remote["title"],
            body=remote.get("body", ""),
            section=remote.get("section", ""),
            updated_at=remote.get("updated_at", ""),
            body_hash=_hash(remote.get("body", "")),
        )
        db.add(article)
        db.flush()
    return article


@router.get("/inquiry-types", response_model=list[schemas.InquiryTypeOut])
def list_types(db: Session = Depends(get_db)):
    return [_serialize(t, db) for t in db.query(InquiryType).order_by(InquiryType.name).all()]


@router.post("/inquiry-types", response_model=schemas.InquiryTypeOut)
def create_type(body: schemas.InquiryTypeIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "유형명을 입력하세요.")
    if db.query(InquiryType).filter(InquiryType.name == name).first():
        raise HTTPException(400, "이미 존재하는 문의유형입니다.")
    itype = InquiryType(name=name, condition=body.condition)
    db.add(itype)
    log(db, actor, "inquiry_type_created", "inquiry_type", None, f"문의유형 '{name}' 생성")
    db.commit()
    db.refresh(itype)
    return _serialize(itype, db)


@router.put("/inquiry-types/{type_id}", response_model=schemas.InquiryTypeOut)
def update_type(
    type_id: int, body: schemas.InquiryTypeIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)
):
    itype = _get_type(db, type_id)
    itype.name = body.name.strip() or itype.name
    itype.condition = body.condition
    log(db, actor, "inquiry_type_updated", "inquiry_type", itype.id, f"문의유형 '{itype.name}' 수정")
    db.commit()
    db.refresh(itype)
    return _serialize(itype, db)


@router.post("/inquiry-types/{type_id}/articles", response_model=schemas.InquiryTypeOut)
def link_article(
    type_id: int, body: schemas.ArticleLinkIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)
):
    itype = _get_type(db, type_id)
    article = _resolve_article(db, body.url)
    if article not in itype.articles:
        itype.articles.append(article)
        log(db, actor, "inquiry_article_linked", "inquiry_type", itype.id,
            f"'{itype.name}' 유형에 아티클 '{article.title}' 링크 추가")
    db.commit()
    db.refresh(itype)
    return _serialize(itype, db)


@router.delete("/inquiry-types/{type_id}/articles/{article_id}", response_model=schemas.InquiryTypeOut)
def unlink_article(
    type_id: int, article_id: int, db: Session = Depends(get_db), actor: str = Depends(require_manager)
):
    itype = _get_type(db, type_id)
    itype.articles = [a for a in itype.articles if a.id != article_id]
    db.commit()
    db.refresh(itype)
    return _serialize(itype, db)


@router.post("/triage", response_model=schemas.TriageOut)
def triage(body: schemas.TriageIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    """수동 링크 검수: 아티클 본문을 가져와 문의유형 조건과 대조해
    AI SOP 적합성 + 보완/신규 액션을 LLM이 판정한다. 실행은 담당자가 결정."""
    itype = _get_type(db, body.inquiry_type_id)
    article = _resolve_article(db, body.url.strip())
    result = generator.triage_article(db, itype, article, actor)
    log(
        db, actor, "triage_run", "inquiry_type", itype.id,
        f"'{itype.name}' 유형으로 아티클 '{article.title}' 검수 → "
        f"{'적합' if result['suitable'] else '부적합'} · {result['action']}",
    )
    db.commit()
    return {"article": article, **result}
