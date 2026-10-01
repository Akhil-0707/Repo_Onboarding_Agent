import type { LineRange } from "../components/CodeViewer";

/** Parse "12" or "12-30" (also "L12-L30") into a line range. */
export function parseRange(value: string | null): LineRange | null {
  if (!value) return null;
  const match = /^L?(\d+)(?:-L?(\d+))?$/i.exec(value.trim());
  if (!match) return null;
  const start = Number(match[1]);
  const end = match[2] ? Number(match[2]) : start;
  if (!Number.isFinite(start) || start < 1) return null;
  return { start: Math.min(start, end), end: Math.max(start, end) };
}

export function formatRange(range: LineRange | null): string | null {
  if (!range) return null;
  return range.start === range.end ? `${range.start}` : `${range.start}-${range.end}`;
}
