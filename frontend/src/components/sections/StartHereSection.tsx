import type { StartHere } from "../../api/types";
import { CitationChip } from "../CitationChip";
import type { CodeRef } from "../../lib/refs";
import { RichText } from "../RichText";

export function StartHereSection({
  data,
  onOpen,
}: {
  data: StartHere;
  onOpen: (ref: CodeRef) => void;
}) {
  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <p className="mb-4 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
        Read these files in order. Each one builds on the previous.
      </p>
      <ol className="stagger flex flex-col gap-3" aria-label="Reading list">
        {data.files.map((file, index) => (
          <li key={file.path} className="flex gap-4 surface p-4">
            <span
              aria-hidden="true"
              className="bg-brand flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold"
            >
              {index + 1}
            </span>
            <div className="min-w-0">
              <CitationChip reference={file} onOpen={onOpen} />
              <p className="mt-1.5 text-sm text-slate-700 dark:text-slate-300">
                <RichText text={file.reason} />
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
