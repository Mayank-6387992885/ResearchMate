import {
  LayoutDashboard,
  FileSearch,
  Library,
  ChevronDown,
  ChevronRight,
  Sun,
  Moon,
  Monitor,
  Server,
} from "lucide-react";
import { useState } from "react";
import { isLocalApi, setApiTarget } from "../services/api";

const COLOR_MODE_OPTIONS = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

export default function Sidebar({
  activePage,
  onNavigate,
  colorMode = "light",
  onColorModeChange,
}) {
  const [workspaceOpen, setWorkspaceOpen] = useState(true);

  return (
    <aside className={`sidebar ${workspaceOpen ? "" : "collapsed"}`}>
      <button
        className="sidebar-section-header"
        type="button"
        aria-label={`${workspaceOpen ? "Collapse" : "Expand"} workspace`}
        aria-expanded={workspaceOpen}
        aria-controls="workspace-navigation"
        onClick={() => setWorkspaceOpen((open) => !open)}
      >
        <span className="sidebar-label">WORKSPACE</span>
        <span className="sidebar-chevron">
          {workspaceOpen ? <ChevronDown size={16} /> : <ChevronRight size={18} />}
        </span>
      </button>

      <nav id="workspace-navigation" aria-label="Workspace">
        <button
          className={`nav-item ${
            activePage === "dashboard" ? "active" : ""
          }`}
          title="Dashboard"
          onClick={() => onNavigate("dashboard")}
        >
          <LayoutDashboard size={18} />
          <span>Dashboard</span>
        </button>

        <button
          className={`nav-item ${
            activePage === "summary" ? "active" : ""
          }`}
          title="AI Paper Summary"
          onClick={() => onNavigate("summary")}
        >
          <FileSearch size={18} />
          <span>AI Paper Summary</span>
        </button>

        <button
          className={`nav-item ${
            activePage === "my-summaries" ? "active" : ""
          }`}
          title="My Summaries"
          onClick={() => onNavigate("my-summaries")}
        >
          <Library size={18} />
          <span>My Summaries</span>
        </button>
      </nav>

      <div className="sidebar-note">
        <strong>ResearchMate</strong>
        <span>Turn complex papers into clear ideas.</span>
      </div>
      <div className="sidebar-theme">
        <span className="sidebar-theme-label">Appearance</span>
        <div className="sidebar-theme-options" role="group" aria-label="Color theme">
          {COLOR_MODE_OPTIONS.map(({ id, label, icon: Icon }) => (
            <button
              className={`sidebar-theme-option${colorMode === id ? " active" : ""}`}
              type="button"
              key={id}
              aria-label={`${label} theme`}
              aria-pressed={colorMode === id}
              title={`${label} theme`}
              onClick={() => onColorModeChange?.(id)}
            >
              <Icon size={15} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="sidebar-api-badge" style={{ padding: "10px 14px", borderTop: "1px solid var(--border-color, rgba(0,0,0,0.06))", fontSize: "11px", display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text-secondary, #64748b)" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
          <Server size={13} style={{ color: isLocalApi() ? "#059669" : "#4f46e5" }} />
          <span>API: <strong style={{ color: isLocalApi() ? "#059669" : "#4f46e5" }}>{isLocalApi() ? "Local (:8000)" : "Cloud (Render)"}</strong></span>
        </span>
        <button
          type="button"
          style={{ background: "none", border: "none", color: "var(--accent-color, #4f46e5)", cursor: "pointer", fontSize: "11px", textDecoration: "underline", padding: 0 }}
          onClick={() => {
            const next = isLocalApi() ? "render" : "local";
            setApiTarget(next);
            window.location.reload();
          }}
          title={isLocalApi() ? "Switch to Render cloud backend" : "Switch to local backend (localhost:8000)"}
        >
          {isLocalApi() ? "Use Cloud" : "Use Local"}
        </button>
      </div>
    </aside>
  );
}