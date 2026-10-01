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
        className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
      />
      <button
        type="submit"
        disabled={start.isPending}
        className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
      >
        {start.isPending ? "Starting…" : "Analyze"}
      </button>
      {error && (
        <p id="new-repo-error" role="alert" className="text-sm text-rose-600 sm:basis-full">
          {error}
        </p>
      )}
    </form>
  );
}

function RepoCard({ repo }: { repo: Repository }) {
  const remove = useRemoveRepository();
  return (
    <li className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-2">
        <Link
          to={repoHref(repo)}
          className="min-w-0 truncate font-mono font-semibold hover:text-indigo-600 dark:hover:text-indigo-400"
        >
          {repo.full_name}
        </Link>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <StatusBadge status={repo.status} />
          {repo.status === "ready" && repo.analysis_status === "waiting_for_model" && (
            <span className="text-xs text-amber-600 dark:text-amber-400">AI waiting for model</span>
          )}
          {repo.status === "ready" && repo.analysis_status === "running" && (
            <span className="text-xs text-sky-600 dark:text-sky-400">AI analysis running</span>
          )}
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
      <div className="mt-auto flex items-center justify-between pt-3 text-xs text-slate-500">
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
          className="rounded px-1.5 py-0.5 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800"
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
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Your repositories</h1>
          {user && (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              Signed in as @{user.username}
            </p>
          )}
        </div>
      </div>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-semibold">Analyze a repository</h2>
        <NewAnalysisForm initial={pending} />
      </section>

      <section className="mt-8" aria-label="Analyzed repositories">
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
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {repos.data.results.map((repo) => (
              <RepoCard key={repo.id} repo={repo} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
