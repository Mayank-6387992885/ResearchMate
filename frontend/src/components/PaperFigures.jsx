import React, { useState, useEffect } from "react";
import "../styles/paperFigures.css";

export default function PaperFigures({ figures = [] }) {
  const [selectedFigure, setSelectedFigure] = useState(null);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setSelectedFigure(null);
      }
    }
    if (selectedFigure) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedFigure]);

  if (!figures || figures.length === 0) {
    return (
      <section className="panel paper-figures-panel">
        <p className="eyebrow">VISUAL INSIGHTS</p>
        <h2>Paper Figures & Diagrams</h2>
        <p className="muted">
          No embedded diagrams or figures were detected in this document.
          Architecture illustrations and charts appear here when present in the PDF.
        </p>
      </section>
    );
  }

  const handleDownload = (fig) => {
    try {
      const link = document.createElement("a");
      link.href = fig.data_url;
      link.download = `figure-p${fig.page || 1}-${fig.id || 1}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      console.error("Failed to download figure:", e);
    }
  };

  return (
    <section className="panel paper-figures-panel">
      <div className="figures-header-row">
        <div>
          <p className="eyebrow">VISUAL INSIGHTS</p>
          <h2>Paper Figures & Diagrams</h2>
        </div>
        <span className="figures-count-badge">
          🖼️ {figures.length} {figures.length === 1 ? "figure" : "figures"} extracted
        </span>
      </div>

      <div className="figures-grid">
        {figures.map((fig) => (
          <div
            key={fig.id}
            className="figure-card"
            onClick={() => setSelectedFigure(fig)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelectedFigure(fig);
              }
            }}
          >
            <div className="figure-card-img-wrap">
              <span className="figure-card-badge">Page {fig.page}</span>
              <img
                src={fig.data_url}
                alt={fig.caption || `Figure ${fig.id}`}
                className="figure-card-img"
                loading="lazy"
              />
            </div>
            <div className="figure-card-info">
              <p className="figure-card-caption">{fig.caption || `Figure ${fig.id}`}</p>
              <div className="figure-card-meta">
                <span>{fig.width && fig.height ? `${fig.width} × ${fig.height} px` : "Diagram"}</span>
                <span>Click to expand ↗</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {selectedFigure && (
        <div
          className="figure-modal-backdrop"
          onClick={() => setSelectedFigure(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="figure-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="figure-modal-header">
              <div className="figure-modal-title">
                <span className="figures-count-badge">Page {selectedFigure.page}</span>
                <span>{selectedFigure.caption?.slice(0, 60) || `Figure ${selectedFigure.id}`}</span>
              </div>
              <div className="figure-modal-actions">
                <button
                  type="button"
                  className="figure-modal-btn"
                  onClick={() => handleDownload(selectedFigure)}
                  title="Download image as PNG"
                >
                  ⬇ Download
                </button>
                <button
                  type="button"
                  className="figure-modal-close-btn"
                  onClick={() => setSelectedFigure(null)}
                  aria-label="Close figure preview"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="figure-modal-body">
              <img
                src={selectedFigure.data_url}
                alt={selectedFigure.caption || `Figure ${selectedFigure.id}`}
                className="figure-modal-img"
              />
            </div>

            <div className="figure-modal-footer">
              <p className="figure-modal-caption">
                <strong>Caption:</strong> {selectedFigure.caption || "No caption detected."}
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
