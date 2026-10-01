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
      className="inline-flex max-w-full items-center gap-1 truncate rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 align-middle font-mono text-xs text-indigo-700 hover:border-indigo-300 hover:bg-indigo-50 disabled:cursor-default disabled:text-slate-600 disabled:hover:border-slate-200 disabled:hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-indigo-300 dark:hover:bg-slate-700 dark:disabled:text-slate-300"
    >
      <span aria-hidden="true">{isDir ? "📁" : "📄"}</span>
      <span className="truncate">{label}</span>
    </button>
  );
}
