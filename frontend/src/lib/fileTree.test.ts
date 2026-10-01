import { describe, expect, it } from "vitest";

import type { FileEntry } from "../api/types";
import { ancestors, buildTree, filterFiles } from "./fileTree";
import { formatRange, parseRange } from "./range";

const file = (path: string): FileEntry => ({ path, language: "text", size: 1, lines: 1 });

describe("buildTree", () => {
  it("nests paths with directories first, then files, alphabetically", () => {
    const tree = buildTree(["src/b.ts", "README.md", "src/a/x.ts", "src/a.ts"].map(file));
    expect(tree.children.map((n) => `${n.type}:${n.name}`)).toEqual(["dir:src", "file:README.md"]);
    const src = tree.children[0];
    expect(src?.children.map((n) => `${n.type}:${n.path}`)).toEqual([
      "dir:src/a",
      "file:src/a.ts",
      "file:src/b.ts",
    ]);
  });
});

describe("helpers", () => {
  it("lists ancestor directories", () => {
    expect(ancestors("a/b/c.py")).toEqual(["a", "a/b"]);
    expect(ancestors("top.py")).toEqual([]);
  });

  it("filters case-insensitively", () => {
    expect(filterFiles(["src/App.tsx", "lib/x.ts"].map(file), "app").map((f) => f.path)).toEqual([
      "src/App.tsx",
    ]);
  });

  it.each([
    ["12", { start: 12, end: 12 }],
    ["12-30", { start: 12, end: 30 }],
    ["L5-L9", { start: 5, end: 9 }],
    ["30-12", { start: 12, end: 30 }],
  ])("parses range %s", (input, expected) => {
    expect(parseRange(input)).toEqual(expected);
  });

  it("rejects bad ranges and formats good ones", () => {
    expect(parseRange("0")).toBeNull();
    expect(parseRange("abc")).toBeNull();
    expect(formatRange({ start: 3, end: 3 })).toBe("3");
    expect(formatRange({ start: 3, end: 8 })).toBe("3-8");
  });
});
