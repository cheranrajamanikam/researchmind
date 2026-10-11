export type JobState = "queued" | "running" | "done" | "failed";

export interface Paper {
  id: number;
  project_id: number;
  title: string;
  authors: string;
  year: number | null;
  venue: string;
  filename: string;
  page_count: number;
  status: string;
  job_state: JobState;
  stage: string;
  progress: number;
  detail: string;
  error: string;
  chunk_count: number;
  embedded_count: number;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  question: string;
  think_first: boolean;
  paper_count: number;
  thread_count: number;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  n?: number;
  chunk_id?: number;
  paper_id: number;
  paper_title: string;
  authors: string;
  year: number | null;
  page: number;
  quote: string;
  score?: number | null;
  term_overlap?: number;
}

export type MessageStatus = "answered" | "insufficient" | "offline" | "reading" | "extractive";

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  citations: Citation[];
  meta: Record<string, unknown>;
  created_at: string;
}

export interface Thread {
  id: number;
  project_id: number;
  title: string;
  starred: boolean;
  message_count: number;
  last_status: string | null;
  last_citations: number;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}

export interface AppSettings {
  ollama_url: string;
  answer_model: string;
  embed_model: string;
  online_discovery: boolean;
  think_first_default: boolean;
  tolerance: number;
}

export interface OllamaStatus {
  url: string;
  reachable: boolean;
  version: string | null;
  models: string[];
  answer_model: string;
  embed_model: string;
  answer_model_installed: boolean;
  embed_model_installed: boolean;
  error: string | null;
}

export interface SearchResponse {
  query: string;
  requested_mode: string;
  mode: string;
  degraded: string | null;
  total: number;
  papers_searched: number;
  results: Citation[];
}

export type FieldStatus = "agree" | "verify" | "confirmed" | "edited" | "rejected" | "not_reported";
export interface PassValue { value?: string; quote?: string; page?: number | null }
export interface FieldRow {
  id: number;
  name: string;
  value: string;
  quote: string;
  page: number | null;
  status: FieldStatus;
  pass_a: PassValue;
  pass_b: PassValue;
}
export interface PaperFields {
  paper_id: number;
  fields: FieldRow[];
  counts: { total: number; reviewed: number; verify: number; agree: number };
  agreement_rate: number | null;
  accepted: number;
}
export interface ProjectExtraction {
  papers: (PaperFields & { paper: { id: number; title: string; label: string; status: string } })[];
  disclaimer: string;
}

export interface DiffCell { value: string; quote: string; page: number | null; status: string; field_id: number | null }
export interface DiffResponse {
  papers: { id: number; title: string; label: string; year: number | null }[];
  rows: { field: string; cells: DiffCell[]; differs: boolean; has_missing: boolean }[];
  note: string;
  disclaimer: string;
}

export interface ConflictSide {
  paper_id: number; paper_title: string; label: string; value: number; unit: string; display: string;
  quote: string; page: number | null; method: string;
}
export interface Conflict {
  n: number;
  key: { method: string; dataset: string; metric: string };
  title: string;
  relative_difference_pct: number;
  a: ConflictSide;
  b: ConflictSide;
  setup_differences: { field: string; a: string; b: string; a_page: number | null; b_page: number | null }[];
  possible_reasons: string[];
  candidate_experiment: string;
}
export interface ContradictionsResponse { tolerance: number; items: Conflict[]; note: string; disclaimer: string }

export interface NumericSide { value: string; section: string; page: number; quote: string; source: string }
export interface NumericResponse {
  paper_id: number; title: string; mentions_checked: number; note: string; disclaimer: string;
  mismatches: { label: string; metric: string; summary: string; a: NumericSide; b: NumericSide }[];
}
export interface ReproItem { item: string; status: "reported" | "partial" | "missing"; detail: string; page: number | null; quote: string }
export interface ReproResponse {
  paper_id: number; title: string; items: ReproItem[]; counts: Record<string, number>; note: string; disclaimer: string;
}

export interface OverclaimFinding {
  start: number; end: number; sentence: string;
  wording: { term: string; kind: string; qualifier: string }[];
  evidence: Citation[];
  facts: { label: string; value: string }[];
  questions: string[];
}
export interface OverclaimResponse { findings: OverclaimFinding[]; sentences_checked: number; note: string; disclaimer: string }

export interface AuditRow {
  marker: string;
  citing_sentence: string;
  location: string;
  citing_paper?: { paper_id: number; title: string };
  cited: { paper_id: number; label: string; title: string };
  passage: Citation & { term_overlap: number };
  overlap_label: string;
}
export interface AuditResponse { items: AuditRow[]; note: string; disclaimer: string }

export interface Candidate {
  rank: number; title: string; authors: string; year: number | null; venue: string; url: string; source: string;
  why: string; why_source: string; tags: string[]; score: number; paper_id: number | null; page: number | null;
  abstract_available: boolean;
}
export interface Receipt {
  id: number; project_id: number; kind: string; input_text: string; queries: string[];
  sources_searched: string[]; sources_not_searched: string[];
  counts: Record<string, number | string>;
  results: Candidate[]; online: boolean; created_at: string; notice: string;
  result_count?: number; disclaimer?: string;
}
export interface PriorWorkResponse {
  receipt: Receipt;
  closest: (Candidate & { overlap: { shared_terms: string[]; method_statement: string; datasets: string[] } })[];
  notices: string[];
  disclaimer: string;
}

export interface ReadingItem {
  id: number; project_id: number; title: string; authors: string; year: number | null; venue: string; url: string;
  why: string; tags: string[]; status: "to_read" | "reading" | "read"; note: string; paper_id: number | null; created_at: string;
}

export interface GapStatement { paper_id: number; paper_title: string; label: string; page: number; quote: string; kind: string }
export interface GapCluster {
  n: number; label: string; label_terms: string[]; paper_count: number; statement_count: number; kinds: string[];
  statements: GapStatement[];
}
export interface GapResponse {
  clusters: GapCluster[]; method: string; statements_total: number; threshold: number | null;
  note?: string; disclaimer: string; label: string;
}

export interface EvalMetrics {
  k: number; recall_at_k: number | null; mrr: number | null; citation_faithfulness: number | null;
  refusal_accuracy: number | null; false_refusal_rate: number | null; answerable: number; unanswerable: number;
  papers: number; retrieval_mode: string; answer_mode: string;
  judge: { used: boolean; judged: number; supported: number };
  extraction: null | { overall: number; n_fields: number; n_papers: number; by_field: Record<string, number> };
}
export interface EvalDetail {
  question: string; answerable: boolean; behavior: string; status_raw: string; recall_rank: number | null;
  citations_valid: string; faithfulness: number | null; result: "Pass" | "Review";
}
export interface EvalRun {
  id: number; project_id: number; created_at: string; mode: string; n_questions: number; metrics: EvalMetrics;
  details?: EvalDetail[];
}

export interface Alert {
  id: number; decision_id: number; paper_id: number; message: string; resolved: boolean; created_at: string;
  quote: { paper_id: number; label: string; page: number | null; quote: string; value: string;
    baseline: { paper_id: number; label: string; page: number | null; quote: string; value: string } };
  decision_title?: string;
}
export interface Decision {
  id: number; project_id: number; title: string; rationale: string; method: string; dataset: string; metric: string;
  evidence: { paper_id: number; page: number | null; quote: string; label: string; paper_title: string }[];
  created_at: string; alerts: Alert[]; open_alerts: number;
}

export interface EvidenceItem {
  paper_id: number; label: string; value: string; page: number | null; quote: string;
}
export interface PredictionItem { statement: string; field: string; evidence: EvidenceItem[]; your_sentence?: string }
export interface PredictionResult {
  id: number; created_at: string; prediction: string; reflection?: string;
  matched: PredictionItem[]; possibly_missed: PredictionItem[]; check_reading: PredictionItem[];
  papers: { id: number; label: string; title: string }[]; note: string;
}

export interface ProvMark { start: number; end: number; text: string }
export interface ProvEvent { id: number; kind: "created" | "edited" | "ai_marked" | "ai_unmarked"; passage: string; words: number; created_at: string }
export interface ProvDoc {
  id: number; project_id: number; title: string; content: string; marks: ProvMark[]; words: number; marked_words: number;
  updated_at: string; created_at: string; note: string; events?: ProvEvent[];
}

export interface Overview {
  project: { id: number; name: string; question: string; think_first: boolean };
  stats: { papers: number; pages: number; fields_extracted: number; awaiting_review: number };
  index: { chunks: number; embedded: number };
  extraction_health: { agree: number; verify: number; confirmed: number; not_reported: number };
  jobs: Paper[];
  recent_papers: Paper[];
  recent_thread: { id: number; title: string; updated_at: string } | null;
  alerts: Alert[];
  contradictions: Conflict[];
  contradiction_total: number;
  reading: ReadingItem[];
  evaluation: { id: number; created_at: string; metrics: EvalMetrics }[];
  gaps: { n: number; label: string; paper_count: number; statement_count: number }[];
  privacy: { online_discovery: boolean; answer_model: string; embed_model: string };
}

export interface Job extends Paper {}
