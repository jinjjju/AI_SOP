import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { DiffView, Spinner, StatusBadge, fmtDate, useToast } from "../components/ui";
import type { Article, AutoTriage, ChangeDetection, SopSummary, SopVersion } from "../types";

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

  const actionable = change.status === "open" || change.status === "draft_created";

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

  const reviseFromNew = async (sopId: number) => {
    setDrafting(sopId);
    try {
      const v = await api.post<SopVersion>(`/api/sops/${sopId}/revise`, {
        article_id: change.article_id,
        change_id: change.id,
      });
      toast(`신규 아티클 기준 보완 초안(v${v.version})이 생성되었습니다.`);
      nav(`/sops/${sopId}`);
    } catch (e) {
      toast((e as Error).message, true);
      setDrafting(null);
    }
  };

  const dismiss = async () => {
    try {
      await api.post(`/api/changes/${change.id}/dismiss`);
      toast("이 건을 무시 처리했습니다.");
      load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="content-narrow">
      <div className="row between" style={{ marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 500 }}>
            {change.article.title}
            {change.kind === "new_article" && <span className="chip accent" style={{ marginLeft: 10 }}>✧ 신규 아티클</span>}
          </h2>
          <span className="sub" style={{ color: "var(--text-dim)", fontSize: 13 }}>
            {change.article.section} · {fmtDate(change.detected_at)} 감지
          </span>
        </div>
        <div className="row">
          <StatusBadge status={change.status} />
          {actionable && (
            <button className="btn small danger" onClick={dismiss}>무시</button>
          )}
        </div>
      </div>

      {change.kind === "new_article" ? (
        <NewArticleView
          change={change}
          drafting={drafting}
          actionable={actionable}
          onRevise={reviseFromNew}
        />
      ) : (
        <>
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
                    disabled={drafting !== null || !actionable}
                    onClick={() => createDraft(s.id)}
                  >
                    {drafting === s.id ? <><Spinner /> 생성 중…</> : "✦ 보완 초안 생성"}
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* 신규 아티클 감지 건 — 자동 분류(LLM) 결과와 실행 버튼. 실행은 담당자가 결정한다. */
function NewArticleView({
  change,
  drafting,
  actionable,
  onRevise,
}: {
  change: ChangeDetection;
  drafting: number | null;
  actionable: boolean;
  onRevise: (sopId: number) => void;
}) {
  const [body, setBody] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<SopSummary[]>([]);
  const nav = useNavigate();

  let triage: AutoTriage | null = null;
  try {
    triage = change.triage_json ? (JSON.parse(change.triage_json) as AutoTriage) : null;
  } catch {
    triage = null;
  }

  useEffect(() => {
    api.get<Article>(`/api/articles/${change.article_id}`).then((a) => setBody(a.body ?? "")).catch(() => {});
  }, [change.article_id]);

  useEffect(() => {
    const ids = triage?.candidate_sop_ids ?? [];
    if (ids.length === 0) return;
    api.get<SopSummary[]>("/api/sops").then((all) => setCandidates(all.filter((s) => ids.includes(s.id)))).catch(() => {});
    // triage_json 문자열이 바뀔 때만 다시 조회
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [change.triage_json]);

  const goGenerate = () => {
    const params = new URLSearchParams({
      scope: change.article.title,
      article: String(change.article_id),
    });
    if (triage?.inquiry_type_id) params.set("type", String(triage.inquiry_type_id));
    nav(`/generate?${params.toString()}`);
  };

  const ACTION_LABEL: Record<string, string> = {
    revise: "기존 SOP 보완 권장",
    create: "신규 SOP 생성 권장",
    none: "관련 SOP 없음 (무관)",
  };

  return (
    <>
      <div className="card" style={{ borderColor: "var(--accent)" }}>
        <h3>
          자동 분류 결과{" "}
          {triage && (
            <span className={`chip ${triage.confident ? "accent" : "yellow"}`}>
              {triage.confident ? "판정 일치" : "⚠ 판정 불확실 — 직접 확인 필요"}
            </span>
          )}
        </h3>
        {!triage ? (
          <p className="sub">자동 분류 결과가 없습니다. 문의유형 · 검수 화면에서 수동 검수할 수 있습니다.</p>
        ) : (
          <>
            <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
              <span className={`chip ${triage.action === "none" ? "" : "green"}`}>
                {ACTION_LABEL[triage.action] ?? triage.action}
              </span>
              {triage.inquiry_type_name && <span className="chip">❖ {triage.inquiry_type_name}</span>}
            </div>
            <p className="sub" style={{ margin: 0 }}>{triage.reason}</p>
          </>
        )}

        {actionable && (
          <div style={{ marginTop: 14 }}>
            {candidates.length > 0 && (
              <>
                <div className="section-title" style={{ marginTop: 0 }}>보완 대상 후보 SOP</div>
                {candidates.map((s) => (
                  <div key={s.id} className="list-item" style={{ cursor: "default" }}>
                    <div>
                      <Link to={`/sops/${s.id}`} className="title" style={{ color: "var(--accent-strong)" }}>
                        {s.title}
                      </Link>
                      <div className="meta">v{s.current_version} · <StatusBadge status={s.status} /></div>
                    </div>
                    <button
                      className="btn primary small"
                      disabled={drafting !== null}
                      onClick={() => onRevise(s.id)}
                    >
                      {drafting === s.id ? <><Spinner /> 생성 중…</> : "✦ 이 SOP 보완 초안 생성"}
                    </button>
                  </div>
                ))}
              </>
            )}
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn small" onClick={goGenerate}>
                ✦ 이 아티클로 신규 SOP 생성
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h3>아티클 본문</h3>
        <div className="body" style={{ whiteSpace: "pre-wrap", fontSize: 13.5, color: "var(--text-dim)" }}>
          {body ?? "불러오는 중…"}
        </div>
      </div>
    </>
  );
}
