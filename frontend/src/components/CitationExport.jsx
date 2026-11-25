import { useState, useRef, useEffect } from "react";
import { Quote, Copy, Check, Download, ChevronDown } from "lucide-react";
import { fetchPaperCitation } from "../services/api";

const FORMATS = [
  { id: "bibtex", label: "BibTeX (.bib)", ext: "bib" },
  { id: "ris", label: "RIS (.ris)", ext: "ris" },
  { id: "apa", label: "APA", ext: "txt" },
];

export default function CitationExport({ paperId }) {
  const [open, setOpen] = useState(false);
  const [copiedFormat, setCopiedFormat] = useState("");
  const [busyFormat, setBusyFormat] = useState("");
  const [error, setError] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleOutsideClick(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [open]);

  async function handleCopy(formatId) {
    setError("");
    setBusyFormat(`copy-${formatId}`);
    try {
      const text = await fetchPaperCitation(paperId, formatId);
      await navigator.clipboard.writeText(text);
      setCopiedFormat(formatId);
      setTimeout(() => setCopiedFormat(""), 2000);
    } catch (err) {
      setError(err.message || "Failed to copy citation.");
    } finally {
      setBusyFormat("");
    }
  }

  async function handleDownload(formatObj) {
    setError("");
    setBusyFormat(`dl-${formatObj.id}`);
    try {
      const text = await fetchPaperCitation(paperId, formatObj.id);
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `researchmate-citation-${paperId}.${formatObj.ext}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message || "Failed to download citation.");
    } finally {
      setBusyFormat("");
    }
  }

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", display: "inline-block" }}
    >
      <button
        type="button"
        className="secondary-button paper-action-button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <Quote size={15} />
        Cite
        <ChevronDown size={14} />
      </button>

      {open && (
        <div
          role="menu"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            zIndex: 50,
            minWidth: "220px",
            background: "var(--surface-card, #ffffff)",
            color: "var(--text-primary, #111827)",
            border: "1px solid var(--border-subtle, #e5e7eb)",
            borderRadius: "10px",
            padding: "8px",
            boxShadow: "0 10px 25px rgba(0, 0, 0, 0.25)",
          }}
        >
          {FORMATS.map((fmt) => (
            <div
              key={fmt.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "8px",
                padding: "6px 8px",
                borderRadius: "6px",
              }}
            >
              <span style={{ fontSize: "0.875rem", fontWeight: 500 }}>
                {fmt.label}
              </span>
              <div style={{ display: "flex", gap: "4px" }}>
                <button
                  type="button"
                  title={`Copy ${fmt.label}`}
                  className="secondary-button"
                  style={{ padding: "4px 8px", fontSize: "0.75rem" }}
                  disabled={Boolean(busyFormat)}
                  onClick={() => handleCopy(fmt.id)}
                >
                  {copiedFormat === fmt.id ? <Check size={13} /> : <Copy size={13} />}
                </button>
                {(fmt.id === "bibtex" || fmt.id === "ris") && (
                  <button
                    type="button"
                    title={`Download .${fmt.ext}`}
                    className="secondary-button"
                    style={{ padding: "4px 8px", fontSize: "0.75rem" }}
                    disabled={Boolean(busyFormat)}
                    onClick={() => handleDownload(fmt)}
                  >
                    <Download size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
          {error && (
            <div style={{ color: "#f87171", fontSize: "0.75rem", padding: "4px 8px" }}>
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
