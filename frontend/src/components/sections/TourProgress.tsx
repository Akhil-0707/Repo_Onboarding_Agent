import { useEffect, useState } from "react";

import { useJobStream } from "../../hooks/useJobStream";
import { formatElapsed, TOUR_STAGES, tourProgress } from "../../lib/tourProgress";

function StageIcon({ state }: { state: "done" | "current" | "upcoming" }) {
  if (state === "done") {
    return (
      <span className="bg-brand animate-pop-in flex h-5 w-5 items-center justify-center rounded-full">
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" aria-hidden="true">
          <path
            d="m3.5 8.5 3 3 6-7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }
  if (state === "current") {
    return (
      <span className="relative flex h-5 w-5 items-center justify-center">
        <span className="absolute inline-flex h-3 w-3 animate-ping rounded-full bg-slate-400/60 dark:bg-slate-300/50" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-slate-900 dark:bg-white" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center">
      <span className="h-2.5 w-2.5 rounded-full ring-1 ring-slate-400/70 dark:ring-slate-500" />
    </span>
  );
}

/** Live progress while the Guided Tour is being written: stages from the job's events, a bar
 * that keeps moving between them, and the time it has taken so far. */
export function TourProgress({ repoId }: { repoId: string }) {
  const { job } = useJobStream(repoId);
  const step = job?.steps.find((s) => s.key === "analyze");
  const startedAt = step?.started_at ?? job?.started_at ?? null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const elapsed = startedAt ? (now - Date.parse(startedAt)) / 1000 : 0;
  const view = tourProgress(step, elapsed);
  const percent = Math.round(view.fraction * 100);

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <section
        className="surface animate-fade-up p-6"
        aria-busy="true"
        aria-labelledby="tour-progress-title"
      >
        <p className="eyebrow">Guided tour</p>
        <h2 id="tour-progress-title" className="mt-2 text-xl font-semibold tracking-tight">
          Creating your guided tour
        </h2>

        <div
          role="progressbar"
          aria-label="Tour progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-900/[0.06] dark:bg-white/[0.08]"
        >
          <div
            className="bg-brand relative h-full overflow-hidden rounded-full transition-[width] duration-1000 ease-out"
            style={{ width: `${percent}%` }}
          >
            <span className="animate-shimmer absolute inset-0 bg-gradient-to-r from-transparent via-white/45 to-transparent dark:via-black/25" />
          </div>
        </div>
        <p className="mt-2 flex justify-between text-xs text-slate-500 tabular-nums dark:text-slate-400">
          <span>{percent}%</span>
          <span>{formatElapsed(elapsed)} elapsed · usually 3 to 4 minutes</span>
        </p>

        <ol className="mt-5 flex flex-col gap-3" aria-label="Steps">
          {TOUR_STAGES.map((stage, index) => {
            const state =
              index < view.stage ? "done" : index === view.stage ? "current" : "upcoming";
            return (
              <li key={stage.key} className="flex gap-3">
                <StageIcon state={state} />
                <div className="min-w-0">
                  <p
                    className={`text-sm font-medium transition-colors duration-300 ${
                      state === "upcoming"
                        ? "text-slate-400 dark:text-slate-500"
                        : "text-slate-900 dark:text-white"
                    }`}
                  >
                    {stage.label}
                  </p>
                  {state === "current" && (
                    <p
                      key={view.activity}
                      className="animate-fade-in mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400"
                    >
                      {view.activity}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>

        {view.waiting ? (
          <p
            role="status"
            className="animate-fade-in mt-5 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-400/[0.06] dark:text-amber-200"
          >
            Waiting for the AI model to come back online; the tour resumes automatically.
          </p>
        ) : (
          <p className="mt-5 text-sm text-slate-500 dark:text-slate-400">
            You can keep browsing; the tour appears here as soon as it is ready.
          </p>
        )}
      </section>
    </div>
  );
}
