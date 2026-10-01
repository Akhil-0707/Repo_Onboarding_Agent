import type { JobStatus, RepoStatus } from "../api/types";

const STYLES: Record<RepoStatus | JobStatus, { label: string; className: string }> = {
  queued: {
    label: "Queued",
    className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
  ingesting: {
    label: "Ingesting",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  },
  running: {
    label: "Running",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  },
  waiting_for_model: {
    label: "Waiting for model",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  ready: {
    label: "Ready",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  done: {
    label: "Done",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  failed: {
    label: "Failed",
    className: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
  },
};

export function StatusBadge({ status }: { status: RepoStatus | JobStatus }) {
  const style = STYLES[status] ?? STYLES.queued;
  const active = status === "ingesting" || status === "running" || status === "queued";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}
    >
      {active && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {style.label}
    </span>
  );
}
