import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import AssistantChatWidget from "../components/AssistantChatWidget";
import * as apiModule from "../services/api";

describe("AssistantChatWidget", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("opens with a greeting and answers a workspace query", async () => {
    vi.spyOn(apiModule, "apiFetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "You have Attention Is All You Need saved in your library.",
        referenced_papers: [{ id: 1, title: "Attention Is All You Need" }],
      }),
    });

    render(<AssistantChatWidget />);

    fireEvent.click(screen.getByRole("button", { name: /open researchmate assistant/i }));

    expect(
      screen.getByText(/Hi! I'm your ResearchMate Assistant/i),
    ).toBeTruthy();

    const input = screen.getByLabelText(/ask researchmate assistant/i);
    fireEvent.change(input, { target: { value: "What papers do I have?" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/You have Attention Is All You Need saved in your library/i),
      ).toBeTruthy();
    });
  });
});
