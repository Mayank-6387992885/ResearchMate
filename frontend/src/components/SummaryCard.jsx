import { Copy, Check } from "lucide-react";
import { useState } from "react";
import { formatSummaryText } from "../utils/formatSummary";

export default function SummaryCard({ summary, filename }) {
  const [copied, setCopied] = useState(false);

  async function copySummary() {
    try {
      await navigator.clipboard.writeText(summary);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="panel summary-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">YOUR RESULTS</p>
          <h2>Research paper summary</h2>
          {filename && <p className="muted">{filename}</p>}
        </div>
        <button className="secondary-button compact" onClick={copySummary}>
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <article className="summary-text">{formatSummaryText(summary)}</article>
    </section>
  );
}