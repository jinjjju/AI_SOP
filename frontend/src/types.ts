export interface Article {
  id: number;
  zendesk_id: number;
  title: string;
  section: string;
  updated_at: string;
  synced_at: string;
  body?: string;
}

export interface SopSummary {
  id: number;
  title: string;
  target_scope: string;
  status: "draft" | "confirmed" | "published";
  current_version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  has_pending: boolean;
  pending_since: string | null;
  inquiry_type_name: string;
}

export interface InquiryType {
  id: number;
  name: string;
  condition: string;
  articles: Article[];
  sop_count: number;
}

export interface TriageResult {
  article: Article;
  suitable: boolean;
  reason: string;
  action: "revise" | "create" | "none";
  candidate_sops: SopSummary[];
}

export interface Filters {
  in_scope_prefixes: string[];
  exclusion_keywords: string[];
  out_scope_prefixes: string[];
}

export interface SopVersion {
  id: number;
  sop_id: number;
  version: number;
  content: string;
  verification_json: string;
  test_report_json: string;
  source: "new" | "revision" | "manual" | "import";
  change_detection_id: number | null;
  model_used: string;
  created_by: string;
  status: "pending_review" | "applied" | "rejected";
  created_at: string;
}

/* verification_json 파싱 결과 */
export interface Verification {
  checked: boolean;
  warnings: { quote: string; reason: string }[];
  warning_count?: number;
  summary: string;
}

/* test_report_json / golden-test 응답 파싱 결과 */
export interface TestReport {
  ran: boolean;
  results: { question: string; passed: boolean; missing: string[]; note?: string }[];
  passed?: number;
  failed?: number;
  note?: string;
}

export interface GoldenQuestion {
  id: number;
  sop_id: number;
  question: string;
  expected_points: string;
  created_by: string;
}

export interface SopDetail extends SopSummary {
  content: string;
  content_en: string;
  articles: Article[];
  versions: SopVersion[];
  golden_questions: GoldenQuestion[];
}

/* 신규 아티클 자동 분류(triage_json) 파싱 결과 */
export interface AutoTriage {
  suitable: boolean;
  action: "revise" | "create" | "none";
  inquiry_type_id: number | null;
  inquiry_type_name: string;
  reason: string;
  confident: boolean;
  candidate_sop_ids: number[];
}

export interface ChangeDetection {
  id: number;
  article_id: number;
  detected_at: string;
  diff_summary: string;
  kind: "updated" | "new_article";
  triage_json: string;
  status: "open" | "draft_created" | "applied" | "dismissed";
  article: Article;
  affected_sops: SopSummary[];
}

export interface PromptTemplate {
  id: number;
  name: string;
  purpose: "generate" | "revise" | "triage" | "auto_triage" | "verify" | "golden_test" | "translate";
  system_prompt: string;
  user_prompt_template: string;
}

export interface AppSettings {
  default_model: string;
  light_model: string;
  default_generate_template_id: number | null;
  default_revise_template_id: number | null;
  usd_krw: number;
  weekly_budget_usd: number;
  zendesk_daily_call_limit: number;
  auto_draft_on_sync: boolean;
  auto_sync_enabled: boolean;
  sync_hour: number;
  last_sync_at: string | null;
}

export interface ModelPrice {
  model: string;
  input_per_1m: number;
  output_per_1m: number;
}

export interface UsageRow {
  actor: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  usd: number;
  krw: number;
  week_usd: number;
}

export interface UsageSummary {
  total_usd: number;
  total_krw: number;
  week_usd: number;
  week_krw: number;
  weekly_budget_usd: number;
  over_budget: boolean;
  usd_krw: number;
  by_actor: UsageRow[];
  by_model: { model: string; calls: number; input_tokens: number; output_tokens: number; usd: number; krw: number }[];
  recent: {
    id: number; actor: string; purpose: string; model: string;
    input_tokens: number; output_tokens: number; usd: number;
    sop_id: number | null; created_at: string;
  }[];
}

export interface BudgetStatus {
  week_usd: number;
  weekly_budget_usd: number;
  over_budget: boolean;
}

/* LLM 정확도 실측 지표 — 무수정 승인율 95%+가 목표 */
export interface Quality {
  revision_total: number;
  pending: number;
  applied: number;
  rejected: number;
  clean_applied: number;
  clean_apply_rate: number | null;
  target_rate: number;
  verified: number;
  warned: number;
  tested: number;
  test_failed: number;
}

export interface ModelsInfo {
  models: string[];
  use_mock: boolean;
}

export interface SyncResult {
  mode: "incremental" | "full";
  synced: number;
  created: number;
  updated: number;
  new_detections: number;
  new_article_candidates: number;
  drafts_created: number;
  skipped: number;
  budget_exhausted: boolean;
  slack_notified: boolean;
  message: string;
}

export interface ZendeskUsage {
  date: string;
  calls: number;
  limit: number;
}

export interface Manager {
  id: number;
  name: string;
  team: string;
}

export interface Activity {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  detail: string;
  created_at: string;
}

export interface TestResult {
  question: string;
  answer: string;
  model_used: string;
}
