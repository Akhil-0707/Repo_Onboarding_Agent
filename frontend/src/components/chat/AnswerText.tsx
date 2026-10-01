import type { ReactNode } from "react";

import type { ChatCitation } from "../../api/chat";
import type { CodeRef } from "../../lib/refs";
import { CitationChip } from "../CitationChip";

// `code`, **bold**, or a [path:start-end] citation (not a Markdown link).
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\[[^[\]\s]+?(?::\d+(?:-\d+)?)?\](?!\())/g;
const CITATION = /^\[([^[\]\s]+?)(?::(\d+)(?:-(\d+))?)?\]$/;
const FENCE = /```[^\n]*\n?([\s\S]*?)(?:```|$)/g;

function citationKey(path: string, start: number | null, end: number | null): string {
  return `${path}:${start ?? ""}:${end ?? start ?? ""}`;
}

function inline(
  text: string,
  known: Set<string>,
  onOpen: (ref: CodeRef) => void,
  key: string,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index;
    if (index > last) nodes.push(text.slice(last, index));
    const [token, code, bold, citation] = match;
    const id = `${key}-${index}`;
    if (code) {
      nodes.push(
        <code
          key={id}
          className="rounded bg-slate-100 px-1 font-mono text-[0.85em] dark:bg-slate-800"
        >
          {code.slice(1, -1)}
        </code>,
      );
    } else if (bold) {
      nodes.push(<strong key={id}>{bold.slice(2, -2)}</strong>);
    } else if (citation) {
      const parts = CITATION.exec(citation);
      const path = parts?.[1] ?? "";
      const start = parts?.[2] ? Number(parts[2]) : null;
      const end = parts?.[3] ? Number(parts[3]) : start;
      // Only references the server validated become clickable.
      if (known.has(citationKey(path, start, end))) {
        nodes.push(
          <CitationChip
            key={id}
            reference={{ path, start_line: start, end_line: end }}
            onOpen={onOpen}
          />,
        );
      } else {
        nodes.push(token);
      }
    }
    last = index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function Prose({
  text,
  known,
  onOpen,
  keyPrefix,
}: {
  text: string;
  known: Set<string>;
  onOpen: (ref: CodeRef) => void;
  keyPrefix: string;
}) {
  const blocks = text.split(/\n\s*\n/).filter((block) => block.trim());
  return (
    <>
      {blocks.map((block, b) => {
        const key = `${keyPrefix}-${b}`;
        const lines = block.split("\n").filter((line) => line.trim());
        if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
          return (
            <ul key={key} className="ml-5 list-disc">
              {lines.map((line, i) => (
                <li key={i}>
                  {inline(line.replace(/^\s*[-*]\s+/, ""), known, onOpen, `${key}-${i}`)}
                </li>
              ))}
            </ul>
          );
        }
        if (lines.every((line) => /^\s*\d+[.)]\s+/.test(line))) {
          return (
            <ol key={key} className="ml-5 list-decimal">
              {lines.map((line, i) => (
                <li key={i}>
                  {inline(line.replace(/^\s*\d+[.)]\s+/, ""), known, onOpen, `${key}-${i}`)}
                </li>
              ))}
            </ol>
          );
        }
        const heading = /^#{1,6}\s+(.*)$/.exec(lines[0] ?? "");
        if (heading && lines.length === 1) {
          return (
            <p key={key} className="font-semibold">
              {inline(heading[1] ?? "", known, onOpen, key)}
            </p>
          );
        }
        return (
          <p key={key}>
            {lines.map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                {inline(line, known, onOpen, `${key}-${i}`)}
              </span>
            ))}
          </p>
        );
      })}
    </>
  );
}

/** Renders an answer: a safe Markdown subset (no HTML) with clickable validated citations. */
export function AnswerText({
  text,
  citations,
  onOpen,
}: {
  text: string;
  citations: ChatCitation[];
  onOpen: (ref: CodeRef) => void;
}) {
  const known = new Set(citations.map((c) => citationKey(c.path, c.start_line, c.end_line)));
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(FENCE)) {
    if (match.index > last) {
      parts.push(
        <Prose
          key={`p${last}`}
          text={text.slice(last, match.index)}
          known={known}
          onOpen={onOpen}
          keyPrefix={`p${last}`}
        />,
      );
    }
    parts.push(
      <pre
        key={`c${match.index}`}
        className="overflow-x-auto rounded-md bg-slate-100 p-3 font-mono text-xs dark:bg-slate-800"
      >
        <code>{(match[1] ?? "").replace(/\n$/, "")}</code>
      </pre>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push(
      <Prose
        key={`p${last}`}
        text={text.slice(last)}
        known={known}
        onOpen={onOpen}
        keyPrefix={`p${last}`}
      />,
    );
  }
  return <div className="flex flex-col gap-2 text-sm leading-relaxed">{parts}</div>;
}
