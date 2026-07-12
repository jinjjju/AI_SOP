"""Zendesk Help Center 아티클 소스.

로컬 개발은 MockZendeskClient(seed_data JSON), PC에서는 .env에
ZENDESK_SUBDOMAIN / ZENDESK_EMAIL / ZENDESK_API_TOKEN 설정 후 USE_MOCK=false.

모든 HTTP 요청(mock 포함)은 일별 카운터를 거치며, 설정의
zendesk_daily_call_limit(자체 안전 상한)에 도달하면 ZendeskBudgetExceeded를 던진다.
"""
import calendar
import json
from datetime import datetime
from typing import Optional, Protocol

import httpx

from .. import config

OVERRIDES_FILE = config.SEED_DATA_DIR / "overrides.json"


class ZendeskBudgetExceeded(Exception):
    """자체 일일 호출 상한(zendesk_daily_call_limit) 도달."""

    def __init__(self, calls: int, limit: int):
        self.calls = calls
        self.limit = limit
        super().__init__(f"Zendesk 일일 호출 상한에 도달했습니다 ({calls}/{limit}). 설정에서 상한을 조정할 수 있습니다.")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def count_zendesk_call() -> None:
    """HTTP 요청 1건마다 호출되는 카운터. 상한 도달 시 예외로 동기화를 중단시킨다."""
    from ..database import SessionLocal
    from ..models import AppSettings, ZendeskDailyUsage

    db = SessionLocal()
    try:
        settings = db.get(AppSettings, 1)
        limit = settings.zendesk_daily_call_limit if settings else 100
        row = db.query(ZendeskDailyUsage).filter(ZendeskDailyUsage.date == _today()).first()
        if row is None:
            row = ZendeskDailyUsage(date=_today(), calls=0)
            db.add(row)
        if row.calls >= limit:
            db.commit()
            raise ZendeskBudgetExceeded(row.calls, limit)
        row.calls += 1
        db.commit()
    finally:
        db.close()


def zendesk_usage_today() -> dict:
    from ..database import SessionLocal
    from ..models import AppSettings, ZendeskDailyUsage

    db = SessionLocal()
    try:
        settings = db.get(AppSettings, 1)
        row = db.query(ZendeskDailyUsage).filter(ZendeskDailyUsage.date == _today()).first()
        return {
            "date": _today(),
            "calls": row.calls if row else 0,
            "limit": settings.zendesk_daily_call_limit if settings else 100,
        }
    finally:
        db.close()


def _iso_to_epoch(iso: str) -> int:
    """'2026-07-01T09:00:00Z'(UTC) → unix epoch. 파싱 실패 시 0 (항상 포함되도록)."""
    try:
        return calendar.timegm(datetime.strptime(iso.replace("Z", ""), "%Y-%m-%dT%H:%M:%S").timetuple())
    except (ValueError, AttributeError):
        return 0


class ZendeskClient(Protocol):
    def list_articles(self) -> list[dict]:
        """전체 아티클. [{zendesk_id, title, body, section, updated_at}, ...]"""
        ...

    def list_updated_since(self, start_time: int) -> list[dict]:
        """start_time(unix epoch) 이후 생성·수정된 아티클만 (인크리멘털 동기화용)."""
        ...

    def get_article(self, zendesk_id: int) -> Optional[dict]:
        """단건 조회 (수동 링크 검수용). 없으면 None."""
        ...


class MockZendeskClient:
    """seed_data/articles.json 기반. overrides.json이 있으면 기존 아티클을 덮어쓰고
    (seed.py --simulate-change), 새 zendesk_id는 신규 아티클로 추가한다
    (seed.py --simulate-new)."""

    def list_articles(self) -> list[dict]:
        count_zendesk_call()
        articles = json.loads((config.SEED_DATA_DIR / "articles.json").read_text(encoding="utf-8"))
        if OVERRIDES_FILE.exists():
            overrides = {
                a["zendesk_id"]: a
                for a in json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
            }
            base_ids = {a["zendesk_id"] for a in articles}
            articles = [overrides.get(a["zendesk_id"], a) for a in articles]
            articles += [a for zid, a in overrides.items() if zid not in base_ids]
        return articles

    def list_updated_since(self, start_time: int) -> list[dict]:
        return [a for a in self.list_articles() if _iso_to_epoch(a.get("updated_at", "")) >= start_time]

    def get_article(self, zendesk_id: int) -> Optional[dict]:
        for a in self.list_articles():
            if a["zendesk_id"] == zendesk_id:
                return a
        return None


class RealZendeskClient:
    def __init__(self):
        self._base = f"https://{config.ZENDESK_SUBDOMAIN}.zendesk.com"
        self._auth = (f"{config.ZENDESK_EMAIL}/token", config.ZENDESK_API_TOKEN)

    def _get(self, client: httpx.Client, url: str) -> dict:
        count_zendesk_call()
        return client.get(url).raise_for_status().json()

    def _section_names(self, client: httpx.Client) -> dict:
        sections: dict = {}
        url = f"{self._base}/api/v2/help_center/{config.ZENDESK_LOCALE}/sections.json?per_page=100"
        while url:
            data = self._get(client, url)
            for s in data.get("sections", []):
                sections[s["id"]] = s["name"]
            url = data.get("next_page")
        return sections

    @staticmethod
    def _to_item(a: dict, sections: dict) -> dict:
        return {
            "zendesk_id": a["id"],
            "title": a["title"],
            "body": a.get("body") or "",
            "section": sections.get(a.get("section_id"), ""),
            "updated_at": a.get("updated_at", ""),
        }

    def list_articles(self) -> list[dict]:
        articles: list[dict] = []
        with httpx.Client(auth=self._auth, timeout=30) as client:
            sections = self._section_names(client)
            url = f"{self._base}/api/v2/help_center/{config.ZENDESK_LOCALE}/articles.json?per_page=100"
            while url:
                data = self._get(client, url)
                articles += [self._to_item(a, sections) for a in data.get("articles", [])]
                url = data.get("next_page")
        return articles

    def list_updated_since(self, start_time: int) -> list[dict]:
        """Help Center Incremental Articles — start_time 이후 변경분만 반환하므로
        전체(4천여 건) 페이지네이션 없이 1~2회 호출로 끝난다.
        https://developer.zendesk.com/api-reference/help_center/help-center-api/articles/
        """
        raw: list[dict] = []
        with httpx.Client(auth=self._auth, timeout=30) as client:
            url = f"{self._base}/api/v2/help_center/incremental/articles.json?start_time={start_time}"
            while url:
                data = self._get(client, url)
                raw += data.get("articles", [])
                url = data.get("next_page")
            # 인크리멘털 응답은 전체 로케일을 포함하므로 대상 로케일만 남긴다
            raw = [a for a in raw if not a.get("locale") or a.get("locale") == config.ZENDESK_LOCALE]
            sections = self._section_names(client) if raw else {}
        return [self._to_item(a, sections) for a in raw]

    def get_article(self, zendesk_id: int) -> Optional[dict]:
        with httpx.Client(auth=self._auth, timeout=30) as client:
            count_zendesk_call()
            resp = client.get(f"{self._base}/api/v2/help_center/{config.ZENDESK_LOCALE}/articles/{zendesk_id}.json")
            if resp.status_code == 404:
                return None
            a = resp.raise_for_status().json().get("article", {})
        return {
            "zendesk_id": a["id"],
            "title": a["title"],
            "body": a.get("body") or "",
            "section": "",
            "updated_at": a.get("updated_at", ""),
        }


def get_zendesk_client() -> ZendeskClient:
    if config.USE_MOCK:
        return MockZendeskClient()
    return RealZendeskClient()
