import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import PaperChatPanel from "../components/PaperChatPanel";
import * as apiModule from "../services/api";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("PaperChatPanel", () => {
  it("opens PdfViewerModal at the cited page when a citation badge is clicked", async () => {
    vi.spyOn(apiModule, "apiFetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "The model achieved 95% accuracy.",
        citations: [
          { page: 3, section: "Results", excerpt: "We achieved 95% accuracy." },
        ],
      }),
    });

    render(<PaperChatPanel paperId={42} paperTitle="Sample Paper" />);

    const input = screen.getByPlaceholderText(/Ask a question/i);
    fireEvent.change(input, { target: { value: "What was the accuracy?" } });
    fireEvent.submit(input.closest("form"));

    const citationButton = await screen.findByRole("button", {
      name: /Open PDF at page 3/i,
    });
    expect(citationButton).toHaveTextContent("Page 3 · Results");

    fireEvent.click(citationButton);

    const dialog = await screen.findByRole("dialog", {
      name: /PDF Viewer - Sample Paper/i,
    });
    expect(dialog).toBeInTheDocument();

    const iframe = screen.getByTitle(/PDF Viewer - Sample Paper/i);
    expect(iframe).toHaveAttribute(
      "src",
      expect.stringMatching(/\/papers\/42\/pdf#page=3$/)
    );

    const closeBtn = screen.getByRole("button", { name: /Close PDF viewer/i });
    fireEvent.click(closeBtn);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
