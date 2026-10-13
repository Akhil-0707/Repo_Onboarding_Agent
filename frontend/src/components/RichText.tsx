import type { ReactNode } from "react";

// `code` or **bold**; everything else stays plain text (model output is untrusted, no HTML).
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)/g;

/** Inline Markdown subset for AI-written section text (summaries, explanations, definitions). */
export function RichText({ text }: { text: string }) {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const [token, code] = match;
    if (match.index > last) nodes.push(text.slice(last, match.index));
    nodes.push(
      code ? (
        <code
          key={match.index}
          className="rounded-md bg-slate-900/[0.06] px-1 py-px font-mono text-[0.85em] text-slate-900 dark:bg-white/[0.08] dark:text-slate-100"
        >
          {code.slice(1, -1)}
        </code>
      ) : (
        <strong key={match.index} className="font-semibold text-slate-900 dark:text-white">
          {token.slice(2, -2)}
        </strong>
      ),
    );
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}
