"""활동 이력 기록 + 담당자(actor) 추출.

프론트는 선택된 담당자 이름을 encodeURIComponent 하여 X-Actor 헤더로 보낸다.
log()는 db.add만 하므로 호출부의 commit에 함께 묶인다.
"""
from typing import Optional
from urllib.parse import unquote

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ActivityLog, Manager


def get_actor(x_actor: str = Header("")) -> str:
    return unquote(x_actor).strip()[:100]


def require_manager(actor: str = Depends(get_actor), db: Session = Depends(get_db)) -> str:
    """가입된 담당자만 변경 작업(생성/승인/발행 등)을 수행할 수 있다."""
    if not actor or db.query(Manager).filter(Manager.name == actor).first() is None:
        raise HTTPException(403, "가입된 담당자만 수행할 수 있습니다. 닉네임/팀명으로 가입 후 이용하세요.")
    return actor


def log(
    db: Session,
    actor: str,
    action: str,
    entity_type: str = "",
    entity_id: Optional[int] = None,
    detail: str = "",
) -> None:
    db.add(
        ActivityLog(
            actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail
        )
    )
