"""LLM 프로바이더 추상화.

로컬 개발은 MockLLMProvider, PC에서는 GEMINI_API_KEY 설정 + USE_MOCK=false.
모델 목록은 config.AVAILABLE_MODELS (gemini-3.5-flash / gemini-3.5-flash-pro).
"""
import difflib
import json
import re
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

    def _mock_verify(self, user_prompt: str) -> str:
        """근거 검증 mock: SOP의 금액/기간 수치가 참조 아티클에 없으면 경고로 지목."""
        sop_part = user_prompt.split("[검증 대상 SOP]")[-1].split("[참조 아티클]")[0]
        articles_part = user_prompt.split("[참조 아티클]")[-1]
        warnings = []
        for token in set(re.findall(r"\d[\d,]*원|\d+일", sop_part)):
            if token not in articles_part:
                line = next((l.strip() for l in sop_part.splitlines() if token in l), token)
                warnings.append({"quote": line[:150], "reason": f"(mock) '{token}' 수치가 참조 아티클에서 확인되지 않습니다."})
        return json.dumps(
            {"warnings": warnings,
             "summary": "(mock) 근거 없는 문장 없음" if not warnings else f"(mock) 근거 불명 {len(warnings)}건 지목"},
            ensure_ascii=False,
        )

    def _mock_auto_triage(self, user_prompt: str) -> str:
        """자동 분류 mock: 아티클 제목에 유형명이 포함된 첫 유형으로 매칭."""
        title = next((l.strip("# ").strip() for l in user_prompt.splitlines() if l.startswith("### ")), "")
        for line in user_prompt.splitlines():
            m = re.match(r"- \[유형 #(\d+)\] (\S+)", line.strip())
            if m and m.group(2) in title:
                has_sop = "기존 SOP: 없음" not in line
                return json.dumps(
                    {"suitable": True, "inquiry_type_id": int(m.group(1)),
                     "action": "revise" if has_sop else "create",
                     "reason": f"(mock) 제목에 '{m.group(2)}' 유형 키워드가 포함되어 조건과 일치합니다."},
                    ensure_ascii=False,
                )
        return json.dumps(
            {"suitable": False, "inquiry_type_id": None, "action": "none",
             "reason": "(mock) 어떤 문의유형 조건과도 일치하지 않습니다."},
            ensure_ascii=False,
        )

    def _mock_golden_test(self, user_prompt: str) -> str:
        """골든 테스트 mock: 기대 포인트 문자열이 SOP 본문에 있으면 통과로 판정."""
        sop_part = user_prompt.split("[SOP]")[-1].split("[골든 질문]")[0]
        results = []
        for block in user_prompt.split("[골든 질문]")[-1].split("\n\n"):
            lines = [l for l in block.strip().splitlines() if l.strip()]
            if not lines or not re.match(r"Q\d+\.", lines[0]):
                continue
            question = re.sub(r"^Q\d+\.\s*", "", lines[0])
            points = [l.strip() for l in lines[1:] if l.strip() and "[반드시 포함할 포인트]" not in l]
            missing = [p for p in points if p != "(미지정)" and p not in sop_part]
            results.append({
                "question": question,
                "passed": len(missing) == 0,
                "missing": missing,
                "note": "(mock) 포인트 포함 여부 문자열 대조",
            })
        return json.dumps({"results": results}, ensure_ascii=False)

    def _generate_text(self, model: str, system_prompt: str, user_prompt: str) -> str:
        if "[검증 요청]" in user_prompt:
            return self._mock_verify(user_prompt)
        if "[자동 분류 요청]" in user_prompt:
            return self._mock_auto_triage(user_prompt)
        if "[골든 테스트]" in user_prompt:
            return self._mock_golden_test(user_prompt)
        if "[번역 요청]" in user_prompt:
            sop = user_prompt.split("[번역 대상 SOP]")[-1].strip()
            return f"> (mock English translation — {model})\n\n{sop}"
        if "[판단 요청]" in user_prompt:
            # 수동 링크 검수: 기존 SOP 유무에 따라 보완/신규를 가르는 그럴듯한 판정 JSON
            has_existing = "(기존 SOP 없음)" not in user_prompt
            action = "revise" if has_existing else "create"
            import json as _json

            return _json.dumps(
                {
                    "suitable": True,
                    "reason": "(mock) 아티클 내용이 문의유형 조건과 일치합니다. "
                    + ("기존 SOP가 있어 보완을 권장합니다." if has_existing else "해당 유형의 SOP가 없어 신규 생성을 권장합니다."),
                    "action": action,
                },
                ensure_ascii=False,
            )
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
            # temperature 0: SOP는 창의성보다 재현성·정확성 — 할루시네이션 억제의 기본값
            config=types.GenerateContentConfig(
                system_instruction=system_prompt or None, temperature=0.0
            ),
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
