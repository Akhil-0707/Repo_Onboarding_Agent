import { describe, expect, it } from "vitest";

import { MAX_HIGHLIGHT_LINES, canHighlight, highlight, plainTokens } from "./highlight";

// The real Shiki highlighter (JavaScript regex engine, no WASM); other tests mock it.
describe("highlight", () => {
  it("tokenises code with light and dark colours, one array per line", async () => {
    const lines = await highlight("const answer = 42;\nexport default answer;", "typescript");
    expect(lines).toHaveLength(2);
    expect(lines[0]?.map((t) => t.content).join("")).toBe("const answer = 42;");
    const keyword = lines[0]?.find((t) => t.content.trim() === "const");
    expect(keyword?.color).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(keyword?.darkColor).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(keyword?.color).not.toBe(keyword?.darkColor);
  });

  it("maps our language ids to Shiki grammar names", async () => {
    const lines = await highlight('echo "hi"', "shell");
    expect(lines[0]?.length).toBeGreaterThan(1);
  });

  it("falls back to plain text for unknown languages and huge files", async () => {
    expect(await highlight("x = 1", "brainfuck")).toEqual([[{ content: "x = 1" }]]);
    const huge = "a\n".repeat(MAX_HIGHLIGHT_LINES + 1);
    expect(canHighlight("python", huge)).toBe(false);
    expect(await highlight(huge, "python")).toEqual(plainTokens(huge));
  });
});
