import { useMemo, useState } from "react";

import type { Glossary } from "../../api/types";
import { CitationChip } from "../CitationChip";
import type { CodeRef } from "../../lib/refs";
import { RichText } from "../RichText";

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
    <div className="mx-auto max-w-5xl px-6 py-8">
      <label htmlFor="glossary-filter" className="sr-only">
        Filter glossary
      </label>
      <input
        id="glossary-filter"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={`Filter ${data.terms.length} terms…`}
        className="field mb-5 max-w-sm"
      />
      {terms.length === 0 ? (
        <p className="text-sm text-slate-500">No terms match “{query}”.</p>
      ) : (
        <dl className="stagger grid gap-3 lg:grid-cols-2">
          {terms.map((term) => (
            <div key={term.term} className="surface surface-hover p-4">
              <dt className="flex flex-wrap items-center gap-2">
                <span className="font-mono font-semibold">{term.term}</span>
                <span className="rounded-full bg-slate-900/[0.05] px-2 py-0.5 text-xs text-slate-600 dark:bg-white/[0.07] dark:text-slate-300">
                  {term.kind}
                </span>
              </dt>
              <dd className="mt-1.5 text-sm text-slate-700 dark:text-slate-300">
                <RichText text={term.definition} />
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
