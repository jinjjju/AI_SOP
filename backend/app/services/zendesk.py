"""Zendesk Help Center 아티클 소스.

로컬 개발은 MockZendeskClient(seed_data JSON), PC에서는 .env에
ZENDESK_SUBDOMAIN / ZENDESK_EMAIL / ZENDESK_API_TOKEN 설정 후 USE_MOCK=false.
"""
import json
from typing import Protocol

import httpx

from .. import config

OVERRIDES_FILE = config.SEED_DATA_DIR / "overrides.json"


class ZendeskClient(Protocol):
    def list_articles(self) -> list[dict]:
        """[{zendesk_id, title, body, section, updated_at}, ...]"""
        ...


class MockZendeskClient:
    """seed_data/articles.json 기반. overrides.json이 있으면 해당 아티클을
    덮어써서 '아티클이 업데이트된 상황'을 시뮬레이션한다 (seed.py --simulate-change)."""

    def list_articles(self) -> list[dict]:
        articles = json.loads((config.SEED_DATA_DIR / "articles.json").read_text(encoding="utf-8"))
        if OVERRIDES_FILE.exists():
            overrides = {
                a["zendesk_id"]: a
                for a in json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
            }
            articles = [overrides.get(a["zendesk_id"], a) for a in articles]
        return articles


class RealZendeskClient:
    def list_articles(self) -> list[dict]:
        base = f"https://{config.ZENDESK_SUBDOMAIN}.zendesk.com"
        url = f"{base}/api/v2/help_center/{config.ZENDESK_LOCALE}/articles.json?per_page=100"
        auth = (f"{config.ZENDESK_EMAIL}/token", config.ZENDESK_API_TOKEN)
        sections: dict[int, str] = {}
        articles: list[dict] = []
        with httpx.Client(auth=auth, timeout=30) as client:
            # 섹션명 매핑
            sec_url = f"{base}/api/v2/help_center/{config.ZENDESK_LOCALE}/sections.json?per_page=100"
            while sec_url:
                data = client.get(sec_url).raise_for_status().json()
                for s in data.get("sections", []):
                    sections[s["id"]] = s["name"]
                sec_url = data.get("next_page")
            while url:
                data = client.get(url).raise_for_status().json()
                for a in data.get("articles", []):
                    articles.append(
                        {
                            "zendesk_id": a["id"],
                            "title": a["title"],
                            "body": a.get("body") or "",
                            "section": sections.get(a.get("section_id"), ""),
                            "updated_at": a.get("updated_at", ""),
                        }
                    )
                url = data.get("next_page")
        return articles


def get_zendesk_client() -> ZendeskClient:
    if config.USE_MOCK:
        return MockZendeskClient()
    return RealZendeskClient()
