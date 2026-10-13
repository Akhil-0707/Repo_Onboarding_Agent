import { useState } from "react";

import type { Architecture, ArchitectureModule } from "../../api/types";
import type { CodeRef } from "../../lib/refs";
import { CitationChip } from "../CitationChip";
import { MermaidDiagram } from "../MermaidDiagram";
import { RichText } from "../RichText";

function Connections({
  module,
  data,
  names,
}: {
  module: ArchitectureModule;
  data: Architecture;
  names: Map<string, string>;
}) {
  const outgoing = data.edges.filter((edge) => edge.source === module.id);
  if (outgoing.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-col gap-0.5 text-xs text-slate-600 dark:text-slate-400">
      {outgoing.map((edge) => (
        <li key={edge.target}>
          → <span className="font-medium">{names.get(edge.target) ?? edge.target}</span>
          {edge.label && ` — ${edge.label}`}
          {edge.imports > 0 && (
            <span className="text-slate-400">
              {" "}
              ({edge.imports} import{edge.imports === 1 ? "" : "s"})
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ArchitectureSection({
  data,
  onOpen,
}: {
  data: Architecture;
  onOpen: (ref: CodeRef) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const names = new Map(data.modules.map((m) => [m.id, m.name]));

  const select = (id: string) => {
    setSelected(id);
    document.getElementById(`module-${id}`)?.scrollIntoView?.({ block: "nearest" });
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-8">
      <p className="max-w-3xl text-slate-700 dark:text-slate-300">
        <RichText text={data.summary} />
      </p>

      <figure className="surface p-5">
        <MermaidDiagram
          source={data.mermaid}
          label={`Architecture diagram with ${data.modules.length} modules`}
          onNodeClick={select}
        />
        <figcaption className="mt-3 text-xs text-slate-500">
          Solid arrows are relationships described by the AI; dashed arrows are imports found in the
          code, with counts shown for strong links (5 or more). Every count is listed under Modules.
          Click a box to see its files.
        </figcaption>
      </figure>

      <section aria-labelledby="modules-heading">
        <h2 id="modules-heading" className="eyebrow mb-3">
          Modules
        </h2>
        <ul className="stagger grid gap-3 lg:grid-cols-2">
          {data.modules.map((module) => (
            <li
              key={module.id}
              id={`module-${module.id}`}
              aria-current={selected === module.id || undefined}
              className={`surface p-4 transition-shadow duration-450 ${
                selected === module.id ? "ring-2 ring-slate-900 dark:ring-slate-100" : ""
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{module.name}</h3>
                <span className="rounded-full bg-slate-900/[0.05] px-2 py-0.5 text-xs text-slate-600 dark:bg-white/[0.07] dark:text-slate-300">
                  {module.kind}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                <RichText text={module.description} />
              </p>
              {module.paths.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {module.paths.map((path) => (
                    <CitationChip key={path} reference={{ path }} onOpen={onOpen} />
                  ))}
                </div>
              )}
              <Connections module={module} data={data} names={names} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
