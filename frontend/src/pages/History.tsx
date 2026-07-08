import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { fmtDate } from "../components/ui";
import type { Activity, Manager } from "../types";

const ACTION_LABEL: Record<string, { label: string; tone: string }> = {
  sop_created: { label: "SOP 생성", tone: "accent" },
  sop_regenerated: { label: "재생성", tone: "accent" },
  draft_created: { label: "보완 초안", tone: "yellow" },
  version_applied: { label: "보완 승인", tone: "green" },
  version_rejected: { label: "보완 거절", tone: "red" },
  status_changed: { label: "상태 변경", tone: "" },
  content_edited: { label: "본문 수정", tone: "" },
  change_dismissed: { label: "변경 무시", tone: "" },
  sync_run: { label: "동기화", tone: "" },
  settings_updated: { label: "설정 변경", tone: "" },
  prompt_updated: { label: "프롬프트 수정", tone: "" },
};

export default function History() {
  const [items, setItems] = useState<Activity[]>([]);
  const [managers, setManagers] = useState<Manager[]>([]);
  const [actorFilter, setActorFilter] = useState("");

  useEffect(() => {
    api.get<Manager[]>("/api/managers").then(setManagers).catch(() => {});
  }, []);

  useEffect(() => {
    api
      .get<Activity[]>(`/api/activity${actorFilter ? `?actor=${encodeURIComponent(actorFilter)}` : ""}`)
      .then(setItems)
      .catch(() => {});
  }, [actorFilter]);

  return (
    <div className="content-narrow">
      <div className="row wrap" style={{ marginBottom: 18 }}>
        <span
          className={`chip clickable ${actorFilter === "" ? "accent" : ""}`}
          onClick={() => setActorFilter("")}
        >
          전체
        </span>
        {managers.map((m) => (
          <span
            key={m.id}
            className={`chip clickable ${actorFilter === m.name ? "accent" : ""}`}
            onClick={() => setActorFilter(m.name)}
          >
            👤 {m.name}{m.team ? ` · ${m.team}` : ""}
          </span>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="empty">기록된 활동이 없습니다.</div>
      ) : (
        items.map((a) => {
          const act = ACTION_LABEL[a.action] ?? { label: a.action, tone: "" };
          const body = (
            <>
              <div style={{ minWidth: 0 }}>
                <div className="title" style={{ fontWeight: 400 }}>{a.detail || act.label}</div>
                <div className="meta">
                  {a.actor || "(담당자 미지정)"} · {fmtDate(a.created_at)}
                </div>
              </div>
              <span className={`chip ${act.tone}`}>{act.label}</span>
            </>
          );
          return a.entity_type === "sop" && a.entity_id ? (
            <Link key={a.id} to={`/sops/${a.entity_id}`} className="list-item">
              {body}
            </Link>
          ) : (
            <div key={a.id} className="list-item" style={{ cursor: "default" }}>
              {body}
            </div>
          );
        })
      )}
    </div>
  );
}
