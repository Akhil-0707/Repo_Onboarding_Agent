import type { StartHere } from "../../api/types";
import { CitationChip } from "../CitationChip";
import type { CodeRef } from "../../lib/refs";

export function StartHereSection({
  data,
  onOpen,
}: {
  data: StartHere;
  onOpen: (ref: CodeRef) => void;
}) {
  return (
    <div className="p-6">
      <p className="mb-4 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
        Read these files in order. Each one builds on the previous.
      </p>
      <ol className="flex flex-col gap-3" aria-label="Reading list">
        {data.files.map((file, index) => (
          <li
            key={file.path}
            className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white"
            >
              {index + 1}
            </span>
            <div className="min-w-0">
              <CitationChip reference={file} onOpen={onOpen} />
              <p className="mt-1.5 text-sm text-slate-700 dark:text-slate-300">{file.reason}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
