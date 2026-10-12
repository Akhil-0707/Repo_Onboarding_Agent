import type { AnalysisStatus, JobStatus, RepoStatus } from "../api/types";

type Status = RepoStatus | JobStatus | AnalysisStatus;

const STYLES: Record<Status, { label: string; className: string }> = {
  queued: {
    label: "Queued",
    className: "bg-slate-400",
  },
  ingesting: {
    label: "Ingesting",
    className: "bg-sky-500",
  },
  running: {
    label: "Running",
    className: "bg-sky-500",
  },
  waiting_for_model: {
    label: "Waiting for model",
    className: "bg-amber-500",
  },
  ready: {
    label: "Ready",
    className: "bg-emerald-500",
  },
  done: {
    label: "Done",
    className: "bg-emerald-500",
  },
  pending: {
    label: "Pending",
    className: "bg-slate-400",
  },
  partial: {
    label: "Partial",
    className: "bg-amber-500",
  },
  failed: {
    label: "Failed",
    className: "bg-rose-500",
  },
};

export function StatusBadge({ status }: { status: Status }) {
  const style = STYLES[status] ?? STYLES.queued;
  const active = status === "ingesting" || status === "running" || status === "queued";
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-900/[0.04] px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-white/[0.06] dark:text-slate-300">
      <span className="relative flex h-1.5 w-1.5">
        {active && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${style.className}`}
          />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${style.className}`} />
      </span>
      {style.label}
    </span>
  );
}
