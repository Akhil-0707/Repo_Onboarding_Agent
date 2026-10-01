import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/utils";
import { LandingPage } from "./LandingPage";

function setup() {
  return renderWithProviders(<LandingPage />, {
    routes: [
      { path: "/", element: <LandingPage /> },
      { path: "/dashboard", element: <p>dashboard</p> },
    ],
  });
}

describe("LandingPage", () => {
  it("rejects a non-GitHub URL", async () => {
    setup();
    await userEvent.type(
      await screen.findByLabelText(/github repository url/i),
      "https://gitlab.com/a/b",
    );
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/GitHub repository URL/);
  });

  it("navigates with a valid URL", async () => {
    const { router } = setup();
    await userEvent.type(
      await screen.findByLabelText(/github repository url/i),
      "github.com/pallets/flask",
    );
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(router.state.location.pathname).toBe("/dashboard");
    expect(router.state.location.search).toBe("?analyze=pallets%2Fflask");
  });

  it("fills the input from an example", async () => {
    setup();
    await userEvent.click(await screen.findByText("spf13/cobra"));
    expect(screen.getByLabelText(/github repository url/i)).toHaveValue(
      "https://github.com/spf13/cobra",
    );
  });
});
