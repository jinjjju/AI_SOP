import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Spinner, useToast } from "../components/ui";
import type { AppSettings, InquiryType, PromptTemplate, SopDetail } from "../types";

const EXAMPLES = [
  "와우 멤버십 해지와 환불 문의",
  "배송 지연 보상 요청",
  "주문 취소와 쿠폰 복원 문의",
  "오배송 상품 재배송 요청",
];

export default function SopGenerate() {
  const [scope, setScope] = useState("");
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [types, setTypes] = useState<InquiryType[]>([]);
  const [typeId, setTypeId] = useState<number | "">("");
  const toast = useToast();
  const nav = useNavigate();

  useEffect(() => {
    api.get<AppSettings>("/api/settings").then(setSettings).catch(() => {});
    api.get<PromptTemplate[]>("/api/prompts").then(setTemplates).catch(() => {});
    api.get<InquiryType[]>("/api/inquiry-types").then(setTypes).catch(() => {});
  }, []);

  const templateName =
    templates.find((t) => t.id === settings?.default_generate_template_id)?.name ?? "기본 프롬프트";

  const generate = async () => {
    if (!scope.trim() || loading) return;
    setLoading(true);
    try {
      const sop = await api.post<SopDetail>("/api/sops/generate", {
        scope: scope.trim(),
        inquiry_type_id: typeId === "" ? null : typeId,
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
    </div>
  );
}
