export interface CodeRef {
  path: string;
  start_line?: number | null;
  end_line?: number | null;
}

export function formatRef(ref: CodeRef): string {
  if (!ref.start_line) return ref.path;
  return ref.end_line && ref.end_line !== ref.start_line
    ? `${ref.path}:${ref.start_line}-${ref.end_line}`
    : `${ref.path}:${ref.start_line}`;
}
