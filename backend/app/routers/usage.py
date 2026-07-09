"""LLM 사용량/비용 집계 + 모델 단가 관리.

비용은 저장된 토큰 수 × 조회 시점의 model_prices 단가로 계산한다.
→ 어드민에서 단가를 수정하면 과거 사용분의 표시 금액에도 즉시 반영된다.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import LlmUsage, ModelPrice
from ..services.audit import get_actor, log
from ..services.generator import get_settings

router = APIRouter(prefix="/api", tags=["usage"])


def _price_map(db: Session) -> dict:
    return {p.model: p for p in db.query(ModelPrice).all()}


def _cost_usd(usage: LlmUsage, prices: dict) -> float:
    p = prices.get(usage.model)
    if p is None:
        return 0.0
    return usage.input_tokens / 1e6 * p.input_per_1m + usage.output_tokens / 1e6 * p.output_per_1m


def _week_ago() -> datetime:
    return datetime.utcnow() - timedelta(days=7)


@router.get("/prices", response_model=list[schemas.ModelPriceOut])
def list_prices(db: Session = Depends(get_db)):
    return db.query(ModelPrice).order_by(ModelPrice.model).all()


@router.put("/prices/{model}", response_model=schemas.ModelPriceOut)
def update_price(
    model: str, body: schemas.ModelPriceIn, db: Session = Depends(get_db), actor: str = Depends(get_actor)
):
    price = db.query(ModelPrice).filter(ModelPrice.model == model).first()
    if price is None:
        price = ModelPrice(model=model)
        db.add(price)
    price.input_per_1m = body.input_per_1m
    price.output_per_1m = body.output_per_1m
    log(
        db, actor, "price_updated", "settings", None,
        f"'{model}' 단가 변경: 입력 ${body.input_per_1m}/1M · 출력 ${body.output_per_1m}/1M",
    )
    db.commit()
    db.refresh(price)
    return price


@router.get("/usage", response_model=schemas.UsageSummary)
def usage_summary(db: Session = Depends(get_db)):
    settings = get_settings(db)
    prices = _price_map(db)
    rows = db.query(LlmUsage).order_by(LlmUsage.created_at.desc()).all()
    week_ago = _week_ago()

    by_actor: dict = {}
    by_model: dict = {}
    total_usd = week_usd = 0.0

    for u in rows:
        cost = _cost_usd(u, prices)
        total_usd += cost
        in_week = u.created_at >= week_ago
        if in_week:
            week_usd += cost

        a = by_actor.setdefault(
            u.actor or "(미지정)",
            {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0, "week_usd": 0.0},
        )
        a["calls"] += 1
        a["input_tokens"] += u.input_tokens
        a["output_tokens"] += u.output_tokens
        a["usd"] += cost
        if in_week:
            a["week_usd"] += cost

        m = by_model.setdefault(
            u.model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0}
        )
        m["calls"] += 1
        m["input_tokens"] += u.input_tokens
        m["output_tokens"] += u.output_tokens
        m["usd"] += cost

    return {
        "total_usd": total_usd,
        "total_krw": total_usd * settings.usd_krw,
        "week_usd": week_usd,
        "week_krw": week_usd * settings.usd_krw,
        "weekly_budget_usd": settings.weekly_budget_usd,
        "over_budget": week_usd > settings.weekly_budget_usd,
        "usd_krw": settings.usd_krw,
        "by_actor": [
            {"actor": name, **v, "krw": v["usd"] * settings.usd_krw}
            for name, v in sorted(by_actor.items(), key=lambda x: -x[1]["usd"])
        ],
        "by_model": [
            {"model": name, **v, "krw": v["usd"] * settings.usd_krw}
            for name, v in sorted(by_model.items(), key=lambda x: -x[1]["usd"])
        ],
        "recent": [
            {
                "id": u.id,
                "actor": u.actor,
                "purpose": u.purpose,
                "model": u.model,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "usd": _cost_usd(u, prices),
                "sop_id": u.sop_id,
                "created_at": u.created_at.isoformat(),
            }
            for u in rows[:20]
        ],
    }


@router.get("/usage/status", response_model=schemas.BudgetStatus)
def budget_status(db: Session = Depends(get_db)):
    """상단 바 노티용 경량 조회: 최근 7일 사용액 vs 주간 예산."""
    settings = get_settings(db)
    prices = _price_map(db)
    rows = db.query(LlmUsage).filter(LlmUsage.created_at >= _week_ago()).all()
    week_usd = sum(_cost_usd(u, prices) for u in rows)
    return {
        "week_usd": week_usd,
        "weekly_budget_usd": settings.weekly_budget_usd,
        "over_budget": week_usd > settings.weekly_budget_usd,
    }
