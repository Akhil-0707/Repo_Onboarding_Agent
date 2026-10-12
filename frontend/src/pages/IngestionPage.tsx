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
  waiting: "⏸",
  done: "✓",
  failed: "✕",
  skipped: "–",
};

const ICON_COLORS: Record<JobStep["status"], string> = {
  pending: "text-slate-400",
  running: "text-sky-500 animate-pulse",
  waiting: "text-amber-500",
  done: "text-emerald-500",
  failed: "text-rose-500",
  skipped: "text-slate-400",
};

function StepRow({ step }: { step: JobStep }) {
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open =
    toggled ?? (step.status === "running" || step.status === "failed" || step.status === "waiting");

  return (
    <li className="surface overflow-hidden">
      <button
        type="button"
        onClick={() => setToggled(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-slate-900/[0.02] dark:hover:bg-white/[0.02]"
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
        <div className="mx-4 mb-3 h-1 overflow-hidden rounded-full bg-slate-900/[0.06] dark:bg-white/[0.08]">
          <div
            className="bg-brand h-full rounded-full transition-[width] duration-700 ease-out"
            style={{ width: `${Math.max(step.progress, 5)}%` }}
          />
        </div>
      )}
      {open && step.logs.length > 0 && (
        <ol className="animate-fade-in max-h-48 overflow-auto border-t border-slate-900/[0.06] bg-slate-900/[0.02] px-4 py-2 font-mono text-xs dark:border-white/[0.06] dark:bg-black/20">
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
      <Link
        to="/dashboard"
        className="text-sm text-slate-500 transition-colors duration-200 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
      >
        ← Dashboard
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-mono text-2xl font-semibold tracking-tight">
            {repo.data?.full_name ?? "…"}
          </h1>
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
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-900/[0.06] dark:bg-white/[0.08]"
        >
          <div
            className={`h-full rounded-full transition-[width] duration-700 ease-out ${job?.status === "failed" ? "bg-rose-500" : "bg-brand"}`}
            style={{ width: `${job?.progress ?? 0}%` }}
          />
        </div>
      </div>

      {job?.status === "waiting_for_model" && (
        <p
          role="status"
          className="animate-fade-in mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200/70 dark:bg-amber-400/[0.06] dark:text-amber-200 dark:ring-amber-400/20"
        >
          The AI model is offline. The analysis is paused and resumes automatically when it is back.
        </p>
      )}

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
        <ol className="stagger mt-8 flex flex-col gap-2" aria-label="Ingestion steps">
          {job.steps.map((step) => (
            <StepRow key={step.key} step={step} />
          ))}
        </ol>
      )}

      {(done || repo.data?.status === "ready") && (
        <Link to={`/repos/${repoId}`} className="btn btn-primary animate-fade-up mt-8">
          {done ? "Open workspace" : "Browse the code while the AI analysis runs"}
        </Link>
      )}
    </div>
  );
}
