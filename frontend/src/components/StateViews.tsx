import type { ReactNode } from "react";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" aria-label={label} className="inline-flex items-center gap-2 text-sm">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900 dark:border-slate-700 dark:border-t-slate-100" />
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-lg bg-slate-900/[0.06] dark:bg-white/[0.06] ${className}`}
    />
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="animate-fade-in flex flex-col gap-3 p-6" aria-busy="true">
      <span className="sr-only">{label}</span>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade-up flex flex-col items-center justify-center gap-2 rounded-2xl bg-slate-900/[0.03] p-12 text-center dark:bg-white/[0.03]">
      <h3 className="text-base font-semibold">{title}</h3>
      {description && (
        <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="animate-fade-up flex flex-col items-start gap-2 rounded-2xl bg-rose-50 p-5 text-rose-900 ring-1 ring-rose-200/70 dark:bg-rose-950/30 dark:text-rose-200 dark:ring-rose-900/50"
    >
      <h3 className="font-semibold">{title}</h3>
      {message && <p className="text-sm">{message}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="btn mt-1 bg-rose-600 px-3 py-1.5 text-white hover:bg-rose-700"
        >
          Try again
        </button>
      )}
    </div>
  );
}
