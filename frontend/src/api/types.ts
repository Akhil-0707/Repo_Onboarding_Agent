export type RepoStatus = "queued" | "ingesting" | "waiting_for_model" | "ready" | "failed";
export type JobStatus = "queued" | "running" | "waiting_for_model" | "done" | "failed";
export type StepStatus = "pending" | "running" | "waiting" | "done" | "failed" | "skipped";

export interface LogEntry {
  ts: string;
  level: "info" | "warning" | "error";
  message: string;
}

export interface JobStep {
  key: string;
  label: string;
  weight: number;
  status: StepStatus;
  progress: number;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  logs: LogEntry[];
}

export interface JobSummary {
  id: string;
  status: JobStatus;
  progress: number;
  error: string;
  created_at: string;
  finished_at: string | null;
}

export interface Job extends JobSummary {
  steps: JobStep[];
  started_at: string | null;
}

export interface RepoStats {
  files?: number;
  lines?: number;
  bytes?: number;
  chunks?: number;
  symbols?: number;
  dependency_edges?: number;
  external_dependencies?: number;
  skipped?: Record<string, number>;
}

export interface RepoDetection {
  manifests?: string[];
  package_managers?: string[];
  scripts?: Record<string, string>;
  go_module?: string | null;
  primary_language?: string | null;
}

export interface Repository {
  id: string;
  owner: string;
  name: string;
  full_name: string;
  url: string;
  description: string;
  default_branch: string;
  commit_sha: string;
  private: boolean;
  status: RepoStatus;
  error: string;
  stats: RepoStats;
  languages: Record<string, number>;
  frameworks: string[];
  detection: RepoDetection;
  created_at: string;
  ingested_at: string | null;
  latest_job: JobSummary | null;
  analysis_status: AnalysisStatus;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AnalysisStart {
  repository: Repository;
  job: Job | null;
  created: boolean;
  cached: boolean;
}

export interface FileEntry {
  path: string;
  language: string;
  size: number;
  lines: number;
}

export interface SymbolInfo {
  name: string;
  kind: string;
  start_line: number;
  end_line: number;
  parent: string | null;
}

export interface FileContent extends FileEntry {
  start_line: number;
  end_line: number;
  content: string;
  symbols: SymbolInfo[];
  github_url: string;
}

// --- AI analysis ---------------------------------------------------------------------------

export type AnalysisStatus =
  "pending" | "running" | "waiting_for_model" | "done" | "partial" | "failed";

export type SectionStatus = "pending" | "running" | "done" | "failed";

export interface SectionState<T> {
  status: SectionStatus;
  error: string;
  updated_at: string | null;
  data: T | null;
}

export interface Overview {
  summary: string;
  tech_stack: { name: string; role: string }[];
  structure: { path: string; description: string }[];
  prerequisites: string[];
  how_to_run: { description: string; command: string | null }[];
  entry_points: {
    path: string;
    description: string;
    start_line: number | null;
    end_line: number | null;
  }[];
  starter_questions: string[];
}

export interface StartHere {
  files: { path: string; reason: string; start_line: number | null; end_line: number | null }[];
}

export interface GlossaryTerm {
  term: string;
  kind: "concept" | "class" | "function" | "module" | "config" | "other";
  definition: string;
  path: string | null;
  start_line: number | null;
  end_line: number | null;
}

export interface Glossary {
  terms: GlossaryTerm[];
}

export type ModuleKind =
  "entry" | "core" | "service" | "data" | "ui" | "config" | "util" | "external" | "test" | "other";

export interface ArchitectureModule {
  id: string;
  name: string;
  kind: ModuleKind;
  paths: string[];
  description: string;
}

export interface ArchitectureEdge {
  source: string;
  target: string;
  label: string | null;
  /** Added from the import graph rather than written by the model. */
  derived: boolean;
  imports: number;
}

export interface Architecture {
  summary: string;
  modules: ArchitectureModule[];
  edges: ArchitectureEdge[];
  /** Rendered on the server from the verified graph. */
  mermaid: string;
}

export type TourStepKind =
  | "intro"
  | "entry_point"
  | "flow_trace"
  | "core_logic"
  | "data_model"
  | "config"
  | "testing"
  | "other";

export interface TourStep {
  title: string;
  kind: TourStepKind;
  path: string;
  start_line: number | null;
  end_line: number | null;
  symbol: string | null;
  explanation: string;
}

export interface Tour {
  intro: string;
  steps: TourStep[];
}

export interface Analysis {
  status: AnalysisStatus;
  model: string;
  error: string;
  sections: {
    overview: SectionState<Overview>;
    architecture: SectionState<Architecture>;
    start_here: SectionState<StartHere>;
    tour: SectionState<Tour>;
    glossary: SectionState<Glossary>;
  };
  usage: {
    calls?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    latency_ms?: number;
  };
  est_cost: number;
  waiting_since: string | null;
  started_at: string | null;
  finished_at: string | null;
}
