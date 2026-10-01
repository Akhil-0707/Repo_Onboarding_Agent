import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { useFileContent } from "../api/repos";
import { githubRangeLink } from "../lib/github";
import { highlight, plainTokens } from "../lib/highlight";
import type { Token } from "../lib/highlight";
import { ErrorState, LoadingState } from "./StateViews";

export interface LineRange {
  start: number;
  end: number;
}

interface Props {
  repoId: string;
  path: string;
  range: LineRange | null;
  onClose?: () => void;
  onRangeChange?: (range: LineRange | null) => void;
}

export function CodeViewer({ repoId, path, range, onClose, onRangeChange }: Props) {
  const file = useFileContent(repoId, path);
  const [highlighted, setHighlighted] = useState<{ content: string; tokens: Token[][] } | null>(
    null,
  );
  const firstHighlighted = useRef<HTMLDivElement | null>(null);

  const content = file.data?.content;
  const language = file.data?.language ?? "text";

  useEffect(() => {
    if (content === undefined) return;
    let cancelled = false;
    highlight(content, language)
      .then((tokens) => !cancelled && setHighlighted({ content, tokens }))
      .catch(() => undefined); // keep plain text
    return () => {
      cancelled = true;
    };
  }, [content, language]);

  useEffect(() => {
    firstHighlighted.current?.scrollIntoView({ block: "center" });
  }, [highlighted, range?.start]);

  const symbols = useMemo(
    () => (file.data?.symbols ?? []).filter((s) => s.kind !== "variable"),
    [file.data?.symbols],
  );

  if (file.isPending) return <LoadingState label={`Loading ${path}`} />;
  if (file.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Could not open file"
          message={file.error.message}
          onRetry={() => file.refetch()}
        />
      </div>
    );
  }

  const data = file.data;
  // Plain text first; swap in highlighted tokens once they exist for this exact content.
  const lines =
    highlighted?.content === data.content ? highlighted.tokens : plainTokens(data.content);
  const inRange = (line: number) => range !== null && line >= range.start && line <= range.end;

  return (
    <section aria-label={`Code viewer: ${path}`} className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <h2 className="min-w-0 flex-1 truncate font-mono text-sm font-semibold" title={path}>
          {path}
          {range && (
            <span className="ml-2 font-normal text-slate-500">
              L{range.start}
              {range.end !== range.start && `–${range.end}`}
            </span>
          )}
        </h2>
        <span className="text-xs text-slate-500">
          {data.lines} lines · {language}
        </span>
        {symbols.length > 0 && onRangeChange && (
          <select
            aria-label="Jump to symbol"
            className="max-w-48 rounded border border-slate-300 bg-white px-1 py-0.5 text-xs dark:border-slate-700 dark:bg-slate-900"
            value=""
            onChange={(event) => {
              const symbol = symbols[Number(event.target.value)];
              if (symbol) onRangeChange({ start: symbol.start_line, end: symbol.end_line });
            }}
          >
            <option value="" disabled>
              Jump to symbol…
            </option>
            {symbols.map((symbol, index) => (
              <option key={`${symbol.name}-${symbol.start_line}`} value={index}>
                {symbol.parent ? `${symbol.parent}.` : ""}
                {symbol.name} ({symbol.kind})
              </option>
            ))}
          </select>
        )}
        <a
          href={githubRangeLink(data.github_url, range)}
          target="_blank"
          rel="noreferrer"
          className="rounded px-2 py-0.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950"
        >
          View on GitHub ↗
        </a>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close code viewer"
            className="rounded px-2 py-0.5 text-sm hover:bg-slate-200 dark:hover:bg-slate-800"
          >
            ✕
          </button>
        )}
      </header>
      <div className="min-h-0 flex-1 overflow-auto bg-white font-mono text-[13px] leading-5 dark:bg-slate-950">
        <div className="min-w-max py-2">
          {lines.map((lineTokens, index) => {
            const number = index + 1;
            const highlighted = inRange(number);
            return (
              <div
                key={number}
                ref={highlighted && number === range?.start ? firstHighlighted : undefined}
                data-line={number}
                data-highlighted={highlighted || undefined}
                className={`flex ${highlighted ? "bg-amber-100 dark:bg-amber-400/15" : ""}`}
              >
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => onRangeChange?.({ start: number, end: number })}
                  className={`w-12 shrink-0 select-none pr-3 text-right text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 ${
                    highlighted ? "border-l-2 border-amber-500" : "border-l-2 border-transparent"
                  }`}
                >
                  {number}
                </button>
                <code className="whitespace-pre pr-4">
                  {lineTokens.map((token, i) => (
                    <span
                      key={i}
                      className="code-token"
                      style={
                        token.color
                          ? ({ color: token.color, "--dark": token.darkColor } as CSSProperties)
                          : undefined
                      }
                    >
                      {token.content}
                    </span>
                  ))}
                  {lineTokens.length === 0 && " "}
                </code>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
