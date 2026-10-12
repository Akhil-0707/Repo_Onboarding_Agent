import { formatRef } from "../lib/refs";
import type { CodeRef } from "../lib/refs";

/** A clickable `path:start-end` reference that opens the code viewer at those lines. */
export function CitationChip({
  reference,
  onOpen,
}: {
  reference: CodeRef;
  onOpen: (ref: CodeRef) => void;
}) {
  const label = formatRef(reference);
  const isDir = reference.path.endsWith("/");
  return (
    <button
      type="button"
      onClick={() => onOpen(reference)}
      disabled={isDir}
      title={isDir ? reference.path : `Open ${label}`}
      className="inline-flex max-w-full items-center gap-1.5 truncate rounded-md bg-slate-900/[0.05] px-1.5 py-0.5 align-middle font-mono text-xs text-slate-800 ring-1 ring-slate-900/[0.06] transition-colors duration-200 hover:bg-slate-900/10 hover:text-slate-950 disabled:cursor-default disabled:text-slate-600 disabled:hover:bg-slate-900/[0.05] dark:bg-white/[0.06] dark:text-slate-200 dark:ring-white/[0.08] dark:hover:bg-white/[0.12] dark:hover:text-white dark:disabled:text-slate-400 dark:disabled:hover:bg-white/[0.06]"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 16 16"
        className="h-3 w-3 shrink-0 opacity-60"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      >
        {isDir ? (
          <path d="M1.75 4.25A1.25 1.25 0 0 1 3 3h3l1.5 1.5H13a1.25 1.25 0 0 1 1.25 1.25v6A1.25 1.25 0 0 1 13 13H3a1.25 1.25 0 0 1-1.25-1.25z" />
        ) : (
          <path d="M4 1.75h5L12.25 5v8.25A.75.75 0 0 1 11.5 14h-7.5a.75.75 0 0 1-.75-.75V2.5A.75.75 0 0 1 4 1.75zM9 1.75V5h3.25" />
        )}
      </svg>
      <span className="truncate">{label}</span>
    </button>
  );
}
