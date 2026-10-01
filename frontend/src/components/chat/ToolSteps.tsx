import type { ToolStep } from "../../api/chat";
import { Spinner } from "../StateViews";

function StepList({ steps, live }: { steps: ToolStep[]; live: boolean }) {
  return (
    <ol className="flex flex-col gap-1 text-xs text-slate-600 dark:text-slate-400">
      {steps.map((step) => {
        const running = live && step.ok === undefined;
        return (
          <li key={step.id} className="flex items-center gap-2">
            <span className="w-4 shrink-0 text-center">
              {running ? <Spinner label="Running" /> : step.ok === false ? "✗" : "✓"}
            </span>
            <span className={step.ok === false ? "text-red-600 dark:text-red-400" : ""}>
              {step.summary}
            </span>
            {step.duration_ms !== undefined && (
              <span className="text-slate-400">{step.duration_ms} ms</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** What the agent did: live while answering, collapsed afterwards. */
export function ToolSteps({ steps, live = false }: { steps: ToolStep[]; live?: boolean }) {
  if (steps.length === 0) return null;
  if (live) {
    return (
      <div aria-live="polite" className="mb-2">
        <StepList steps={steps} live />
      </div>
    );
  }
  return (
    <details className="mb-2 text-xs">
      <summary className="cursor-pointer text-slate-500 select-none hover:text-slate-700 dark:hover:text-slate-300">
        {steps.length} research step{steps.length === 1 ? "" : "s"}
      </summary>
      <div className="mt-1.5">
        <StepList steps={steps} live={false} />
      </div>
    </details>
  );
}
