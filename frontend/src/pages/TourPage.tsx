import { useCallback, useEffect } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router";

import { useAnalysis } from "../api/analysis";
import { useRepository } from "../api/repos";
import { CodeViewer } from "../components/CodeViewer";
import { SectionShell } from "../components/sections/SectionShell";
import { TourProgress } from "../components/sections/TourProgress";
import { TourRequest } from "../components/sections/TourRequest";
import { TourKindBadge } from "../components/sections/TourSection";
import { ErrorState, LoadingState } from "../components/StateViews";
import type { Tour } from "../api/types";
import { parseStep } from "../lib/tour";
import { RichText } from "../components/RichText";

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
      <div className="border-b border-slate-900/[0.06] px-4 py-2.5 dark:border-white/[0.06]">
        <div className="flex items-center gap-3 text-sm">
          <Link
            to={`/repos/${repoId}?tab=tour`}
            className="text-slate-500 transition-colors duration-300 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
          >
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
          className="mt-2.5 h-1 overflow-hidden rounded-full bg-slate-900/[0.06] dark:bg-white/[0.08]"
        >
          <div
            className="bg-brand h-full rounded-full transition-[width] duration-500 ease-out"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_24rem] lg:grid-rows-1">
        <section
          aria-label="Code"
          className="order-2 min-h-[50vh] min-w-0 border-slate-900/[0.06] lg:order-1 lg:min-h-0 lg:border-r dark:border-white/[0.06]"
        >
          <CodeViewer key={step.path} repoId={repoId} path={step.path} range={range} />
        </section>

        <aside
          aria-label="Explanation"
          className="order-1 flex min-h-0 flex-col gap-5 overflow-auto p-6 lg:order-2"
        >
          <div key={`title-${index}`} className="animate-fade-up">
            <TourKindBadge kind={step.kind} />
            <h1 className="mt-2.5 text-xl font-semibold tracking-tight">{step.title}</h1>
            {step.symbol && <p className="mt-1 font-mono text-xs text-slate-500">{step.symbol}</p>}
          </div>
          <p
            key={`text-${index}`}
            className="animate-fade-up leading-relaxed whitespace-pre-line text-slate-700 [animation-delay:60ms] dark:text-slate-300"
          >
            <RichText text={step.explanation} />
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => go(index - 1)}
              disabled={index === 0}
              className="btn btn-secondary px-3 py-1.5"
            >
              ← Previous
            </button>
            {last ? (
              <Link to={`/repos/${repoId}?tab=tour`} className="btn btn-primary px-3 py-1.5">
                Finish
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => go(index + 1)}
                className="btn btn-primary px-3 py-1.5"
              >
                Next →
              </button>
            )}
            <span className="ml-auto hidden text-xs text-slate-400 sm:inline">← → keys</span>
          </div>
          <nav
            aria-label="Tour steps"
            className="border-t border-slate-900/[0.06] pt-4 dark:border-white/[0.06]"
          >
            <ol className="flex flex-col gap-0.5 text-sm">
              {tour.steps.map((item, i) => (
                <li key={`${item.path}-${i}`}>
                  <button
                    type="button"
                    onClick={() => go(i)}
                    aria-current={i === index ? "step" : undefined}
                    className={`w-full rounded-lg px-2.5 py-1.5 text-left transition-colors duration-300 ${
                      i === index
                        ? "bg-slate-900/[0.06] font-medium text-slate-900 dark:bg-white/10 dark:text-white"
                        : "text-slate-500 hover:bg-slate-900/[0.04] hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.05] dark:hover:text-white"
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
          className="block px-6 pt-4 text-sm text-slate-500 transition-colors duration-300 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          ← Back to workspace
        </Link>
      )}
      {analysis.data.sections.tour.status === "not_requested" ? (
        <TourRequest repoId={repoId} analysisStatus={analysis.data.status} />
      ) : ["pending", "running"].includes(analysis.data.sections.tour.status) ? (
        <TourProgress repoId={repoId} />
      ) : (
        <SectionShell
          title="Guided Tour"
          section={analysis.data.sections.tour}
          analysisStatus={analysis.data.status}
          writingHint="A tour usually takes 3 to 4 minutes; this page shows it as soon as it is ready."
        >
          {(tour) => <TourStepper repoId={repoId} tour={tour} />}
        </SectionShell>
      )}
    </div>
  );
}
