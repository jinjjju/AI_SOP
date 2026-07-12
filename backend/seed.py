"""DB 초기화 + 시드.

사용법:
  python seed.py                    # 테이블 생성 + 아티클 동기화 + 기본 프롬프트/설정 + 샘플 SOP
  python seed.py --simulate-change  # 아티클 변경 시뮬레이션(overrides.json 생성) → 어드민에서 '동기화' 실행 시 감지됨
  python seed.py --simulate-new     # 신규 아티클 시뮬레이션 → 동기화 시 '신규 후보' 감지 + 자동 분류
  python seed.py --reset-changes    # 변경/신규 시뮬레이션 원복
  python seed.py --reset            # DB 파일 삭제 후 처음부터 다시 시드
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.database import Base, SessionLocal, engine, migrate
from app.models import (
    AiSop,
    AppSettings,
    Article,
    GoldenQuestion,
    InquiryType,
    ModelPrice,
    PromptTemplate,
    SopVersion,
)

# 기본 단가 (USD / 100만 토큰) — https://ai.google.dev/gemini-api/docs/pricing 기준 (2026-07 확인)
# gemini-3.5-flash-pro는 가격 페이지에 미게재라 3.1-pro-preview 단가를 임시 적용 → 어드민에서 수정
DEFAULT_PRICES = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-pro": (2.00, 12.00),
}
from app.services.detector import sync_articles
from app.services.filters import DEFAULT_FILTERS, FILTERS_FILE, save_filters
from app.services.zendesk import OVERRIDES_FILE

GENERATE_SYSTEM = """너는 고객센터 AI 챗봇용 SOP(응대 표준 절차)를 작성하는 전문가다.
상담사용 헬프센터 아티클을 근거로, AI 챗봇이 고객 문의에 자동 응대할 때 따라야 할 SOP를 작성한다.

작성 원칙 (할루시네이션 방지 — 반드시 지킬 것):
- 반드시 제공된 참조 아티클에 명시된 정책만 근거로 한다. 일반 상식이나 타사 정책으로 보충하지 않는다.
- 모든 정책 문장(조건·기간·금액·절차) 끝에 근거를 표기한다: [근거: Zendesk #아티클ID]
- 아티클에 없는 정보가 필요한 자리는 지어내지 말고 정확히 이렇게 표시한다: ⚠️ 아티클에 근거 없음 — 담당자 확인 필요
- 챗봇이 판단해야 할 조건 분기를 명확히 한다 (조건 → 안내 내용).
- 챗봇이 처리할 수 없는 경우(정책 예외, 불만 고조 등)의 상담사 에스컬레이션 기준을 반드시 포함한다.
- 고객에게 보낼 안내 문구 예시를 포함한다."""

GENERATE_USER = """아래 타겟 문의 스코프에 대한 AI 챗봇용 SOP를 마크다운으로 작성하라.

[타겟 문의 스코프]
{scope}

[참조 아티클]
{articles}

출력 형식:
# AI SOP: (제목)
## 1. 적용 대상 문의
## 2. 챗봇 응대 절차 (조건 분기 포함)
## 3. 안내 문구 예시
## 4. 상담사 에스컬레이션 기준
## 5. 금지 사항"""

REVISE_SYSTEM = """너는 고객센터 AI 챗봇용 SOP를 유지보수하는 전문가다.
근거가 되는 헬프센터 아티클이 변경되었을 때, 기존 AI SOP에서 수정이 필요한 부분만 반영해 개정안을 작성한다.

작성 원칙 (할루시네이션 방지 — 반드시 지킬 것):
- 기존 SOP의 구조와 문체를 유지하고, 변경된 정책과 충돌하는 부분만 수정한다.
- 변경과 무관한 내용은 그대로 둔다.
- 수정하는 문장에는 근거를 표기한다: [근거: Zendesk #아티클ID]
- 아티클에서 확인되지 않는 내용은 지어내지 말고 이렇게 표시한다: ⚠️ 아티클에 근거 없음 — 담당자 확인 필요
- 문서 맨 위에 '> [개정 요약] 어느 섹션의 무엇을 왜 바꿨는지' 인용구로 1~3줄 요약한다."""

REVISE_USER = """아래 기존 AI SOP를, 변경된 참조 아티클 내용에 맞게 개정하라.

[타겟 문의 스코프]
{scope}

[기존 AI SOP]
{current_sop}

[변경된 참조 아티클 및 diff]
{articles}

개정된 SOP 전문을 마크다운으로 출력하라."""

TRIAGE_SYSTEM = """너는 고객센터 AI 챗봇용 SOP 관리 시스템의 심사관이다.
담당자가 입력한 헬프센터 아티클이 특정 문의유형의 AI SOP 재료로 적합한지 정밀하게 판정한다.

판정 원칙:
- 아티클 내용이 문의유형의 조건과 실제로 일치하는지 근거를 들어 확인한다.
- 이 유형의 기존 SOP가 있고 아티클이 그 내용과 겹치면 '보완(revise)', 겹치는 SOP가 없으면 '신규(create)'.
- 반드시 JSON 하나만 출력한다. 다른 텍스트를 붙이지 않는다."""

TRIAGE_USER = """[판단 요청]
아래 아티클이 문의유형 "{inquiry_type}"의 AI SOP로 적합한지 판정하라.

[문의유형 조건]
{condition}

[검수 대상 아티클]
{articles}

[이 유형의 기존 AI SOP 목록]
{existing_sops}

출력 형식 (JSON만):
{"suitable": true/false, "reason": "판정 근거 1~3문장", "action": "revise" 또는 "create" 또는 "none"}
- suitable=false이면 action은 "none"
- suitable=true이고 기존 SOP와 내용이 겹치면 "revise", 겹치는 SOP가 없으면 "create\""""

AUTO_TRIAGE_SYSTEM = """너는 고객센터 AI SOP 관리 시스템의 자동 분류기다.
동기화에서 새로 발견된 헬프센터 아티클이 등록된 문의유형 중 어디에 속하는지,
그 유형의 기존 AI SOP를 보완해야 하는지 / 신규 SOP가 필요한지 / 무관한지 판정한다.

판정 원칙:
- 각 문의유형의 '조건' 설명과 아티클 내용을 실제로 대조해 근거를 들어 판정한다.
- 확신이 없으면 suitable=false로 보수적으로 판정한다 (실행은 담당자가 결정한다).
- 반드시 JSON 하나만 출력한다."""

AUTO_TRIAGE_USER = """[자동 분류 요청]
신규 수집된 아래 아티클을 문의유형 목록과 대조해 분류하라.

[문의유형 목록]
{inquiry_types}

[신규 아티클]
{articles}

출력 형식 (JSON만):
{"suitable": true/false, "inquiry_type_id": 숫자 또는 null, "action": "revise" 또는 "create" 또는 "none", "reason": "판정 근거 1~3문장"}
- 해당 유형에 기존 SOP가 있고 이 아티클이 그 내용과 겹치면 "revise", SOP가 없으면 "create"
- 어떤 유형과도 무관하면 suitable=false, action="none\""""

VERIFY_SYSTEM = """너는 고객센터 AI SOP의 사실 검증관이다.
생성된 SOP의 정책적 주장(조건·기간·금액·절차)이 참조 아티클에 실제로 명시되어 있는지 문장 단위로 대조한다.

검증 원칙:
- 아티클에 명시된 내용과 일치하는 문장은 통과시킨다.
- 아티클에서 근거를 찾을 수 없는 정책 문장만 warnings에 담는다 (원문 그대로 인용).
- 일반적인 응대 표현(인사, 접수 안내, 에스컬레이션 권고)은 검증 대상이 아니다.
- 반드시 JSON 하나만 출력한다."""

VERIFY_USER = """[검증 요청]
아래 SOP의 모든 정책적 주장이 참조 아티클에 실제로 있는 내용인지 대조하고, 근거 없는 문장을 전부 지목하라.

[검증 대상 SOP]
{sop}

[참조 아티클]
{articles}

출력 형식 (JSON만):
{"warnings": [{"quote": "근거를 찾을 수 없는 문장 원문", "reason": "왜 근거 불명인지 1문장"}], "summary": "전체 판정 1~2문장"}"""

GOLDEN_SYSTEM = """너는 고객센터 AI 챗봇의 품질 평가관이다.
주어진 SOP만 근거로 각 골든 질문에 챗봇이 답한다고 가정하고,
'반드시 포함할 포인트'가 답변에 포함될 수 있는지(SOP에 근거가 있는지) 판정한다.
반드시 JSON 하나만 출력한다."""

GOLDEN_USER = """[골든 테스트]
아래 SOP를 근거로 각 골든 질문에 대한 답변이 기대 포인트를 충족하는지 판정하라.

[SOP]
{sop}

[골든 질문]
{questions}

출력 형식 (JSON만):
{"results": [{"question": "질문 원문", "passed": true/false, "missing": ["SOP에서 근거를 찾을 수 없는 포인트"], "note": "짧은 설명"}]}"""

TRANSLATE_SYSTEM = """You are a professional Korean→English translator specialized in customer-service SOP documents.
Translate faithfully — never add, remove, or reinterpret policy content."""

TRANSLATE_USER = """[번역 요청]
아래 한국어 AI SOP를 영어로 번역하라.
- 마크다운 구조(헤딩 레벨, 목록, 인용구)와 근거 표기([근거: Zendesk #ID] → [Source: Zendesk #ID])를 유지한다.
- 고객 안내 문구 예시는 자연스러운 영어 CS 표현으로 옮긴다.
- ⚠️ 표시된 '근거 없음' 플레이스홀더는 "⚠️ Not found in source articles — needs manager confirmation"으로 옮긴다.
- 번역문만 출력한다.

[번역 대상 SOP]
{sop}"""

# 문의유형 시드: (이름, 조건, 관련 아티클 zendesk_id 목록)
INQUIRY_TYPES = [
    ("반품", "고객이 상품 반품 절차·기간·배송비·환불을 문의하는 경우", [90003, 90004, 90010]),
    ("교환", "상품 옵션 교환, 재배송, 오배송 교환을 문의하는 경우", [90005, 90010]),
    ("무응답", "챗봇이 답변 근거를 찾지 못한 문의 (상담사 연결 안내 대상)", []),
]

# 변경 감지 데모용 샘플 SOP (반품 관련 아티클 참조)
SAMPLE_SOP_CONTENT = """# AI SOP: 반품 신청 및 배송비 안내

## 1. 적용 대상 문의
반품 신청 방법, 반품 가능 기간, 반품 배송비를 묻는 고객 문의

## 2. 챗봇 응대 절차 (조건 분기 포함)
1. 주문번호를 확인하고 배송완료일을 조회한다.
2. 배송완료일로부터 30일 이내인지 확인한다.
   - 30일 초과 → 반품 불가 안내 후 상담사 연결 제안
3. 반품 사유를 확인한다.
   - 단순변심 → 반품 배송비 5,000원 고객 부담 안내
   - 상품하자/오배송 → 배송비 판매자 부담 안내
4. 신선식품·개봉한 위생용품 여부를 확인하고 해당 시 단순변심 반품 불가를 안내한다.
5. 마이페이지 > 주문목록 > 반품 신청 경로를 안내한다.

## 3. 안내 문구 예시
- "반품 신청을 도와드릴게요. 주문번호를 알려주시겠어요?"
- "단순변심 반품은 배송비 5,000원이 발생합니다. 진행할까요?"

## 4. 상담사 에스컬레이션 기준
- 반품 기간(30일) 초과 후 예외 요청
- 반품 배송비 면제 요구
- 판매자와 분쟁 중인 건

## 5. 금지 사항
- 아티클에 없는 배송비 면제를 임의로 약속하지 않는다.
"""


# purpose별 기본 프롬프트 — 없는 purpose만 추가되므로 기존 DB에 재실행해도 안전
DEFAULT_TEMPLATES = {
    "generate": ("기본 SOP 생성 프롬프트", GENERATE_SYSTEM, GENERATE_USER),
    "revise": ("기본 SOP 보완 프롬프트", REVISE_SYSTEM, REVISE_USER),
    "triage": ("기본 링크 검수(판단) 프롬프트", TRIAGE_SYSTEM, TRIAGE_USER),
    "auto_triage": ("기본 신규 아티클 자동 분류 프롬프트", AUTO_TRIAGE_SYSTEM, AUTO_TRIAGE_USER),
    "verify": ("기본 근거 검증 프롬프트", VERIFY_SYSTEM, VERIFY_USER),
    "golden_test": ("기본 골든 질문 테스트 프롬프트", GOLDEN_SYSTEM, GOLDEN_USER),
    "translate": ("기본 영문 번역 프롬프트", TRANSLATE_SYSTEM, TRANSLATE_USER),
}

# 샘플 SOP의 골든 질문 (보완 초안 생성 시 자동 회귀 테스트 데모용)
SAMPLE_GOLDEN_QUESTIONS = [
    ("단순변심으로 반품하고 싶은데 배송비가 드나요?", "5,000원\n고객 부담"),
    ("배송 받은 지 40일 지났는데 반품 가능한가요?", "30일\n상담사"),
]


def seed():
    migrate()
    if not FILTERS_FILE.exists():
        save_filters(DEFAULT_FILTERS)
        print(f"수집 필터 기본값 생성: {FILTERS_FILE.name}")
    db = SessionLocal()
    try:
        templates = {}
        added = []
        for purpose, (name, system, user) in DEFAULT_TEMPLATES.items():
            existing = db.query(PromptTemplate).filter(PromptTemplate.purpose == purpose).first()
            if existing is None:
                existing = PromptTemplate(
                    name=name, purpose=purpose, system_prompt=system, user_prompt_template=user
                )
                db.add(existing)
                added.append(purpose)
            templates[purpose] = existing
        db.commit()  # 동기화(별도 세션의 호출 카운터)가 락에 걸리지 않도록 먼저 커밋
        if added:
            print(f"기본 프롬프트 템플릿 추가: {', '.join(added)}")

        if db.get(AppSettings, 1) is None:
            db.add(
                AppSettings(
                    id=1,
                    default_model=config.AVAILABLE_MODELS[-1],  # 생성·검증은 상위 모델
                    light_model=config.AVAILABLE_MODELS[0],  # 판정·시뮬레이션은 경량 모델
                    default_generate_template_id=templates["generate"].id,
                    default_revise_template_id=templates["revise"].id,
                )
            )
            db.commit()
            print("앱 설정 생성 (호출 상한 100/일, 자동 초안 on)")

        result = sync_articles(db)
        print(f"아티클 동기화: {result}")

        if db.query(InquiryType).count() == 0:
            for name, condition, zendesk_ids in INQUIRY_TYPES:
                linked = db.query(Article).filter(Article.zendesk_id.in_(zendesk_ids)).all()
                db.add(InquiryType(name=name, condition=condition, articles=linked))
            db.flush()  # 아래 샘플 SOP가 문의유형을 조회할 수 있도록 (autoflush=False)
            print(f"문의유형 {len(INQUIRY_TYPES)}종 시드 (반품/교환/무응답)")

        if db.query(ModelPrice).count() == 0:
            for model in config.AVAILABLE_MODELS:
                inp, out = DEFAULT_PRICES.get(model, (0.0, 0.0))
                db.add(ModelPrice(model=model, input_per_1m=inp, output_per_1m=out))
            print(f"모델 단가 시드: {DEFAULT_PRICES}")

        # 담당자는 시드하지 않는다 — 첫 접속 시 닉네임/팀명으로 직접 가입

        if db.query(AiSop).count() == 0:
            ref = (
                db.query(Article)
                .filter(Article.zendesk_id.in_([90003, 90004, 90010]))
                .all()
            )
            return_type = db.query(InquiryType).filter(InquiryType.name == "반품").first()
            sop = AiSop(
                title="반품 신청 및 배송비 안내",
                target_scope="반품 신청 방법, 반품 가능 기간, 반품 배송비 문의",
                content=SAMPLE_SOP_CONTENT,
                status="published",
                current_version=1,
                created_by="",
                inquiry_type_id=return_type.id if return_type else None,
                articles=ref,
            )
            db.add(sop)
            db.flush()
            db.add(
                SopVersion(
                    sop_id=sop.id, version=1, content=SAMPLE_SOP_CONTENT, source="new", status="applied"
                )
            )
            for question, points in SAMPLE_GOLDEN_QUESTIONS:
                db.add(GoldenQuestion(sop_id=sop.id, question=question, expected_points=points))
            print("샘플 SOP 1건 생성 (published, 반품 아티클 참조 + 골든 질문 2건 → 변경 감지 데모용)")

        db.commit()
        print("시드 완료.")
    finally:
        db.close()


def simulate_change():
    """반품 정책 아티클(90003)이 수정된 상황을 만든다. 이후 어드민에서 동기화하면 감지됨."""
    articles = json.loads((config.SEED_DATA_DIR / "articles.json").read_text(encoding="utf-8"))
    target = next(a for a in articles if a["zendesk_id"] == 90003)
    target["body"] = target["body"].replace("고객 부담 (5,000원)", "고객 부담 (6,000원, 2026-07 개정)").replace(
        "배송완료일로부터 30일 이내", "배송완료일로부터 14일 이내 (2026-07 개정)"
    )
    target["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OVERRIDES_FILE.write_text(json.dumps([target], ensure_ascii=False, indent=2), encoding="utf-8")
    print("변경 시뮬레이션 생성: '반품 신청 절차' 아티클의 반품 기간 30일→14일, 배송비 5,000→6,000원")
    print("어드민 대시보드에서 [Zendesk 동기화]를 실행하면 감지됩니다.")


def simulate_new():
    """수집 필터를 통과하는 신규 아티클이 Zendesk에 생긴 상황을 만든다.
    이후 어드민에서 동기화하면 '신규 아티클 후보'로 감지되고 자동 분류가 실행된다."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_article = {
        "zendesk_id": 90099,
        "title": "반품 파손 상품 사진 등록 절차 안내",
        "body": (
            "<h2>파손 상품 반품 시 사진 등록</h2>"
            "<p>2026-07 신설: 파손·불량 사유 반품은 신청 시 상품 사진 1장 이상을 등록해야 합니다.</p>"
            "<p>사진 미등록 건은 판매자 확인 후 처리되어 영업일 기준 2일이 추가 소요됩니다.</p>"
            "<p>사진 등록 경로: 마이페이지 &gt; 주문목록 &gt; 반품 신청 &gt; 사진 첨부</p>"
        ),
        "section": "반품/환불",
        "updated_at": now,
    }
    existing = (
        json.loads(OVERRIDES_FILE.read_text(encoding="utf-8")) if OVERRIDES_FILE.exists() else []
    )
    existing = [a for a in existing if a["zendesk_id"] != new_article["zendesk_id"]] + [new_article]
    OVERRIDES_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print("신규 아티클 시뮬레이션 생성: '반품 파손 상품 사진 등록 절차 안내' (zendesk_id 90099)")
    print("어드민 대시보드에서 [Zendesk 동기화]를 실행하면 신규 후보로 감지 + 자동 분류됩니다.")


def reset_changes():
    if OVERRIDES_FILE.exists():
        OVERRIDES_FILE.unlink()
        print("변경 시뮬레이션 원복 완료.")
    else:
        print("원복할 변경 시뮬레이션이 없습니다.")


if __name__ == "__main__":
    if "--simulate-change" in sys.argv:
        simulate_change()
    elif "--simulate-new" in sys.argv:
        simulate_new()
    elif "--reset-changes" in sys.argv:
        reset_changes()
    else:
        if "--reset" in sys.argv:
            db_file = Path(config.DATABASE_URL.replace("sqlite:///", ""))
            if db_file.exists():
                db_file.unlink()
                print(f"DB 삭제: {db_file}")
            reset_changes()
        seed()
