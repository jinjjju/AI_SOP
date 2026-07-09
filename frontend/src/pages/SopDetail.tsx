import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { Md, Spinner, StatusBadge, TextDiff, fmtDate, useToast } from "../components/ui";
import type { Article, SopDetail as Sop, SopVersion, TestResult } from "../types";

export default function SopDetail() {
  const { id } = useParams();
  const [sop, setSop] = useState<Sop | null>(null);
  const toast = useToast();

  const load = useCallback(() => {
    api.get<Sop>(`/api/sops/${id}`).then(setSop).catch(() => {});
  }, [id]);

  useEffect(load, [load]);

  if (!sop) return <div className="empty">불러오는 중…</div>;

  const pending = sop.versions.find((v) => v.status === "pending_review");

  return (
    <div className="content-narrow">
      <Header sop={sop} onChanged={load} />
      {pending && <PendingReview sop={sop} version={pending} onChanged={load} />}
      <Editor sop={sop} onChanged={load} />
      <References sop={sop} onChanged={load} />
      <TestPanel sopId={sop.id} />
      <History versions={sop.versions} current={sop.current_version} />
    </div>
  );

  function Header({ sop, onChanged }: { sop: Sop; onChanged: () => void }) {
    const [busy, setBusy] = useState(false);
    const move = async (status: string) => {
      setBusy(true);
      try {
        await api.post(`/api/sops/${sop.id}/status`, { status });
        toast(
          status === "published"
            ? "발행되었습니다. 개발팀은 published API/JSON으로 가져갈 수 있습니다."
            : status === "confirmed"
              ? "컨펌되었습니다."
              : "초안 상태로 되돌렸습니다.",
        );
        onChanged();
      } catch (e) {
        toast((e as Error).message, true);
      } finally {
        setBusy(false);
      }
    };
    return (
      <div className="row between" style={{ marginBottom: 16, alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 500 }}>{sop.title}</h2>
          <span style={{ color: "var(--text-dim)", fontSize: 13 }}>
            {sop.target_scope} · v{sop.current_version} · 생성 {sop.created_by || "미지정"} · {fmtDate(sop.updated_at)}
          </span>
        </div>
        <div className="row">
          {sop.inquiry_type_name && <span className="chip">❖ {sop.inquiry_type_name}</span>}
          <StatusBadge status={sop.status} />
          {sop.status === "draft" && (
            <button className="btn primary small" disabled={busy} onClick={() => move("confirmed")}>
              ✓ 컨펌
            </button>
          )}
          {sop.status === "confirmed" && (
            <>
              <button className="btn small" disabled={busy} onClick={() => move("draft")}>초안으로</button>
              <button className="btn primary small" disabled={busy} onClick={() => move("published")}>
                🚀 발행
              </button>
            </>
          )}
          {sop.status === "published" && (
            <button className="btn small" disabled={busy} onClick={() => move("draft")}>발행 철회</button>
          )}
        </div>
      </div>
    );
  }

  function PendingReview({ sop, version, onChanged }: { sop: Sop; version: SopVersion; onChanged: () => void }) {
    const [draft, setDraft] = useState(version.content);
    const [busy, setBusy] = useState(false);
    const [mode, setMode] = useState<"diff" | "side" | "edit">("diff");
    const act = async (action: "apply" | "reject") => {
      setBusy(true);
      try {
        if (action === "apply" && draft !== version.content) {
          await api.patch(`/api/sops/${sop.id}/versions/${version.version}`, { content: draft });
        }
        await api.post(`/api/sops/${sop.id}/versions/${version.version}/${action}`);
        toast(action === "apply" ? `v${version.version} 보완안이 SOP에 반영되었습니다.` : "보완안을 거절했습니다.");
        onChanged();
      } catch (e) {
        toast((e as Error).message, true);
      } finally {
        setBusy(false);
      }
    };
    return (
      <div className="card" style={{ borderColor: "var(--yellow)" }}>
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>
            보완 초안 검토{" "}
            <span className="chip yellow">
              v{version.version} · {version.model_used || "manual"}
              {version.created_by && ` · ${version.created_by} 요청`} · {fmtDate(version.created_at)}
            </span>
          </h3>
          <div className="row">
            <button className="btn small danger" disabled={busy} onClick={() => act("reject")}>거절</button>
            <button className="btn primary small" disabled={busy} onClick={() => act("apply")}>
              {busy ? <Spinner /> : "✓"} 승인하고 SOP 갱신
            </button>
          </div>
        </div>

        <div className="tab-row" style={{ marginBottom: 14 }}>
          <button className={`tab ${mode === "diff" ? "active" : ""}`} onClick={() => setMode("diff")}>
            변경점
          </button>
          <button className={`tab ${mode === "side" ? "active" : ""}`} onClick={() => setMode("side")}>
            나란히 보기
          </button>
          <button className={`tab ${mode === "edit" ? "active" : ""}`} onClick={() => setMode("edit")}>
            초안 편집
          </button>
        </div>

        {mode === "diff" && <TextDiff oldText={sop.content} newText={draft} />}

        {mode === "side" && (
          <div className="grid-2">
            <div>
              <span className="chip">현재 SOP (v{sop.current_version})</span>
              <div className="card" style={{ maxHeight: 420, overflowY: "auto", marginTop: 8 }}>
                <Md text={sop.content} />
              </div>
            </div>
            <div>
              <span className="chip yellow">보완 초안 (v{version.version})</span>
              <div className="card" style={{ maxHeight: 420, overflowY: "auto", marginTop: 8 }}>
                <Md text={draft} />
              </div>
            </div>
          </div>
        )}

        {mode === "edit" && (
          <div>
            <p className="sub" style={{ marginTop: 0 }}>
              초안을 직접 수정할 수 있습니다. 수정 내용은 변경점 탭에 바로 반영되고, 승인 시 이 내용으로 SOP가 갱신됩니다.
            </p>
            <textarea
              className="textarea mono"
              style={{ height: 420 }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          </div>
        )}
      </div>
    );
  }

  function Editor({ sop, onChanged }: { sop: Sop; onChanged: () => void }) {
    const [editing, setEditing] = useState(false);
    const [content, setContent] = useState(sop.content);
    const [busy, setBusy] = useState(false);
    useEffect(() => setContent(sop.content), [sop.content]);

    const save = async () => {
      setBusy(true);
      try {
        await api.patch(`/api/sops/${sop.id}`, { content });
        toast("수정 내용이 새 버전으로 저장되었습니다.");
        setEditing(false);
        onChanged();
      } catch (e) {
        toast((e as Error).message, true);
      } finally {
        setBusy(false);
      }
    };

    return (
      <div className="card">
        <div className="row between" style={{ marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>SOP 본문</h3>
          {editing ? (
            <div className="row">
              <button className="btn small" onClick={() => { setEditing(false); setContent(sop.content); }}>취소</button>
              <button className="btn primary small" disabled={busy || content === sop.content} onClick={save}>
                {busy ? <Spinner /> : null} 저장
              </button>
            </div>
          ) : (
            <button className="btn small" onClick={() => setEditing(true)}>✎ 편집</button>
          )}
        </div>
        {editing ? (
          <textarea
            className="textarea mono"
            style={{ minHeight: 460 }}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
        ) : (
          <Md text={sop.content} />
        )}
      </div>
    );
  }

  function References({ sop, onChanged }: { sop: Sop; onChanged: () => void }) {
    const [all, setAll] = useState<Article[]>([]);
    const [selected, setSelected] = useState<Set<number>>(new Set(sop.articles.map((a) => a.id)));
    const [adjusting, setAdjusting] = useState(false);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
      if (adjusting && all.length === 0) {
        api.get<Article[]>("/api/articles").then(setAll).catch(() => {});
      }
    }, [adjusting, all.length]);

    const regenerate = async () => {
      setBusy(true);
      try {
        await api.post(`/api/sops/${sop.id}/regenerate`, { article_ids: [...selected] });
        toast("조정된 아티클로 SOP를 다시 생성했습니다.");
        setAdjusting(false);
        onChanged();
      } catch (e) {
        toast((e as Error).message, true);
      } finally {
        setBusy(false);
      }
    };

    return (
      <div className="card">
        <div className="row between" style={{ marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>참조 아티클 ({sop.articles.length})</h3>
          {sop.status === "draft" &&
            (adjusting ? (
              <div className="row">
                <button className="btn small" onClick={() => setAdjusting(false)}>취소</button>
                <button className="btn primary small" disabled={busy || selected.size === 0} onClick={regenerate}>
                  {busy ? <><Spinner /> 재생성 중…</> : "✦ 이 아티클로 재생성"}
                </button>
              </div>
            ) : (
              <button className="btn small" onClick={() => setAdjusting(true)}>아티클 조정 · 재생성</button>
            ))}
        </div>

        {adjusting ? (
          <div>
            {all.map((a) => (
              <label key={a.id} className="row" style={{ padding: "6px 4px", cursor: "pointer" }}>
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
                <span>{a.title}</span>
                <span className="chip" style={{ marginLeft: "auto" }}>{a.section}</span>
              </label>
            ))}
          </div>
        ) : sop.articles.length === 0 ? (
          <p className="sub">참조 아티클이 없습니다.</p>
        ) : (
          sop.articles.map((a) => <ArticleAcc key={a.id} article={a} />)
        )}
      </div>
    );
  }
}

function ArticleAcc({ article }: { article: Article }) {
  const [body, setBody] = useState<string | null>(null);
  return (
    <details
      className="article-acc"
      onToggle={(e) => {
        if ((e.target as HTMLDetailsElement).open && body === null) {
          api.get<Article>(`/api/articles/${article.id}`).then((a) => setBody(a.body ?? "")).catch(() => {});
        }
      }}
    >
      <summary>
        📄 {article.title}
        <span className="chip" style={{ marginLeft: "auto" }}>{article.section}</span>
      </summary>
      <div className="body">{body ?? "불러오는 중…"}</div>
    </details>
  );
}

function TestPanel({ sopId }: { sopId: number }) {
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const send = async () => {
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await api.post<TestResult>(`/api/sops/${sopId}/test`, { question: q });
      setMessages((m) => [...m, { role: "bot", text: r.answer }]);
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>챗봇 테스트 <span className="chip">이 SOP를 시스템 프롬프트로 사용</span></h3>
      {messages.length > 0 && (
        <div className="chat" style={{ marginBottom: 12 }}>
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>{m.text}</div>
          ))}
          {busy && <div className="bubble bot">…</div>}
        </div>
      )}
      <div className="row">
        <input
          className="input"
          placeholder="고객 질문을 입력해 챗봇 응답을 미리 확인하세요"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="btn primary" onClick={send} disabled={!question.trim() || busy}>
          전송
        </button>
      </div>
    </div>
  );
}

function History({ versions, current }: { versions: SopVersion[]; current: number }) {
  const SOURCE: Record<string, string> = { new: "생성", revision: "보완", manual: "수동 수정" };
  return (
    <div className="card">
      <h3>버전 이력</h3>
      {[...versions].reverse().map((v) => (
        <div key={v.id} className="row between" style={{ padding: "7px 4px", fontSize: 13 }}>
          <span>
            <strong>v{v.version}</strong>
            {v.version === current && <span className="chip green" style={{ marginLeft: 8 }}>현재</span>}
            <span style={{ color: "var(--text-dim)", marginLeft: 8 }}>
              {SOURCE[v.source] ?? v.source}
              {v.model_used && ` · ${v.model_used}`}
              {v.created_by && ` · ${v.created_by}`}
            </span>
          </span>
          <span className="row" style={{ gap: 8 }}>
            <StatusBadge status={v.status} />
            <span style={{ color: "var(--text-faint)", fontSize: 12 }}>{fmtDate(v.created_at)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
