import { Link } from "react-router";

import type { Tour } from "../../api/types";
import type { CodeRef } from "../../lib/refs";
import { TOUR_KIND_LABELS } from "../../lib/tour";
import { CitationChip } from "../CitationChip";

export function TourKindBadge({ kind }: { kind: Tour["steps"][number]["kind"] }) {
  const flow = kind === "flow_trace";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        flow
          ? "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
      }`}
    >
      {TOUR_KIND_LABELS[kind]}
    </span>
  );
}

export function TourSection({
  repoId,
  data,
  onOpen,
}: {
  repoId: string;
  data: Tour;
  onOpen: (ref: CodeRef) => void;
}) {
  return (
    <div className="p-6">
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <p className="max-w-2xl flex-1 text-slate-700 dark:text-slate-300">{data.intro}</p>
        <Link
          to={`/repos/${repoId}/tour`}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Start the tour →
        </Link>
      </div>
      <ol className="flex flex-col gap-3" aria-label="Tour stops">
        {data.steps.map((step, index) => (
          <li
            key={`${step.path}-${index}`}
            className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-200 text-sm font-semibold dark:bg-slate-700"
            >
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/repos/${repoId}/tour?step=${index + 1}`}
                  className="font-semibold hover:underline"
                >
                  {step.title}
                </Link>
                <TourKindBadge kind={step.kind} />
                <CitationChip reference={step} onOpen={onOpen} />
              </div>
              <p className="mt-1.5 line-clamp-2 text-sm text-slate-700 dark:text-slate-300">
                {step.explanation}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
