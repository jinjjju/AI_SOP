import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { StatusBadge, fmtDate, useToast } from "../components/ui";
import type { SopSummary } from "../types";

const FILTERS = [
  { key: "", label: "전체" },
  { key: "draft", label: "초안" },
  { key: "confirmed", label: "컨펌됨" },
  { key: "published", label: "발행됨" },
];

export default function SopList() {
  const [sops, setSops] = useState<SopSummary[]>([]);
  const [filter, setFilter] = useState("");
  const toast = useToast();
  const nav = useNavigate();

  useEffect(() => {
    api.get<SopSummary[]>(`/api/sops${filter ? `?status=${filter}` : ""}`).then(setSops).catch(() => {});
  }, [filter]);

  const download = async () => {
    try {
      const data = await api.get<unknown[]>("/api/sops/published");
      if (data.length === 0) {
        toast("발행된 SOP가 없습니다.", true);
        return;
      }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `ai-sops-published-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast(`발행 SOP ${data.length}건을 JSON으로 내려받았습니다.`);
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="content-narrow">
      <div className="row between" style={{ marginBottom: 18 }}>
        <div className="row" style={{ gap: 8 }}>
          {FILTERS.map((f) => (
            <span
              key={f.key}
              className={`chip clickable ${filter === f.key ? "accent" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </span>
          ))}
        </div>
        <div className="row">
          <button className="btn small" onClick={download} title="개발팀 전달용 · GET /api/sops/published 와 동일한 JSON">
            ⬇ 발행본 JSON
          </button>
          <Link to="/generate" className="btn primary small">✦ 새 SOP 생성</Link>
        </div>
      </div>

      {sops.length === 0 ? (
        <div className="empty">해당 상태의 SOP가 없습니다.</div>
      ) : (
        sops.map((s) => (
          <div key={s.id} className="list-item" onClick={() => nav(`/sops/${s.id}`)}>
            <div style={{ minWidth: 0 }}>
              <div className="title">{s.title}</div>
              <div className="meta">
                {s.target_scope} · v{s.current_version} · {s.created_by || "담당자 미지정"} · {fmtDate(s.updated_at)}
              </div>
            </div>
            <span className="row" style={{ gap: 6 }}>
              {s.inquiry_type_name && <span className="chip">❖ {s.inquiry_type_name}</span>}
              {s.has_pending && (
                <span className="chip yellow">
                  검토 대기{s.pending_since && ` · ${fmtDate(s.pending_since)}`}
                </span>
              )}
              <StatusBadge status={s.status} />
            </span>
          </div>
        ))
      )}

      <p style={{ color: "var(--text-faint)", fontSize: 12.5, marginTop: 20 }}>
        개발팀 연동: 발행된 SOP는 <code style={{ color: "var(--text-dim)" }}>GET /api/sops/published</code> API
        또는 위 JSON 다운로드로 전달할 수 있습니다.
      </p>
    </div>
  );
}
