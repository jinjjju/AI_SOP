import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { Spinner, useToast } from "../components/ui";
import type { AppSettings, Filters, Manager, ModelPrice, ModelsInfo, PromptTemplate, UsageSummary } from "../types";

const usd = (v: number) => `$${v.toFixed(v >= 1 ? 2 : 4)}`;
const krw = (v: number) => `₩${Math.round(v).toLocaleString("ko-KR")}`;

export default function Settings() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const toast = useToast();

  const load = useCallback(() => {
    api.get<AppSettings>("/api/settings").then(setSettings).catch(() => {});
    api.get<ModelsInfo>("/api/models").then((m) => setModels(m.models)).catch(() => {});
    api.get<PromptTemplate[]>("/api/prompts").then(setTemplates).catch(() => {});
  }, []);

  useEffect(load, [load]);

  if (!settings) return <div className="empty">불러오는 중…</div>;

  const update = async (patch: Partial<AppSettings>) => {
    try {
      const next = await api.put<AppSettings>("/api/settings", patch);
      setSettings(next);
      toast("기본 설정이 저장되었습니다. 이후 생성부터 자동 적용됩니다.");
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  const byPurpose = (p: string) => templates.filter((t) => t.purpose === p);

  return (
    <div className="content-narrow">
      <div className="card">
        <h3>기본 생성 설정</h3>
        <p className="sub" style={{ marginTop: 0 }}>
          SOP 생성 화면에서는 담당자가 스코프만 입력하며, 아래 기본값이 자동으로 적용됩니다.
        </p>
        <div className="grid-2" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
          <label className="field">
            <span>기본 모델</span>
            <select
              className="select"
              value={settings.default_model}
              onChange={(e) => update({ default_model: e.target.value })}
            >
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>신규 생성 프롬프트</span>
            <select
              className="select"
              value={settings.default_generate_template_id ?? ""}
              onChange={(e) => update({ default_generate_template_id: Number(e.target.value) })}
            >
              {byPurpose("generate").map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>보완(개정) 프롬프트</span>
            <select
              className="select"
              value={settings.default_revise_template_id ?? ""}
              onChange={(e) => update({ default_revise_template_id: Number(e.target.value) })}
            >
              {byPurpose("revise").map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="section-title">아티클 수집 필터 (article_filters.json)</div>
      <FiltersCard />

      <div className="section-title">LLM 사용량 · 비용</div>
      <UsageCard />

      <ManagerCard />

      <div className="section-title">프롬프트 템플릿</div>
      {templates.map((t) => (
        <TemplateEditor key={t.id} template={t} onSaved={load} />
      ))}
      <NewTemplate onSaved={load} />
    </div>
  );
}

/* 키워드 칩 입력 — 쉼표/엔터로 추가, 여러 개 붙여넣기(쉼표·줄바꿈 혼용) 자동 분리, ✕로 개별 삭제 */
function TagInput({
  label,
  hint,
  values,
  onChange,
}: {
  label: string;
  hint: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const [input, setInput] = useState("");

  const add = (raw: string) => {
    const parts = raw.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    if (parts.length === 0) return;
    const next = [...values];
    for (const p of parts) if (!next.includes(p)) next.push(p);
    onChange(next);
    setInput("");
  };

  return (
    <label className="field">
      <span>
        {label} <strong style={{ color: "var(--text)" }}>({values.length})</strong> — {hint}
      </span>
      <div
        className="input"
        style={{ display: "flex", flexWrap: "wrap", gap: 6, minHeight: 76, alignContent: "flex-start", cursor: "text" }}
        onClick={(e) => (e.currentTarget.querySelector("input") as HTMLInputElement)?.focus()}
      >
        {values.map((v) => (
          <span key={v} className="chip" style={{ gap: 4 }}>
            {v}
            <span
              style={{ cursor: "pointer", color: "var(--text-faint)" }}
              onClick={(e) => {
                e.stopPropagation();
                onChange(values.filter((x) => x !== v));
              }}
            >
              ✕
            </span>
          </span>
        ))}
        <input
          style={{ border: "none", outline: "none", background: "transparent", flex: 1, minWidth: 120, font: "inherit", color: "var(--text)" }}
          placeholder={values.length === 0 ? "키워드 입력 후 Enter (쉼표로 여러 개 가능)" : ""}
          value={input}
          onChange={(e) => {
            if (e.target.value.includes(",")) add(e.target.value);
            else setInput(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add(input);
            } else if (e.key === "Backspace" && !input && values.length > 0) {
              onChange(values.slice(0, -1));
            }
          }}
          onPaste={(e) => {
            e.preventDefault();
            add(input + e.clipboardData.getData("text"));
          }}
          onBlur={() => input.trim() && add(input)}
        />
      </div>
    </label>
  );
}

function FiltersCard() {
  const [filters, setFilters] = useState<Filters | null>(null);
  const [saved, setSaved] = useState<Filters | null>(null);
  const toast = useToast();

  useEffect(() => {
    api.get<Filters>("/api/filters").then((f) => {
      setFilters(f);
      setSaved(f);
    }).catch(() => {});
  }, []);

  if (!filters) return null;

  const dirty = JSON.stringify(filters) !== JSON.stringify(saved);
  const save = async () => {
    try {
      const next = await api.put<Filters>("/api/filters", filters);
      setFilters(next);
      setSaved(next);
      toast("수집 필터가 저장되었습니다. 다음 동기화부터 적용됩니다.");
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="card">
      <p className="sub" style={{ marginTop: 0 }}>
        아티클 동기화 시 제목 기준으로 수집 여부를 결정합니다. 키워드는 <strong>Enter 또는 쉼표</strong>로
        추가하고 (쉼표·줄바꿈 섞인 목록 붙여넣기 가능), 우선순위는 <strong>필수 수집 → 제외</strong> 순입니다.
        파일(<code>backend/article_filters.json</code>)을 직접 수정해도 동일하게 동작합니다.
      </p>
      <TagInput
        label="in_scope_prefixes"
        hint="이 접두어로 시작하면 반드시 수집 (최우선)"
        values={filters.in_scope_prefixes}
        onChange={(v) => setFilters({ ...filters, in_scope_prefixes: v })}
      />
      <TagInput
        label="exclusion_keywords"
        hint="제목에 포함되면 제외"
        values={filters.exclusion_keywords}
        onChange={(v) => setFilters({ ...filters, exclusion_keywords: v })}
      />
      <TagInput
        label="out_scope_prefixes"
        hint="이 접두어로 시작하면 제외"
        values={filters.out_scope_prefixes}
        onChange={(v) => setFilters({ ...filters, out_scope_prefixes: v })}
      />
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn primary small" disabled={!dirty} onClick={save}>필터 저장</button>
      </div>
    </div>
  );
}

function UsageCard() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [prices, setPrices] = useState<ModelPrice[]>([]);
  const [usdKrw, setUsdKrw] = useState("");
  const [budget, setBudget] = useState("");
  const toast = useToast();

  const load = useCallback(() => {
    api.get<UsageSummary>("/api/usage").then((u) => {
      setUsage(u);
      setUsdKrw(String(u.usd_krw));
      setBudget(String(u.weekly_budget_usd));
    }).catch(() => {});
    api.get<ModelPrice[]>("/api/prices").then(setPrices).catch(() => {});
  }, []);
  useEffect(load, [load]);

  if (!usage) return null;

  const saveMoney = async () => {
    try {
      await api.put("/api/settings", { usd_krw: Number(usdKrw), weekly_budget_usd: Number(budget) });
      toast("환율/예산이 저장되었습니다.");
      load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <>
      {usage.over_budget && (
        <div className="card" style={{ borderColor: "var(--red)", background: "var(--red-bg)", marginBottom: 16 }}>
          ⚠ <strong>주간 예산 초과</strong> — 최근 7일 사용액 {usd(usage.week_usd)}이
          설정된 예산 {usd(usage.weekly_budget_usd)}을 넘었습니다.
        </div>
      )}

      <div className="grid-cards" style={{ marginBottom: 16 }}>
        <div className="stat">
          <div className="num" style={{ color: usage.over_budget ? "var(--red)" : undefined }}>
            {usd(usage.week_usd)}
          </div>
          <div className="label">최근 7일 사용액 ({krw(usage.week_krw)}) / 예산 {usd(usage.weekly_budget_usd)}</div>
        </div>
        <div className="stat">
          <div className="num">{usd(usage.total_usd)}</div>
          <div className="label">전체 누적 ({krw(usage.total_krw)})</div>
        </div>
      </div>

      <div className="card">
        <h3>담당자별 사용량</h3>
        {usage.by_actor.length === 0 ? (
          <p className="sub">아직 LLM 호출 기록이 없습니다.</p>
        ) : (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ color: "var(--text-dim)", textAlign: "left" }}>
                <th style={{ padding: "6px 4px" }}>담당자</th>
                <th>호출</th>
                <th>입력 토큰</th>
                <th>출력 토큰</th>
                <th>최근 7일</th>
                <th>누적 (USD)</th>
                <th>누적 (KRW)</th>
              </tr>
            </thead>
            <tbody>
              {usage.by_actor.map((r) => (
                <tr key={r.actor} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "7px 4px", fontWeight: 500 }}>👤 {r.actor}</td>
                  <td>{r.calls}</td>
                  <td>{r.input_tokens.toLocaleString()}</td>
                  <td>{r.output_tokens.toLocaleString()}</td>
                  <td>{usd(r.week_usd)}</td>
                  <td>{usd(r.usd)}</td>
                  <td>{krw(r.krw)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {usage.by_model.length > 0 && (
          <p className="sub" style={{ marginBottom: 0 }}>
            모델별: {usage.by_model.map((m) => `${m.model} ${m.calls}회 · ${usd(m.usd)}`).join("  |  ")}
          </p>
        )}
      </div>

      <div className="card">
        <h3>모델 단가 · 환율 · 예산</h3>
        <p className="sub" style={{ marginTop: 0 }}>
          단가(USD/100만 토큰)를 수정하면 과거 사용분을 포함한 모든 비용 표시에 즉시 반영됩니다.
          출처: <a href="https://ai.google.dev/gemini-api/docs/pricing?hl=ko" target="_blank" rel="noreferrer" style={{ color: "var(--accent-strong)" }}>Gemini API 가격</a>
        </p>
        {prices.map((p) => (
          <PriceRow key={p.model} price={p} onSaved={load} />
        ))}
        <div className="row wrap" style={{ marginTop: 14, alignItems: "flex-end" }}>
          <label className="field" style={{ marginBottom: 0, width: 160 }}>
            <span>환율 (₩ / $1)</span>
            <input className="input" type="number" value={usdKrw} onChange={(e) => setUsdKrw(e.target.value)} />
          </label>
          <label className="field" style={{ marginBottom: 0, width: 180 }}>
            <span>주간 예산 (USD, 초과 시 노티)</span>
            <input className="input" type="number" step="0.5" value={budget} onChange={(e) => setBudget(e.target.value)} />
          </label>
          <button className="btn small" onClick={saveMoney}>저장</button>
        </div>
      </div>
    </>
  );
}

function PriceRow({ price, onSaved }: { price: ModelPrice; onSaved: () => void }) {
  const [inp, setInp] = useState(String(price.input_per_1m));
  const [out, setOut] = useState(String(price.output_per_1m));
  const toast = useToast();
  const dirty = Number(inp) !== price.input_per_1m || Number(out) !== price.output_per_1m;

  const save = async () => {
    try {
      await api.put(`/api/prices/${price.model}`, { input_per_1m: Number(inp), output_per_1m: Number(out) });
      toast(`'${price.model}' 단가가 저장되었습니다. 모든 비용 계산에 반영됩니다.`);
      onSaved();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="row wrap" style={{ padding: "6px 0", alignItems: "flex-end" }}>
      <span className="chip accent" style={{ minWidth: 180, justifyContent: "center" }}>{price.model}</span>
      <label className="field" style={{ marginBottom: 0, width: 150 }}>
        <span>입력 $/1M</span>
        <input className="input" type="number" step="0.01" value={inp} onChange={(e) => setInp(e.target.value)} />
      </label>
      <label className="field" style={{ marginBottom: 0, width: 150 }}>
        <span>출력 $/1M</span>
        <input className="input" type="number" step="0.01" value={out} onChange={(e) => setOut(e.target.value)} />
      </label>
      <button className="btn small" disabled={!dirty} onClick={save}>저장</button>
    </div>
  );
}

function ManagerCard() {
  const [managers, setManagers] = useState<Manager[]>([]);
  const toast = useToast();

  const load = useCallback(() => {
    api.get<Manager[]>("/api/managers").then(setManagers).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const remove = async (m: Manager) => {
    if (!confirm(`'${m.name}' 담당자를 삭제할까요? 기존 활동 이력은 그대로 남습니다.`)) return;
    try {
      await api.del(`/api/managers/${m.id}`);
      toast("삭제되었습니다.");
      load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>가입된 담당자</h3>
      <p className="sub" style={{ marginTop: 0 }}>
        첫 접속 시 닉네임/팀명으로 가입한 담당자 목록입니다. 가입된 담당자만 SOP 생성·승인·발행을
        수행할 수 있으며, 모든 활동이 이름으로 기록됩니다.
      </p>
      <div className="row wrap">
        {managers.map((m) => (
          <span key={m.id} className="chip">
            👤 {m.name}{m.team ? ` · ${m.team}` : ""}
            <span
              style={{ cursor: "pointer", color: "var(--text-faint)", marginLeft: 2 }}
              title="삭제 (활동 이력은 보존)"
              onClick={() => remove(m)}
            >
              ✕
            </span>
          </span>
        ))}
        {managers.length === 0 && <span className="sub">아직 가입한 담당자가 없습니다.</span>}
      </div>
    </div>
  );
}

function TemplateEditor({ template, onSaved }: { template: PromptTemplate; onSaved: () => void }) {
  const [form, setForm] = useState(template);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const dirty = JSON.stringify(form) !== JSON.stringify(template);

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/api/prompts/${template.id}`, {
        name: form.name,
        purpose: form.purpose,
        system_prompt: form.system_prompt,
        user_prompt_template: form.user_prompt_template,
      });
      toast("템플릿이 저장되었습니다.");
      onSaved();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="article-acc">
      <summary>
        {template.purpose === "generate" ? "✦" : template.purpose === "revise" ? "♺" : "⚖"} {template.name}
        <span className="chip" style={{ marginLeft: "auto" }}>
          {template.purpose === "generate" ? "신규 생성용" : template.purpose === "revise" ? "보완용" : "판단용(링크 검수)"}
        </span>
      </summary>
      <div style={{ padding: "4px 14px 14px" }}>
        <TemplateFields form={form} setForm={setForm} />
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn primary small" disabled={!dirty || busy} onClick={save}>
            {busy ? <Spinner /> : null} 저장
          </button>
        </div>
      </div>
    </details>
  );
}

function NewTemplate({ onSaved }: { onSaved: () => void }) {
  const empty: Omit<PromptTemplate, "id"> = {
    name: "",
    purpose: "generate",
    system_prompt: "",
    user_prompt_template: "",
  };
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const create = async () => {
    setBusy(true);
    try {
      await api.post("/api/prompts", form);
      toast("새 템플릿이 추가되었습니다. 기본 설정에서 선택하면 적용됩니다.");
      setForm(empty);
      setOpen(false);
      onSaved();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button className="btn" style={{ marginTop: 4 }} onClick={() => setOpen(true)}>
        ＋ 새 프롬프트 템플릿
      </button>
    );
  }
  return (
    <div className="card">
      <h3>새 프롬프트 템플릿</h3>
      <TemplateFields form={form} setForm={setForm} />
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn small" onClick={() => setOpen(false)}>취소</button>
        <button className="btn primary small" disabled={!form.name.trim() || busy} onClick={create}>
          {busy ? <Spinner /> : null} 추가
        </button>
      </div>
    </div>
  );
}

function TemplateFields<T extends Omit<PromptTemplate, "id">>({
  form,
  setForm,
}: {
  form: T;
  setForm: (f: T) => void;
}) {
  return (
    <>
      <div className="grid-2">
        <label className="field">
          <span>이름</span>
          <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="field">
          <span>용도</span>
          <select
            className="select"
            value={form.purpose}
            onChange={(e) => setForm({ ...form, purpose: e.target.value as T["purpose"] })}
          >
            <option value="generate">신규 생성용</option>
            <option value="revise">보완용</option>
            <option value="triage">판단용(링크 검수)</option>
          </select>
        </label>
      </div>
      <label className="field">
        <span>시스템 프롬프트</span>
        <textarea
          className="textarea mono"
          value={form.system_prompt}
          onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
        />
      </label>
      <label className="field">
        <span>유저 프롬프트 템플릿 — 플레이스홀더: {"{scope}"} {"{articles}"} {"{current_sop}"} · 판단용: {"{inquiry_type}"} {"{condition}"} {"{existing_sops}"}</span>
        <textarea
          className="textarea mono"
          style={{ minHeight: 160 }}
          value={form.user_prompt_template}
          onChange={(e) => setForm({ ...form, user_prompt_template: e.target.value })}
        />
      </label>
    </>
  );
}
