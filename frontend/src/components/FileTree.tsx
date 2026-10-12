import { useMemo, useState } from "react";

import type { FileEntry } from "../api/types";
import { ancestors, buildTree, filterFiles } from "../lib/fileTree";
import type { TreeNode } from "../lib/fileTree";

interface Props {
  files: FileEntry[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

export function FileTree({ files, selectedPath, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  // Folders the user collapsed while a given file was selected (reset when selection changes).
  const [collapsed, setCollapsed] = useState<{ for: string | null; dirs: Set<string> }>({
    for: null,
    dirs: new Set(),
  });

  const visible = useMemo(() => filterFiles(files, query), [files, query]);
  const tree = useMemo(() => buildTree(visible), [visible]);

  // Reveal the selected file (e.g. opened from a citation).
  const revealed = useMemo(
    () => new Set(selectedPath ? ancestors(selectedPath) : []),
    [selectedPath],
  );
  const userCollapsed = collapsed.for === selectedPath ? collapsed.dirs : new Set<string>();
  const isExpanded = (path: string) =>
    !userCollapsed.has(path) && (open.has(path) || revealed.has(path));

  const toggle = (path: string) => {
    const expanded = isExpanded(path);
    setOpen((current) => {
      const next = new Set(current);
      if (expanded) next.delete(path);
      else next.add(path);
      return next;
    });
    const dirs = new Set(userCollapsed);
    if (expanded) dirs.add(path);
    else dirs.delete(path);
    setCollapsed({ for: selectedPath, dirs });
  };

  const searching = query.trim().length > 0;

  const renderNode = (node: TreeNode, depth: number) => {
    const indent = { paddingLeft: `${depth * 12 + 8}px` };
    if (node.type === "dir") {
      const expanded = searching || isExpanded(node.path);
      return (
        <li key={node.path} role="treeitem" aria-expanded={expanded} aria-selected={false}>
          <button
            type="button"
            onClick={() => toggle(node.path)}
            style={indent}
            className="flex w-full items-center gap-1.5 truncate rounded-md py-1 pr-2 text-left text-sm transition-colors duration-200 hover:bg-slate-900/5 dark:hover:bg-white/[0.06]"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 16 16"
              className={`h-3 w-3 shrink-0 text-slate-400 transition-transform duration-300 ${
                expanded ? "rotate-90" : ""
              }`}
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m6 4 4 4-4 4" />
            </svg>
            <span className="truncate">{node.name}</span>
          </button>
          {expanded && (
            <ul role="group" className="animate-fade-in">
              {node.children.map((c) => renderNode(c, depth + 1))}
            </ul>
          )}
        </li>
      );
    }
    const selected = node.path === selectedPath;
    return (
      <li key={node.path} role="treeitem" aria-selected={selected}>
        <button
          type="button"
          onClick={() => onSelect(node.path)}
          style={indent}
          title={node.path}
          className={`flex w-full items-center gap-1.5 truncate rounded-md py-1 pr-2 text-left font-mono text-[13px] transition-colors duration-200 ${
            selected
              ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
              : "text-slate-700 hover:bg-slate-900/5 dark:text-slate-300 dark:hover:bg-white/[0.06]"
          }`}
        >
          <span className="w-3 shrink-0" />
          <span className="truncate">{node.name}</span>
        </button>
      </li>
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="p-2">
        <label htmlFor="file-filter" className="sr-only">
          Filter files
        </label>
        <input
          id="file-filter"
          type="search"
          placeholder="Filter files…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="field py-1.5"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-1 pb-4">
        {visible.length === 0 ? (
          <p className="px-3 py-2 text-sm text-slate-500">No files match “{query}”.</p>
        ) : (
          <ul role="tree" aria-label="Repository files">
            {tree.children.map((node) => renderNode(node, 0))}
          </ul>
        )}
      </div>
    </div>
  );
}
