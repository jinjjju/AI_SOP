import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, clearUser, getUser, setUser } from "./api/client";
import type { CurrentUser } from "./api/client";
import { Spinner, useToast } from "./components/ui";
import type { BudgetStatus, Manager, ModelsInfo } from "./types";
import Dashboard from "./pages/Dashboard";
import ChangeDetail from "./pages/ChangeDetail";
import SopGenerate from "./pages/SopGenerate";
import SopList from "./pages/SopList";
import SopDetail from "./pages/SopDetail";
import History from "./pages/History";
import InquiryTypes from "./pages/InquiryTypes";
import Settings from "./pages/Settings";

const NAV = [
  { to: "/", icon: "◧", label: "대시보드" },
  { to: "/generate", icon: "✦", label: "SOP 생성" },
  { to: "/inquiry", icon: "❖", label: "문의유형·검수" },
  { to: "/sops", icon: "▤", label: "AI SOP 관리" },
  { to: "/history", icon: "≣", label: "히스토리" },
  { to: "/settings", icon: "⚙", label: "설정" },
];

const TITLES: [RegExp, string][] = [
  [/^\/$/, "대시보드"],
  [/^\/generate/, "새 AI SOP 생성"],
  [/^\/inquiry/, "문의유형 · 아티클 검수"],
  [/^\/sops\/\d+/, "AI SOP 상세"],
  [/^\/sops/, "AI SOP 관리"],
  [/^\/changes/, "아티클 변경 감지"],
  [/^\/history/, "활동 히스토리"],
  [/^\/settings/, "설정"],
];

function JoinScreen({ onJoined }: { onJoined: (u: CurrentUser) => void }) {
  const [name, setName] = useState("");
  const [team, setTeam] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const join = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const m = await api.post<Manager>("/api/join", { name: name.trim(), team: team.trim() });
      const user = { name: m.name, team: m.team };
      setUser(user);
      onJoined(user);
    } catch (e) {
      toast((e as Error).message, true);
      setBusy(false);
    }
  };

  return (
    <div className="layout" style={{ alignItems: "center", justifyContent: "center", background: "var(--bg-raised)" }}>
      <div className="card" style={{ width: 400, padding: 32, background: "var(--bg)" }}>
        <div className="brand" style={{ padding: "0 0 14px" }}>
          <div className="logo">S</div>
          <div>
            AI SOP Studio
            <small>Zendesk 기반 SOP 어드민</small>
          </div>
        </div>
        <p className="sub" style={{ margin: "0 0 20px" }}>
          닉네임과 팀명만 입력하면 담당자로 가입됩니다.
          SOP 생성 · 검토 · 승인 활동이 이 이름으로 기록됩니다.
        </p>
        <label className="field">
          <span>닉네임 *</span>
          <input
            className="input"
            placeholder="예: 조엘"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && join()}
            autoFocus
          />
        </label>
        <label className="field">
          <span>팀명</span>
          <input
            className="input"
            placeholder="예: PA Automation"
            value={team}
            onChange={(e) => setTeam(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && join()}
          />
        </label>
        <button className="btn primary" style={{ width: "100%" }} onClick={join} disabled={!name.trim() || busy}>
          {busy ? <Spinner /> : null} 가입하고 시작하기
        </button>
        <p style={{ color: "var(--text-faint)", fontSize: 12, marginTop: 14, marginBottom: 0 }}>
          이미 가입한 닉네임을 입력하면 그 계정으로 이어서 사용합니다.
        </p>
      </div>
    </div>
  );
}

export default function App() {
  const { pathname } = useLocation();
  const [info, setInfo] = useState<ModelsInfo | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [user, setUserState] = useState<CurrentUser | null>(getUser());

  useEffect(() => {
    api.get<ModelsInfo>("/api/models").then(setInfo).catch(() => {});
  }, []);

  useEffect(() => {
    // 페이지 이동마다 주간 예산 상태 갱신 (초과 시 상단 노티)
    api.get<BudgetStatus>("/api/usage/status").then(setBudget).catch(() => {});
  }, [pathname]);

  if (!user) return <JoinScreen onJoined={setUserState} />;

  const title = TITLES.find(([re]) => re.test(pathname))?.[1] ?? "";

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">S</div>
          <div>
            AI SOP Studio
            <small>Zendesk 기반 SOP 어드민</small>
          </div>
        </div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
          >
            <span className="icon">{n.icon}</span>
            {n.label}
          </NavLink>
        ))}
        <div className="sidebar-footer">
          {info?.use_mock ? "Mock 모드 (로컬 개발)" : "Live 모드"} · MVP v0.3
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>{title}</h1>
          <div className="topbar-meta">
            {budget?.over_budget && (
              <NavLink to="/settings" className="chip red" title="설정에서 사용량 상세 확인">
                ⚠ 주간 예산 초과 ${budget.week_usd.toFixed(2)} / ${budget.weekly_budget_usd}
              </NavLink>
            )}
            {info?.use_mock && <span className="chip yellow">MOCK</span>}
            {info && <span className="chip">{info.models[0]} 외 {info.models.length - 1}종</span>}
            <span className="chip accent" title="현재 담당자 — 모든 작업이 이 이름으로 기록됩니다">
              👤 {user.name}{user.team ? ` · ${user.team}` : ""}
            </span>
            <button
              className="btn small"
              onClick={() => {
                clearUser();
                setUserState(null);
              }}
            >
              계정 변경
            </button>
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/generate" element={<SopGenerate />} />
            <Route path="/inquiry" element={<InquiryTypes />} />
            <Route path="/sops" element={<SopList />} />
            <Route path="/sops/:id" element={<SopDetail />} />
            <Route path="/changes/:id" element={<ChangeDetail />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
