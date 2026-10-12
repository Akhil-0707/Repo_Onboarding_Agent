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
      className="shrink-0 rounded-md px-2 py-0.5 text-xs text-slate-400 transition-colors duration-150 hover:bg-white/10 hover:text-white"
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
    <article className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-8">
      <section aria-labelledby="ov-summary">
        <h2 id="ov-summary" className="sr-only">
          Summary
        </h2>
        <p className="max-w-3xl text-lg leading-relaxed text-slate-700 dark:text-slate-200">
          {data.summary}
        </p>
      </section>

      <section aria-labelledby="ov-stack">
        <h3 id="ov-stack" className="eyebrow mb-3">
          Tech stack
        </h3>
        <ul className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.tech_stack.map((item) => (
            <li
              key={item.name}
              className="rounded-xl bg-slate-900/[0.03] p-4 transition-colors duration-200 hover:bg-slate-900/[0.05] dark:bg-white/[0.04] dark:hover:bg-white/[0.06]"
            >
              <p className="font-medium">{item.name}</p>
              <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">{item.role}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ov-structure">
        <h3 id="ov-structure" className="eyebrow mb-3">
          Structure
        </h3>
        <ul className="stagger flex flex-col gap-2.5">
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
          <h3 id="ov-run" className="eyebrow mb-3">
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
                  <div className="mt-1.5 flex items-center gap-2 rounded-xl bg-slate-900 px-3.5 py-2.5 font-mono text-[13px] text-slate-100 ring-1 ring-white/[0.06] dark:bg-black/40">
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
          <h3 id="ov-entry" className="eyebrow mb-3">
            Entry points
          </h3>
          <ul className="stagger flex flex-col gap-2.5">
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
          <h3 id="ov-questions" className="eyebrow mb-3">
            Questions to ask
          </h3>
          <ul className="flex flex-wrap gap-2">
            {data.starter_questions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  disabled={!onAsk}
                  onClick={() => onAsk?.(question)}
                  className="rounded-full bg-slate-900/[0.04] px-3.5 py-1.5 text-sm text-slate-700 ring-1 ring-slate-900/[0.06] transition-all duration-200 hover:-translate-y-px hover:bg-slate-900/[0.08] hover:text-slate-900 active:translate-y-0 disabled:cursor-default disabled:opacity-60 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.08] dark:hover:bg-white/10 dark:hover:text-white"
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
