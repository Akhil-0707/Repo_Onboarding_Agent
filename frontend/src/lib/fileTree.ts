import type { FileEntry } from "../api/types";

export interface TreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  children: TreeNode[];
  file?: FileEntry;
}

/** Build a nested tree from flat repo paths; directories first, then files, both by name. */
export function buildTree(files: FileEntry[]): TreeNode {
  const root: TreeNode = { name: "", path: "", type: "dir", children: [] };
  const dirs = new Map<string, TreeNode>([["", root]]);

  for (const file of files) {
    const parts = file.path.split("/");
    let parent = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const dirPath = parts.slice(0, i + 1).join("/");
      let dir = dirs.get(dirPath);
      if (!dir) {
        dir = { name: parts[i] ?? "", path: dirPath, type: "dir", children: [] };
        dirs.set(dirPath, dir);
        parent.children.push(dir);
      }
      parent = dir;
    }
    parent.children.push({
      name: parts[parts.length - 1] ?? file.path,
      path: file.path,
      type: "file",
      children: [],
      file,
    });
  }

  const sort = (node: TreeNode) => {
    node.children.sort((a, b) =>
      a.type === b.type ? a.name.localeCompare(b.name) : a.type === "dir" ? -1 : 1,
    );
    node.children.forEach(sort);
  };
  sort(root);
  return root;
}

/** Every ancestor directory of ``path`` (so a selected file can be revealed). */
export function ancestors(path: string): string[] {
  const parts = path.split("/");
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join("/"));
}

export function filterFiles(files: FileEntry[], query: string): FileEntry[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return files;
  return files.filter((file) => file.path.toLowerCase().includes(needle));
}
