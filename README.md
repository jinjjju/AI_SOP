# AI SOP Studio (MVP)

상담사용 Zendesk SOP 아티클을 기반으로, AI 챗봇이 따라야 할 **AI SOP**를 생성·검토·발행하는 어드민 툴.

📐 [아키텍처 · 시스템 구조도](docs/ARCHITECTURE.md) · 📚 [개발자 레퍼런스 (데이터 모델·타입·API)](docs/REFERENCE.md)

- 담당자는 **타겟 문의 스코프만 입력** → 관련 아티클 자동 조회 → 기본 모델+프롬프트로 SOP 자동 생성
- 아티클이 업데이트되면 **변경 감지** → 보완 초안 생성 → 담당자 비교·승인 시 기존 SOP가 새 버전으로 갱신
- 발행된 SOP는 개발팀이 `GET /api/sops/published` API 또는 JSON 다운로드로 가져가 챗봇 프롬프트에 반영

## 실행 (로컬, mock 모드)

Python 3.9+ / Node 18+ 필요. mock 모드는 API 키 없이 동작한다.

```bash
# 백엔드 (http://localhost:8001)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # 최초 1회
.venv/bin/python seed.py                                             # 최초 1회 (샘플 데이터)
.venv/bin/uvicorn app.main:app --reload --port 8001

# 프론트엔드 (http://localhost:5173)
cd frontend
npm install        # 최초 1회
npm run dev
```

## 데모 시나리오

1. **신규 생성**: SOP 생성 → 스코프 입력(예: "배송 지연 보상 요청") → 자동 생성 → 검토·편집 → 컨펌 → 발행
2. **변경 감지**: `cd backend && .venv/bin/python seed.py --simulate-change` 실행 → 대시보드에서 [Zendesk 동기화] → 감지된 변경 클릭 → [보완 초안 생성] → 현재 SOP와 나란히 비교 → 승인 → 버전 갱신 확인
   - 원복: `.venv/bin/python seed.py --reset-changes` (전체 초기화: `--reset`)
3. **보완초안 확인**: 보완초안이 생성되면 대시보드 "검토가 필요한 보완초안" 섹션과 SOP 목록의 `검토 대기` 뱃지로 표시됨 → SOP 상세 상단에서 현재본과 비교 후 승인/거절
4. **테스트**: SOP 상세 하단 챗봇 테스트에서 고객 질문 입력
5. **개발팀 전달**: AI SOP 관리 → [발행본 JSON] 다운로드 또는 `curl localhost:8001/api/sops/published`

## 담당자(간이 가입) · 히스토리

- 첫 접속 시 **닉네임/팀명**(예: 조엘 / PA Automation)만 입력하면 담당자로 가입됨. 같은 닉네임 재입력 시 그 계정으로 이어서 사용
- **가입된 담당자만** SOP 생성·보완초안·승인·발행 등 변경 작업 가능 (미가입 요청은 403)
- 모든 작업(생성·보완초안·승인·상태변경·동기화·설정변경)이 가입한 이름으로 기록되고, **히스토리** 메뉴에서 담당자별 필터로 확인. SOP 관련 항목은 클릭 시 해당 SOP로 이동
- 검토 대기 중인 보완초안은 대시보드/목록 뱃지에 **생성 일시**가 함께 표시됨
- 가입자 목록 확인·삭제는 설정 페이지 (삭제해도 활동 이력은 보존)

## PC에서 실제 API 연결

`backend/.env.example`을 `.env`로 복사해 환경변수만 채우면 됩니다 (코드 수정 불필요):

```bash
cd backend && cp .env.example .env
# .env에서 USE_MOCK=false + GEMINI_API_KEY + ZENDESK_* 설정 후 서버 재시작
```

- Zendesk 연동: `app/services/zendesk.py` 의 `RealZendeskClient` (Help Center Articles API)
- Gemini 연동: `app/services/llm.py` 의 `GeminiProvider` (google-genai SDK)
- 모델 후보 변경: `AVAILABLE_MODELS` env (콤마 구분)

## 구조

```
backend/    FastAPI + SQLAlchemy + SQLite — routers(HTTP) / services(도메인 로직) / seed_data
frontend/   React + Vite + TypeScript — pages / components / api
docs/       ARCHITECTURE.md(구조도·플로우) / REFERENCE.md(데이터 모델·타입·API)
```

자세한 구조도와 플로우는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
테이블·타입·API 계약은 [docs/REFERENCE.md](docs/REFERENCE.md) 참고.
