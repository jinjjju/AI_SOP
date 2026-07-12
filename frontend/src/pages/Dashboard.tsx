import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Spinner, StatusBadge, fmtDate, useToast } from "../components/ui";
import type { AutoTriage, ChangeDetection, SopSummary, SyncResult, ZendeskUsage } from "../types";

/* 신규 아티클 후보의 자동 분류 결과 — 목록에서 열어보지 않고도 판단할 수 있게 칩으로 표시 */
function TriageChip({ raw }: { raw: string }) {
  let t: AutoTriage | null = null;
  try {
    t = raw ? (JSON.parse(raw) as AutoTriage) : null;
  } catch {
    t = null;
  }
  if (!t) return null;
  const label =
    t.action === "revise" ? "보완 권장" : t.action === "create" ? "신규 SOP 권장" : "무관 판정 — 무시 권장";
  const tone = t.action === "none" ? "" : t.action === "revise" ? "green" : "accent";
  return (
    <>
      <span className={`chip ${tone}`}>{label}</span>
      {!t.confident && <span className="chip yellow">판정 불확실</span>}
    </>
  );
}

export default function Dashboard() {
  const [changes, setChanges] = useState<ChangeDetection[]>([]);
  const [sops, setSops] = useState<SopSummary[]>([]);
  const [usage, setUsage] = useState<ZendeskUsage | null>(null);
  const [showAllChanges, setShowAllChanges] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const toast = useToast();
  const nav = useNavigate();

  const load = useCallback(() => {
    api.get<ChangeDetection[]>("/api/changes").then(setChanges).catch(() => {});
    api.get<SopSummary[]>("/api/sops").then(setSops).catch(() => {});
    api.get<ZendeskUsage>("/api/zendesk-usage").then(setUsage).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const sync = async (mode: "auto" | "full" = "auto") => {
    setSyncing(true);
    try {
      const r = await api.post<SyncResult>(`/api/sync?mode=${mode}`);
      if (r.budget_exhausted) {
        toast(r.message || "일일 호출 상한에 도달해 동기화가 중단되었습니다.", true);
      } else {
        const parts = [
          r.new_detections > 0 && `변경 ${r.new_detections}건`,
          r.new_article_candidates > 0 && `신규 후보 ${r.new_article_candidates}건`,
          r.drafts_created > 0 && `보완 초안 ${r.drafts_created}건 자동 생성`,
        ].filter(Boolean);
        toast(
          parts.length > 0
            ? `동기화 완료(${r.mode === "incremental" ? "증분" : "전체"}) — ${parts.join(" · ")}`
            : "동기화 완료 — 새 변경사항 없음",
        );
      }
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

  // 기본 노출은 "담당자 결정이 필요한 것"만:
  // - open 건 (신규 후보 / 영향 SOP 없는 변경 / 자동 초안 실패 건)
  // - draft_created는 위 '검토 대기 보완초안' 목록에서 이미 다루므로 여기선 숨긴다 (중복 제거)
  const needsDecision = changes.filter((c) => c.status === "open");
  const visibleChanges = showAllChanges ? changes : needsDecision;

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
          동기화는 마지막 실행 이후 변경분만 가져오고(증분), 변경·신규 아티클을 자동 감지합니다.
          발행 SOP에 영향이 있으면 보완 초안까지 자동 생성됩니다.
        </span>
        <span className="row" style={{ gap: 8, flexShrink: 0 }}>
          {usage && (
            <span
              className={`chip ${usage.calls >= usage.limit ? "red" : ""}`}
              title="오늘의 Zendesk API 호출 수 / 자체 상한 (설정에서 조정)"
            >
              API {usage.calls}/{usage.limit}
            </span>
          )}
          <button className="btn small" onClick={() => sync("full")} disabled={syncing} title="전체 재수집 — 호출 수 많음, 주 1회 정합성 확인용">
            전체
          </button>
          <button className="btn primary" onClick={() => sync()} disabled={syncing}>
            {syncing && <Spinner />} Zendesk 동기화
          </button>
        </span>
      </div>
      {changes.length > needsDecision.length && (
        <div className="row" style={{ marginBottom: 10 }}>
          <button className="btn small" onClick={() => setShowAllChanges(!showAllChanges)}>
            {showAllChanges ? "결정 필요한 것만 보기" : `전체 이력 보기 (${changes.length})`}
          </button>
        </div>
      )}
      {visibleChanges.length === 0 ? (
        <div className="empty">
          {changes.length === 0
            ? "감지된 변경사항이 없습니다. 동기화를 실행해보세요."
            : "지금 결정이 필요한 건은 없습니다. (자동 초안이 생성된 건은 위 '검토 대기 보완초안'에서 검토)"}
        </div>
      ) : (
        visibleChanges.map((c) => (
          <div key={c.id} className="list-item" onClick={() => nav(`/changes/${c.id}`)}>
            <div>
              <div className="title">
                {c.article.title}
                {c.kind === "new_article" && <span className="chip accent" style={{ marginLeft: 8 }}>✧ 신규 아티클</span>}
              </div>
              <div className="meta">
                {fmtDate(c.detected_at)} 감지 ·{" "}
                {c.kind === "new_article"
                  ? "새로 발견된 아티클"
                  : c.affected_sops.length > 0
                    ? `영향받는 SOP ${c.affected_sops.length}건 (${c.affected_sops.map((s) => s.title).join(", ")})`
                    : "이 아티클을 참조하는 SOP 없음 — 참고용"}
              </div>
            </div>
            <span className="row" style={{ gap: 6 }}>
              {c.kind === "new_article" && <TriageChip raw={c.triage_json} />}
              <StatusBadge status={c.status} />
            </span>
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
