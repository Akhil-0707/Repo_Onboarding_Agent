import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SoundEngine } from "../lib/sound";
import { SoundToggle } from "./SoundToggle";

describe("SoundToggle", () => {
  it("mutes and unmutes the UI sounds", async () => {
    const engine = new SoundEngine(undefined);
    render(<SoundToggle engine={engine} />);

    const button = screen.getByRole("button", { name: "Turn sound off" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(button);
    expect(engine.enabled).toBe(false);
    expect(screen.getByRole("button", { name: "Turn sound on" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await userEvent.click(screen.getByRole("button", { name: "Turn sound on" }));
    expect(engine.enabled).toBe(true);
  });
});
