import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Spinner, StatusBadge, useToast } from "../components/ui";
import type { InquiryType, SopDetail, SopVersion, TriageResult } from "../types";

export default function InquiryTypes() {
  const [types, setTypes] = useState<InquiryType[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(() => {
    api.get<InquiryType[]>("/api/inquiry-types").then((list) => {
      setTypes(list);
      setSelectedId((cur) => cur ?? list[0]?.id ?? null);
    }).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const selected = types.find((t) => t.id === selectedId) ?? null;

  return (
    <div className="content-narrow">
      <div className="row wrap" style={{ marginBottom: 16 }}>
        {types.map((t) => (
          <span
            key={t.id}
            className={`chip clickable ${t.id === selectedId ? "accent" : ""}`}
            onClick={() => setSelectedId(t.id)}
          >
            {t.name} <small style={{ opacity: 0.7 }}>아티클 {t.articles.length} · SOP {t.sop_count}</small>
          </span>
        ))}
        <NewTypeChip onCreated={load} />
      </div>

      {selected && (
        <>
          <TypeEditor key={selected.id} type={selected} onChanged={load} />
          <TriagePanel type={selected} />
        </>
      )}
    </div>
  );
}

function NewTypeChip({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const toast = useToast();

  if (!open) {
    return <span className="chip clickable" onClick={() => setOpen(true)}>＋ 유형 추가</span>;
  }
  const create = async () => {
    if (!name.trim()) return;
    try {
      await api.post("/api/inquiry-types", { name: name.trim(), condition: "" });
      toast("문의유형이 추가되었습니다. 조건을 작성해주세요.");
      setName("");
      setOpen(false);
      onCreated();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };
  return (
    <span className="row" style={{ gap: 6 }}>
      <input
        className="input"
        style={{ width: 140, padding: "4px 12px" }}
        placeholder="유형명"
        value={name}
        autoFocus
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && create()}
      />
      <button className="btn small" onClick={create}>추가</button>
    </span>
  );
}

function TypeEditor({ type, onChanged }: { type: InquiryType; onChanged: () => void }) {
  const [condition, setCondition] = useState(type.condition);
  const [linkUrl, setLinkUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const saveCondition = async () => {
    try {
      await api.put(`/api/inquiry-types/${type.id}`, { name: type.name, condition });
      toast("조건이 저장되었습니다. 링크 검수 시 이 조건으로 적합성을 판단합니다.");
      onChanged();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  const addLink = async () => {
    if (!linkUrl.trim()) return;
    setBusy(true);
    try {
      await api.post(`/api/inquiry-types/${type.id}/articles`, { url: linkUrl.trim() });
      toast("관련 아티클이 연결되었습니다.");
      setLinkUrl("");
      onChanged();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  const unlink = async (articleId: number) => {
    try {
      await api.del(`/api/inquiry-types/${type.id}/articles/${articleId}`);
      onChanged();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="card">
      <h3>「{type.name}」 유형 정의</h3>
      <label className="field">
        <span>문의유형 조건 — 링크 검수 시 LLM이 이 조건과 아티클을 대조해 적합성을 판단합니다</span>
        <textarea
          className="textarea"
          style={{ minHeight: 70 }}
          placeholder="예: 고객이 상품 반품 절차·기간·배송비·환불을 문의하는 경우"
          value={condition}
          onChange={(e) => setCondition(e.target.value)}
        />
      </label>
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: 14 }}>
        <button className="btn small" disabled={condition === type.condition} onClick={saveCondition}>
          조건 저장
        </button>
      </div>

      <h3>관련 아티클 링크 ({type.articles.length})</h3>
      {type.articles.map((a) => (
        <div key={a.id} className="row between" style={{ padding: "5px 0", fontSize: 13 }}>
          <span>📄 {a.title} <span className="chip" style={{ marginLeft: 6 }}>{a.section || `#${a.zendesk_id}`}</span></span>
          <span
            style={{ cursor: "pointer", color: "var(--text-faint)" }}
            title="링크 해제"
            onClick={() => unlink(a.id)}
          >
            ✕
          </span>
        </div>
      ))}
      <div className="row" style={{ marginTop: 10 }}>
        <input
          className="input"
          placeholder="Zendesk 아티클 URL 또는 ID 입력 (…/articles/12345)"
          value={linkUrl}
          onChange={(e) => setLinkUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addLink()}
        />
        <button className="btn small" disabled={busy || !linkUrl.trim()} onClick={addLink}>
          {busy ? <Spinner /> : "＋"} 링크 추가
        </button>
      </div>
    </div>
  );
}

function TriagePanel({ type }: { type: InquiryType }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [acting, setActing] = useState(false);
  const [result, setResult] = useState<TriageResult | null>(null);
  const [targetSopId, setTargetSopId] = useState<number | null>(null);
  const toast = useToast();
  const nav = useNavigate();

  const run = async () => {
    if (!url.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await api.post<TriageResult>("/api/triage", { url: url.trim(), inquiry_type_id: type.id });
      setResult(r);
      setTargetSopId(r.candidate_sops[0]?.id ?? null);
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  const doRevise = async () => {
    if (!result || !targetSopId) return;
    setActing(true);
    try {
      const v = await api.post<SopVersion>(`/api/sops/${targetSopId}/revise`, { article_id: result.article.id });
      toast(`보완 초안 v${v.version}이 생성되었습니다. 변경점을 검토하세요.`);
      nav(`/sops/${targetSopId}`);
    } catch (e) {
      toast((e as Error).message, true);
      setActing(false);
    }
  };

  const doCreate = async () => {
    if (!result) return;
    setActing(true);
    try {
      const sop = await api.post<SopDetail>("/api/sops/generate", {
        scope: `${type.name} 문의 — ${type.condition || result.article.title}`,
        article_ids: [result.article.id],
        inquiry_type_id: type.id,
      });
      toast("신규 AI SOP 초안이 생성되었습니다.");
      nav(`/sops/${sop.id}`);
    } catch (e) {
      toast((e as Error).message, true);
      setActing(false);
    }
  };

  return (
    <div className="card">
      <h3>아티클 링크 검수 <span className="chip">자동 감지가 놓친 변경/신규 아티클 수동 검수</span></h3>
      <p className="sub" style={{ marginTop: 0 }}>
        링크를 입력하면 본문을 가져와 「{type.name}」 조건과 대조해 <strong>AI SOP 적합성</strong>과
        <strong> 보완/신규</strong> 여부를 판정합니다. 실행은 판정 결과를 확인한 뒤 담당자가 결정합니다.
      </p>
      <div className="row">
        <input
          className="input"
          placeholder="Zendesk 아티클 URL 입력"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        <button className="btn primary" disabled={busy || !url.trim()} onClick={run}>
          {busy ? <><Spinner /> 판정 중…</> : "✦ 검수 실행"}
        </button>
      </div>

      {result && (
        <div
          className="card"
          style={{
            marginTop: 14,
            borderColor: result.suitable ? "var(--green)" : "var(--red)",
            background: result.suitable ? "var(--green-bg)" : "var(--red-bg)",
          }}
        >
          <div className="row between wrap">
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                {result.suitable ? "✓ 적합" : "✕ 부적합"} — 📄 {result.article.title}
              </div>
              <div style={{ fontSize: 13 }}>{result.reason}</div>
            </div>
            {result.suitable && result.action === "revise" && (
              <div className="row">
                <select
                  className="select"
                  style={{ width: "auto" }}
                  value={targetSopId ?? ""}
                  onChange={(e) => setTargetSopId(Number(e.target.value))}
                >
                  {result.candidate_sops.map((s) => (
                    <option key={s.id} value={s.id}>{s.title} (v{s.current_version})</option>
                  ))}
                </select>
                <button className="btn primary small" disabled={acting} onClick={doRevise}>
                  {acting ? <Spinner /> : "♺"} 보완 초안 생성
                </button>
                <button className="btn small" disabled={acting} onClick={doCreate}>신규로 생성</button>
              </div>
            )}
            {result.suitable && result.action === "create" && (
              <button className="btn primary small" disabled={acting} onClick={doCreate}>
                {acting ? <Spinner /> : "✦"} 신규 SOP 생성
              </button>
            )}
          </div>
          {result.action === "revise" && result.candidate_sops.length > 0 && (
            <div style={{ marginTop: 10, fontSize: 12.5 }}>
              보완 대상 후보:{" "}
              {result.candidate_sops.map((s) => (
                <span key={s.id} className="chip" style={{ marginRight: 6 }}>
                  {s.title} <StatusBadge status={s.status} />
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
