import asyncio
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import SessionLocal, migrate
from .routers import admin, articles, changes, inquiry, settings, sops, usage

migrate()  # 테이블 생성 + 기존 DB에 신규 컬럼 반영 (경량 마이그레이션)

app = FastAPI(title="AI SOP Admin", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(articles.router)
app.include_router(changes.router)
app.include_router(sops.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(usage.router)
app.include_router(inquiry.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _run_scheduled_sync():
    from .services.audit import log
    from .services.detector import sync_articles

    db = SessionLocal()
    try:
        result = sync_articles(db, mode="auto", actor="scheduler")
        log(
            db, "scheduler", "sync_run", "sync", None,
            f"[자동] 아티클 {result['synced']}건 동기화({result['mode']}) · 변경 {result['new_detections']}건 · "
            f"신규 후보 {result['new_article_candidates']}건 · 자동 초안 {result['drafts_created']}건",
        )
        db.commit()
    finally:
        db.close()


async def _sync_scheduler():
    """데일리 자동 동기화 — 설정(auto_sync_enabled, sync_hour)에 따라 하루 1회 실행.

    백엔드가 상시 구동일 때 동작한다. 회사 PC에서 OS 스케줄러를 쓰는 경우
    `curl -X POST http://localhost:8001/api/sync`로 대체 가능."""
    last_run: Optional[date] = None
    while True:
        await asyncio.sleep(60)
        try:
            db = SessionLocal()
            try:
                from .models import AppSettings

                s = db.get(AppSettings, 1)
                enabled = bool(s and s.auto_sync_enabled)
                sync_hour = s.sync_hour if s else 8
            finally:
                db.close()
            now = datetime.now()  # 로컬 시간 기준
            if enabled and now.hour == sync_hour and last_run != now.date():
                last_run = now.date()  # 실패해도 같은 날 재시도로 호출을 낭비하지 않는다
                await asyncio.to_thread(_run_scheduled_sync)
        except Exception:
            pass  # 스케줄러는 어떤 경우에도 죽지 않는다


@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(_sync_scheduler())
