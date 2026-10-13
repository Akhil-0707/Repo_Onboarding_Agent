import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { ApiError } from "../api/client";
import { useRemoveRepository, useRepositories, useStartAnalysis } from "../api/repos";
import type { Repository } from "../api/types";
import { LanguageBar } from "../components/LanguageBar";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { useAuth } from "../lib/auth";
import { parseGitHubUrl } from "../lib/github";
import { repoHref } from "../lib/navigation";

function NewAnalysisForm({ initial }: { initial: string }) {
  const navigate = useNavigate();
  const start = useStartAnalysis();
  const [value, setValue] = useState(initial ? `https://github.com/${initial}` : "");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const ref = parseGitHubUrl(value);
    if (!ref) {
      setError("Enter a GitHub repository URL like https://github.com/owner/repo");
      return;
    }
    setError(null);
    try {
      const result = await start.mutateAsync(`https://github.com/${ref.owner}/${ref.name}`);
      navigate(repoHref(result.repository));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the analysis.");
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" noValidate>
      <label htmlFor="new-repo-url" className="sr-only">
        GitHub repository URL
      </label>
      <input
        id="new-repo-url"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="https://github.com/owner/repo"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "new-repo-error" : undefined}
        className="field flex-1"
      />
      <button type="submit" disabled={start.isPending} className="btn btn-primary px-5">
        {start.isPending ? "Starting…" : "Analyze"}
      </button>
      {error && (
        <p
          id="new-repo-error"
          role="alert"
          className="animate-fade-in text-sm text-rose-600 sm:basis-full dark:text-rose-400"
        >
          {error}
        </p>
      )}
    </form>
  );
}

/** One badge for the whole card: ingestion first, then how far the AI analysis got. */
function RepoBadge({ repo }: { repo: Repository }) {
  if (repo.status !== "ready") return <StatusBadge status={repo.status} />;
  switch (repo.analysis_status) {
    case "running":
      return <StatusBadge status="running" label="Analyzing" />;
    case "waiting_for_model":
      return <StatusBadge status="waiting_for_model" />;
    case "partial":
      return <StatusBadge status="partial" label="Partly analyzed" />;
    case "failed":
      return <StatusBadge status="failed" label="Analysis failed" />;
    default:
      return <StatusBadge status="ready" />;
  }
}

function RepoCard({ repo }: { repo: Repository }) {
  const remove = useRemoveRepository();
  return (
    <li className="surface surface-hover flex flex-col p-5">
      <div className="flex items-start justify-between gap-2">
        <Link
          to={repoHref(repo)}
          className="min-w-0 truncate font-mono font-semibold underline-offset-4 hover:underline"
        >
          {repo.full_name}
        </Link>
        <div className="shrink-0">
          <RepoBadge repo={repo} />
        </div>
      </div>
      {repo.description && (
        <p className="mt-1 line-clamp-2 text-sm text-slate-600 dark:text-slate-400">
          {repo.description}
        </p>
      )}
      <div className="mt-3">
        <LanguageBar languages={repo.languages} limit={3} />
      </div>
      {repo.status === "failed" && repo.error && (
        <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{repo.error}</p>
      )}
      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-slate-500 dark:text-slate-400">
        <span title={repo.commit_sha}>
          {repo.default_branch} @ <span className="font-mono">{repo.commit_sha.slice(0, 7)}</span>
          {repo.stats.files ? ` · ${repo.stats.files} files` : ""}
        </span>
        <button
          type="button"
          onClick={() => {
            if (window.confirm(`Remove ${repo.full_name} from your dashboard?`)) {
              remove.mutate(repo.id);
            }
          }}
          className="rounded-md px-1.5 py-0.5 transition-colors duration-300 hover:bg-rose-500/10 hover:text-rose-600 dark:hover:text-rose-400"
        >
          Remove
        </button>
      </div>
    </li>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const repos = useRepositories();
  const pending = params.get("analyze") ?? "";

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Your repositories</h1>
          {user && (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Signed in as @{user.username}
            </p>
          )}
        </div>
      </div>

      <section className="surface mt-8 p-5">
        <h2 className="eyebrow mb-3">Analyze a repository</h2>
        <NewAnalysisForm initial={pending} />
      </section>

      <section className="mt-10" aria-label="Analyzed repositories">
        {repos.isPending && <LoadingState label="Loading your repositories" />}
        {repos.isError && (
          <ErrorState message={repos.error.message} onRetry={() => repos.refetch()} />
        )}
        {repos.data && repos.data.results.length === 0 && (
          <EmptyState
            title="No repositories yet"
            description="Paste a GitHub URL above to get an overview, architecture map, guided tour and Q&A."
          />
        )}
        {repos.data && repos.data.results.length > 0 && (
          <ul className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {repos.data.results.map((repo) => (
              <RepoCard key={repo.id} repo={repo} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
