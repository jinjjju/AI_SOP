import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { DiffView, Spinner, StatusBadge, fmtDate, useToast } from "../components/ui";
import type { ChangeDetection, SopVersion } from "../types";

export default function ChangeDetail() {
  const { id } = useParams();
  const [change, setChange] = useState<ChangeDetection | null>(null);
  const [drafting, setDrafting] = useState<number | null>(null);
  const toast = useToast();
  const nav = useNavigate();

  const load = useCallback(() => {
    api.get<ChangeDetection>(`/api/changes/${id}`).then(setChange).catch(() => {});
  }, [id]);

  useEffect(load, [load]);

  if (!change) return <div className="empty">불러오는 중…</div>;

  const createDraft = async (sopId: number) => {
    setDrafting(sopId);
    try {
      const v = await api.post<SopVersion>(`/api/changes/${change.id}/draft?sop_id=${sopId}`);
      toast(`보완 초안(v${v.version})이 생성되었습니다. SOP 화면에서 비교 · 승인하세요.`);
      nav(`/sops/${sopId}`);
    } catch (e) {
      toast((e as Error).message, true);
      setDrafting(null);
    }
  };

  const dismiss = async () => {
    try {
      await api.post(`/api/changes/${change.id}/dismiss`);
      toast("변경 건을 무시 처리했습니다.");
      load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="content-narrow">
      <div className="row between" style={{ marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 500 }}>{change.article.title}</h2>
          <span className="sub" style={{ color: "var(--text-dim)", fontSize: 13 }}>
            {change.article.section} · {fmtDate(change.detected_at)} 감지
          </span>
        </div>
        <div className="row">
          <StatusBadge status={change.status} />
          {(change.status === "open" || change.status === "draft_created") && (
            <button className="btn small danger" onClick={dismiss}>무시</button>
          )}
        </div>
      </div>

      <div className="card">
        <h3>아티클 변경 내용</h3>
        <DiffView diff={change.diff_summary} />
      </div>

      <div className="card">
        <h3>영향받는 AI SOP</h3>
        {change.affected_sops.length === 0 ? (
          <p className="sub">
            이 아티클을 참조하는 SOP가 없습니다. 필요하다면{" "}
            <Link to="/generate" style={{ color: "var(--accent-strong)" }}>새 SOP를 생성</Link>하세요.
          </p>
        ) : (
          change.affected_sops.map((s) => (
            <div key={s.id} className="list-item" style={{ cursor: "default" }}>
              <div>
                <Link to={`/sops/${s.id}`} className="title" style={{ color: "var(--accent-strong)" }}>
                  {s.title}
                </Link>
                <div className="meta">v{s.current_version} · <StatusBadge status={s.status} /></div>
              </div>
              <button
                className="btn primary small"
                disabled={drafting !== null || change.status === "applied" || change.status === "dismissed"}
                onClick={() => createDraft(s.id)}
              >
                {drafting === s.id ? <><Spinner /> 생성 중…</> : "✦ 보완 초안 생성"}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
