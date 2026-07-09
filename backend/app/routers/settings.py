from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, schemas
from ..database import get_db
from ..models import PromptTemplate
from ..services.audit import get_actor, log
from ..services.generator import get_settings

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/models")
def list_models():
    return {"models": config.AVAILABLE_MODELS, "use_mock": config.USE_MOCK}


@router.get("/settings", response_model=schemas.SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@router.put("/settings", response_model=schemas.SettingsOut)
def update_settings(body: schemas.SettingsIn, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    settings = get_settings(db)
    if body.default_model is not None:
        if body.default_model not in config.AVAILABLE_MODELS:
            raise HTTPException(400, f"허용되지 않는 모델입니다: {body.default_model}")
        settings.default_model = body.default_model
    for field in ("default_generate_template_id", "default_revise_template_id"):
        value = getattr(body, field)
        if value is not None:
            if db.get(PromptTemplate, value) is None:
                raise HTTPException(400, f"존재하지 않는 템플릿 ID: {value}")
            setattr(settings, field, value)
    for field in ("usd_krw", "weekly_budget_usd"):
        value = getattr(body, field)
        if value is not None:
            if value <= 0:
                raise HTTPException(400, f"{field}는 0보다 커야 합니다.")
            setattr(settings, field, value)
    log(db, actor, "settings_updated", "settings", None, f"기본 생성 설정 변경 (모델: {settings.default_model})")
    db.commit()
    db.refresh(settings)
    return settings


@router.get("/prompts", response_model=list[schemas.PromptTemplateOut])
def list_prompts(db: Session = Depends(get_db)):
    return db.query(PromptTemplate).order_by(PromptTemplate.id).all()


@router.post("/prompts", response_model=schemas.PromptTemplateOut)
def create_prompt(body: schemas.PromptTemplateIn, db: Session = Depends(get_db)):
    template = PromptTemplate(**body.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.put("/prompts/{prompt_id}", response_model=schemas.PromptTemplateOut)
def update_prompt(
    prompt_id: int, body: schemas.PromptTemplateIn, db: Session = Depends(get_db), actor: str = Depends(get_actor)
):
    template = db.get(PromptTemplate, prompt_id)
    if template is None:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다.")
    for key, value in body.model_dump().items():
        setattr(template, key, value)
    log(db, actor, "prompt_updated", "settings", template.id, f"프롬프트 템플릿 '{template.name}' 수정")
    db.commit()
    db.refresh(template)
    return template
