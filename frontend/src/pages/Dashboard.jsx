import { FileText, Zap, ShieldCheck } from "lucide-react";

export default function Dashboard({ onStartSummarizing }) {
  return (
    <div className="page">
      <div className="welcome-row">
        <div>
          <p className="eyebrow">YOUR RESEARCH WORKSPACE</p>
          <h1>Make research easier to understand.</h1>
          <p className="muted">Upload a research paper and let ResearchMate explain its key ideas in simple language.</p>
        </div>
        <button className="primary-button" onClick={onStartSummarizing}>
          <FileText size={17} /> Summarize a paper
        </button>
      </div>

      <div className="feature-grid">
        <div className="panel feature-card">
          <div className="feature-icon"><FileText /></div>
          <h3>Upload a PDF</h3>
          <p className="muted">Select a research paper in PDF format.</p>
        </div>
        <div className="panel feature-card">
          <div className="feature-icon"><Zap /></div>
          <h3>AI summarization</h3>
          <p className="muted">Break down complex sections into simpler explanations.</p>
        </div>
        <div className="panel feature-card">
          <div className="feature-icon"><ShieldCheck /></div>
          <h3>Track progress</h3>
          <p className="muted">See live progress while the paper is being analyzed.</p>
        </div>
      </div>

      <section className="panel getting-started">
        <div>
          <p className="eyebrow">GET STARTED</p>
          <h2>Have a research paper ready?</h2>
          <p className="muted">Start with one PDF. Your summary will appear here after processing.</p>
        </div>
        <button className="secondary-button" onClick={onStartSummarizing}>Open AI Paper Summary</button>
      </section>
    </div>
  );
}