
import { useEffect, useLayoutEffect, useState } from "react";

import Header from "./components/Header";
import Sidebar from "./components/Sidebar";

import Dashboard from "./pages/Dashboard";
import AutoSummary from "./pages/AutoSummary";
import MySummaries from "./pages/MySummaries";
import AuthGate from "./pages/AuthGate";
import LandingPage from "./pages/LandingPage";
import ProfilePage from "./pages/ProfilePage";
import { API, apiFetch } from "./services/api";

const ACTIVE_PAGE_STORAGE_KEY = "researchmate.activePage";
const PREVIOUS_WORKSPACE_PAGE_STORAGE_KEY = "researchmate.previousWorkspacePage";
const COLOR_MODE_STORAGE_KEY = "researchmate.colorMode";
const APP_PAGES = new Set([
  "dashboard",
  "summary",
  "my-summaries",
  "profile",
  "settings",
  "account-settings",
  "home",
]);
const COLOR_MODES = new Set(["light", "dark", "system"]);

function getSavedColorMode() {
  try {
    const savedMode = window.localStorage.getItem(COLOR_MODE_STORAGE_KEY);
    return COLOR_MODES.has(savedMode) ? savedMode : "light";
  } catch (error) {
    console.warn("Could not read the saved color mode.", error);
    return "light";
  }
}

export default function App() {
  const [activePage, setActivePage] = useState(() => {
    const savedPage = window.sessionStorage.getItem(ACTIVE_PAGE_STORAGE_KEY);
    return APP_PAGES.has(savedPage) ? savedPage : "dashboard";
  });
  const [authMode, setAuthMode] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("verify_email")) return "login";
    if (params.has("reset_password")) return "reset";
    return null;
  });
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [colorMode, setColorMode] = useState(getSavedColorMode);
  const [systemPrefersDark, setSystemPrefersDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const resolvedColorMode = colorMode === "system"
    ? systemPrefersDark ? "dark" : "light"
    : colorMode;

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    function updateSystemPreference(event) {
      setSystemPrefersDark(event.matches);
    }
    mediaQuery.addEventListener("change", updateSystemPreference);
    return () => mediaQuery.removeEventListener("change", updateSystemPreference);
  }, []);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = resolvedColorMode;
  }, [resolvedColorMode]);

  function updateColorMode(mode) {
    if (!COLOR_MODES.has(mode)) return;
    setColorMode(mode);
    try {
      window.localStorage.setItem(COLOR_MODE_STORAGE_KEY, mode);
    } catch (error) {
      console.warn("Could not save the color mode.", error);
    }
  }

  function navigateToPage(page) {
    if (!APP_PAGES.has(page)) return;
    if (page === "home" && activePage !== "home") {
      window.sessionStorage.setItem(PREVIOUS_WORKSPACE_PAGE_STORAGE_KEY, activePage);
    }
    window.sessionStorage.setItem(ACTIVE_PAGE_STORAGE_KEY, page);
    setActivePage(page);
  }

  function returnToPreviousWorkspacePage() {
    const previousPage = window.sessionStorage.getItem(PREVIOUS_WORKSPACE_PAGE_STORAGE_KEY);
    navigateToPage(
      previousPage && APP_PAGES.has(previousPage) && previousPage !== "home"
        ? previousPage
        : "dashboard",
    );
  }

  useEffect(() => {
    let active = true;
    apiFetch(API.currentUser)
      .then(async (response) => {
        if (response.ok) {
          const data = await response.json();
          if (active) setUser(data.user);
        }
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setAuthLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (authLoading) {
    return <div className="auth-loading" role="status">Loading ResearchMate...</div>;
  }

  if (!user) {
    if (!authMode) {
      return (
        <LandingPage
          colorMode={resolvedColorMode}
          onColorModeChange={updateColorMode}
          onNavigateToAuth={setAuthMode}
        />
      );
    }
    return (
      <AuthGate
        initialMode={authMode}
        colorMode={resolvedColorMode}
        onColorModeChange={updateColorMode}
        onAuthenticated={setUser}
        onBackToHome={() => setAuthMode(null)}
      />
    );
  }

  if (activePage === "home") {
    return (
      <LandingPage
        isAuthenticated
        colorMode={resolvedColorMode}
        onColorModeChange={updateColorMode}
        onNavigateToWorkspace={() => navigateToPage("dashboard")}
        onReturnToResearch={returnToPreviousWorkspacePage}
      />
    );
  }

  return (
    <div className="app-shell">
      <Header
        user={user}
        onNavigate={navigateToPage}
        onSignOut={async () => {
          try {
            await apiFetch(API.logout, { method: "POST" });
          } finally {
            window.sessionStorage.removeItem("researchmate.activeSummaryTask");
            window.sessionStorage.removeItem("researchmate.progressSamples");
            window.sessionStorage.removeItem(ACTIVE_PAGE_STORAGE_KEY);
            setUser(null);
          }
        }}
      />

      <div className="app-body">
        <Sidebar
          activePage={activePage}
          onNavigate={navigateToPage}
          colorMode={colorMode}
          onColorModeChange={updateColorMode}
        />

        <main className="main-content">
          {activePage === "dashboard" && (
            <Dashboard
              onStartSummarizing={() => navigateToPage("summary")}
            />
          )}

          <div hidden={activePage !== "summary"}>
            <AutoSummary />
          </div>

          {activePage === "my-summaries" && (
            <MySummaries />
          )}

          {(activePage === "profile" || activePage === "settings" || activePage === "account-settings") && (
            <ProfilePage
              user={user}
              activePage={activePage}
              onNavigate={navigateToPage}
              onUserUpdated={setUser}
            />
          )}
        </main>
      </div>
    </div>
  );
}
