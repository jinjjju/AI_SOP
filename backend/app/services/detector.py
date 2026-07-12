"""아티클 동기화 + 변경 감지.

동기화 파이프라인 (데일리 1회 권장):
1. 인크리멘털 수집 — last_sync_at 이후 생성·수정분만 Zendesk에서 가져온다
   (최초 1회 또는 mode="full"이면 전체 수집). 호출 수는 zendesk_daily_call_limit로 가드.
2. 판정은 해시가 한다 — updated_at은 메타데이터 수정에도 갱신되므로,
   body_hash가 실제로 바뀐 것만 ChangeDetection(kind="updated")을 만든다.
3. 신규 아티클 — 수집 필터(article_filters.json) 통과분은 저장 +
   ChangeDetection(kind="new_article") 생성 + LLM 자동 분류(auto_triage) 결과 저장.
4. 자동 보완 초안 — published SOP에 영향 주는 변경 건은 보완 초안(검증·골든테스트 포함)까지
   자동 생성해 담당자는 컨펌만 하면 된다 (설정 auto_draft_on_sync).
5. Slack 알림 — 처리할 건이 있으면 채널에 건수+링크만 1회 발송.
"""
import calendar
import difflib
import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import AppSettings, Article, ChangeDetection, SopVersion
from .filters import is_in_scope
from .zendesk import ZendeskBudgetExceeded, get_zendesk_client

# 인크리멘털 수집 시 겹침 여유 (시계 오차·경계 누락 방지 — 중복은 해시 비교가 걸러줌)
INCREMENTAL_OVERLAP_SECONDS = 300


def _hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _diff_summary(old: str, new: str, max_lines: int = 40) -> str:
    diff = list(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), fromfile="이전", tofile="변경 후", lineterm="", n=1
        )
    )
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"... (이하 {len(diff) - max_lines}줄 생략)"]
    return "\n".join(diff)


def _has_pending_version(db: Session, sop_id: int) -> bool:
    return (
        db.query(SopVersion)
        .filter(SopVersion.sop_id == sop_id, SopVersion.status == "pending_review")
        .first()
        is not None
    )


def sync_articles(db: Session, mode: str = "auto", actor: str = "") -> dict:
    """mode: auto(마지막 동기화 있으면 인크리멘털) / full(전체 재수집) / incremental(강제)"""
    import json as _json

    from . import generator, notify

    settings = db.get(AppSettings, 1)
    client = get_zendesk_client()
    started_at = datetime.utcnow()

    incremental = mode != "full" and settings is not None and settings.last_sync_at is not None
    result = {
        "mode": "incremental" if incremental else "full",
        "synced": 0,
        "created": 0,
        "updated": 0,
        "new_detections": 0,
        "new_article_candidates": 0,
        "drafts_created": 0,
        "skipped": 0,
        "budget_exhausted": False,
        "slack_notified": False,
        "message": "",
    }

    try:
        if incremental:
            start_time = calendar.timegm(settings.last_sync_at.timetuple()) - INCREMENTAL_OVERLAP_SECONDS
            remote = client.list_updated_since(start_time)
        else:
            remote = client.list_articles()
    except ZendeskBudgetExceeded as e:
        db.rollback()
        result["budget_exhausted"] = True
        result["message"] = str(e)
        return result

    changed: list[ChangeDetection] = []
    new_candidates: list[ChangeDetection] = []

    for item in remote:
        body = item.get("body") or ""
        new_hash = _hash(body)
        article = db.query(Article).filter(Article.zendesk_id == item["zendesk_id"]).first()
        if article is None:
            # 신규 아티클은 수집 필터(article_filters.json) 통과분만 저장
            if not is_in_scope(item["title"]):
                result["skipped"] += 1
                continue
            article = Article(
                zendesk_id=item["zendesk_id"],
                title=item["title"],
                body=body,
                section=item.get("section", ""),
                updated_at=item.get("updated_at", ""),
                body_hash=new_hash,
                synced_at=datetime.utcnow(),
            )
            db.add(article)
            db.flush()
            result["created"] += 1
            # 최초 전체 수집(테이블이 비어 있던 시점)이 아니라면 '신규 발견'으로 감지
            if incremental:
                detection = ChangeDetection(
                    article_id=article.id, kind="new_article", new_hash=new_hash
                )
                db.add(detection)
                new_candidates.append(detection)
                result["new_article_candidates"] += 1
            continue

        if article.body_hash != new_hash:
            # 동일 아티클에 대해 이미 열린 감지가 있으면 중복 생성하지 않는다
            existing_open = (
                db.query(ChangeDetection)
                .filter(
                    ChangeDetection.article_id == article.id,
                    ChangeDetection.status.in_(["open", "draft_created"]),
                )
                .first()
            )
            if existing_open is None:
                detection = ChangeDetection(
                    article_id=article.id,
                    kind="updated",
                    prev_hash=article.body_hash,
                    new_hash=new_hash,
                    prev_body=article.body,
                    diff_summary=_diff_summary(article.body, body),
                )
                db.add(detection)
                changed.append(detection)
                result["new_detections"] += 1
            article.body = body
            article.body_hash = new_hash
            article.updated_at = item.get("updated_at", "")
            result["updated"] += 1

        article.title = item["title"]
        article.section = item.get("section", "")
        article.synced_at = datetime.utcnow()

    result["synced"] = len(remote)
    db.commit()

    # 신규 아티클 자동 분류 (LLM 2~3회 투표) — 실패해도 감지 자체는 남긴다
    for detection in new_candidates:
        try:
            triage = generator.auto_triage(db, detection.article, actor or "auto-sync")
        except Exception as e:
            triage = {"suitable": False, "action": "none", "reason": f"자동 분류 실패: {e}", "confident": False}
        detection.triage_json = _json.dumps(triage, ensure_ascii=False)
        db.commit()

    # published SOP에 영향 주는 변경 건 → 보완 초안(검증+골든테스트 포함) 자동 생성
    if settings is not None and settings.auto_draft_on_sync:
        for detection in changed:
            for sop in detection.article.sops:
                if sop.status != "published" or _has_pending_version(db, sop.id):
                    continue
                try:
                    generator.create_revision_draft(db, detection, sop, actor or "auto-sync")
                    result["drafts_created"] += 1
                except Exception:
                    db.rollback()  # 초안 실패 시 감지 건은 open으로 남아 수동 생성 가능

    if settings is not None:
        settings.last_sync_at = started_at
        db.commit()

    result["slack_notified"] = notify.send_sync_summary(result)
    return result
