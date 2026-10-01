import { useState } from "react";

import type { Overview } from "../../api/types";
import { CitationChip } from "../CitationChip";
import type { CodeRef } from "../../lib/refs";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // clipboard unavailable (insecure context)
        }
      }}
      className="shrink-0 rounded px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export function OverviewSection({
  data,
  onOpen,
  onAsk,
}: {
  data: Overview;
  onOpen: (ref: CodeRef) => void;
  onAsk?: (question: string) => void;
}) {
  return (
    <article className="flex flex-col gap-8 p-6">
      <section aria-labelledby="ov-summary">
        <h2 id="ov-summary" className="sr-only">
          Summary
        </h2>
        <p className="max-w-3xl text-lg leading-relaxed">{data.summary}</p>
      </section>

      <section aria-labelledby="ov-stack">
        <h3
          id="ov-stack"
          className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Tech stack
        </h3>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.tech_stack.map((item) => (
            <li
              key={item.name}
              className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
            >
              <p className="font-medium">{item.name}</p>
              <p className="text-sm text-slate-600 dark:text-slate-400">{item.role}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ov-structure">
        <h3
          id="ov-structure"
          className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
        >
          Structure
        </h3>
        <ul className="flex flex-col gap-2">
          {data.structure.map((item) => (
            <li key={item.path} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <CitationChip reference={{ path: item.path }} onOpen={onOpen} />
              <span className="text-sm text-slate-700 dark:text-slate-300">{item.description}</span>
            </li>
          ))}
        </ul>
      </section>

      {(data.prerequisites.length > 0 || data.how_to_run.length > 0) && (
        <section aria-labelledby="ov-run">
          <h3
            id="ov-run"
            className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
          >
            Run it locally
          </h3>
          {data.prerequisites.length > 0 && (
            <p className="mb-3 text-sm">
              <span className="font-medium">Prerequisites: </span>
              {data.prerequisites.join(", ")}
            </p>
          )}
          <ol className="flex list-decimal flex-col gap-3 pl-5">
            {data.how_to_run.map((step, index) => (
              <li key={index} className="text-sm">
                <p>{step.description}</p>
                {step.command && (
                  <div className="mt-1 flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 font-mono text-[13px] text-slate-100">
                    <code className="min-w-0 flex-1 overflow-x-auto whitespace-pre">
                      {step.command}
                    </code>
                    <CopyButton text={step.command} />
                  </div>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {data.entry_points.length > 0 && (
        <section aria-labelledby="ov-entry">
          <h3
            id="ov-entry"
            className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
          >
            Entry points
          </h3>
          <ul className="flex flex-col gap-2">
            {data.entry_points.map((entry) => (
              <li key={entry.path} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <CitationChip reference={entry} onOpen={onOpen} />
                <span className="text-sm text-slate-700 dark:text-slate-300">
                  {entry.description}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.starter_questions.length > 0 && (
        <section aria-labelledby="ov-questions">
          <h3
            id="ov-questions"
            className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500"
          >
            Questions to ask
          </h3>
          <ul className="flex flex-wrap gap-2">
            {data.starter_questions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  disabled={!onAsk}
                  onClick={() => onAsk?.(question)}
                  className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-sm text-indigo-800 hover:bg-indigo-100 disabled:cursor-default dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200"
                >
                  {question}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
