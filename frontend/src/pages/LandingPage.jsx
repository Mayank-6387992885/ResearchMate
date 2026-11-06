import {
  ArrowRight, BookOpen, BrainCircuit, FileSearch, FolderOpen, Moon, Sparkles, Sun,
} from "lucide-react";

export default function LandingPage({
  onNavigateToAuth,
  isAuthenticated = false,
  colorMode = "light",
  onColorModeChange,
  onNavigateToWorkspace,
  onReturnToResearch,
}) {
  const primaryAction = isAuthenticated ? onNavigateToWorkspace : () => onNavigateToAuth("register");
  const secondaryAction = isAuthenticated ? onReturnToResearch : () => onNavigateToAuth("login");

  return (
    <main className="landing-page">
      <header className="landing-header">
        <div className="brand landing-brand" aria-label="ResearchMate home">
          <span className="brand-icon"><BookOpen size={21} /></span>
          <span>Research<span className="brand-accent">Mate</span></span>
        </div>
        <nav className="landing-actions" aria-label="Account">
          <button
            className="landing-theme-toggle"
            type="button"
            aria-label={`Switch to ${colorMode === "dark" ? "light" : "dark"} theme`}
            aria-pressed={colorMode === "dark"}
            title={`Switch to ${colorMode === "dark" ? "light" : "dark"} theme`}
            onClick={() => onColorModeChange?.(colorMode === "dark" ? "light" : "dark")}
          >
            {colorMode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {isAuthenticated ? (
            <button
              className="primary-button landing-create"
              type="button"
              onClick={onNavigateToWorkspace}
            >
              Open workspace
            </button>
          ) : (
            <>
              <button className="landing-signin" type="button" onClick={() => onNavigateToAuth("login")}>
                Sign in
              </button>
              <button className="primary-button landing-create" type="button" onClick={() => onNavigateToAuth("register")}>
                Create account
              </button>
            </>
          )}
        </nav>
      </header>

      <section className="landing-hero">
        <div className="landing-copy">
          <span className="landing-pill"><Sparkles size={14} /> YOUR AI RESEARCH WORKSPACE</span>
          <h1>Make every research paper easier to understand.</h1>
          <p>
            Turn dense academic papers into clear summaries, organize your library,
            and spend more time on the ideas that matter.
          </p>
          <div className="landing-hero-actions">
            <button className="primary-button landing-primary" type="button" onClick={primaryAction}>
              {isAuthenticated ? "Open workspace" : "Get started"} <ArrowRight size={17} />
            </button>
            <button className="landing-secondary" type="button" onClick={secondaryAction}>
              {isAuthenticated ? "Return to your research" : "I already have an account"}
            </button>
          </div>
          <div className="landing-trust">
            <span><span className="landing-dot" /> Private paper library</span>
            <span><span className="landing-dot" /> AI-powered summaries</span>
          </div>
        </div>

        <div className="landing-preview" aria-label="ResearchMate workspace preview">
          <div className="landing-preview-top">
            <span className="landing-preview-mark"><BookOpen size={17} /></span>
            <div>
              <strong>Research workspace</strong>
              <small>Your library at a glance</small>
            </div>
            <span className="landing-preview-status">Ready</span>
          </div>
          <div className="landing-preview-paper">
            <span className="landing-paper-icon"><FileSearch size={19} /></span>
            <div>
              <strong>Research paper analysis</strong>
              <small>Key ideas, organized for you</small>
            </div>
          </div>
          <div className="landing-summary">
            <div className="landing-summary-title"><BrainCircuit size={17} /> AI summary</div>
            <div className="landing-summary-line landing-summary-line-long" />
            <div className="landing-summary-line" />
            <div className="landing-summary-line landing-summary-line-short" />
            <div className="landing-summary-highlight">
              <Sparkles size={14} />
              <span>Clear takeaways, without the reading overload.</span>
            </div>
          </div>
          <div className="landing-preview-footer">
            <span><FolderOpen size={15} /> Saved research</span>
            <span>Organized by you</span>
          </div>
        </div>
      </section>

      <section className="landing-benefits" aria-label="ResearchMate features">
        <article>
          <span className="landing-benefit-icon"><FileSearch size={19} /></span>
          <div><h2>Understand faster</h2><p>Get readable summaries of complex research papers.</p></div>
        </article>
        <article>
          <span className="landing-benefit-icon"><FolderOpen size={19} /></span>
          <div><h2>Stay organized</h2><p>Save, categorize, and find your research in one place.</p></div>
        </article>
        <article>
          <span className="landing-benefit-icon"><Sparkles size={19} /></span>
          <div><h2>Focus on insights</h2><p>Spend less time sorting through papers and more time learning.</p></div>
        </article>
      </section>
      <footer className="landing-footer">ResearchMate · Your research, organized.</footer>
    </main>
  );
}
