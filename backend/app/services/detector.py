"""아티클 동기화 + 변경 감지.

Zendesk에서 아티클을 가져와 로컬 캐시(articles)와 body_hash를 비교하고,
변경된 아티클마다 ChangeDetection(open)을 생성한다.
"""
import difflib
import hashlib
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Article, ChangeDetection
from .zendesk import get_zendesk_client


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


def sync_articles(db: Session) -> dict:
    client = get_zendesk_client()
    remote = client.list_articles()

    created = updated = new_detections = 0
    for item in remote:
        body = item.get("body") or ""
        new_hash = _hash(body)
        article = db.query(Article).filter(Article.zendesk_id == item["zendesk_id"]).first()
        if article is None:
            db.add(
                Article(
                    zendesk_id=item["zendesk_id"],
                    title=item["title"],
                    body=body,
                    section=item.get("section", ""),
                    updated_at=item.get("updated_at", ""),
                    body_hash=new_hash,
                    synced_at=datetime.utcnow(),
                )
            )
            created += 1
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
                db.add(
                    ChangeDetection(
                        article_id=article.id,
                        prev_hash=article.body_hash,
                        new_hash=new_hash,
                        prev_body=article.body,
                        diff_summary=_diff_summary(article.body, body),
                    )
                )
                new_detections += 1
            article.body = body
            article.body_hash = new_hash
            article.updated_at = item.get("updated_at", "")
            updated += 1

        article.title = item["title"]
        article.section = item.get("section", "")
        article.synced_at = datetime.utcnow()

    db.commit()
    return {
        "synced": len(remote),
        "created": created,
        "updated": updated,
        "new_detections": new_detections,
    }
