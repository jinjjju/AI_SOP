from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import AiSop, ChangeDetection, SopVersion
from ..services import generator
from ..services.audit import get_actor, log, require_manager

router = APIRouter(prefix="/api/sops", tags=["sops"])

VALID_STATUS_FLOW = {
    "draft": {"confirmed"},
    "confirmed": {"published", "draft"},
    "published": {"draft"},  # 발행 철회 후 재작업
}


def _get_sop(db: Session, sop_id: int) -> AiSop:
    sop = db.get(AiSop, sop_id)
    if sop is None:
        raise HTTPException(404, "SOP를 찾을 수 없습니다.")
    return sop


@router.get("", response_model=list[schemas.SopSummaryOut])
def list_sops(status: str = "", db: Session = Depends(get_db)):
    q = db.query(AiSop).order_by(AiSop.updated_at.desc())
    if status:
        q = q.filter(AiSop.status == status)
    sops = q.all()
    pending_since = {
        sop_id: created_at
        for sop_id, created_at in db.query(SopVersion.sop_id, SopVersion.created_at)
        .filter(SopVersion.status == "pending_review")
        .all()
    }
    return [
        {
            **{c.name: getattr(s, c.name) for c in AiSop.__table__.columns},
            "has_pending": s.id in pending_since,
            "pending_since": pending_since.get(s.id),
        }
        for s in sops
    ]


@router.get("/published", response_model=list[schemas.PublishedSopOut])
def published_sops(db: Session = Depends(get_db)):
    """개발팀 전달용: 발행된 SOP 전체를 구조화 JSON으로 반환."""
    sops = db.query(AiSop).filter(AiSop.status == "published").order_by(AiSop.id).all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "target_scope": s.target_scope,
            "content": s.content,
            "version": s.current_version,
            "updated_at": s.updated_at,
            "source_articles": [
                {"zendesk_id": a.zendesk_id, "title": a.title, "section": a.section}
                for a in s.articles
            ],
        }
        for s in sops
    ]


@router.post("/generate", response_model=schemas.SopDetailOut)
def generate(body: schemas.GenerateIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    """스코프 입력 → 아티클 자동 검색 → 기본 모델/프롬프트로 SOP 생성 (원스텝)."""
    if not body.scope.strip():
        raise HTTPException(400, "타겟 문의 스코프를 입력하세요.")
    return generator.generate_new_sop(db, body.scope.strip(), body.article_ids, actor)


@router.get("/{sop_id}", response_model=schemas.SopDetailOut)
def get_sop(sop_id: int, db: Session = Depends(get_db)):
    return _get_sop(db, sop_id)


@router.patch("/{sop_id}", response_model=schemas.SopDetailOut)
def update_sop(
    sop_id: int, body: schemas.SopUpdateIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)
):
    sop = _get_sop(db, sop_id)
    if body.title is not None:
        sop.title = body.title
    if body.target_scope is not None:
        sop.target_scope = body.target_scope
    if body.content is not None and body.content != sop.content:
        sop.content = body.content
        sop.current_version = generator.next_version(db, sop.id)
        db.add(
            SopVersion(
                sop_id=sop.id,
                version=sop.current_version,
                content=body.content,
                source="manual",
                created_by=actor,
                status="applied",
            )
        )
        log(db, actor, "content_edited", "sop", sop.id, f"'{sop.title}' 본문 수동 수정 (v{sop.current_version})")
    db.commit()
    db.refresh(sop)
    return sop


@router.post("/{sop_id}/status", response_model=schemas.SopDetailOut)
def change_status(
    sop_id: int, body: schemas.StatusIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)
):
    sop = _get_sop(db, sop_id)
    if body.status not in VALID_STATUS_FLOW.get(sop.status, set()):
        raise HTTPException(400, f"'{sop.status}' → '{body.status}' 전환은 허용되지 않습니다.")
    log(db, actor, "status_changed", "sop", sop.id, f"'{sop.title}' 상태 변경: {sop.status} → {body.status}")
    sop.status = body.status
    db.commit()
    db.refresh(sop)
    return sop


@router.post("/{sop_id}/regenerate", response_model=schemas.SopDetailOut)
def regenerate(
    sop_id: int, body: schemas.RegenerateIn, db: Session = Depends(get_db), actor: str = Depends(require_manager)
):
    sop = _get_sop(db, sop_id)
    if sop.status != "draft":
        raise HTTPException(400, "draft 상태에서만 재생성할 수 있습니다.")
    return generator.regenerate_sop(db, sop, body.article_ids, actor)


@router.post("/{sop_id}/versions/{version}/apply", response_model=schemas.SopDetailOut)
def apply_version(sop_id: int, version: int, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    """보완 초안(pending_review)을 승인해 기존 SOP를 새 버전으로 갱신."""
    sop = _get_sop(db, sop_id)
    v = (
        db.query(SopVersion)
        .filter(SopVersion.sop_id == sop_id, SopVersion.version == version)
        .first()
    )
    if v is None:
        raise HTTPException(404, "버전을 찾을 수 없습니다.")
    if v.status != "pending_review":
        raise HTTPException(400, "검토 대기 상태의 버전만 승인할 수 있습니다.")
    v.status = "applied"
    sop.content = v.content
    sop.current_version = v.version
    if v.change_detection_id:
        change = db.get(ChangeDetection, v.change_detection_id)
        if change:
            change.status = "applied"
    log(db, actor, "version_applied", "sop", sop.id, f"'{sop.title}' 보완안 v{v.version} 승인 · SOP 갱신")
    db.commit()
    db.refresh(sop)
    return sop


@router.post("/{sop_id}/versions/{version}/reject", response_model=schemas.SopVersionOut)
def reject_version(sop_id: int, version: int, db: Session = Depends(get_db), actor: str = Depends(require_manager)):
    v = (
        db.query(SopVersion)
        .filter(SopVersion.sop_id == sop_id, SopVersion.version == version)
        .first()
    )
    if v is None:
        raise HTTPException(404, "버전을 찾을 수 없습니다.")
    if v.status != "pending_review":
        raise HTTPException(400, "검토 대기 상태의 버전만 거절할 수 있습니다.")
    v.status = "rejected"
    sop = _get_sop(db, sop_id)
    log(db, actor, "version_rejected", "sop", sop.id, f"'{sop.title}' 보완안 v{v.version} 거절")
    db.commit()
    db.refresh(v)
    return v


@router.patch("/{sop_id}/versions/{version}", response_model=schemas.SopVersionOut)
def edit_pending_version(
    sop_id: int,
    version: int,
    body: schemas.SopUpdateIn,
    db: Session = Depends(get_db),
    actor: str = Depends(require_manager),
):
    """승인 전 보완 초안 내용을 담당자가 수정."""
    v = (
        db.query(SopVersion)
        .filter(SopVersion.sop_id == sop_id, SopVersion.version == version)
        .first()
    )
    if v is None:
        raise HTTPException(404, "버전을 찾을 수 없습니다.")
    if v.status != "pending_review":
        raise HTTPException(400, "검토 대기 상태의 버전만 수정할 수 있습니다.")
    if body.content is not None:
        v.content = body.content
    db.commit()
    db.refresh(v)
    return v


@router.post("/{sop_id}/test", response_model=schemas.TestOut)
def test(sop_id: int, body: schemas.TestIn, db: Session = Depends(get_db)):
    sop = _get_sop(db, sop_id)
    if not body.question.strip():
        raise HTTPException(400, "질문을 입력하세요.")
    return generator.test_sop(db, sop, body.question.strip())
