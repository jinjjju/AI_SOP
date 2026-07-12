"""AI SOP 생성 파이프라인.

- 신규 생성: 스코프 → 관련 아티클 자동 검색 → 기본(generate) 프롬프트 + 기본 모델로 생성
- 보완 초안: 변경 감지 건 → 기본(revise) 프롬프트로 기존 SOP 보완 → pending_review 버전
담당자는 스코프만 입력하면 되고, 모델/프롬프트는 AppSettings의 기본값이 자동 적용된다.

품질 파이프라인:
- 생성/보완 직후 근거 검증 패스(verify)가 근거 없는 문장을 지목해 버전에 저장
- 보완 초안은 SOP의 골든 질문 자동 회귀 테스트(golden_test)까지 수행
- 판정류(triage/auto_triage)는 light_model로 2~3회 투표해 일치 여부를 함께 반환
- 내용이 확정/수정될 때마다 영문본(content_en)을 자동 번역 (개발팀 전달용)
"""
import json
import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    AiSop,
    AppSettings,
    Article,
    ChangeDetection,
    InquiryType,
    LlmUsage,
    PromptTemplate,
    SopVersion,
)
from collections import Counter
from .audit import log
from .llm import get_llm_provider

MAX_SEARCH_RESULTS = 8
ARTICLE_BODY_LIMIT = 4000  # 프롬프트에 넣을 아티클 본문 길이 제한


def get_settings(db: Session) -> AppSettings:
    settings = db.get(AppSettings, 1)
    if settings is None:
        raise HTTPException(500, "app_settings가 없습니다. seed.py를 먼저 실행하세요.")
    return settings


def _get_template(db: Session, template_id: Optional[int], purpose: str) -> PromptTemplate:
    template = db.get(PromptTemplate, template_id) if template_id else None
    if template is None:
        template = db.query(PromptTemplate).filter(PromptTemplate.purpose == purpose).first()
    if template is None:
        raise HTTPException(500, f"'{purpose}' 프롬프트 템플릿이 없습니다. 설정을 확인하세요.")
    return template


def _call_llm(
    db: Session,
    actor: str,
    purpose: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    sop_id: Optional[int] = None,
) -> str:
    """LLM 호출 + 토큰 사용량 기록 (커밋은 호출부 트랜잭션에 묶임)."""
    result = get_llm_provider().generate(model, system_prompt, user_prompt)
    db.add(
        LlmUsage(
            actor=actor,
            purpose=purpose,
            model=model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            sop_id=sop_id,
        )
    )
    return result.text


def next_version(db: Session, sop_id: int) -> int:
    """거절된 버전 포함 전체 이력 기준으로 다음 버전 번호를 채번 (중복 방지)."""
    latest = db.query(func.max(SopVersion.version)).filter(SopVersion.sop_id == sop_id).scalar()
    return (latest or 0) + 1


def search_articles(db: Session, scope: str, limit: int = MAX_SEARCH_RESULTS) -> list[Article]:
    """스코프 키워드 매칭 점수 기반의 단순 검색 (MVP). 제목 매칭에 가중치."""
    tokens = [t for t in re.split(r"[\s,./·]+", scope) if len(t) >= 2]
    if not tokens:
        return []
    scored: list[tuple[int, Article]] = []
    for article in db.query(Article).all():
        score = 0
        for token in tokens:
            if token in article.title:
                score += 3
            score += min(article.body.count(token), 5)
        if score > 0:
            scored.append((score, article))
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:limit]]


def _format_articles(articles: list[Article]) -> str:
    blocks = []
    for a in articles:
        body = a.body[:ARTICLE_BODY_LIMIT]
        blocks.append(f"### {a.title}\n(섹션: {a.section} / Zendesk ID: {a.zendesk_id})\n\n{body}")
    return "\n\n---\n\n".join(blocks) or "(참조 아티클 없음)"


def _fill(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:200]
    return fallback[:200]


def _parse_json(raw: str) -> Optional[dict]:
    try:
        return json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def verify_grounding(
    db: Session, content: str, articles: list[Article], actor: str = "", sop_id: Optional[int] = None
) -> dict:
    """근거 검증 패스 — 생성된 SOP의 문장 하나하나가 참조 아티클에 실제로 있는지
    별도 LLM 호출로 대조하고, 근거 없는 문장을 지목한다.
    담당자는 전체를 정독하는 대신 warnings에 지목된 문장만 확인하면 된다."""
    settings = get_settings(db)
    try:
        template = _get_template(db, None, "verify")
    except HTTPException:
        return {"checked": False, "warnings": [], "summary": "검증(verify) 프롬프트 템플릿이 없습니다."}

    user_prompt = _fill(template.user_prompt_template, sop=content, articles=_format_articles(articles))

    # 2회 실행 후 경고를 합집합으로 병합 — 검증은 '놓치는 것'이 최악이므로 재현율을 우선한다
    # (한 번이라도 지목된 문장은 전부 표면화, 판단은 담당자가 한다)
    merged: dict = {}
    summaries: list[str] = []
    checked = False
    for _ in range(2):
        try:
            raw = _call_llm(db, actor, "verify", settings.default_model, template.system_prompt, user_prompt, sop_id)
        except Exception as e:  # 검증 실패가 생성 자체를 막지 않도록
            summaries.append(f"검증 호출 실패: {e}")
            continue
        parsed = _parse_json(raw)
        if parsed is None:
            summaries.append(f"검증 응답 파싱 실패 — 원문: {raw[:200]}")
            continue
        checked = True
        for w in parsed.get("warnings", []):
            if isinstance(w, dict) and w.get("quote"):
                merged.setdefault(str(w["quote"]).strip(), str(w.get("reason", "")))
        if parsed.get("summary"):
            summaries.append(str(parsed["summary"]))

    warnings = [{"quote": q, "reason": r} for q, r in merged.items()]
    return {
        "checked": checked,
        "warnings": warnings,
        "warning_count": len(warnings),
        "summary": " / ".join(dict.fromkeys(summaries)),
    }


def run_golden_test(db: Session, sop: AiSop, content: str, actor: str = "") -> dict:
    """SOP의 골든 질문 세트를 초안 내용에 대해 자동 실행하는 회귀 테스트.
    보완으로 다른 답변이 의도치 않게 망가지지 않았는지 사람이 안 읽고도 확인하는 장치."""
    questions = sop.golden_questions
    if not questions:
        return {"ran": False, "results": [], "note": "등록된 골든 질문이 없습니다."}
    settings = get_settings(db)
    try:
        template = _get_template(db, None, "golden_test")
    except HTTPException:
        return {"ran": False, "results": [], "note": "골든 테스트 프롬프트 템플릿이 없습니다."}

    q_block = "\n\n".join(
        f"Q{i}. {q.question}\n[반드시 포함할 포인트]\n{q.expected_points or '(미지정)'}"
        for i, q in enumerate(questions, 1)
    )
    user_prompt = _fill(template.user_prompt_template, sop=content, questions=q_block)
    try:
        raw = _call_llm(db, actor, "golden_test", settings.light_model, template.system_prompt, user_prompt, sop.id)
    except Exception as e:
        return {"ran": False, "results": [], "note": f"골든 테스트 호출 실패: {e}"}

    parsed = _parse_json(raw)
    results = parsed.get("results", []) if parsed else []
    if not isinstance(results, list):
        results = []
    passed = sum(1 for r in results if isinstance(r, dict) and r.get("passed"))
    return {"ran": True, "results": results, "passed": passed, "failed": len(results) - passed}


def refresh_translation(db: Session, sop: AiSop, actor: str = "") -> bool:
    """SOP 내용이 확정/수정될 때 영문본(content_en)을 자동 갱신.
    챗봇 반영 개발자가 외국인이라 발행본은 영문본과 함께 전달된다.
    실패해도 승인/저장 플로우를 막지 않는다 (False 반환)."""
    settings = get_settings(db)
    try:
        template = _get_template(db, None, "translate")
        sop.content_en = _call_llm(
            db, actor, "translate", settings.default_model, template.system_prompt,
            _fill(template.user_prompt_template, sop=sop.content), sop.id,
        )
        return True
    except Exception:
        return False


def generate_new_sop(
    db: Session,
    scope: str,
    article_ids: Optional[list[int]] = None,
    actor: str = "",
    inquiry_type_id: Optional[int] = None,
) -> AiSop:
    settings = get_settings(db)
    template = _get_template(db, settings.default_generate_template_id, "generate")

    if article_ids:
        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
    else:
        articles = search_articles(db, scope)
        # 문의유형이 지정되면 유형에 등록된 관련 아티클을 우선 포함
        if inquiry_type_id:
            itype = db.get(InquiryType, inquiry_type_id)
            if itype:
                merged = {a.id: a for a in itype.articles}
                for a in articles:
                    merged.setdefault(a.id, a)
                articles = list(merged.values())[:MAX_SEARCH_RESULTS]

    user_prompt = _fill(
        template.user_prompt_template,
        scope=scope,
        articles=_format_articles(articles),
    )
    content = _call_llm(db, actor, "generate", settings.default_model, template.system_prompt, user_prompt)
    verification = verify_grounding(db, content, articles, actor)

    sop = AiSop(
        title=_extract_title(content, scope),
        target_scope=scope,
        content=content,
        status="draft",
        current_version=1,
        created_by=actor,
        inquiry_type_id=inquiry_type_id,
        articles=articles,
    )
    db.add(sop)
    db.flush()
    refresh_translation(db, sop, actor)
    db.add(
        SopVersion(
            sop_id=sop.id,
            version=1,
            content=content,
            verification_json=json.dumps(verification, ensure_ascii=False),
            source="new",
            model_used=settings.default_model,
            created_by=actor,
            template_id=template.id,
            status="applied",
        )
    )
    log(db, actor, "sop_created", "sop", sop.id, f"'{sop.title}' 신규 생성 ({settings.default_model})")
    db.commit()
    db.refresh(sop)
    return sop


def regenerate_sop(db: Session, sop: AiSop, article_ids: list[int], actor: str = "") -> AiSop:
    """담당자가 참조 아티클을 조정해 다시 생성 (draft 내용을 새 버전으로 교체)."""
    settings = get_settings(db)
    template = _get_template(db, settings.default_generate_template_id, "generate")
    articles = db.query(Article).filter(Article.id.in_(article_ids)).all()

    user_prompt = _fill(
        template.user_prompt_template,
        scope=sop.target_scope,
        articles=_format_articles(articles),
    )
    content = _call_llm(
        db, actor, "regenerate", settings.default_model, template.system_prompt, user_prompt, sop.id
    )
    verification = verify_grounding(db, content, articles, actor, sop.id)

    sop.articles = articles
    sop.content = content
    sop.current_version = next_version(db, sop.id)
    refresh_translation(db, sop, actor)
    db.add(
        SopVersion(
            sop_id=sop.id,
            version=sop.current_version,
            content=content,
            verification_json=json.dumps(verification, ensure_ascii=False),
            source="new",
            model_used=settings.default_model,
            created_by=actor,
            template_id=template.id,
            status="applied",
        )
    )
    log(db, actor, "sop_regenerated", "sop", sop.id, f"'{sop.title}' 아티클 조정 후 재생성 (v{sop.current_version})")
    db.commit()
    db.refresh(sop)
    return sop


def create_revision_draft(
    db: Session, change: ChangeDetection, sop: AiSop, actor: str = ""
) -> SopVersion:
    """변경된 아티클 기준으로 기존 SOP 보완 초안을 생성해 pending_review 버전으로 저장."""
    settings = get_settings(db)
    template = _get_template(db, settings.default_revise_template_id, "revise")

    user_prompt = _fill(
        template.user_prompt_template,
        scope=sop.target_scope,
        current_sop=sop.content,
        articles=_format_articles([change.article]) + f"\n\n[변경 diff]\n{change.diff_summary}",
    )
    content = _call_llm(
        db, actor, "revise", settings.default_model, template.system_prompt, user_prompt, sop.id
    )
    # 검증은 SOP의 참조 아티클 전체(변경 아티클 포함) 기준으로 대조
    ground_articles = list({a.id: a for a in list(sop.articles) + [change.article]}.values())
    verification = verify_grounding(db, content, ground_articles, actor, sop.id)
    test_report = run_golden_test(db, sop, content, actor)

    version = SopVersion(
        sop_id=sop.id,
        version=next_version(db, sop.id),
        content=content,
        verification_json=json.dumps(verification, ensure_ascii=False),
        test_report_json=json.dumps(test_report, ensure_ascii=False),
        source="revision",
        change_detection_id=change.id,
        model_used=settings.default_model,
        created_by=actor,
        template_id=template.id,
        status="pending_review",
    )
    db.add(version)
    change.status = "draft_created"
    log(
        db, actor, "draft_created", "sop", sop.id,
        f"'{sop.title}' 보완 초안 v{version.version} 생성 (아티클 '{change.article.title}' 변경 감지 #{change.id})",
    )
    db.commit()
    db.refresh(version)
    return version


def create_manual_revision_draft(db: Session, sop: AiSop, article: Article, actor: str = "") -> SopVersion:
    """수동 링크 검수에서 넘어온 아티클 기준 보완 초안 (변경 감지 없이)."""
    settings = get_settings(db)
    template = _get_template(db, settings.default_revise_template_id, "revise")

    user_prompt = _fill(
        template.user_prompt_template,
        scope=sop.target_scope,
        current_sop=sop.content,
        articles=_format_articles([article]),
    )
    content = _call_llm(db, actor, "revise", settings.default_model, template.system_prompt, user_prompt, sop.id)
    ground_articles = list({a.id: a for a in list(sop.articles) + [article]}.values())
    verification = verify_grounding(db, content, ground_articles, actor, sop.id)
    test_report = run_golden_test(db, sop, content, actor)

    version = SopVersion(
        sop_id=sop.id,
        version=next_version(db, sop.id),
        content=content,
        verification_json=json.dumps(verification, ensure_ascii=False),
        test_report_json=json.dumps(test_report, ensure_ascii=False),
        source="revision",
        model_used=settings.default_model,
        created_by=actor,
        template_id=template.id,
        status="pending_review",
    )
    db.add(version)
    if article not in sop.articles:
        sop.articles.append(article)
    log(
        db, actor, "draft_created", "sop", sop.id,
        f"'{sop.title}' 보완 초안 v{version.version} 생성 (수동 링크 검수: '{article.title}')",
    )
    db.commit()
    db.refresh(version)
    return version


def _triage_once(db: Session, template: PromptTemplate, model: str, user_prompt: str, actor: str) -> dict:
    raw = _call_llm(db, actor, "triage", model, template.system_prompt, user_prompt)
    parsed = _parse_json(raw)
    if parsed is None:
        return {"suitable": False, "reason": f"판정 응답 파싱 실패 — 원문: {raw[:300]}", "action": "none"}
    action = parsed.get("action", "none")
    if action not in ("revise", "create", "none"):
        action = "none"
    return {"suitable": bool(parsed.get("suitable")), "reason": str(parsed.get("reason", "")), "action": action}


def triage_article(db: Session, itype: InquiryType, article: Article, actor: str = "") -> dict:
    """수동 입력 아티클이 해당 문의유형의 AI SOP로 적합한지 + 보완/신규 여부를 LLM이 판정.

    분류 문제라 다수결이 잘 통한다 — light_model로 2회 실행해 일치하면 확정,
    갈리면 3번째 호출로 다수결. confident=False면 UI에 '판정 불확실'로 표시된다."""
    template = _get_template(db, None, "triage")
    settings = get_settings(db)

    existing = db.query(AiSop).filter(AiSop.inquiry_type_id == itype.id).all()
    existing_desc = (
        "\n".join(f"- [SOP #{s.id}] {s.title} (상태: {s.status}) — 스코프: {s.target_scope}" for s in existing)
        or "(기존 SOP 없음)"
    )
    user_prompt = _fill(
        template.user_prompt_template,
        inquiry_type=itype.name,
        condition=itype.condition or "(조건 미작성)",
        articles=_format_articles([article]),
        existing_sops=existing_desc,
    )

    votes = [_triage_once(db, template, settings.light_model, user_prompt, actor) for _ in range(2)]
    if (votes[0]["action"], votes[0]["suitable"]) != (votes[1]["action"], votes[1]["suitable"]):
        votes.append(_triage_once(db, template, settings.light_model, user_prompt, actor))
    db.commit()

    tally = Counter((v["action"], v["suitable"]) for v in votes)
    (action, suitable), top_count = tally.most_common(1)[0]
    confident = top_count >= 2
    reason = next(v["reason"] for v in votes if (v["action"], v["suitable"]) == (action, suitable))
    if action == "revise" and not existing:
        action = "create"  # 보완 대상이 없으면 신규로 강등

    return {
        "suitable": suitable,
        "reason": reason,
        "action": action,
        "confident": confident,
        "votes": len(votes),
        "candidate_sops": existing if action == "revise" else [],
    }


def auto_triage(db: Session, article: Article, actor: str = "") -> dict:
    """동기화에서 발견된 신규 아티클을 전체 문의유형 조건과 대조해
    어느 유형에 속하는지 + 기존 SOP 보완/신규 생성/무관을 자동 판정 (2~3회 투표).
    실행은 담당자가 결정한다 — 결과는 변경 감지 건의 triage_json에 저장될 뿐이다."""
    types = db.query(InquiryType).order_by(InquiryType.id).all()
    if not types:
        return {"suitable": False, "action": "none", "reason": "등록된 문의유형이 없습니다.", "confident": True}

    settings = get_settings(db)
    try:
        template = _get_template(db, None, "auto_triage")
    except HTTPException:
        return {"suitable": False, "action": "none", "reason": "자동 분류(auto_triage) 프롬프트 템플릿이 없습니다.", "confident": False}

    type_desc = "\n".join(
        f"- [유형 #{t.id}] {t.name} — 조건: {t.condition or '(미작성)'} / 기존 SOP: "
        + (", ".join(f"#{s.id} {s.title}" for s in t.sops) or "없음")
        for t in types
    )
    user_prompt = _fill(template.user_prompt_template, inquiry_types=type_desc, articles=_format_articles([article]))

    def once() -> dict:
        raw = _call_llm(db, actor, "auto_triage", settings.light_model, template.system_prompt, user_prompt)
        parsed = _parse_json(raw) or {}
        action = parsed.get("action", "none")
        if action not in ("revise", "create", "none"):
            action = "none"
        try:
            type_id = int(parsed.get("inquiry_type_id") or 0)
        except (TypeError, ValueError):
            type_id = 0
        return {
            "suitable": bool(parsed.get("suitable")),
            "action": action,
            "inquiry_type_id": type_id,
            "reason": str(parsed.get("reason", "")),
        }

    votes = [once(), once()]
    key = lambda v: (v["action"], v["inquiry_type_id"])  # noqa: E731
    if key(votes[0]) != key(votes[1]):
        votes.append(once())
    db.commit()

    tally = Counter(key(v) for v in votes)
    (action, type_id), top_count = tally.most_common(1)[0]
    winner = next(v for v in votes if key(v) == (action, type_id))
    matched = db.get(InquiryType, type_id) if type_id else None
    if matched is None:
        action = "none" if action != "create" else action
    if action == "revise" and (matched is None or not matched.sops):
        action = "create"  # 보완할 SOP가 없으면 신규로 강등

    return {
        "suitable": winner["suitable"],
        "action": action,
        "inquiry_type_id": matched.id if matched else None,
        "inquiry_type_name": matched.name if matched else "",
        "reason": winner["reason"],
        "confident": top_count >= 2,
        "votes": len(votes),
        "candidate_sop_ids": [s.id for s in matched.sops] if (matched and action == "revise") else [],
    }


def test_sop(db: Session, sop: AiSop, question: str, actor: str = "") -> dict:
    """SOP를 시스템 프롬프트로 넣고 고객 질문을 시뮬레이션."""
    settings = get_settings(db)
    system_prompt = (
        "너는 고객센터 AI 챗봇이다. 아래 AI SOP에 정의된 절차와 안내 문구만 근거로 답변한다. "
        "SOP에 없는 정책은 안내하지 말고 상담사 연결을 권한다.\n\n[AI SOP]\n" + sop.content
    )
    answer = _call_llm(
        db, actor, "test", settings.light_model, system_prompt, f"[고객 질문]\n{question}", sop.id
    )
    db.commit()
    return {"question": question, "answer": answer, "model_used": settings.light_model}
