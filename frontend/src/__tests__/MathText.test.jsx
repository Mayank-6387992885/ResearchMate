import { describe, it, expect } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import MathText from "../components/MathText";

describe("MathText", () => {
  it("renders plain text safely without math", () => {
    render(<MathText text="Plain text <script>alert(1)</script> here." />);
    expect(
      screen.getByText("Plain text <script>alert(1)</script> here."),
    ).toBeInTheDocument();
  });

  it("renders inline $...$ and \\(...\\) expressions with KaTeX", () => {
    const { container } = render(
      <MathText text={"Energy is $E = mc^2$ and momentum is \\(p = mv\\)."} />,
    );
    const katexElements = container.querySelectorAll(".katex");
    expect(katexElements.length).toBe(2);
    expect(container.textContent).toContain("Energy is");
    expect(container.textContent).toContain("and momentum is");
  });

  it("renders display $$...$$ and \\[...\\] expressions with KaTeX", () => {
    const { container } = render(
      <MathText text={"First:\n$$a^2 + b^2 = c^2$$\nSecond:\n\\[\\int_0^1 x\\,dx = \\frac{1}{2}\\]"} />,
    );
    const displayElements = container.querySelectorAll(".katex-display");
    expect(displayElements.length).toBe(2);
  });

  it("handles invalid LaTeX gracefully without throwing", () => {
    const { container } = render(<MathText text="Broken $\\invalidcommand{$ math" />);
    expect(container.querySelector(".katex-error")).toBeInTheDocument();
  });
});
