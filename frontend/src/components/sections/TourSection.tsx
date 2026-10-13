import { Link } from "react-router";

import type { Tour } from "../../api/types";
import type { CodeRef } from "../../lib/refs";
import { TOUR_KIND_LABELS } from "../../lib/tour";
import { CitationChip } from "../CitationChip";
import { RichText } from "../RichText";

export function TourKindBadge({ kind }: { kind: Tour["steps"][number]["kind"] }) {
  const flow = kind === "flow_trace";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        flow
          ? "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300"
          : "bg-slate-900/[0.05] text-slate-600 dark:bg-white/[0.07] dark:text-slate-300"
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
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <p className="max-w-2xl flex-1 text-slate-700 dark:text-slate-300">
          <RichText text={data.intro} />
        </p>
        <Link to={`/repos/${repoId}/tour`} className="btn btn-primary">
          Start the tour →
        </Link>
      </div>
      <ol className="stagger flex flex-col gap-3" aria-label="Tour stops">
        {data.steps.map((step, index) => (
          <li key={`${step.path}-${index}`} className="flex gap-4 surface surface-hover p-4">
            <span
              aria-hidden="true"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900/[0.06] text-sm font-semibold tabular-nums dark:bg-white/10"
            >
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to={`/repos/${repoId}/tour?step=${index + 1}`}
                  className="font-semibold underline-offset-4 hover:underline"
                >
                  {step.title}
                </Link>
                <TourKindBadge kind={step.kind} />
                <CitationChip reference={step} onOpen={onOpen} />
              </div>
              <p className="mt-1.5 line-clamp-2 text-sm text-slate-700 dark:text-slate-300">
                <RichText text={step.explanation} />
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
