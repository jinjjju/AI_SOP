from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, schemas
from ..database import get_db
from ..models import PromptTemplate
from ..services import filters as filter_service
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
    for field in ("default_model", "light_model"):
        value = getattr(body, field)
        if value is not None:
            if value not in config.AVAILABLE_MODELS:
                raise HTTPException(400, f"허용되지 않는 모델입니다: {value}")
            setattr(settings, field, value)
    for field in ("default_generate_template_id", "default_revise_template_id"):
        value = getattr(body, field)
        if value is not None:
            if db.get(PromptTemplate, value) is None:
                raise HTTPException(400, f"존재하지 않는 템플릿 ID: {value}")
            setattr(settings, field, value)
    for field in ("usd_krw", "weekly_budget_usd", "zendesk_daily_call_limit"):
        value = getattr(body, field)
        if value is not None:
            if value <= 0:
                raise HTTPException(400, f"{field}는 0보다 커야 합니다.")
            setattr(settings, field, value)
    if body.sync_hour is not None:
        if not (0 <= body.sync_hour <= 23):
            raise HTTPException(400, "sync_hour는 0~23 사이여야 합니다.")
        settings.sync_hour = body.sync_hour
    for field in ("auto_draft_on_sync", "auto_sync_enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(settings, field, 1 if value else 0)
    log(db, actor, "settings_updated", "settings", None, f"기본 생성 설정 변경 (모델: {settings.default_model})")
    db.commit()
    db.refresh(settings)
    return settings


@router.get("/filters", response_model=schemas.FiltersModel)
def read_filters():
    return filter_service.load_filters()


@router.put("/filters", response_model=schemas.FiltersModel)
def update_filters(body: schemas.FiltersModel, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    saved = filter_service.save_filters(body.model_dump())
    log(db, actor, "filters_updated", "settings", None,
        f"수집 필터 수정 (in:{len(saved['in_scope_prefixes'])} / excl:{len(saved['exclusion_keywords'])} / out:{len(saved['out_scope_prefixes'])})")
    db.commit()
    return saved


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
