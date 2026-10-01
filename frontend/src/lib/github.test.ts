import { describe, expect, it } from "vitest";

import { githubBlobUrl, parseGitHubUrl } from "./github";

describe("parseGitHubUrl", () => {
  it.each([
    ["https://github.com/pallets/flask", "pallets", "flask"],
    ["https://github.com/pallets/flask.git", "pallets", "flask"],
    ["github.com/pallets/flask/tree/main/src", "pallets", "flask"],
    ["pallets/flask", "pallets", "flask"],
    ["  https://www.github.com/a-b/c.d  ", "a-b", "c.d"],
  ])("parses %s", (input, owner, name) => {
    expect(parseGitHubUrl(input)).toEqual({ owner, name });
  });

  it.each([
    "",
    "https://gitlab.com/a/b",
    "https://github.com/onlyowner",
    "not a url",
    "https://github.com/a/..",
  ])("rejects %s", (input) => {
    expect(parseGitHubUrl(input)).toBeNull();
  });
});

describe("githubBlobUrl", () => {
  it("links to a line range at a commit", () => {
    expect(githubBlobUrl({ owner: "o", name: "r" }, "abc123", "src/a b.py", 3, 9)).toBe(
      "https://github.com/o/r/blob/abc123/src/a%20b.py#L3-L9",
    );
  });

  it("links to a single line", () => {
    expect(githubBlobUrl({ owner: "o", name: "r" }, "abc", "x.go", 5, 5)).toMatch(/#L5$/);
  });
});
