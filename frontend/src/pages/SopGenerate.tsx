import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { Spinner, useToast } from "../components/ui";
import type { AppSettings, Article, InquiryType, PromptTemplate, SopDetail } from "../types";

const EXAMPLES = [
  "와우 멤버십 해지와 환불 문의",
  "배송 지연 보상 요청",
  "주문 취소와 쿠폰 복원 문의",
  "오배송 상품 재배송 요청",
];

export default function SopGenerate() {
  const [params] = useSearchParams();
  // 신규 아티클 감지 건에서 넘어온 경우 스코프/유형/참조 아티클이 미리 채워진다
  const [mode, setMode] = useState<"generate" | "import">("generate");
  const [scope, setScope] = useState(params.get("scope") ?? "");
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [types, setTypes] = useState<InquiryType[]>([]);
  const [typeId, setTypeId] = useState<number | "">(params.get("type") ? Number(params.get("type")) : "");
  const [articleId] = useState<number | null>(params.get("article") ? Number(params.get("article")) : null);
  const [articleTitle, setArticleTitle] = useState("");
  const toast = useToast();
  const nav = useNavigate();

  useEffect(() => {
    api.get<AppSettings>("/api/settings").then(setSettings).catch(() => {});
    api.get<PromptTemplate[]>("/api/prompts").then(setTemplates).catch(() => {});
    api.get<InquiryType[]>("/api/inquiry-types").then(setTypes).catch(() => {});
  }, []);

  useEffect(() => {
    if (articleId) {
      api.get<Article>(`/api/articles/${articleId}`).then((a) => setArticleTitle(a.title)).catch(() => {});
    }
  }, [articleId]);

  const templateName =
    templates.find((t) => t.id === settings?.default_generate_template_id)?.name ?? "기본 프롬프트";

  const generate = async () => {
    if (!scope.trim() || loading) return;
    setLoading(true);
    try {
      const sop = await api.post<SopDetail>("/api/sops/generate", {
        scope: scope.trim(),
        inquiry_type_id: typeId === "" ? null : typeId,
        article_ids: articleId ? [articleId] : null,
      });
      toast("AI SOP 초안이 생성되었습니다. 검토 후 컨펌하세요.");
      nav(`/sops/${sop.id}`);
    } catch (e) {
      toast((e as Error).message, true);
      setLoading(false);
    }
  };

  return (
    <div className="content-narrow">
      <div className="tab-row" style={{ justifyContent: "center", marginBottom: 18 }}>
        <button className={`tab ${mode === "generate" ? "active" : ""}`} onClick={() => setMode("generate")}>
          ✦ AI 생성
        </button>
        <button className={`tab ${mode === "import" ? "active" : ""}`} onClick={() => setMode("import")}>
          ⇪ 기존 SOP 등록
        </button>
      </div>

      {mode === "import" ? (
        <ImportForm types={types} />
      ) : (
        <>
          <div className="hero">
            <h2>어떤 문의에 대한 AI SOP가 필요한가요?</h2>
            <p>타겟 문의 스코프만 입력하면, 관련 아티클 조회부터 SOP 생성까지 자동으로 진행됩니다.</p>
          </div>

          <div className="prompt-box">
            <textarea
              placeholder="예: 와우 멤버십 해지 시 환불 가능 여부와 절차를 안내하는 문의"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate();
              }}
              autoFocus
            />
            <div className="prompt-actions">
              <div className="row" style={{ gap: 8 }}>
                <select
                  className="select"
                  style={{ width: "auto", padding: "4px 28px 4px 12px", borderRadius: 999, fontSize: 12.5 }}
                  value={typeId}
                  onChange={(e) => setTypeId(e.target.value === "" ? "" : Number(e.target.value))}
                  title="문의유형을 선택하면 유형에 등록된 관련 아티클이 우선 참조됩니다"
                >
                  <option value="">문의유형 (선택)</option>
                  {types.map((t) => (
                    <option key={t.id} value={t.id}>❖ {t.name}</option>
                  ))}
                </select>
                {articleId && (
                  <span className="chip green" title="신규 아티클 감지 건에서 지정된 참조 아티클">
                    📄 {articleTitle || `아티클 #${articleId}`}
                  </span>
                )}
                {settings && <span className="chip accent">✦ {settings.default_model}</span>}
                <span className="chip">{templateName}</span>
              </div>
              <button className="btn primary" onClick={generate} disabled={!scope.trim() || loading}>
                {loading ? (
                  <>
                    <Spinner /> 생성 중…
                  </>
                ) : (
                  "AI SOP 생성"
                )}
              </button>
            </div>
          </div>

          <div className="row wrap" style={{ marginTop: 18, justifyContent: "center" }}>
            {EXAMPLES.map((ex) => (
              <span key={ex} className="chip clickable" onClick={() => setScope(ex)}>
                {ex}
              </span>
            ))}
          </div>

          <p style={{ textAlign: "center", color: "var(--text-faint)", fontSize: 12.5, marginTop: 28 }}>
            모델과 프롬프트는 <a href="/settings" style={{ color: "var(--accent-strong)" }}>설정</a>의
            기본값이 자동 적용됩니다. 생성된 초안은 담당자 검토 · 컨펌 후에만 발행됩니다.
          </p>
        </>
      )}
    </div>
  );
}

/* 이미 만들어진 SOP 완성본 등록 — LLM 생성 없이 저장, 영문본만 자동 번역.
   관련 아티클을 연결해야 변경 감지 → 영향 SOP 역추적이 동작한다. */
function ImportForm({ types }: { types: InquiryType[] }) {
  const [title, setTitle] = useState("");
  const [scope, setScope] = useState("");
  const [content, setContent] = useState("");
  const [typeId, setTypeId] = useState<number | "">("");
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [articles, setArticles] = useState<Article[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const nav = useNavigate();

  useEffect(() => {
    api.get<Article[]>("/api/articles").then(setArticles).catch(() => {});
  }, []);

  const submit = async () => {
    if (!scope.trim() || !content.trim() || busy) return;
    setBusy(true);
    try {
      const sop = await api.post<SopDetail>("/api/sops/import", {
        title: title.trim(),
        target_scope: scope.trim(),
        content,
        inquiry_type_id: typeId === "" ? null : typeId,
        article_ids: [...selected],
        status,
      });
      toast(`'${sop.title}' 등록 완료 — 영문본이 자동 번역되었습니다.`);
      nav(`/sops/${sop.id}`);
    } catch (e) {
      toast((e as Error).message, true);
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>기존 SOP 등록</h3>
      <p className="sub" style={{ marginTop: 0 }}>
        이미 만들어둔 AI SOP를 그대로 등록합니다 (LLM 생성 없음).{" "}
        <strong>관련 아티클을 연결해야</strong> 이후 아티클 변경 감지 때 이 SOP가 영향 대상으로 잡힙니다.
      </p>
      <div className="grid-2">
        <label className="field">
          <span>제목 (비우면 본문 첫 헤딩 사용)</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="예: 반품 신청 및 배송비 안내" />
        </label>
        <label className="field">
          <span>문의유형</span>
          <select className="select" value={typeId} onChange={(e) => setTypeId(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">선택 안 함</option>
            {types.map((t) => (
              <option key={t.id} value={t.id}>❖ {t.name}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="field">
        <span>타겟 문의 스코프 *</span>
        <input className="input" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="예: 반품 신청 방법, 반품 가능 기간, 반품 배송비 문의" />
      </label>
      <label className="field">
        <span>SOP 본문 (마크다운) *</span>
        <textarea
          className="textarea mono"
          style={{ minHeight: 320 }}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="# AI SOP: …&#10;&#10;## 1. 적용 대상 문의&#10;…"
        />
      </label>
      <label className="field">
        <span>관련 아티클 연결 ({selected.size}건 선택)</span>
        <div style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8, padding: "4px 8px" }}>
          {articles.map((a) => (
            <label key={a.id} className="row" style={{ padding: "5px 2px", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={selected.has(a.id)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(a.id);
                  else next.delete(a.id);
                  setSelected(next);
                }}
              />
              <span style={{ fontSize: 13 }}>{a.title}</span>
              <span className="chip" style={{ marginLeft: "auto" }}>{a.section}</span>
            </label>
          ))}
        </div>
      </label>
      <div className="row between">
        <label className="row" style={{ gap: 8 }}>
          <span className="sub">등록 상태</span>
          <select className="select" style={{ width: "auto" }} value={status} onChange={(e) => setStatus(e.target.value as "draft" | "published")}>
            <option value="draft">초안 (검토 후 발행)</option>
            <option value="published">바로 발행</option>
          </select>
        </label>
        <button className="btn primary" disabled={!scope.trim() || !content.trim() || busy} onClick={submit}>
          {busy ? <><Spinner /> 등록 중…</> : "등록"}
        </button>
      </div>
    </div>
  );
}
