import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useRepository, useStartAnalysis } from "../api/repos";
import type { JobStep } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { ErrorState, LoadingState } from "../components/StateViews";
import { useJobStream } from "../hooks/useJobStream";

const ICONS: Record<JobStep["status"], string> = {
  pending: "○",
  running: "◐",
  done: "✓",
  failed: "✕",
  skipped: "–",
};

const ICON_COLORS: Record<JobStep["status"], string> = {
  pending: "text-slate-400",
  running: "text-sky-500 animate-pulse",
  done: "text-emerald-500",
  failed: "text-rose-500",
  skipped: "text-slate-400",
};

function StepRow({ step }: { step: JobStep }) {
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? (step.status === "running" || step.status === "failed");

  return (
    <li className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <button
        type="button"
        onClick={() => setToggled(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span
          aria-hidden="true"
          className={`w-4 text-center font-bold ${ICON_COLORS[step.status]}`}
        >
          {ICONS[step.status]}
        </span>
        <span className="flex-1 font-medium">{step.label}</span>
        <span className="text-sm text-slate-500">{step.message}</span>
        <span className="sr-only">{step.status}</span>
      </button>
      {step.status === "running" && (
        <div className="mx-4 mb-3 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="h-full bg-sky-500 transition-all"
            style={{ width: `${Math.max(step.progress, 5)}%` }}
          />
        </div>
      )}
      {open && step.logs.length > 0 && (
        <ol className="max-h-48 overflow-auto border-t border-slate-200 bg-slate-50 px-4 py-2 font-mono text-xs dark:border-slate-800 dark:bg-slate-950">
          {step.logs.map((log, index) => (
            <li
              key={`${log.ts}-${index}`}
              className={
                log.level === "error"
                  ? "text-rose-600"
                  : log.level === "warning"
                    ? "text-amber-600"
                    : "text-slate-600 dark:text-slate-400"
              }
            >
              <span className="text-slate-400">{new Date(log.ts).toLocaleTimeString()} </span>
              {log.message}
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}

export function IngestionPage() {
  const { repoId = "" } = useParams();
  const navigate = useNavigate();
  const repo = useRepository(repoId);
  const [attempt, setAttempt] = useState(0);
  const { job, error, ended } = useJobStream(repoId, attempt);
  const retry = useStartAnalysis();

  const done = job?.status === "done";
  useEffect(() => {
    if (!done) return;
    const timer = setTimeout(() => navigate(`/repos/${repoId}`, { replace: true }), 1500);
    return () => clearTimeout(timer);
  }, [done, navigate, repoId]);

  if (repo.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <ErrorState title="Repository not found" message={repo.error.message} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Link to="/dashboard" className="text-sm text-slate-500 hover:underline">
        ← Dashboard
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-mono text-2xl font-bold">{repo.data?.full_name ?? "…"}</h1>
          {repo.data && (
            <p className="mt-1 text-sm text-slate-500">
              {repo.data.default_branch} @{" "}
              <span className="font-mono">{repo.data.commit_sha.slice(0, 7)}</span>
            </p>
          )}
        </div>
        {job && <StatusBadge status={job.status} />}
      </div>

      <div className="mt-6">
        <div className="flex justify-between text-sm">
          <span>{done ? "Finished, opening workspace…" : "Overall progress"}</span>
          <span className="font-mono">{job?.progress ?? 0}%</span>
        </div>
        <div
          role="progressbar"
          aria-valuenow={job?.progress ?? 0}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Ingestion progress"
          className="mt-1 h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
        >
          <div
            className={`h-full transition-all ${job?.status === "failed" ? "bg-rose-500" : "bg-indigo-600"}`}
            style={{ width: `${job?.progress ?? 0}%` }}
          />
        </div>
      </div>

      {error && !ended && (
        <p role="status" className="mt-4 text-sm text-amber-600">
          Connection interrupted ({error}). Reconnecting…
        </p>
      )}

      {job?.status === "failed" && (
        <div className="mt-6">
          <ErrorState
            title="Analysis failed"
            message={job.error || "Something went wrong."}
            onRetry={
              repo.data
                ? () => retry.mutate(repo.data.url, { onSuccess: () => setAttempt((n) => n + 1) })
                : undefined
            }
          />
        </div>
      )}

      {!job ? (
        <LoadingState label="Connecting to progress stream" />
      ) : (
        <ol className="mt-6 flex flex-col gap-2" aria-label="Ingestion steps">
          {job.steps.map((step) => (
            <StepRow key={step.key} step={step} />
          ))}
        </ol>
      )}

      {done && (
        <Link
          to={`/repos/${repoId}`}
          className="mt-6 inline-block rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700"
        >
          Open workspace
        </Link>
      )}
    </div>
  );
}
