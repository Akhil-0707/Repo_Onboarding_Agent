export type RepoStatus = "queued" | "ingesting" | "waiting_for_model" | "ready" | "failed";
export type JobStatus = "queued" | "running" | "waiting_for_model" | "done" | "failed";
export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped";

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
