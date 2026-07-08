from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import AiSop, ChangeDetection
from ..services import generator
from ..services.audit import get_actor, log, require_manager

router = APIRouter(prefix="/api/changes", tags=["changes"])


def _with_affected(change: ChangeDetection) -> dict:
    return {
        **{c.name: getattr(change, c.name) for c in ChangeDetection.__table__.columns},
        "article": change.article,
        "affected_sops": change.article.sops if change.article else [],
    }


@router.get("", response_model=list[schemas.ChangeDetectionOut])
def list_changes(status: str = "", db: Session = Depends(get_db)):
    q = db.query(ChangeDetection).order_by(ChangeDetection.detected_at.desc())
    if status:
        q = q.filter(ChangeDetection.status == status)
    return [_with_affected(c) for c in q.all()]


@router.get("/{change_id}", response_model=schemas.ChangeDetectionOut)
def get_change(change_id: int, db: Session = Depends(get_db)):
    change = db.get(ChangeDetection, change_id)
    if change is None:
        raise HTTPException(404, "변경 감지 건을 찾을 수 없습니다.")
    return _with_affected(change)


@router.post("/{change_id}/draft", response_model=schemas.SopVersionOut)
def create_draft(change_id: int, sop_id: int, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    """변경 감지 건에 대해 특정 SOP의 보완 초안(pending_review 버전)을 생성."""
    change = db.get(ChangeDetection, change_id)
    if change is None:
        raise HTTPException(404, "변경 감지 건을 찾을 수 없습니다.")
    sop = db.get(AiSop, sop_id)
    if sop is None:
        raise HTTPException(404, "SOP를 찾을 수 없습니다.")
    if sop not in change.article.sops:
        raise HTTPException(400, "해당 아티클을 참조하지 않는 SOP입니다.")
    return generator.create_revision_draft(db, change, sop, actor)


@router.post("/{change_id}/dismiss", response_model=schemas.ChangeDetectionOut)
def dismiss(change_id: int, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    change = db.get(ChangeDetection, change_id)
    if change is None:
        raise HTTPException(404, "변경 감지 건을 찾을 수 없습니다.")
    change.status = "dismissed"
    log(db, actor, "change_dismissed", "change", change.id, f"아티클 '{change.article.title}' 변경 건 무시 처리")
    db.commit()
    return _with_affected(change)
