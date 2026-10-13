import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RichText } from "./RichText";

describe("RichText", () => {
  it("renders inline code and bold, and leaves the rest as text", () => {
    const { container } = render(
      <p>
        <RichText text="The `Command` class in `lib/command.js` is **the core**." />
      </p>,
    );
    const codes = [...container.querySelectorAll("code")].map((el) => el.textContent);
    expect(codes).toEqual(["Command", "lib/command.js"]);
    expect(container.querySelector("strong")).toHaveTextContent("the core");
    expect(container).toHaveTextContent("The Command class in lib/command.js is the core.");
  });

  it("never interprets HTML and keeps unmatched markers", () => {
    const { container } = render(
      <p>
        <RichText text="<b>x</b> a `b and **c" />
      </p>,
    );
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent("<b>x</b> a `b and **c");
  });
});
