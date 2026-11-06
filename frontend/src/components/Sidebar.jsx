import {
  LayoutDashboard,
  FileSearch,
  Library,
  ChevronDown,
  ChevronRight,
  Sun,
  Moon,
  Monitor,
} from "lucide-react";
import { useState } from "react";

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
    </aside>
  );
}