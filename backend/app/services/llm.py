"""LLM 프로바이더 추상화.

로컬 개발은 MockLLMProvider, PC에서는 GEMINI_API_KEY 설정 + USE_MOCK=false.
모델 목록은 config.AVAILABLE_MODELS (gemini-3.5-flash / gemini-3.5-flash-pro).
"""
import difflib
from dataclasses import dataclass
from typing import Protocol

from .. import config


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int


def _estimate_tokens(text: str) -> int:
    """mock용 대략치: 한국어 기준 ~2.5자/토큰."""
    return max(1, int(len(text) / 2.5))


class LLMProvider(Protocol):
    def generate(self, model: str, system_prompt: str, user_prompt: str) -> LLMResult:
        ...


class MockLLMProvider:
    """실제 LLM 없이 플로우를 검증하기 위한 그럴듯한 응답 생성기."""

    def _mock_revise(self, model: str, user_prompt: str) -> str:
        """보완(개정) 요청: 기존 SOP를 유지하면서 아티클 diff의 변경 조각만 치환해
        '바뀐 부분만 수정된' 개정안을 흉내낸다."""
        current = user_prompt.split("[기존 AI SOP]")[1].split("[변경된 참조 아티클")[0].strip()
        diff_part = user_prompt.split("[변경 diff]")[-1] if "[변경 diff]" in user_prompt else ""
        dels = [l[1:].strip() for l in diff_part.splitlines() if l.startswith("-") and not l.startswith("---")]
        adds = [l[1:].strip() for l in diff_part.splitlines() if l.startswith("+") and not l.startswith("+++")]

        revised = current
        changes: list[str] = []
        for old_line, new_line in zip(dels, adds):
            ops = [
                op for op in difflib.SequenceMatcher(None, old_line, new_line).get_opcodes()
                if op[0] != "equal"
            ]
            if not ops:
                continue
            # 라인 내 변경 구간을 하나로 합쳐 old→new 조각 치환
            i1 = min(op[1] for op in ops)
            i2 = max(op[2] for op in ops)
            j1 = min(op[3] for op in ops)
            j2 = max(op[4] for op in ops)
            old_frag, new_frag = old_line[i1:i2], new_line[j1:j2]
            if len(old_frag) >= 2 and old_frag in revised:
                revised = revised.replace(old_frag, new_frag)
                changes.append(f"'{old_frag}' → '{new_frag}'")

        summary = " / ".join(changes) if changes else "참조 아티클 변경사항 검토 후 반영 필요"
        return f"> [개정 요약] {summary} — {model} (mock) 생성 초안, 담당자 검토 필요\n\n{revised}"

    def generate(self, model: str, system_prompt: str, user_prompt: str) -> LLMResult:
        text = self._generate_text(model, system_prompt, user_prompt)
        return LLMResult(
            text=text,
            input_tokens=_estimate_tokens(system_prompt + user_prompt),
            output_tokens=_estimate_tokens(text),
        )

    def _generate_text(self, model: str, system_prompt: str, user_prompt: str) -> str:
        if "[기존 AI SOP]" in user_prompt:
            return self._mock_revise(model, user_prompt)
        if "[고객 질문]" in user_prompt:
            question = user_prompt.split("[고객 질문]")[-1].strip()
            return (
                f"(mock 챗봇 응답 · {model})\n\n"
                f"고객님, 문의 주셔서 감사합니다. \"{question[:80]}\" 관련해서 안내드릴게요.\n\n"
                "1. 등록된 AI SOP의 절차에 따라 우선 주문/계정 정보를 확인합니다.\n"
                "2. SOP에 정의된 조건에 해당하면 즉시 처리하고, 예외 조건이면 상담사 연결을 안내합니다.\n\n"
                "추가로 궁금한 점이 있으시면 말씀해주세요."
            )
        scope = ""
        for line in user_prompt.splitlines():
            if line.startswith("[타겟 문의 스코프]"):
                idx = user_prompt.splitlines().index(line)
                rest = user_prompt.splitlines()[idx + 1 :]
                scope = rest[0].strip() if rest else ""
                break
        titles = [l.strip("# ").strip() for l in user_prompt.splitlines() if l.startswith("### ")]
        refs = "\n".join(f"- {t}" for t in titles) or "- (참조 아티클 없음)"
        return f"""# AI SOP: {scope or '생성 요청 건'}

> ⚠️ 이 문서는 **{model} (mock)** 이 생성한 초안입니다. 담당자 검토 후 컨펌하세요.

## 1. 적용 대상 문의
{scope or user_prompt[:200]}

## 2. 챗봇 응대 절차
1. 고객의 문의 의도를 확인하고 주문번호/계정 정보를 요청한다.
2. 아래 참조 아티클의 정책 조건을 순서대로 확인한다.
3. 조건 충족 시 처리 방법을 단계별로 안내한다.
4. 다음 경우 상담사 연결로 에스컬레이션한다:
   - 정책 예외 요청
   - 고객 불만 고조
   - SOP 범위를 벗어난 문의

## 3. 안내 문구 예시
- 접수: "네, 고객님. 해당 문의 확인을 위해 주문번호를 알려주시겠어요?"
- 처리 완료: "요청하신 건이 정상 접수되었습니다. 처리 결과는 알림으로 안내드릴게요."
- 에스컬레이션: "정확한 확인을 위해 상담사에게 연결해드리겠습니다."

## 4. 금지 사항
- 참조 아티클에 없는 정책을 임의로 안내하지 않는다.
- 보상/환불 금액을 SOP 근거 없이 약속하지 않는다.

## 5. 참조 아티클
{refs}
"""


class GeminiProvider:
    def __init__(self):
        from google import genai  # PC에서만 실제 호출 (lazy import)

        self._client = genai.Client(api_key=config.GEMINI_API_KEY)

    def generate(self, model: str, system_prompt: str, user_prompt: str) -> LLMResult:
        from google.genai import types

        resp = self._client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(system_instruction=system_prompt or None),
        )
        usage = getattr(resp, "usage_metadata", None)
        return LLMResult(
            text=resp.text or "",
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )


def get_llm_provider() -> LLMProvider:
    if config.USE_MOCK or not config.GEMINI_API_KEY:
        return MockLLMProvider()
    return GeminiProvider()
