import { useCallback, useEffect } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router";

import { useAnalysis } from "../api/analysis";
import { useRepository } from "../api/repos";
import { CodeViewer } from "../components/CodeViewer";
import { SectionShell } from "../components/sections/SectionShell";
import { TourKindBadge } from "../components/sections/TourSection";
import { ErrorState, LoadingState } from "../components/StateViews";
import type { Tour } from "../api/types";
import { parseStep } from "../lib/tour";

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

function TourStepper({ repoId, tour }: { repoId: string; tour: Tour }) {
  const [params, setParams] = useSearchParams();
  const total = tour.steps.length;
  const index = parseStep(params.get("step"), total);
  const step = tour.steps[index];

  const go = useCallback(
    (next: number) => {
      if (next < 0 || next >= total) return;
      setParams({ step: String(next + 1) }, { replace: true });
    },
    [setParams, total],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || isTyping(event.target)) return;
      if (event.key === "ArrowRight") go(index + 1);
      if (event.key === "ArrowLeft") go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  if (!step) return null;
  const range = step.start_line
    ? { start: step.start_line, end: step.end_line ?? step.start_line }
    : null;
  const percent = Math.round(((index + 1) / total) * 100);
  const last = index === total - 1;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-slate-200 px-4 py-2 dark:border-slate-800">
        <div className="flex items-center gap-3 text-sm">
          <Link to={`/repos/${repoId}?tab=tour`} className="text-slate-500 hover:underline">
            ← Back to workspace
          </Link>
          <span className="ml-auto text-slate-500" aria-live="polite">
            Step {index + 1} of {total}
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Tour progress"
          aria-valuemin={1}
          aria-valuemax={total}
          aria-valuenow={index + 1}
          aria-valuetext={`Step ${index + 1} of ${total}`}
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
        >
          <div
            className="h-full rounded-full bg-indigo-600 transition-[width]"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_24rem] lg:grid-rows-1">
        <section
          aria-label="Code"
          className="order-2 min-h-[50vh] min-w-0 border-slate-200 lg:order-1 lg:min-h-0 lg:border-r dark:border-slate-800"
        >
          <CodeViewer key={step.path} repoId={repoId} path={step.path} range={range} />
        </section>

        <aside
          aria-label="Explanation"
          className="order-1 flex min-h-0 flex-col gap-4 overflow-auto p-5 lg:order-2"
        >
          <div>
            <TourKindBadge kind={step.kind} />
            <h1 className="mt-2 text-xl font-semibold">{step.title}</h1>
            {step.symbol && <p className="mt-1 font-mono text-xs text-slate-500">{step.symbol}</p>}
          </div>
          <p className="leading-relaxed whitespace-pre-line text-slate-700 dark:text-slate-300">
            {step.explanation}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => go(index - 1)}
              disabled={index === 0}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-40 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              ← Previous
            </button>
            {last ? (
              <Link
                to={`/repos/${repoId}?tab=tour`}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
              >
                Finish
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => go(index + 1)}
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
              >
                Next →
              </button>
            )}
            <span className="ml-auto hidden text-xs text-slate-400 sm:inline">← → keys</span>
          </div>
          <nav
            aria-label="Tour steps"
            className="border-t border-slate-200 pt-3 dark:border-slate-800"
          >
            <ol className="flex flex-col gap-0.5 text-sm">
              {tour.steps.map((item, i) => (
                <li key={`${item.path}-${i}`}>
                  <button
                    type="button"
                    onClick={() => go(i)}
                    aria-current={i === index ? "step" : undefined}
                    className={`w-full rounded px-2 py-1 text-left ${
                      i === index
                        ? "bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                        : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                    }`}
                  >
                    {i + 1}. {item.title}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        </aside>
      </div>
    </div>
  );
}

export function TourPage() {
  const { repoId = "" } = useParams();
  const repo = useRepository(repoId);
  const ready = repo.data?.status === "ready";
  const analysis = useAnalysis(repoId, ready);

  if (repo.isPending) return <LoadingState label="Loading repository" />;
  if (repo.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <ErrorState title="Repository not found" message={repo.error.message} />
      </div>
    );
  }
  if (!ready) return <Navigate to={`/repos/${repoId}/progress`} replace />;
  if (analysis.isPending) return <LoadingState label="Loading the tour" />;
  if (analysis.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <ErrorState message={analysis.error.message} onRetry={() => analysis.refetch()} />
      </div>
    );
  }

  return (
    <div className="h-full min-h-0">
      {analysis.data.sections.tour.status !== "done" && (
        <Link
          to={`/repos/${repoId}?tab=tour`}
          className="block px-6 pt-4 text-sm text-slate-500 hover:underline"
        >
          ← Back to workspace
        </Link>
      )}
      <SectionShell
        title="Guided Tour"
        section={analysis.data.sections.tour}
        analysisStatus={analysis.data.status}
      >
        {(tour) => <TourStepper repoId={repoId} tour={tour} />}
      </SectionShell>
    </div>
  );
}
