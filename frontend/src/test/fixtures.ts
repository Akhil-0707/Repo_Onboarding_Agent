import type { Job, JobStep, Repository } from "../api/types";

export function makeStep(overrides: Partial<JobStep> = {}): JobStep {
  return {
    key: "clone",
    label: "Clone repository",
    weight: 15,
    status: "pending",
    progress: 0,
    message: "",
    started_at: null,
    finished_at: null,
    logs: [],
    ...overrides,
  };
}

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job1",
    status: "running",
    progress: 10,
    error: "",
    created_at: "2026-10-01T00:00:00Z",
    started_at: "2026-10-01T00:00:01Z",
    finished_at: null,
    steps: [
      makeStep({ key: "clone", label: "Clone repository", status: "running" }),
      makeStep({ key: "parse", label: "Parse code" }),
    ],
    ...overrides,
  };
}

export function makeRepo(overrides: Partial<Repository> = {}): Repository {
  return {
    id: "repo1",
    owner: "acme",
    name: "tool",
    full_name: "acme/tool",
    url: "https://github.com/acme/tool",
    description: "A tool",
    default_branch: "main",
    commit_sha: "abcdef1234567890abcdef1234567890abcdef12",
    private: false,
    status: "ready",
    error: "",
    stats: { files: 12, lines: 900, symbols: 40, dependency_edges: 9, chunks: 30 },
    languages: { python: 90, shell: 10 },
    frameworks: ["Flask"],
    detection: { scripts: { "make test": "" } },
    created_at: "2026-10-01T00:00:00Z",
    ingested_at: "2026-10-01T00:01:00Z",
    latest_job: null,
    ...overrides,
  };
}
