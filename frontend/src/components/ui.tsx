import { marked } from "marked";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

/* 상태 뱃지 ─ SOP/변경감지/버전 공용 */
const STATUS_LABEL: Record<string, { label: string; tone: string }> = {
  draft: { label: "초안", tone: "yellow" },
  confirmed: { label: "컨펌됨", tone: "accent" },
  published: { label: "발행됨", tone: "green" },
  open: { label: "미처리", tone: "red" },
  draft_created: { label: "초안 생성됨", tone: "yellow" },
  applied: { label: "반영됨", tone: "green" },
  dismissed: { label: "무시됨", tone: "" },
  pending_review: { label: "검토 대기", tone: "yellow" },
  rejected: { label: "거절됨", tone: "" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_LABEL[status] ?? { label: status, tone: "" };
  return <span className={`chip ${s.tone}`}>{s.label}</span>;
}

export function Md({ text }: { text: string }) {
  return <div className="md" dangerouslySetInnerHTML={{ __html: marked.parse(text) as string }} />;
}

export function DiffView({ diff }: { diff: string }) {
  return (
    <div className="diff">
      {diff.split("\n").map((line, i) => {
        const cls = line.startsWith("+")
          ? "add"
          : line.startsWith("-")
            ? "del"
            : line.startsWith("@@")
              ? "hunk"
              : "";
        return (
          <span key={i} className={cls}>
            {line || " "}
            {"\n"}
          </span>
        );
      })}
    </div>
  );
}

/* 두 텍스트의 라인 단위 diff (LCS) — 기존본 대비 초안의 삭제/추가 라인 계산 */
type DiffOp = { type: "same" | "add" | "del"; text: string };

export function lineDiff(oldText: string, newText: string): DiffOp[] {
  const a = oldText.split("\n");
  const b = newText.split("\n");
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops: DiffOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      ops.push({ type: "same", text: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: "del", text: a[i] });
      i++;
    } else {
      ops.push({ type: "add", text: b[j] });
      j++;
    }
  }
  while (i < n) ops.push({ type: "del", text: a[i++] });
  while (j < m) ops.push({ type: "add", text: b[j++] });
  return ops;
}

/* 변경점 뷰 — 기존 SOP(old) 대비 보완 초안(new)에서 바뀐 라인을 하이라이트 */
export function TextDiff({ oldText, newText }: { oldText: string; newText: string }) {
  const ops = useMemo(() => lineDiff(oldText, newText), [oldText, newText]);
  const adds = ops.filter((o) => o.type === "add").length;
  const dels = ops.filter((o) => o.type === "del").length;

  if (adds === 0 && dels === 0) {
    return <p className="sub">변경된 내용이 없습니다. 초안이 기존 SOP와 동일합니다.</p>;
  }
  return (
    <div>
      <div className="row" style={{ gap: 8, marginBottom: 8, fontSize: 12.5 }}>
        <span className="chip red">− 삭제 {dels}줄</span>
        <span className="chip green">＋ 추가 {adds}줄</span>
        <span style={{ color: "var(--text-faint)" }}>빨간 줄이 기존 내용, 초록 줄이 초안의 새 내용입니다.</span>
      </div>
      <div className="diff">
        {ops.map((o, idx) => (
          <span key={idx} className={o.type === "add" ? "add" : o.type === "del" ? "del" : "ctx"}>
            {o.type === "add" ? "＋ " : o.type === "del" ? "− " : "  "}
            {o.text || " "}
            {"\n"}
          </span>
        ))}
      </div>
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" />;
}

export function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

/* 토스트 */
const ToastCtx = createContext<(msg: string, isError?: boolean) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; error: boolean } | null>(null);
  const show = useCallback((msg: string, isError = false) => {
    setToast({ msg, error: isError });
    setTimeout(() => setToast(null), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className={`toast ${toast.error ? "error" : ""}`}>{toast.msg}</div>}
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
