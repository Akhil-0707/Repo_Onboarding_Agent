import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, mockFetch, renderWithProviders } from "../test/utils";
import { CodeViewer } from "./CodeViewer";
import { FileTree } from "./FileTree";

vi.mock("../lib/highlight", async (original) => {
  const actual = await original<typeof import("../lib/highlight")>();
  // Shiki is exercised in the browser; tests only need tokens.
  return { ...actual, highlight: async (code: string) => actual.plainTokens(code) };
});

const content = Array.from({ length: 30 }, (_, i) => `line ${i + 1}`).join("\n");

function fileResponse() {
  return jsonResponse({
    path: "src/app.py",
    language: "python",
    size: content.length,
    lines: 30,
    start_line: 1,
    end_line: 30,
    content,
    symbols: [{ name: "main", kind: "function", start_line: 20, end_line: 25, parent: null }],
    github_url: "https://github.com/acme/tool/blob/abc/src/app.py",
  });
}

describe("CodeViewer", () => {
  it("renders the file, highlights the range and links to those lines on GitHub", async () => {
    mockFetch(() => fileResponse());
    renderWithProviders(<CodeViewer repoId="r1" path="src/app.py" range={{ start: 5, end: 7 }} />);

    expect(await screen.findByText("line 30")).toBeInTheDocument();
    const highlighted = document.querySelectorAll("[data-highlighted]");
    expect([...highlighted].map((el) => el.getAttribute("data-line"))).toEqual(["5", "6", "7"]);
    expect(screen.getByRole("link", { name: /view on github/i })).toHaveAttribute(
      "href",
      "https://github.com/acme/tool/blob/abc/src/app.py#L5-L7",
    );
  });

  it("jumps to a symbol", async () => {
    mockFetch(() => fileResponse());
    const onRangeChange = vi.fn();
    renderWithProviders(
      <CodeViewer repoId="r1" path="src/app.py" range={null} onRangeChange={onRangeChange} />,
    );
    await userEvent.selectOptions(await screen.findByLabelText("Jump to symbol"), "0");
    expect(onRangeChange).toHaveBeenCalledWith({ start: 20, end: 25 });
  });

  it("shows an error state when the file cannot be loaded", async () => {
    mockFetch(() =>
      jsonResponse({ error: { code: "not_found", message: "File not found: x" } }, 404),
    );
    renderWithProviders(<CodeViewer repoId="r1" path="x" range={null} />);
    expect(await screen.findByText("File not found: x")).toBeInTheDocument();
  });
});

describe("FileTree", () => {
  const files = ["src/app.py", "src/util/helpers.py", "README.md"].map((path) => ({
    path,
    language: "python",
    size: 10,
    lines: 1,
  }));

  it("reveals the selected file and selects files on click", async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <FileTree files={files} selectedPath="src/util/helpers.py" onSelect={onSelect} />,
    );
    const tree = await screen.findByRole("tree");
    expect(within(tree).getByRole("button", { name: "helpers.py" })).toBeInTheDocument();
    await userEvent.click(within(tree).getByRole("button", { name: "README.md" }));
    expect(onSelect).toHaveBeenCalledWith("README.md");
  });

  it("collapses folders and filters by path", async () => {
    renderWithProviders(<FileTree files={files} selectedPath={null} onSelect={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "app.py" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "src" }));
    expect(screen.getByRole("button", { name: "app.py" })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Filter files"), "helpers");
    expect(screen.getByRole("button", { name: "helpers.py" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "README.md" })).not.toBeInTheDocument();
  });
});
