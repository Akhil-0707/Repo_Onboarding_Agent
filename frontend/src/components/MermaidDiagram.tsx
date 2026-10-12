import { useEffect, useId, useState } from "react";
import type { MouseEvent } from "react";

import { graphiteDiagram, themeVariables } from "../lib/mermaidTheme";
import { useTheme } from "../lib/theme";

type Mermaid = (typeof import("mermaid"))["default"];

let loader: Promise<Mermaid> | null = null;

/** Mermaid is large: load it only when a diagram is actually shown. */
function loadMermaid(): Promise<Mermaid> {
  loader ??= import("mermaid").then((module) => module.default);
  return loader;
}

// Server node ids are `m_<module id>`; Mermaid renders them as `<prefix>-flowchart-m_<id>-<n>`.
const NODE_ID = /flowchart-m_(.+)-\d+$/;

export function MermaidDiagram({
  source,
  label,
  onNodeClick,
}: {
  source: string;
  label: string;
  onNodeClick?: (moduleId: string) => void;
}) {
  const { resolved } = useTheme();
  const renderId = `mermaid-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [result, setResult] = useState<{ key: string; svg?: string; error?: string } | null>(null);
  const key = `${resolved}\n${source}`;

  useEffect(() => {
    let cancelled = false;
    loadMermaid()
      .then(async (mermaid) => {
        mermaid.initialize({
          startOnLoad: false,
          // No scripts, click callbacks or raw HTML from the diagram source.
          securityLevel: "strict",
          theme: "base",
          themeVariables: themeVariables(resolved === "dark"),
          flowchart: { htmlLabels: false },
        });
        const { svg } = await mermaid.render(
          renderId,
          graphiteDiagram(source, resolved === "dark"),
        );
        if (!cancelled) setResult({ key, svg });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResult({
            key,
            error: error instanceof Error ? error.message : "The diagram could not be drawn.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [key, renderId, resolved, source]);

  const onClick = (event: MouseEvent<HTMLDivElement>) => {
    const node = (event.target as Element).closest("g.node");
    const match = node?.id.match(NODE_ID);
    if (match?.[1] && onNodeClick) onNodeClick(match[1]);
  };

  const current = result?.key === key ? result : null;
  if (current?.error) {
    return (
      <div
        role="alert"
        className="rounded-xl bg-rose-50 p-4 ring-1 ring-rose-200/70 dark:bg-rose-950/30 dark:ring-rose-900/50"
      >
        <p className="text-sm text-red-700 dark:text-red-300">
          The diagram could not be drawn: {current.error}
        </p>
        <pre className="mt-2 overflow-auto text-xs text-slate-500">{source}</pre>
      </div>
    );
  }
  if (!current?.svg) {
    return (
      <div
        role="status"
        aria-label="Drawing diagram"
        className="h-64 animate-pulse rounded-xl bg-slate-900/[0.04] dark:bg-white/[0.04]"
      />
    );
  }
  return (
    // Mermaid sanitises its SVG output (securityLevel "strict"); the source is server-rendered.
    <div
      role="img"
      aria-label={label}
      onClick={onClick}
      className="animate-fade-in overflow-auto [&_g.node]:cursor-pointer [&_g.node]:transition-opacity [&_g.node]:duration-200 [&_g.node:hover]:opacity-80 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: current.svg }}
    />
  );
}
