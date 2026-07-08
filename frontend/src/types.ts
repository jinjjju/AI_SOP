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
}

export interface SopVersion {
  id: number;
  sop_id: number;
  version: number;
  content: string;
  source: "new" | "revision" | "manual";
  change_detection_id: number | null;
  model_used: string;
  created_by: string;
  status: "pending_review" | "applied" | "rejected";
  created_at: string;
}

export interface SopDetail extends SopSummary {
  content: string;
  articles: Article[];
  versions: SopVersion[];
}

export interface ChangeDetection {
  id: number;
  article_id: number;
  detected_at: string;
  diff_summary: string;
  status: "open" | "draft_created" | "applied" | "dismissed";
  article: Article;
  affected_sops: SopSummary[];
}

export interface PromptTemplate {
  id: number;
  name: string;
  purpose: "generate" | "revise";
  system_prompt: string;
  user_prompt_template: string;
}

export interface AppSettings {
  default_model: string;
  default_generate_template_id: number | null;
  default_revise_template_id: number | null;
}

export interface ModelsInfo {
  models: string[];
  use_mock: boolean;
}

export interface SyncResult {
  synced: number;
  created: number;
  updated: number;
  new_detections: number;
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
