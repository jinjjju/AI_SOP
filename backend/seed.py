"""DB 초기화 + 시드.

사용법:
  python seed.py                    # 테이블 생성 + 아티클 동기화 + 기본 프롬프트/설정 + 샘플 SOP
  python seed.py --simulate-change  # 아티클 변경 시뮬레이션(overrides.json 생성) → 어드민에서 '동기화' 실행 시 감지됨
  python seed.py --reset-changes    # 변경 시뮬레이션 원복
  python seed.py --reset            # DB 파일 삭제 후 처음부터 다시 시드
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.database import Base, SessionLocal, engine
from app.models import AiSop, AppSettings, Article, PromptTemplate, SopVersion
from app.services.detector import sync_articles
from app.services.zendesk import OVERRIDES_FILE

GENERATE_SYSTEM = """너는 고객센터 AI 챗봇용 SOP(응대 표준 절차)를 작성하는 전문가다.
상담사용 헬프센터 아티클을 근거로, AI 챗봇이 고객 문의에 자동 응대할 때 따라야 할 SOP를 작성한다.

작성 원칙:
- 반드시 제공된 참조 아티클에 명시된 정책만 근거로 한다. 아티클에 없는 내용은 추측하지 않는다.
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

작성 원칙:
- 기존 SOP의 구조와 문체를 유지하고, 변경된 정책과 충돌하는 부분만 수정한다.
- 변경과 무관한 내용은 그대로 둔다.
- 문서 맨 위에 '> [개정 요약] ...' 인용구로 무엇이 왜 바뀌었는지 1~3줄로 요약한다."""

REVISE_USER = """아래 기존 AI SOP를, 변경된 참조 아티클 내용에 맞게 개정하라.

[타겟 문의 스코프]
{scope}

[기존 AI SOP]
{current_sop}

[변경된 참조 아티클 및 diff]
{articles}

개정된 SOP 전문을 마크다운으로 출력하라."""

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


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = sync_articles(db)
        print(f"아티클 동기화: {result}")

        if db.query(PromptTemplate).count() == 0:
            gen = PromptTemplate(
                name="기본 SOP 생성 프롬프트",
                purpose="generate",
                system_prompt=GENERATE_SYSTEM,
                user_prompt_template=GENERATE_USER,
            )
            rev = PromptTemplate(
                name="기본 SOP 보완 프롬프트",
                purpose="revise",
                system_prompt=REVISE_SYSTEM,
                user_prompt_template=REVISE_USER,
            )
            db.add_all([gen, rev])
            db.flush()
            db.add(
                AppSettings(
                    id=1,
                    default_model=config.AVAILABLE_MODELS[0],
                    default_generate_template_id=gen.id,
                    default_revise_template_id=rev.id,
                )
            )
            print("기본 프롬프트 템플릿 2개 + 설정 생성")

        # 담당자는 시드하지 않는다 — 첫 접속 시 닉네임/팀명으로 직접 가입

        if db.query(AiSop).count() == 0:
            ref = (
                db.query(Article)
                .filter(Article.zendesk_id.in_([90003, 90004, 90010]))
                .all()
            )
            sop = AiSop(
                title="반품 신청 및 배송비 안내",
                target_scope="반품 신청 방법, 반품 가능 기간, 반품 배송비 문의",
                content=SAMPLE_SOP_CONTENT,
                status="published",
                current_version=1,
                created_by="",
                articles=ref,
            )
            db.add(sop)
            db.flush()
            db.add(
                SopVersion(
                    sop_id=sop.id, version=1, content=SAMPLE_SOP_CONTENT, source="new", status="applied"
                )
            )
            print("샘플 SOP 1건 생성 (published, 반품 아티클 참조 → 변경 감지 데모용)")

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


def reset_changes():
    if OVERRIDES_FILE.exists():
        OVERRIDES_FILE.unlink()
        print("변경 시뮬레이션 원복 완료.")
    else:
        print("원복할 변경 시뮬레이션이 없습니다.")


if __name__ == "__main__":
    if "--simulate-change" in sys.argv:
        simulate_change()
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
