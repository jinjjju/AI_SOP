from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import ActivityLog, Manager
from ..services.audit import log

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/managers", response_model=list[schemas.ManagerOut])
def list_managers(db: Session = Depends(get_db)):
    return db.query(Manager).order_by(Manager.name).all()


@router.post("/join", response_model=schemas.ManagerOut)
def join(body: schemas.ManagerIn, db: Session = Depends(get_db)):
    """간이 가입: 닉네임/팀명만 입력하면 담당자로 등록되어 생성·승인 권한을 갖는다.
    동일 닉네임이 이미 있으면 그 계정으로 이어서 사용한다(팀명은 최신값으로 갱신)."""
    name = body.name.strip()
    team = body.team.strip()
    if not name:
        raise HTTPException(400, "닉네임을 입력하세요.")
    manager = db.query(Manager).filter(Manager.name == name).first()
    if manager is None:
        manager = Manager(name=name, team=team)
        db.add(manager)
        log(db, name, "member_joined", "manager", None, f"'{name}'({team or '팀 미지정'}) 담당자 가입")
    elif team and manager.team != team:
        manager.team = team
    db.commit()
    db.refresh(manager)
    return manager


@router.delete("/managers/{manager_id}")
def delete_manager(manager_id: int, db: Session = Depends(get_db)):
    manager = db.get(Manager, manager_id)
    if manager is None:
        raise HTTPException(404, "담당자를 찾을 수 없습니다.")
    db.delete(manager)  # 활동 이력(actor 문자열)은 그대로 보존된다
    db.commit()
    return {"ok": True}


@router.get("/activity", response_model=list[schemas.ActivityOut])
def list_activity(
    entity_type: str = "",
    entity_id: int = 0,
    actor: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(ActivityLog).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
    if entity_type:
        q = q.filter(ActivityLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(ActivityLog.entity_id == entity_id)
    if actor:
        q = q.filter(ActivityLog.actor == actor)
    return q.limit(min(limit, 300)).all()
