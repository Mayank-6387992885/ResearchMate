import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft, BadgeCheck, Bell, BriefcaseBusiness, CalendarDays, Camera, ChevronDown, ChevronLeft, ChevronRight,
  ExternalLink, FileText, GraduationCap, KeyRound, Link, LockKeyhole, MapPin, Microscope, Phone, ShieldCheck,
  Trash2, UserRound,
} from "lucide-react";

import { API, apiFetch } from "../services/api";
import ProfilePhoto from "../components/ProfilePhoto";
import TimedFeedback from "../components/TimedFeedback";

const PROFILE_DEFAULTS = {
  username: "",
  full_name: "",
  date_of_birth: "",
  gender: "",
  phone_number: "",
  country: "",
  state: "",
  city: "",
  short_bio: "",
  education_level: "",
  institution: "",
  department: "",
  degree: "",
  specialization: "",
  graduation_year: "",
  academic_role: "",
  research_interests: "",
  research_areas: "",
  skills: "",
  research_experience: "",
  publications: "",
  projects: "",
  research_goals: "",
  github_url: "",
  linkedin_url: "",
  google_scholar_url: "",
  orcid_id: "",
  personal_website: "",
  researchgate_url: "",
  email_address: "",
  email_verified: false,
  profile_image_url: null,
};

const NOTIFICATION_DEFAULTS = {
  email_notifications: false,
  research_recommendations: false,
  collaboration_requests: false,
  project_updates: false,
  messages_replies: false,
  platform_announcements: false,
  weekly_digest: false,
};

const PRIVACY_DEFAULTS = {
  profile_visibility: "private",
  show_email: false,
  show_education: true,
  show_research_interests: true,
  show_publications: true,
  allow_collaboration_requests: false,
  search_engine_visibility: false,
};

const SETTINGS_SECTION_STORAGE_KEY = "researchmate.profileSettingsSection";
const SETTINGS_SECTION_IDS = new Set([
  "personal",
  "academic",
  "research",
  "links",
  "account",
  "notifications",
  "privacy",
]);

const SECTIONS = [
  { id: "personal", title: "Personal Information", description: "Name, photo, bio, location", icon: UserRound },
  { id: "academic", title: "Academic Information", description: "Education, degree, institution", icon: GraduationCap },
  { id: "research", title: "Research Profile", description: "Interests, skills, publications", icon: Microscope },
  { id: "links", title: "Social & Professional Links", description: "GitHub, LinkedIn, ORCID", icon: Link },
  { id: "account", title: "Account & Security", description: "Password, login, security", icon: ShieldCheck },
  { id: "notifications", title: "Notifications", description: "Email and platform alerts", icon: Bell },
  { id: "privacy", title: "Privacy", description: "Visibility and permissions", icon: LockKeyhole },
];

const PROFILE_FIELDS = {
  personal: [
    { name: "full_name", label: "Full name", placeholder: "Your name", required: true },
    { name: "username", label: "Username", placeholder: "Choose a unique username", hint: "3–30 letters, numbers, or underscores.", required: true },
    { name: "email_address", label: "Email address", readOnly: true, required: true },
    { name: "date_of_birth", label: "Date of birth", type: "date", required: true },
    { name: "gender", label: "Gender", type: "select", options: ["", "Woman", "Man", "Non-binary", "Prefer not to say"], required: true },
    { name: "phone_number", label: "Phone number", type: "tel", required: true },
    { name: "country", label: "Country", required: true },
    { name: "state", label: "State / Province", required: true },
    { name: "city", label: "City", required: true },
    { name: "short_bio", label: "Short bio", type: "textarea", placeholder: "A brief introduction", wide: true, required: true },
  ],
  academic: [
    { name: "education_level", label: "Education level", placeholder: "e.g. Undergraduate, Graduate, PhD" },
    { name: "institution", label: "Institution", placeholder: "College or university" },
    { name: "department", label: "Department", placeholder: "e.g. Computer Science" },
    { name: "degree", label: "Degree", placeholder: "e.g. B.Tech, M.Sc, PhD" },
    { name: "specialization", label: "Specialization" },
    { name: "graduation_year", label: "Graduation year", type: "number", min: 1900, max: 2200 },
    { name: "academic_role", label: "Academic role", placeholder: "Student, Researcher, Professor..." },
  ],
  research: [
    { name: "research_interests", label: "Research interests", type: "textarea", placeholder: "AI, machine learning, NLP..." },
    { name: "research_areas", label: "Research areas", type: "textarea", placeholder: "Your primary research domains" },
    { name: "skills", label: "Skills", type: "textarea", placeholder: "Python, Java, TensorFlow..." },
    { name: "research_experience", label: "Research experience", type: "textarea", placeholder: "Previous research experience", wide: true },
    { name: "publications", label: "Publications", type: "textarea", placeholder: "Add publication titles or links", wide: true },
    { name: "projects", label: "Projects", type: "textarea", placeholder: "Academic and personal projects", wide: true },
    { name: "research_goals", label: "Research goals", type: "textarea", placeholder: "What would you like to explore?", wide: true },
  ],
  links: [
    { name: "github_url", label: "GitHub profile", type: "url", placeholder: "https://github.com/username" },
    { name: "linkedin_url", label: "LinkedIn profile", type: "url", placeholder: "https://linkedin.com/in/username" },
    { name: "google_scholar_url", label: "Google Scholar", type: "url", placeholder: "Google Scholar profile URL" },
    { name: "orcid_id", label: "ORCID iD", placeholder: "0000-0000-0000-0000" },
    { name: "personal_website", label: "Personal website", type: "url", placeholder: "https://example.com" },
    { name: "researchgate_url", label: "ResearchGate", type: "url", placeholder: "ResearchGate profile URL" },
  ],
};

const NOTIFICATION_FIELDS = [
  ["email_notifications", "Email notifications"],
  ["research_recommendations", "New research recommendations"],
  ["collaboration_requests", "Research collaboration requests"],
  ["project_updates", "Project updates"],
  ["messages_replies", "Messages and replies"],
  ["platform_announcements", "Platform announcements"],
  ["weekly_digest", "Weekly research digest"],
];

const PRIVACY_FIELDS = [
  ["show_email", "Show email address"],
  ["show_education", "Show education"],
  ["show_research_interests", "Show research interests"],
  ["show_publications", "Show publications"],
  ["allow_collaboration_requests", "Allow collaboration requests"],
  ["search_engine_visibility", "Search engine visibility"],
];

function getPortfolioItems(value, separator = /[\n;]+/) {
  return String(value || "").split(separator).map((item) => item.trim()).filter(Boolean);
}

function getExternalUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(value.startsWith("http") ? value : `https://${value}`);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

async function readResponse(response, fallback) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || fallback);
  return data;
}

function ProfileImage({ url, previewUrl, name, className = "" }) {
  return (
    <ProfilePhoto
      className={className}
      imageVersion={url}
      previewUrl={previewUrl}
      name={name}
    />
  );
}

const CALENDAR_MONTHS = Array.from({ length: 12 }, (_, month) => (
  new Intl.DateTimeFormat("en", { month: "short" }).format(new Date(2020, month, 1))
));
const CALENDAR_WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function parseDateValue(value) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
    ? parsed
    : null;
}

function dateToIso(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function DateOfBirthPicker({ value, onChange, id, label, required = false }) {
  const selectedDate = parseDateValue(value);
  const today = new Date();
  const currentYear = today.getFullYear();
  const [isOpen, setIsOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const initialDate = selectedDate || today;
    return new Date(initialDate.getFullYear(), initialDate.getMonth(), 1);
  });
  const pickerRef = useRef(null);
  const monthYear = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
  const firstWeekday = monthYear.getDay();
  const daysInMonth = new Date(
    visibleMonth.getFullYear(),
    visibleMonth.getMonth() + 1,
    0,
  ).getDate();
  const calendarStart = new Date(
    visibleMonth.getFullYear(),
    visibleMonth.getMonth(),
    1 - firstWeekday,
  );
  const calendarDays = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(
      calendarStart.getFullYear(),
      calendarStart.getMonth(),
      calendarStart.getDate() + index,
    );
    return { date, iso: dateToIso(date) };
  });

  useEffect(() => {
    if (!isOpen) return undefined;
    function handleOutsideClick(event) {
      if (!pickerRef.current?.contains(event.target)) setIsOpen(false);
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  function chooseDate(date) {
    onChange(dateToIso(date));
    setVisibleMonth(new Date(date.getFullYear(), date.getMonth(), 1));
    setIsOpen(false);
  }

  function shiftMonth(amount) {
    setVisibleMonth((month) => new Date(month.getFullYear(), month.getMonth() + amount, 1));
  }

  function openCalendar() {
    const date = selectedDate || today;
    setVisibleMonth(new Date(date.getFullYear(), date.getMonth(), 1));
    setIsOpen((open) => !open);
  }

  const formattedDate = selectedDate
    ? `${String(selectedDate.getDate()).padStart(2, "0")}-${String(selectedDate.getMonth() + 1).padStart(2, "0")}-${selectedDate.getFullYear()}`
    : "";
  const isCurrentMonth = visibleMonth.getFullYear() === currentYear
    && visibleMonth.getMonth() === today.getMonth();

  return (
    <div className="settings-date-picker" ref={pickerRef}>
      <button
        id={id}
        className="settings-date-trigger"
        type="button"
        aria-label={selectedDate ? `${label}: ${formattedDate}` : `Choose ${label.toLowerCase()}`}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-required={required || undefined}
        onClick={openCalendar}
      >
        <span className={formattedDate ? "" : "settings-date-placeholder"}>
          {formattedDate || "dd-mm-yyyy"}
        </span>
        <CalendarDays size={17} aria-hidden="true" />
      </button>
      {isOpen && (
        <div className="settings-calendar" role="dialog" aria-label={`${label} calendar`}>
          <div className="settings-calendar-header">
            <div className="settings-calendar-selects">
              <ProfileSelect
                id="calendar-month"
                label="Select month"
                options={CALENDAR_MONTHS.map((month, index) => ({
                  value: index,
                  label: month,
                  disabled: visibleMonth.getFullYear() === currentYear && index > today.getMonth(),
                }))}
                value={visibleMonth.getMonth()}
                onChange={(month) => setVisibleMonth(
                  new Date(visibleMonth.getFullYear(), Number(month), 1),
                )}
              />
              <ProfileSelect
                id="calendar-year"
                label="Select year"
                options={Array.from(
                  { length: currentYear - 1899 },
                  (_, index) => currentYear - index,
                ).map((year) => ({ value: year, label: String(year) }))}
                value={visibleMonth.getFullYear()}
                onChange={(year) => setVisibleMonth(
                  new Date(Number(year), visibleMonth.getMonth(), 1),
                )}
                className="settings-select-year"
                menuClassName="settings-calendar-year-options"
              />
            </div>
            <div className="settings-calendar-nav">
              <button
                type="button"
                aria-label="Previous month"
                disabled={visibleMonth.getFullYear() === 1900 && visibleMonth.getMonth() === 0}
                onClick={() => shiftMonth(-1)}
              >
                <ChevronLeft size={17} />
              </button>
              <button
                type="button"
                aria-label="Next month"
                disabled={isCurrentMonth || visibleMonth > today}
                onClick={() => shiftMonth(1)}
              >
                <ChevronRight size={17} />
              </button>
            </div>
          </div>
          <div className="settings-calendar-grid" role="group" aria-label={`${monthYear.toLocaleDateString(undefined, { month: "long", year: "numeric" })} calendar days`}>
            {CALENDAR_WEEKDAYS.map((day) => (
              <span className="settings-calendar-weekday" aria-hidden="true" key={day}>{day}</span>
            ))}
            {calendarDays.map(({ date, iso }, index) => {
              const isSelected = iso === value;
              const isToday = iso === dateToIso(today);
              const isOutsideMonth = date.getMonth() !== visibleMonth.getMonth();
              const isFuture = date > new Date(currentYear, today.getMonth(), today.getDate());
              const isOutsideVisibleMonth = date.getMonth() !== visibleMonth.getMonth()
                || date.getFullYear() !== visibleMonth.getFullYear();
              return (
                <button
                  type="button"
                  className={[
                    "settings-calendar-day",
                    isSelected ? "selected" : "",
                    isToday ? "today" : "",
                    isOutsideMonth ? "outside-month" : "",
                  ].filter(Boolean).join(" ")}
                  aria-label={date.toLocaleDateString(undefined, {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                  aria-pressed={isSelected}
                  disabled={isFuture || date.getFullYear() < 1900 || isOutsideVisibleMonth}
                  key={`${iso}-${index}`}
                  onClick={() => chooseDate(date)}
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>
          <div className="settings-calendar-footer">
            <button type="button" onClick={() => { onChange(""); setIsOpen(false); }}>
              Clear
            </button>
            <button type="button" disabled={isCurrentMonth} onClick={() => chooseDate(today)}>
              Today
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function TextField({ field, value, onChange }) {
  const fieldValue = field.name === "phone_number" && value
    ? String(value).replace(/\D/g, "").slice(-10)
    : value || "";
  const commonProps = {
    id: field.name,
    name: field.name,
    value: fieldValue,
    onChange,
    readOnly: field.readOnly,
    placeholder: field.placeholder || "",
    "aria-describedby": field.hint ? `${field.name}-hint` : undefined,
  };

  if (field.type === "date") {
    return (
      <div className={`settings-field${field.wide ? " settings-field-wide" : ""}`}>
        <span id={`${field.name}-label`}>
          {field.label}{field.required && <span className="settings-required-mark" aria-hidden="true"> *</span>}
        </span>
        <DateOfBirthPicker
          id={field.name}
          label={field.label}
          value={value || ""}
          required={field.required}
          onChange={(nextValue) => onChange({ target: { name: field.name, value: nextValue } })}
        />
      </div>
    );
  }

  if (field.type === "select") {
    return (
      <div className={`settings-field${field.wide ? " settings-field-wide" : ""}`}>
        <span id={`${field.name}-label`}>
          {field.label}{field.required && <span className="settings-required-mark" aria-hidden="true"> *</span>}
        </span>
        <ProfileSelect
          id={field.name}
          label={field.label}
          options={field.options}
          value={value || ""}
          required={field.required}
          onChange={(nextValue) => onChange({ target: { name: field.name, value: nextValue } })}
        />
        {field.hint && <small id={`${field.name}-hint`}>{field.hint}</small>}
      </div>
    );
  }

  return (
    <label className={`settings-field${field.wide ? " settings-field-wide" : ""}`} htmlFor={field.name}>
      <span>
        {field.label}{field.required && <span className="settings-required-mark" aria-hidden="true"> *</span>}
      </span>
      {field.type === "textarea" ? (
        <textarea
          {...commonProps}
          rows={4}
          required={field.required}
          maxLength={field.name === "short_bio" ? 500 : 3000}
        />
      ) : (
        <input
          {...commonProps}
          type={field.type || "text"}
          min={field.min}
          max={field.max}
          inputMode={field.name === "phone_number" ? "numeric" : undefined}
          pattern={field.name === "phone_number" ? "\\d{10}" : undefined}
          required={field.required}
          maxLength={field.name === "phone_number" ? 10 : field.type === "number" ? undefined : 500}
          title={field.name === "phone_number" ? "Enter exactly 10 digits." : undefined}
        />
      )}
      {field.hint && <small id={`${field.name}-hint`}>{field.hint}</small>}
    </label>
  );
}

function ProfileSelect({
  id,
  label,
  options,
  value,
  onChange,
  className = "",
  menuClassName = "",
  required = false,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selectRef = useRef(null);
  const optionRefs = useRef([]);
  const normalizedOptions = options.map((option) => (
    typeof option === "object"
      ? option
      : { value: option, label: option || "Select an option" }
  ));
  const selectedIndex = Math.max(
    normalizedOptions.findIndex((option) => option.value === value),
    0,
  );
  const selectedLabel = normalizedOptions[selectedIndex]?.label || "Select an option";

  useEffect(() => {
    if (!isOpen) return undefined;
    optionRefs.current[selectedIndex]?.scrollIntoView({ block: "nearest" });
    function handleOutsideClick(event) {
      if (!selectRef.current?.contains(event.target)) setIsOpen(false);
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setIsOpen(false);
        selectRef.current?.querySelector(".settings-select-trigger")?.focus();
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  function handleOptionKeyDown(event) {
    const optionIndex = Number(event.currentTarget.dataset.optionIndex);
    let nextIndex = null;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const direction = event.key === "ArrowDown" ? 1 : -1;
      for (let index = optionIndex + direction; index >= 0 && index < normalizedOptions.length; index += direction) {
        if (!normalizedOptions[index].disabled) {
          nextIndex = index;
          break;
        }
      }
    }
    if (event.key === "Home") {
      nextIndex = normalizedOptions.findIndex((option) => !option.disabled);
    }
    if (event.key === "End") {
      nextIndex = normalizedOptions.findLastIndex((option) => !option.disabled);
    }
    if (nextIndex !== null) {
      event.preventDefault();
      optionRefs.current[nextIndex]?.focus();
    }
  }

  return (
    <div className={`settings-select ${className}`.trim()} ref={selectRef}>
      <button
        id={id}
        className="settings-select-trigger"
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-required={required || undefined}
        aria-controls={`${id}-options`}
        onClick={() => setIsOpen((open) => !open)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !isOpen) {
            event.preventDefault();
            setIsOpen(true);
            requestAnimationFrame(() => optionRefs.current[selectedIndex]?.focus());
          }
        }}
      >
        <span className={!value ? "settings-select-placeholder" : ""}>{selectedLabel}</span>
        <ChevronDown size={17} aria-hidden="true" />
      </button>
      {isOpen && (
        <div
          className={`settings-select-options ${menuClassName}`.trim()}
          id={`${id}-options`}
          role="listbox"
          aria-label={label}
        >
          {normalizedOptions.map((option, index) => (
            <button
              className={`settings-select-option${value === option.value ? " selected" : ""}`}
              type="button"
              role="option"
              aria-selected={value === option.value}
              aria-disabled={option.disabled || undefined}
              data-option-index={index}
              key={option.value}
              ref={(element) => { optionRefs.current[index] = element; }}
              tabIndex={index === selectedIndex && !option.disabled ? 0 : -1}
              disabled={option.disabled}
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
                selectRef.current?.querySelector(".settings-select-trigger")?.focus();
              }}
              onKeyDown={handleOptionKeyDown}
            >
              <span>{option.label}</span>
              {value === option.value && <span className="settings-select-check" aria-hidden="true">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ProfilePage({ user, activePage, onNavigate, onUserUpdated }) {
  const [settings, setSettings] = useState(null);
  const [selectedSection, setSelectedSectionState] = useState(() => {
    const savedSection = window.sessionStorage.getItem(SETTINGS_SECTION_STORAGE_KEY);
    return SETTINGS_SECTION_IDS.has(savedSection) ? savedSection : null;
  });
  const [loading, setLoading] = useState(true);
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [smsPhone, setSmsPhone] = useState(user.phone_number || "");
  const [smsCode, setSmsCode] = useState("");
  const [smsChallengeId, setSmsChallengeId] = useState("");

  const hasPassword = user.providers?.includes("email") ?? false;
  const providers = (user.providers || []).map((provider) => (
    provider === "email" ? "Email and password"
      : provider === "sms" ? "SMS phone"
        : provider[0].toUpperCase() + provider.slice(1)
  ));
  const createdDate = user.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
    })
    : "Available";
  const isAccountSettings = activePage === "account-settings";
  const isSettingsOverview = activePage === "settings" && selectedSection === null;
  const sectionId = isAccountSettings ? "account" : selectedSection;
  const section = SECTIONS.find((item) => item.id === sectionId);
  const profile = settings?.profile || PROFILE_DEFAULTS;
  const displayName = profile.full_name || user.full_name || "Your name";
  const researchInterests = getPortfolioItems(profile.research_interests, /[\n,;]+/);
  const researchAreas = getPortfolioItems(profile.research_areas, /[\n,;]+/);
  const skills = getPortfolioItems(profile.skills, /[\n,;]+/);
  const publications = getPortfolioItems(profile.publications);
  const projects = getPortfolioItems(profile.projects);
  const location = [profile.city, profile.state, profile.country].filter(Boolean).join(", ");
  const orcid = String(profile.orcid_id || "").replace(/^https?:\/\/orcid\.org\//i, "");
  const professionalLinks = [
    ["Personal website", profile.personal_website],
    ["Google Scholar", profile.google_scholar_url],
    ["ORCID", orcid ? `https://orcid.org/${orcid}` : ""],
    ["LinkedIn", profile.linkedin_url],
    ["GitHub", profile.github_url],
    ["ResearchGate", profile.researchgate_url],
  ].map(([label, value]) => ({ label, url: getExternalUrl(value) })).filter(({ url }) => url);

  function setSelectedSection(section) {
    if (SETTINGS_SECTION_IDS.has(section)) {
      window.sessionStorage.setItem(SETTINGS_SECTION_STORAGE_KEY, section);
    } else {
      window.sessionStorage.removeItem(SETTINGS_SECTION_STORAGE_KEY);
    }
    setSelectedSectionState(SETTINGS_SECTION_IDS.has(section) ? section : null);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    apiFetch(API.authConfig)
      .then((response) => readResponse(response, "Could not load sign-in options."))
      .then((config) => {
        if (active) setSmsEnabled(config.sms_enabled === true);
      })
      .catch(() => {
        if (active) setSmsEnabled(false);
      });
    apiFetch(API.profile)
      .then((response) => readResponse(response, "Could not load profile settings."))
      .then((data) => {
        if (active) setSettings(data);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message || "Could not load profile settings.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function updateProfileField(event) {
    const { name } = event.target;
    const value = name === "phone_number"
      ? event.target.value.replace(/\D/g, "").slice(0, 10)
      : event.target.value;
    setSettings((current) => ({
      ...current,
      profile: { ...PROFILE_DEFAULTS, ...current?.profile, [name]: value },
    }));
  }

  async function saveProfile(event) {
    event.preventDefault();
    setError("");
    setNotice("");

    const normalizedPhone = String(profile.phone_number || "").replace(/\D/g, "").slice(-10);
    if (sectionId === "personal") {
      if (!/^\d{10}$/.test(normalizedPhone)) {
        setError("Enter a phone number containing exactly 10 digits.");
        return;
      }
      const missingFields = PROFILE_FIELDS.personal
        .filter(({ name }) => name !== "phone_number")
        .filter(({ name }) => !String(profile[name] || "").trim())
        .map(({ label }) => label);
      if (!profile.profile_image_url && !profile.profile_image_preview_url && !user.profile_image_url && !user.profile_image_preview_url) {
        missingFields.push("Profile picture");
      }
      if (missingFields.length) {
        setError(`Complete all required fields before saving: ${missingFields.join(", ")}.`);
        return;
      }
    }

    setBusy(true);
    try {
      const { username, ...profileFields } = profile;
      if (sectionId === "personal") profileFields.phone_number = normalizedPhone;
      const data = await readResponse(
        await apiFetch(API.profile, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...profileFields, username }),
        }),
        "Could not save your profile.",
      );
      setSettings(data);
      if (data.user) onUserUpdated(data.user);
      setNotice("Your profile information has been saved.");
    } catch (requestError) {
      setError(requestError.message || "Could not save your profile.");
    } finally {
      setBusy(false);
    }
  }

  async function changeProfileImage(event) {
    const image = event.target.files?.[0];
    event.target.value = "";
    if (!image) return;
    if (image.size > 2 * 1024 * 1024) {
      setError("Profile images must be 2 MB or smaller.");
      return;
    }
    setError("");
    setNotice("");
    const previewUrl = URL.createObjectURL(image);
    const previousPreviewUrl = user.profile_image_preview_url;
    onUserUpdated({ ...user, profile_image_preview_url: previewUrl });
    setSettings((current) => ({
      ...current,
      profile: { ...PROFILE_DEFAULTS, ...current?.profile },
      user: { ...user, profile_image_preview_url: previewUrl },
    }));
    const formData = new FormData();
    formData.append("image", image);
    setBusy(true);
    try {
      await readResponse(
        await apiFetch(API.profileImage, { method: "POST", body: formData }),
        "Could not upload your profile image.",
      );
      const data = await readResponse(
        await apiFetch(API.profile),
        "Could not refresh your profile.",
      );
      setSettings({
        ...data,
        profile: { ...data.profile, profile_image_preview_url: previewUrl },
        user: { ...data.user, profile_image_preview_url: previewUrl },
      });
      if (data.user) onUserUpdated({ ...data.user, profile_image_preview_url: previewUrl });
      if (previousPreviewUrl) URL.revokeObjectURL(previousPreviewUrl);
      setNotice("Your profile picture has been updated.");
    } catch (requestError) {
      URL.revokeObjectURL(previewUrl);
      onUserUpdated(user);
      setSettings((current) => ({
        ...current,
        profile: {
          ...PROFILE_DEFAULTS,
          ...current?.profile,
          profile_image_url: user.profile_image_url,
          profile_image_preview_url: user.profile_image_preview_url,
        },
      }));
      setError(requestError.message || "Could not upload your profile image.");
    } finally {
      setBusy(false);
    }
  }

  async function removeProfileImage() {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await readResponse(
        await apiFetch(API.profileImage, { method: "DELETE" }),
        "Could not remove your profile picture.",
      );
      const data = await readResponse(await apiFetch(API.profile), "Could not refresh your profile.");
      setSettings(data);
      if (data.user) onUserUpdated(data.user);
      setNotice("Your profile picture has been removed.");
    } catch (requestError) {
      setError(requestError.message || "Could not remove your profile picture.");
    } finally {
      setBusy(false);
    }
  }

  async function savePreferences(endpoint, values, successMessage) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const data = await readResponse(
        await apiFetch(endpoint, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(values),
        }),
        "Could not save your settings.",
      );
      setSettings(data);
      setNotice(successMessage);
    } catch (requestError) {
      setError(requestError.message || "Could not save your settings.");
    } finally {
      setBusy(false);
    }
  }

  async function updatePassword(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const data = await readResponse(
        await apiFetch(API.changePassword, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...(hasPassword ? { current_password: currentPassword } : {}),
            new_password: newPassword,
          }),
        }),
        "Could not update your password.",
      );
      if (data.user) onUserUpdated(data.user);
      setCurrentPassword("");
      setNewPassword("");
      setNotice(data.message || "Your password has been updated.");
    } catch (requestError) {
      setError(requestError.message || "Could not update your password.");
    } finally {
      setBusy(false);
    }
  }

  async function sendPhoneLinkCode(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const data = await readResponse(
        await apiFetch(API.sendPhoneLinkCode, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone_number: smsPhone }),
        }),
        "Could not send a verification code.",
      );
      if (data.verified) {
        setSmsChallengeId("");
        setNotice("This phone number is already verified for SMS sign-in.");
        return;
      }
      setSmsChallengeId(data.challenge_id);
      setSmsCode("");
      setNotice(data.message);
    } catch (requestError) {
      setError(requestError.message || "Could not send a verification code.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyPhoneLinkCode(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const data = await readResponse(
        await apiFetch(API.verifyPhoneLinkCode, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ challenge_id: smsChallengeId, code: smsCode }),
        }),
        "Could not verify this phone number.",
      );
      setSmsPhone(data.phone_number);
      setSmsChallengeId("");
      setSmsCode("");
      if (data.user) onUserUpdated(data.user);
      setNotice(data.message);
    } catch (requestError) {
      setError(requestError.message || "Could not verify this phone number.");
    } finally {
      setBusy(false);
    }
  }

  const heading = activePage === "profile"
    ? "Your profile"
    : isAccountSettings
      ? "Account settings"
      : "Profile settings";

  return (
    <section className="page profile-page">
      <div className="profile-heading">
        <p className="eyebrow">{activePage === "profile" ? "YOUR ACCOUNT" : "SETTINGS"}</p>
        <h1>{heading}</h1>
        <p className="muted">
          {activePage === "profile"
            ? "Your academic identity and ResearchMate account."
            : isAccountSettings
              ? "Manage your sign-in methods and account security."
              : "Manage your profile, preferences, and privacy."}
        </p>
      </div>

      <div className="profile-tabs" role="tablist" aria-label="Account sections">
        <button
          type="button"
          role="tab"
          aria-selected={activePage === "profile"}
          className={activePage === "profile" ? "active" : ""}
          onClick={() => onNavigate("profile")}
        >
          Profile
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activePage === "settings" || isAccountSettings}
          className={activePage === "settings" || isAccountSettings ? "active" : ""}
          onClick={() => { setSelectedSection(null); onNavigate("settings"); }}
        >
          Profile settings
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isAccountSettings}
          className={isAccountSettings ? "active" : ""}
          onClick={() => onNavigate("account-settings")}
        >
          Account settings
        </button>
      </div>

      {error && (
        <TimedFeedback
          as="p"
          className="auth-message error-message profile-feedback"
          role="alert"
          message={error}
        >
          {error}
        </TimedFeedback>
      )}
      {notice && (
        <TimedFeedback
          as="p"
          className="auth-message auth-notice profile-feedback"
          role="status"
          message={notice}
        >
          {notice}
        </TimedFeedback>
      )}
      {loading ? (
        <div className="profile-card" role="status">Loading your settings...</div>
      ) : activePage === "profile" ? (
        <article className="research-portfolio">
          <section className="portfolio-hero">
            <div className="portfolio-hero-art" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div className="portfolio-hero-content">
              <ProfileImage
                url={profile.profile_image_url || user.profile_image_url}
                previewUrl={profile.profile_image_preview_url || user.profile_image_preview_url}
                name={displayName}
                className="portfolio-avatar"
              />
              <div className="portfolio-intro">
                <p className="portfolio-kicker"><Microscope size={14} /> RESEARCHER PORTFOLIO</p>
                <h2>{displayName}</h2>
                <p className="portfolio-role">
                  {[profile.academic_role, profile.specialization || profile.department]
                    .filter(Boolean).join(" · ") || "Build your academic identity"}
                </p>
                <div className="portfolio-meta">
                  {profile.institution && (
                    <span><GraduationCap size={15} /> {profile.institution}</span>
                  )}
                  {location && <span><MapPin size={15} /> {location}</span>}
                  {profile.username && <span className="portfolio-handle">@{profile.username}</span>}
                </div>
              </div>
              <button
                className="secondary-button portfolio-edit"
                type="button"
                onClick={() => { setSelectedSection("personal"); onNavigate("settings"); }}
              >
                Edit portfolio
              </button>
            </div>
          </section>

          <div className="portfolio-layout">
            <div className="portfolio-main-column">
              <section className="portfolio-section portfolio-about">
                <div className="portfolio-section-heading">
                  <span className="portfolio-section-icon"><UserRound size={18} /></span>
                  <div><p className="eyebrow">ABOUT</p><h3>Researcher at a glance</h3></div>
                </div>
                <p className={profile.short_bio ? "portfolio-bio" : "portfolio-empty-copy"}>
                  {profile.short_bio || "Add a short bio to introduce your background, the questions you explore, and what motivates your work."}
                </p>
                {(researchInterests.length > 0 || researchAreas.length > 0) ? (
                  <div className="portfolio-focus-groups">
                    {researchInterests.length > 0 && (
                      <div>
                        <h4>Research interests</h4>
                        <div className="portfolio-chips">
                          {researchInterests.map((interest) => <span key={interest}>{interest}</span>)}
                        </div>
                      </div>
                    )}
                    {researchAreas.length > 0 && (
                      <div>
                        <h4>Research areas</h4>
                        <div className="portfolio-chips portfolio-chips-muted">
                          {researchAreas.map((area) => <span key={area}>{area}</span>)}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    className="portfolio-inline-action"
                    type="button"
                    onClick={() => { setSelectedSection("research"); onNavigate("settings"); }}
                  >
                    Add your research focus <ChevronRight size={14} />
                  </button>
                )}
              </section>

              {profile.research_experience && (
                <section className="portfolio-section">
                  <div className="portfolio-section-heading">
                    <span className="portfolio-section-icon"><BriefcaseBusiness size={18} /></span>
                    <div><p className="eyebrow">JOURNEY</p><h3>Research experience</h3></div>
                  </div>
                  <p className="portfolio-prose">{profile.research_experience}</p>
                </section>
              )}

              <section className="portfolio-section">
                <div className="portfolio-section-heading">
                  <span className="portfolio-section-icon"><FileText size={18} /></span>
                  <div><p className="eyebrow">SELECTED WORK</p><h3>Publications & projects</h3></div>
                </div>
                {publications.length || projects.length ? (
                  <div className="portfolio-work-grid">
                    {[...publications.map((title) => ({ title, kind: "Publication" })),
                      ...projects.map((title) => ({ title, kind: "Project" }))].map((item, index) => (
                      <div className="portfolio-work-item" key={`${item.kind}-${item.title}-${index}`}>
                        <span>{item.kind}</span>
                        <strong>{item.title}</strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="portfolio-empty-state">
                    <p>Your publications and projects will have a home here.</p>
                    <button
                      className="portfolio-inline-action"
                      type="button"
                      onClick={() => { setSelectedSection("research"); onNavigate("settings"); }}
                    >
                      Add selected work <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </section>
            </div>

            <aside className="portfolio-side-column">
              <section className="portfolio-section portfolio-education">
                <div className="portfolio-section-heading">
                  <span className="portfolio-section-icon"><GraduationCap size={18} /></span>
                  <div><p className="eyebrow">BACKGROUND</p><h3>Education</h3></div>
                </div>
                {profile.institution || profile.degree || profile.education_level ? (
                  <div className="portfolio-education-entry">
                    <strong>{profile.degree || profile.education_level}</strong>
                    {profile.specialization && <span>{profile.specialization}</span>}
                    {profile.department && <span>{profile.department}</span>}
                    {profile.institution && <span>{profile.institution}</span>}
                    {profile.graduation_year && <small>{profile.graduation_year}</small>}
                  </div>
                ) : (
                  <p className="portfolio-empty-copy">Add your education to share your academic background.</p>
                )}
              </section>

              {skills.length > 0 && (
                <section className="portfolio-section">
                  <div className="portfolio-section-heading">
                    <span className="portfolio-section-icon"><BadgeCheck size={18} /></span>
                    <div><p className="eyebrow">TOOLKIT</p><h3>Skills & methods</h3></div>
                  </div>
                  <div className="portfolio-chips">
                    {skills.map((skill) => <span key={skill}>{skill}</span>)}
                  </div>
                </section>
              )}

              <section className="portfolio-section portfolio-connect">
                <div className="portfolio-section-heading">
                  <span className="portfolio-section-icon"><Link size={18} /></span>
                  <div><p className="eyebrow">ELSEWHERE</p><h3>Connect</h3></div>
                </div>
                {professionalLinks.length > 0 ? (
                  <div className="portfolio-links">
                    {professionalLinks.map(({ label, url }) => (
                      <a href={url} key={label} target="_blank" rel="noreferrer">
                        {label}<ExternalLink size={14} />
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="portfolio-empty-copy">Add professional links so collaborators can find your work.</p>
                )}
              </section>
              <p className="portfolio-member-note">ResearchMate member since {createdDate}</p>
            </aside>
          </div>
        </article>
      ) : isSettingsOverview ? (
        <article className="profile-card profile-settings-overview">
          <div className="settings-profile-summary">
            <ProfileImage
              url={user.profile_image_url}
              previewUrl={user.profile_image_preview_url}
              name={user.full_name || user.email}
              className="settings-profile-avatar"
            />
            <div>
              <h2>{user.full_name || "Your Profile"}</h2>
              <p>{user.username ? `@${user.username}` : "Manage your academic identity"}</p>
              <span className="settings-status">Profile active</span>
            </div>
          </div>
          <nav className="settings-section-list" aria-label="Profile settings sections">
            {SECTIONS.map(({ id, title, description, icon: Icon }) => (
              <button
                className="settings-section-link"
                key={id}
                type="button"
                onClick={() => {
                  if (id === "account") onNavigate("account-settings");
                  else setSelectedSection(id);
                }}
              >
                <Icon size={20} aria-hidden="true" />
                <span><strong>{title}</strong><small>{description}</small></span>
                <span className="settings-section-chevron" aria-hidden="true">›</span>
              </button>
            ))}
          </nav>
        </article>
      ) : section ? (
        <article className="profile-card profile-settings-card">
          <button
            type="button"
            className="settings-back"
            onClick={() => {
              if (isAccountSettings) onNavigate("settings");
              setSelectedSection(null);
            }}
          >
            <ArrowLeft size={16} /> All settings
          </button>
          <div className="profile-settings-title">
            <span className="profile-detail-icon"><section.icon size={18} /></span>
            <div>
              <h2>{section.title}</h2>
              <p>{section.description}</p>
            </div>
          </div>

          {(sectionId === "personal" || sectionId === "academic" || sectionId === "research" || sectionId === "links") && (
            <form className="settings-form" onSubmit={saveProfile}>
              {sectionId === "personal" && (
                <>
                  <p className="settings-required-note">
                    All fields marked <span aria-hidden="true">*</span> are required.
                  </p>
                  <div className="settings-photo-field">
                    <ProfileImage
                      url={profile.profile_image_url}
                      previewUrl={profile.profile_image_preview_url || user.profile_image_preview_url}
                      name={profile.full_name}
                      className="settings-photo-preview"
                    />
                    <div>
                      <strong>
                        Profile picture<span className="settings-required-mark" aria-hidden="true"> *</span>
                      </strong>
                      <p>PNG, JPEG, or WebP up to 2 MB.</p>
                      <label className="secondary-button settings-upload-button">
                        <Camera size={16} /> Upload image
                        <input type="file" accept="image/png,image/jpeg,image/webp" onChange={changeProfileImage} disabled={busy} />
                      </label>
                      {profile.profile_image_url && (
                        <button className="settings-remove-image" type="button" onClick={removeProfileImage} disabled={busy}>
                          <Trash2 size={15} /> Remove picture
                        </button>
                      )}
                    </div>
                  </div>
                </>
              )}
              <div className="settings-fields-grid">
                {PROFILE_FIELDS[sectionId].map((field) => (
                  <TextField key={field.name} field={field} value={profile[field.name]} onChange={updateProfileField} />
                ))}
              </div>
              <button className="primary-button profile-save" type="submit" disabled={busy}>
                {busy ? "Saving..." : "Save changes"}
              </button>
            </form>
          )}

          {sectionId === "account" && (
            <div className="settings-account-content">
              <div className="settings-account-facts">
                <p><strong>Email address</strong><span>{user.email}</span></p>
                <p><strong>Connected sign-in methods</strong><span>{providers.length ? providers.join(", ") : "None"}</span></p>
                <p><strong>Verified phone for SMS sign-in</strong><span>{user.phone_verified ? user.phone_number : "Not set up"}</span></p>
              </div>
              <p className="profile-provider-note">
                Email changes, two-factor authentication, session management, and account deletion are not available yet.
              </p>
              <div className="profile-settings-title settings-password-title">
                <span className="profile-detail-icon"><KeyRound size={18} /></span>
                <div>
                  <h2>Password and security</h2>
                  <p>{hasPassword ? "Update your account password." : "Add a password to also sign in with email."}</p>
                </div>
              </div>
              <form className="profile-password-form" onSubmit={updatePassword}>
                {hasPassword && (
                  <label>
                    Current password
                    <input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
                  </label>
                )}
                {!hasPassword && (
                  <p className="profile-provider-note">
                    You signed in with {providers.join(" or ") || "a connected account"}. Choose a password here to also sign in with email.
                  </p>
                )}
                <label>
                  {hasPassword ? "New password" : "Create a password"}
                  <input type="password" autoComplete="new-password" minLength={10} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
                  <small>Use at least 10 characters.</small>
                </label>
                <button className="primary-button profile-save" type="submit" disabled={busy}>
                  {busy ? "Saving..." : hasPassword ? "Update password" : "Create password"}
                </button>
              </form>
              <div className="profile-settings-title settings-password-title">
                <span className="profile-detail-icon"><Phone size={18} /></span>
                <div>
                  <h2>Phone sign-in</h2>
                  <p>Verify a phone number before using it to sign in with SMS.</p>
                </div>
              </div>
              {smsEnabled ? (
                <form className="profile-password-form" onSubmit={smsChallengeId ? verifyPhoneLinkCode : sendPhoneLinkCode}>
                {!smsChallengeId ? (
                  <label>
                    Phone number in international format
                    <input
                      type="tel"
                      autoComplete="tel"
                      placeholder="+14155552671"
                      value={smsPhone}
                      onChange={(event) => setSmsPhone(event.target.value)}
                      required
                    />
                    <small>Include the country calling code, for example +1 for the United States.</small>
                  </label>
                ) : (
                  <label>
                    Verification code
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={smsCode}
                      onChange={(event) => setSmsCode(event.target.value.replace(/\D/g, "").slice(0, 10))}
                      required
                    />
                    <small>Enter the code sent to {smsPhone}.</small>
                  </label>
                )}
                <button className="primary-button profile-save" type="submit" disabled={busy}>
                  {busy ? "Please wait..." : smsChallengeId ? "Verify phone number" : "Send verification code"}
                </button>
                {smsChallengeId && (
                  <button
                    className="settings-phone-change"
                    type="button"
                    disabled={busy}
                    onClick={() => { setSmsChallengeId(""); setSmsCode(""); setError(""); setNotice(""); }}
                  >
                    Change phone number
                  </button>
                )}
                </form>
              ) : (
                <p className="profile-provider-note">
                  SMS sign-in needs Twilio Verify credentials in backend/.env and a backend restart.
                </p>
              )}
            </div>
          )}

          {sectionId === "notifications" && (
            <>
              <p className="settings-explainer">
                Choose which updates you’d like to receive. These preferences are saved to your account; notifications beyond account verification and password recovery are not currently sent.
              </p>
              <div className="settings-toggle-list">
                {NOTIFICATION_FIELDS.map(([key, label]) => (
                  <label className="settings-toggle" key={key}>
                    <span>{label}</span>
                    <input
                      type="checkbox"
                      checked={Boolean(settings?.notifications?.[key] ?? NOTIFICATION_DEFAULTS[key])}
                      disabled={busy}
                      onChange={(event) => savePreferences(
                        API.profileNotifications,
                        { ...NOTIFICATION_DEFAULTS, ...settings?.notifications, [key]: event.target.checked },
                        "Notification preferences saved.",
                      )}
                    />
                  </label>
                ))}
              </div>
            </>
          )}

          {sectionId === "privacy" && (
            <>
              <p className="settings-explainer">
                Your ResearchMate profile is currently visible only to you. Saved visibility preferences will apply if public profile features are enabled.
              </p>
              <label className="settings-field settings-visibility-field">
                <span>Profile visibility</span>
                <select
                  value={settings?.privacy?.profile_visibility || "private"}
                  disabled={busy}
                  onChange={(event) => savePreferences(
                    API.profilePrivacy,
                    { ...PRIVACY_DEFAULTS, ...settings?.privacy, profile_visibility: event.target.value },
                    "Privacy preferences saved.",
                  )}
                >
                  <option value="private">Private</option>
                  <option value="public">Public (when public profiles are available)</option>
                </select>
              </label>
              <div className="settings-toggle-list">
                {PRIVACY_FIELDS.map(([key, label]) => (
                  <label className="settings-toggle" key={key}>
                    <span>{label}</span>
                    <input
                      type="checkbox"
                      checked={Boolean(settings?.privacy?.[key] ?? PRIVACY_DEFAULTS[key])}
                      disabled={busy}
                      onChange={(event) => savePreferences(
                        API.profilePrivacy,
                        { ...PRIVACY_DEFAULTS, ...settings?.privacy, [key]: event.target.checked },
                        "Privacy preferences saved.",
                      )}
                    />
                  </label>
                ))}
              </div>
            </>
          )}
        </article>
      ) : null}
    </section>
  );
}
