import type { Analysis, Job, JobStep, Repository, SectionState } from "../api/types";

function done<T>(data: T): SectionState<T> {
  return { status: "done", error: "", updated_at: null, data };
}

export function makeAnalysis(overrides: Partial<Analysis> = {}): Analysis {
  return {
    status: "done",
    model: "Qwen/Qwen3-8B",
    error: "",
    sections: {
      overview: done({
        summary: "A tiny Flask service that serves users over HTTP for testing purposes.",
        tech_stack: [{ name: "Flask", role: "HTTP framework" }],
        structure: [
          { path: "app/", description: "Application package" },
          { path: "README.md", description: "Docs" },
        ],
        prerequisites: ["Python 3.12"],
        how_to_run: [{ description: "Install it", command: "pip install -e ." }],
        entry_points: [
          { path: "app/main.py", description: "Creates the app", start_line: 8, end_line: 11 },
        ],
        starter_questions: ["Where are users stored?", "How are routes registered?"],
      }),
      start_here: done({
        files: [
          {
            path: "app/main.py",
            reason: "Boots the application.",
            start_line: null,
            end_line: null,
          },
          {
            path: "app/services.py",
            reason: "Holds the domain logic.",
            start_line: 10,
            end_line: 21,
          },
        ],
      }),
      glossary: done({
        terms: [
          {
            term: "UserService",
            kind: "class",
            definition: "Stores users in memory.",
            path: "app/services.py",
            start_line: 10,
            end_line: 21,
          },
          {
            term: "Settings",
            kind: "config",
            definition: "Environment-driven configuration.",
            path: null,
            start_line: null,
            end_line: null,
          },
        ],
      }),
    },
    usage: { calls: 9, prompt_tokens: 9000, completion_tokens: 1200 },
    est_cost: 0,
    waiting_since: null,
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

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
    analysis_status: "done",
    ...overrides,
  };
}
