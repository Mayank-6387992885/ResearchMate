import { useState } from "react";
import { MessageSquare, Send, LoaderCircle, BookOpen, AlertCircle } from "lucide-react";
import { API, apiFetch } from "../services/api";
import MathText from "./MathText";
import PdfViewerModal from "./PdfViewerModal";

export default function PaperChatPanel({ paperId, paperTitle }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [viewerPage, setViewerPage] = useState(null);

  if (!paperId) {
    return null;
  }

  async function handleAsk(event) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    setError("");
    setLoading(true);
    setQuestion("");

    const history = messages.map((m) => ({
      question: m.question,
      answer: m.answer,
    }));

    try {
      const response = await apiFetch(API.chatPaper(paperId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, history }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Could not get an answer for this paper.");
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${prev.length}`,
          question: trimmed,
          answer: data.answer || "No answer returned.",
          citations: Array.isArray(data.citations) ? data.citations : [],
        },
      ]);
    } catch (err) {
      setError(err.message || "Failed to ask question.");
      setQuestion(trimmed);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel paper-chat-panel" style={{ marginTop: "1rem" }}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">ASK PAPER (RAG)</p>
          <h3 style={{ display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}>
            <MessageSquare size={18} />
            Chat with {paperTitle || "this paper"}
          </h3>
        </div>
      </div>

      {messages.length > 0 && (
        <div
          className="paper-chat-history"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.9rem",
            marginBottom: "1rem",
            maxHeight: "340px",
            overflowY: "auto",
          }}
        >
          {messages.map((item) => (
            <div
              key={item.id}
              style={{
                border: "1px solid var(--border-color, rgba(148, 163, 184, 0.25))",
                borderRadius: "10px",
                padding: "0.75rem 0.9rem",
                background: "rgba(15, 23, 42, 0.03)",
              }}
            >
              <p style={{ fontWeight: 600, margin: "0 0 0.4rem 0" }}>
                Q: {item.question}
              </p>
              <div style={{ margin: "0 0 0.6rem 0", whiteSpace: "pre-wrap" }}>
                <MathText text={item.answer} />
              </div>
              {item.citations.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                  {item.citations.map((cite, idx) => (
                    <button
                      type="button"
                      key={`${item.id}-cite-${idx}`}
                      title={cite.excerpt}
                      onClick={() => setViewerPage(cite.page || 1)}
                      aria-label={`Open PDF at page ${cite.page}`}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.3rem",
                        fontSize: "0.78rem",
                        padding: "0.2rem 0.55rem",
                        borderRadius: "999px",
                        background: "rgba(79, 70, 229, 0.1)",
                        color: "#4f46e5",
                        fontWeight: 500,
                        border: "none",
                        cursor: "pointer",
                      }}
                    >
                      <BookOpen size={12} />
                      Page {cite.page} · {cite.section}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="classification-warning" role="alert" style={{ marginBottom: "0.75rem" }}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <form
        onSubmit={handleAsk}
        style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about methods, results, datasets, or conclusions..."
          disabled={loading}
          style={{ flex: 1 }}
        />
        <button
          type="submit"
          className="primary-button compact"
          disabled={loading || !question.trim()}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
        >
          {loading ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>
      <PdfViewerModal
        paperId={viewerPage ? paperId : null}
        paperTitle={paperTitle}
        page={viewerPage}
        onClose={() => setViewerPage(null)}
      />
    </section>
  );
}
