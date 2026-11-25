import { X, ExternalLink, FileText } from "lucide-react";
import { API } from "../services/api";

export default function PdfViewerModal({ paperId, paperTitle, page = 1, onClose }) {
  if (!paperId) {
    return null;
  }

  const targetPage = page || 1;
  const pdfUrl = `${API.paperPdf(paperId)}#page=${targetPage}`;

  return (
    <div
      className="pdf-viewer-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={`PDF Viewer - ${paperTitle || "Research Paper"}`}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(15, 23, 42, 0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.25rem",
      }}
    >
      <div
        className="pdf-viewer-modal"
        style={{
          width: "min(1100px, 96vw)",
          height: "min(88vh, 900px)",
          background: "var(--surface-color, #ffffff)",
          color: "var(--text-color, #0f172a)",
          borderRadius: "12px",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          boxShadow: "0 24px 60px rgba(15, 23, 42, 0.35)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0.85rem 1.1rem",
            borderBottom: "1px solid var(--border-color, rgba(148, 163, 184, 0.25))",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
            <FileText size={18} />
            <strong
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {paperTitle || "Research Paper"}
            </strong>
            <span
              style={{
                fontSize: "0.8rem",
                padding: "0.15rem 0.5rem",
                borderRadius: "999px",
                background: "rgba(79, 70, 229, 0.12)",
                color: "#4f46e5",
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              Page {targetPage}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="secondary-button compact"
              style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
            >
              <ExternalLink size={14} />
              Open in tab
            </a>
            <button
              type="button"
              className="icon-button"
              onClick={onClose}
              aria-label="Close PDF viewer"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        <iframe
          title={`PDF Viewer - ${paperTitle || "Research Paper"}`}
          src={pdfUrl}
          style={{
            width: "100%",
            flex: 1,
            border: "none",
            background: "#f8fafc",
          }}
        />
      </div>
    </div>
  );
}
