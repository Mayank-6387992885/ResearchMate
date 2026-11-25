import { useState } from "react";
import { X, Send, LoaderCircle, AlertCircle } from "lucide-react";
import { API, apiFetch } from "../services/api";
import MathText from "./MathText";

function RobotIcon({ size = 28 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <line x1="18" y1="3" x2="18" y2="8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="18" cy="3" r="2" fill="currentColor" />
      <rect x="6" y="8" width="24" height="20" rx="6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="2.2" />
      <circle className="robot-eye" cx="13" cy="17" r="2.3" fill="currentColor" />
      <circle className="robot-eye" cx="23" cy="17" r="2.3" fill="currentColor" />
      <path d="M13 23h10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

const INITIAL_GREETING = {
  role: "assistant",
  content:
    "Hi! I'm your ResearchMate Assistant. Ask me anything about your saved papers or how to use ResearchMate.",
  referenced_papers: [],
};

export default function AssistantChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([INITIAL_GREETING]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;

    const nextHistory = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setQuestion("");
    setError("");
    setLoading(true);

    try {
      const response = await apiFetch(API.assistantChat, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, history: nextHistory }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Could not reach ResearchMate Assistant.");
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "No response received.",
          referenced_papers: data.referenced_papers || [],
        },
      ]);
    } catch (err) {
      setError(err.message || "Failed to send message.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="assistant-widget-root"
      style={{
        position: "fixed",
        right: "20px",
        bottom: "20px",
        zIndex: 1200,
        fontFamily: "inherit",
      }}
    >
      {isOpen ? (
        <div
          className="assistant-dialog"
          role="dialog"
          aria-label="ResearchMate Assistant"
          style={{
            width: "360px",
            maxWidth: "calc(100vw - 32px)",
            height: "480px",
            maxHeight: "calc(100vh - 48px)",
            background: "var(--surface-card, #ffffff)",
            color: "var(--text-primary, #111827)",
            border: "1px solid var(--border-subtle, #e5e7eb)",
            borderRadius: "14px",
            boxShadow: "0 16px 40px rgba(0, 0, 0, 0.18)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 14px",
              borderBottom: "1px solid var(--border-subtle, #e5e7eb)",
              background: "var(--surface-elevated, #f8fafc)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 600 }}>
              <RobotIcon size={20} />
              <span>ResearchMate Assistant</span>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close assistant"
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "inherit",
                padding: "4px",
                display: "flex",
                alignItems: "center",
              }}
            >
              <X size={18} />
            </button>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "12px",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
            }}
          >
            {messages.map((msg, idx) => (
              <div
                key={idx}
                style={{
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "88%",
                  padding: "9px 12px",
                  borderRadius: "10px",
                  fontSize: "0.9rem",
                  lineHeight: 1.45,
                  background:
                    msg.role === "user"
                      ? "var(--accent-primary, #2563eb)"
                      : "var(--surface-elevated, #f1f5f9)",
                  color: msg.role === "user" ? "#ffffff" : "inherit",
                }}
              >
                {msg.role === "assistant" ? <MathText text={msg.content} /> : msg.content}
                {msg.referenced_papers && msg.referenced_papers.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "6px" }}>
                    {msg.referenced_papers.map((p) => (
                      <span
                        key={p.id}
                        style={{
                          fontSize: "0.75rem",
                          padding: "2px 7px",
                          borderRadius: "999px",
                          background: "rgba(37, 99, 235, 0.12)",
                          color: "var(--accent-primary, #2563eb)",
                        }}
                      >
                        {p.title}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", opacity: 0.75 }}>
                <LoaderCircle size={15} className="spin" />
                <span>Thinking...</span>
              </div>
            )}
            {error && (
              <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.85rem", color: "#dc2626" }}>
                <AlertCircle size={15} />
                <span>{error}</span>
              </div>
            )}
          </div>

          <form
            onSubmit={handleSubmit}
            style={{
              display: "flex",
              gap: "8px",
              padding: "10px 12px",
              borderTop: "1px solid var(--border-subtle, #e5e7eb)",
            }}
          >
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask about your papers or ResearchMate..."
              aria-label="Ask ResearchMate Assistant"
              style={{
                flex: 1,
                padding: "8px 10px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle, #d1d5db)",
                fontSize: "0.88rem",
                background: "transparent",
                color: "inherit",
              }}
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              aria-label="Send message"
              style={{
                padding: "8px 12px",
                borderRadius: "8px",
                border: "none",
                background: "var(--accent-primary, #2563eb)",
                color: "#ffffff",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Send size={16} />
            </button>
          </form>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          aria-label="Open ResearchMate Assistant"
          className="assistant-robot-btn"
          style={{
            width: "56px",
            height: "56px",
            borderRadius: "50%",
            border: "none",
            background: "var(--accent-primary, #2563eb)",
            color: "#ffffff",
            boxShadow: "0 8px 24px rgba(37, 99, 235, 0.35)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            animation: "assistantFloat 3s ease-in-out infinite",
          }}
        >
          <style>{`
            @keyframes assistantFloat {
              0%, 100% { transform: translateY(0px); }
              50% { transform: translateY(-5px); }
            }
            @keyframes robotBlink {
              0%, 92%, 100% { transform: scaleY(1); }
              96% { transform: scaleY(0.15); }
            }
            .assistant-robot-btn .robot-eye {
              transform-origin: center;
              animation: robotBlink 4s infinite;
            }
          `}</style>
          <RobotIcon size={30} />
        </button>
      )}
    </div>
  );
}
