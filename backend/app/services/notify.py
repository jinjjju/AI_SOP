"""Slack 알림 (Incoming Webhook / Workflow Builder 웹훅 겸용).

보안 정책상 아티클·SOP 내용은 싣지 않고 건수 + 어드민 링크만 발송한다.
SLACK_WEBHOOK_URL이 비어 있으면 조용히 생략(False 반환)하므로 동기화는 영향받지 않는다.
"""
import httpx

from .. import config


def send_sync_summary(result: dict) -> bool:
    """데일리 동기화 후 처리할 건이 있을 때 채널에 1회 발송."""
    if not config.SLACK_WEBHOOK_URL:
        return False

    parts = []
    if result.get("new_detections"):
        parts.append(f"아티클 변경 {result['new_detections']}건")
    if result.get("new_article_candidates"):
        parts.append(f"신규 아티클 후보 {result['new_article_candidates']}건")
    if result.get("drafts_created"):
        parts.append(f"보완 초안 {result['drafts_created']}건 자동 생성")
    if not parts:
        return False

    text = (
        "📋 [AI SOP 어드민] 오늘의 동기화 결과 — "
        + " · ".join(parts)
        + f"\n검토·승인: {config.ADMIN_BASE_URL}"
    )
    try:
        httpx.post(config.SLACK_WEBHOOK_URL, json={"text": text}, timeout=10).raise_for_status()
        return True
    except Exception:
        return False  # 알림 실패가 동기화를 깨뜨리지 않도록 삼킨다
