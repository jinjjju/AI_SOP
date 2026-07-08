import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Spinner, StatusBadge, fmtDate, useToast } from "../components/ui";
import type { ChangeDetection, SopSummary, SyncResult } from "../types";

export default function Dashboard() {
  const [changes, setChanges] = useState<ChangeDetection[]>([]);
  const [sops, setSops] = useState<SopSummary[]>([]);
  const [syncing, setSyncing] = useState(false);
  const toast = useToast();
  const nav = useNavigate();

  const load = useCallback(() => {
    api.get<ChangeDetection[]>("/api/changes").then(setChanges).catch(() => {});
    api.get<SopSummary[]>("/api/sops").then(setSops).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const sync = async () => {
    setSyncing(true);
    try {
      const r = await api.post<SyncResult>("/api/sync");
      toast(
        r.new_detections > 0
          ? `동기화 완료 — 변경 ${r.new_detections}건 새로 감지됨`
          : "동기화 완료 — 새 변경사항 없음",
      );
      load();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setSyncing(false);
    }
  };

  const openChanges = changes.filter((c) => c.status === "open" || c.status === "draft_created");
  const pendingSops = sops.filter((s) => s.has_pending);
  const count = (s: string) => sops.filter((x) => x.status === s).length;

  return (
    <div className="content-narrow">
      <div className="grid-cards">
        <div className="stat">
          <div className="num" style={{ color: openChanges.length ? "var(--red)" : undefined }}>
            {openChanges.length}
          </div>
          <div className="label">처리 필요한 아티클 변경</div>
        </div>
        <div className="stat">
          <div className="num" style={{ color: pendingSops.length ? "var(--yellow)" : undefined }}>
            {pendingSops.length}
          </div>
          <div className="label">검토 대기 보완초안</div>
        </div>
        <div className="stat">
          <div className="num">{count("draft")}</div>
          <div className="label">초안 SOP</div>
        </div>
        <div className="stat">
          <div className="num" style={{ color: "var(--green)" }}>{count("published")}</div>
          <div className="label">발행된 SOP</div>
        </div>
      </div>

      {pendingSops.length > 0 && (
        <>
          <div className="section-title">검토가 필요한 보완초안</div>
          {pendingSops.map((s) => (
            <div key={s.id} className="list-item" onClick={() => nav(`/sops/${s.id}`)}>
              <div>
                <div className="title">{s.title}</div>
                <div className="meta">
                  아티클 변경으로 생성된 보완안이 승인을 기다리고 있습니다 · 현재 v{s.current_version}
                </div>
              </div>
              <span className="chip yellow">
                검토 대기{s.pending_since && ` · ${fmtDate(s.pending_since)}`}
              </span>
            </div>
          ))}
        </>
      )}

      <div className="section-title">아티클 변경 감지</div>
      <div className="row between" style={{ marginBottom: 14 }}>
        <span className="sub" style={{ color: "var(--text-dim)", fontSize: 13 }}>
          Zendesk 아티클을 동기화하면 기존 AI SOP가 참조하는 아티클의 변경이 자동 감지됩니다.
        </span>
        <button className="btn primary" onClick={sync} disabled={syncing}>
          {syncing && <Spinner />} Zendesk 동기화
        </button>
      </div>
      {changes.length === 0 ? (
        <div className="empty">감지된 변경사항이 없습니다. 동기화를 실행해보세요.</div>
      ) : (
        changes.map((c) => (
          <div key={c.id} className="list-item" onClick={() => nav(`/changes/${c.id}`)}>
            <div>
              <div className="title">{c.article.title}</div>
              <div className="meta">
                {fmtDate(c.detected_at)} 감지 · 영향받는 SOP {c.affected_sops.length}건
                {c.affected_sops.length > 0 && ` (${c.affected_sops.map((s) => s.title).join(", ")})`}
              </div>
            </div>
            <StatusBadge status={c.status} />
          </div>
        ))
      )}

      <div className="section-title">최근 AI SOP</div>
      {sops.length === 0 ? (
        <div className="empty">
          아직 AI SOP가 없습니다. <Link to="/generate" style={{ color: "var(--accent-strong)" }}>첫 SOP를 생성</Link>해보세요.
        </div>
      ) : (
        sops.slice(0, 5).map((s) => (
          <div key={s.id} className="list-item" onClick={() => nav(`/sops/${s.id}`)}>
            <div>
              <div className="title">{s.title}</div>
              <div className="meta">
                v{s.current_version} · {s.created_by || "담당자 미지정"} · {fmtDate(s.updated_at)} 업데이트
              </div>
            </div>
            <span className="row" style={{ gap: 6 }}>
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
    </div>
  );
}
