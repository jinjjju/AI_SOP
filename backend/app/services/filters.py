"""아티클 수집 필터 (article_filters.json).

기존 임시 프로세스와 동일한 포맷을 유지한다:
- in_scope_prefixes  : 제목이 이 접두어로 시작하면 무조건 수집 (최우선)
- exclusion_keywords : 제목에 포함되면 제외
- out_scope_prefixes : 제목이 이 접두어로 시작하면 제외
어드민 설정 화면에서 조회/수정 가능하며, 파일을 직접 수정해도 동일하게 동작한다.
"""
import json

from .. import config

FILTERS_FILE = config.BASE_DIR / "article_filters.json"

DEFAULT_FILTERS = {
    "in_scope_prefixes": ["반품", "교환", "환불"],
    "exclusion_keywords": ["임직원 전용"],
    "out_scope_prefixes": ["[사내]"],
}


def load_filters() -> dict:
    if FILTERS_FILE.exists():
        data = json.loads(FILTERS_FILE.read_text(encoding="utf-8"))
        return {key: list(data.get(key, [])) for key in DEFAULT_FILTERS}
    return {k: list(v) for k, v in DEFAULT_FILTERS.items()}


def save_filters(data: dict) -> dict:
    cleaned = {}
    for key in DEFAULT_FILTERS:
        seen = []
        for s in data.get(key, []):
            s = (s or "").strip()
            if s and s not in seen:  # 중복 제거 (입력 순서 유지)
                seen.append(s)
        cleaned[key] = seen
    FILTERS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def is_in_scope(title: str) -> bool:
    f = load_filters()
    if any(title.startswith(p) for p in f["in_scope_prefixes"]):
        return True
    if any(k in title for k in f["exclusion_keywords"]):
        return False
    if any(title.startswith(p) for p in f["out_scope_prefixes"]):
        return False
    return True
