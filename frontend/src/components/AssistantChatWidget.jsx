import { useRef, useState } from "react";
import {
  X,
  Send,
  Square,
  LoaderCircle,
  AlertCircle,
  Copy,
  Check,
  RotateCcw,
} from "lucide-react";
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
      <rect
        x="6"
        y="8"
        width="24"
        height="20"
        rx="6"
        fill="currentColor"
        fillOpacity="0.16"
        stroke="currentColor"
        strokeWidth="2.2"
      />
      <circle className="robot-eye" cx="13" cy="17" r="2.3" fill="currentColor" />
      <circle className="robot-eye" cx="23" cy="17" r="2.3" fill="currentColor" />
      <path d="M13 23h10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function FormattedAssistantMessage({ text }) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let currentList = [];

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    const bulletMatch = trimmed.match(/^(?:[-*•]|\d+\.)\s+(.*)$/);
    if (bulletMatch) {
      currentList.push(bulletMatch[1]);
    } else {
      if (currentList.length > 0) {
        blocks.push({ type: "list", items: currentList });
        currentList = [];
      }
      if (trimmed) {
        blocks.push({ type: "text", content: trimmed });
      }
    }
  }
  if (currentList.length > 0) {
    blocks.push({ type: "list", items: currentList });
  }

  function renderInline(content) {
    const parts = content.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
        return (
          <strong key={i} style={{ fontWeight: 600 }}>
            <MathText text={part.slice(2, -2)} />
          </strong>
        );
      }
      return <MathText key={i} text={part} />;
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px", overflowWrap: "anywhere", wordBreak: "break-word" }}>
      {blocks.map((block, idx) =>
        block.type === "list" ? (
          <ul
            key={idx}
            style={{
              margin: 0,
              paddingLeft: "18px",
              display: "flex",
              flexDirection: "column",
              gap: "4px",
            }}
          >
            {block.items.map((item, itemIdx) => (
              <li key={itemIdx} style={{ lineHeight: 1.45 }}>
                {renderInline(item)}
              </li>
            ))}
          </ul>
        ) : (
          <div key={idx} style={{ lineHeight: 1.45 }}>
            {renderInline(block.content)}
          </div>
        ),
      )}
    </div>
  );
}

const SUGGESTED_QUESTIONS = [
  "What can ResearchMate do?",
  "Summarize my saved papers",
  "How do I compare papers?",
];

const INITIAL_GREETING = {
  role: "assistant",
  isGreeting: true,
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
  const [copiedIdx, setCopiedIdx] = useState(null);
  const abortControllerRef = useRef(null);

  async function sendQuestion(rawText) {
    const trimmed = String(rawText || "").trim();
    if (!trimmed || loading) return;

    const controller = new AbortController();
    abortControllerRef.current = controller;

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
        signal: controller.signal,
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
      if (err.name === "AbortError") {
        setError("Request cancelled.");
      } else {
        setError(err.message || "Failed to send message.");
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (loading) {
      handleCancel();
      return;
    }
    sendQuestion(question);
  }

  function handleCancel() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
  }

  async function handleCopy(text, idx) {
    try {
      await navigator.clipboard?.writeText(text);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx((prev) => (prev === idx ? null : prev)), 1500);
    } catch {
      // Ignore clipboard permission errors in non-HTTPS or test environments.
    }
  }

  function handleRetryForMessage(idx) {
    if (loading) return;
    const msg = messages[idx];
    if (!msg) return;
    if (msg.role === "user") {
      sendQuestion(msg.content);
      return;
    }
    for (let i = idx - 1; i >= 0; i -= 1) {
      if (messages[i].role === "user") {
        sendQuestion(messages[i].content);
        return;
      }
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
            height: "500px",
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
              overflowX: "hidden",
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
                  minWidth: 0,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                  gap: "4px",
                }}
              >
                <div
                  style={{
                    width: "100%",
                    boxSizing: "border-box",
                    padding: "9px 12px",
                    borderRadius: "10px",
                    fontSize: "0.9rem",
                    lineHeight: 1.45,
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                    background:
                      msg.role === "user"
                        ? "var(--accent-primary, #2563eb)"
                        : "var(--surface-elevated, #f1f5f9)",
                    color: msg.role === "user" ? "#ffffff" : "inherit",
                  }}
                >
                  {msg.role === "assistant" ? (
                    <FormattedAssistantMessage text={msg.content} />
                  ) : (
                    msg.content
                  )}
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
                            maxWidth: "100%",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {p.title}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {!msg.isGreeting && (
                  <div style={{ display: "flex", gap: "8px", padding: "0 2px" }}>
                    <button
                      type="button"
                      onClick={() => handleCopy(msg.content, idx)}
                      aria-label={`Copy ${msg.role} message`}
                      title="Copy"
                      style={{
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        color: "var(--text-secondary, #6b7280)",
                        fontSize: "0.72rem",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "3px",
                        padding: "2px 4px",
                      }}
                    >
                      {copiedIdx === idx ? <Check size={12} /> : <Copy size={12} />}
                      <span>{copiedIdx === idx ? "Copied" : "Copy"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRetryForMessage(idx)}
                      disabled={loading}
                      aria-label={`Retry ${msg.role} message`}
                      title="Retry"
                      style={{
                        background: "transparent",
                        border: "none",
                        cursor: loading ? "not-allowed" : "pointer",
                        opacity: loading ? 0.5 : 1,
                        color: "var(--text-secondary, #6b7280)",
                        fontSize: "0.72rem",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "3px",
                        padding: "2px 4px",
                      }}
                    >
                      <RotateCcw size={12} />
                      <span>Retry</span>
                    </button>
                  </div>
                )}
              </div>
            ))}

            {!loading && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "2px" }}>
                {SUGGESTED_QUESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => sendQuestion(suggestion)}
                    style={{
                      fontSize: "0.78rem",
                      padding: "5px 10px",
                      borderRadius: "999px",
                      border: "1px solid var(--border-subtle, #d1d5db)",
                      background: "var(--surface-card, #ffffff)",
                      color: "var(--accent-primary, #2563eb)",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}

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
              disabled={loading}
              placeholder={loading ? "Waiting for response..." : "Ask about your papers or ResearchMate..."}
              aria-label="Ask ResearchMate Assistant"
              style={{
                flex: 1,
                minWidth: 0,
                padding: "8px 10px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle, #d1d5db)",
                fontSize: "0.88rem",
                background: "transparent",
                color: "inherit",
              }}
            />
            {loading ? (
              <button
                type="button"
                onClick={handleCancel}
                aria-label="Stop generating"
                title="Stop"
                style={{
                  padding: "8px 12px",
                  borderRadius: "8px",
                  border: "none",
                  background: "#dc2626",
                  color: "#ffffff",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Square size={15} fill="currentColor" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!question.trim()}
                aria-label="Send message"
                style={{
                  padding: "8px 12px",
                  borderRadius: "8px",
                  border: "none",
                  background: "var(--accent-primary, #2563eb)",
                  color: "#ffffff",
                  cursor: !question.trim() ? "not-allowed" : "pointer",
                  opacity: !question.trim() ? 0.6 : 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Send size={16} />
              </button>
            )}
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
