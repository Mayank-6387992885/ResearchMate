import { useEffect, useRef, useState } from "react";
import { BookOpen, CircleUserRound, LogOut, Settings, Sparkles } from "lucide-react";

import ProfilePhoto from "./ProfilePhoto";

export default function Header({ user, onSignOut, onNavigate }) {
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef(null);

  function navigateTo(page) {
    setProfileMenuOpen(false);
    onNavigate(page);
  }

  useEffect(() => {
    if (!profileMenuOpen) return undefined;

    function closeOnOutsideInteraction(event) {
      if (!profileMenuRef.current?.contains(event.target)) {
        setProfileMenuOpen(false);
      }
    }

    function closeOnEscape(event) {
      if (event.key === "Escape") setProfileMenuOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutsideInteraction);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideInteraction);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [profileMenuOpen]);

  return (
    <header className="topbar">
      <button
        className="brand"
        type="button"
        aria-label="ResearchMate home"
        title="Go to ResearchMate home"
        onClick={() => navigateTo("home")}
      >
        <div className="brand-icon"><BookOpen size={21} /></div>
        <span>Research<span className="brand-accent">Mate</span></span>
      </button>
      <div className="topbar-account">
        <div className="topbar-tag"><Sparkles size={15} /> Understand research, faster</div>
        <div className="profile-menu-wrap" ref={profileMenuRef}>
          <button
            className="profile-menu-trigger"
            type="button"
            aria-label={`Open account menu for ${user.email}`}
            aria-haspopup="menu"
            aria-expanded={profileMenuOpen}
            onClick={() => setProfileMenuOpen((open) => !open)}
          >
            <ProfilePhoto
              className="profile-menu-avatar"
              fallbackClassName=""
              imageVersion={user.profile_image_url}
              previewUrl={user.profile_image_preview_url}
              name={user.full_name || user.email}
              fallbackText={(user.full_name || user.email).slice(0, 1).toUpperCase()}
            />
          </button>
          {profileMenuOpen && (
            <div className="profile-menu" role="menu">
              <div className="profile-menu-heading">
                <strong>{user.email}</strong>
                <small>ResearchMate account</small>
              </div>
              <button type="button" role="menuitem" onClick={() => navigateTo("profile")}>
                <CircleUserRound size={17} /> View profile
              </button>
              <button type="button" role="menuitem" onClick={() => navigateTo("settings")}>
                <CircleUserRound size={17} /> Profile settings
              </button>
              <button type="button" role="menuitem" onClick={() => navigateTo("account-settings")}>
                <Settings size={17} /> Account settings
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setProfileMenuOpen(false);
                  onSignOut();
                }}
              >
                <LogOut size={17} /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}