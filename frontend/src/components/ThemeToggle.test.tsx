import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/utils";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  it("toggles the dark class and remembers the choice", async () => {
    renderWithProviders(<ThemeToggle />);
    expect(document.documentElement).not.toHaveClass("dark");

    await userEvent.click(await screen.findByRole("button", { name: /switch to dark mode/i }));
    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem("repoguide.theme")).toBe("dark");

    await userEvent.click(screen.getByRole("button", { name: /switch to light mode/i }));
    expect(document.documentElement).not.toHaveClass("dark");
  });
});
