import { useMemo, useState } from "react";

import type { Glossary } from "../../api/types";
import { CitationChip } from "../CitationChip";
import type { CodeRef } from "../../lib/refs";

export function GlossarySection({
  data,
  onOpen,
}: {
  data: Glossary;
  onOpen: (ref: CodeRef) => void;
}) {
  const [query, setQuery] = useState("");
  const terms = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const sorted = [...data.terms].sort((a, b) => a.term.localeCompare(b.term));
    return needle
      ? sorted.filter(
          (t) =>
            t.term.toLowerCase().includes(needle) || t.definition.toLowerCase().includes(needle),
        )
      : sorted;
  }, [data.terms, query]);

  return (
    <div className="p-6">
      <label htmlFor="glossary-filter" className="sr-only">
        Filter glossary
      </label>
      <input
        id="glossary-filter"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={`Filter ${data.terms.length} terms…`}
        className="mb-4 w-full max-w-sm rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
      />
      {terms.length === 0 ? (
        <p className="text-sm text-slate-500">No terms match “{query}”.</p>
      ) : (
        <dl className="grid gap-3 lg:grid-cols-2">
          {terms.map((term) => (
            <div
              key={term.term}
              className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
            >
              <dt className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-semibold">{term.term}</span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {term.kind}
                </span>
              </dt>
              <dd className="mt-1.5 text-sm text-slate-700 dark:text-slate-300">
                {term.definition}
                {term.path && (
                  <span className="mt-2 block">
                    <span className="mr-1 text-xs text-slate-500">Defined in</span>
                    <CitationChip reference={term as CodeRef} onOpen={onOpen} />
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
