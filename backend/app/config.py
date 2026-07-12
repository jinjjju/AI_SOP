import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_DATA_DIR = BASE_DIR / "seed_data"

# 로컬 개발은 mock, PC에서는 .env 로 실제 키 주입 후 USE_MOCK=false
USE_MOCK = os.getenv("USE_MOCK", "true").lower() != "false"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'sop_admin.db'}")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AVAILABLE_MODELS = [
    m.strip()
    for m in os.getenv("AVAILABLE_MODELS", "gemini-3.5-flash,gemini-3.5-flash-pro").split(",")
    if m.strip()
]

# Zendesk Help Center
ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN", "")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL", "")
ZENDESK_API_TOKEN = os.getenv("ZENDESK_API_TOKEN", "")
ZENDESK_LOCALE = os.getenv("ZENDESK_LOCALE", "ko")

# Slack 알림 (Incoming Webhook 또는 Workflow Builder 웹훅 URL — 비우면 알림 생략)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
# 알림 메시지에 넣을 어드민 접속 주소 (아티클/SOP 내용은 싣지 않고 건수+링크만 발송)
ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://localhost:5173")
