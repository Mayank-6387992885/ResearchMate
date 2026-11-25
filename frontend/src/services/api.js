export const RENDER_API_URL = "https://researchmate-api-0e78.onrender.com";
export const LOCAL_API_URL = "http://localhost:8000";
const API_TARGET_STORAGE_KEY = "researchmate.api_target";

export function getApiBaseUrl() {
  try {
    const override = window.localStorage.getItem(API_TARGET_STORAGE_KEY);
    if (override === "local") return LOCAL_API_URL;
    if (override === "render") return RENDER_API_URL;
    if (override && override.startsWith("http")) return override.replace(/\/$/, "");
  } catch {}
  return (
    import.meta.env.VITE_API_BASE_URL || LOCAL_API_URL
  ).replace(/\/$/, "");
}

export function setApiTarget(target) {
  try {
    if (!target) {
      window.localStorage.removeItem(API_TARGET_STORAGE_KEY);
    } else {
      window.localStorage.setItem(API_TARGET_STORAGE_KEY, target);
    }
  } catch (error) {
    console.warn("Could not save API target override.", error);
  }
}

export function isLocalApi() {
  const current = getApiBaseUrl();
  return current.includes("localhost") || current.includes("127.0.0.1");
}

export const API_BASE = getApiBaseUrl();

export const API = {
  get authConfig() { return `${getApiBaseUrl()}/auth/config`; },
  get adminSettings() { return `${getApiBaseUrl()}/auth/admin/settings`; },
  get currentUser() { return `${getApiBaseUrl()}/auth/me`; },
  get profile() { return `${getApiBaseUrl()}/auth/profile`; },
  get profileImage() { return `${getApiBaseUrl()}/auth/profile/image`; },
  get profileNotifications() { return `${getApiBaseUrl()}/auth/profile/notifications`; },
  get profilePrivacy() { return `${getApiBaseUrl()}/auth/profile/privacy`; },
  get register() { return `${getApiBaseUrl()}/auth/register`; },
  get login() { return `${getApiBaseUrl()}/auth/login`; },
  get sendPhoneLoginCode() { return `${getApiBaseUrl()}/auth/phone/login/code`; },
  get verifyPhoneLoginCode() { return `${getApiBaseUrl()}/auth/phone/login/verify`; },
  get sendPhoneLinkCode() { return `${getApiBaseUrl()}/auth/phone/link/code`; },
  get verifyPhoneLinkCode() { return `${getApiBaseUrl()}/auth/phone/link/verify`; },
  get changePassword() { return `${getApiBaseUrl()}/auth/password`; },
  get logout() { return `${getApiBaseUrl()}/auth/logout`; },
  get verifyEmail() { return `${getApiBaseUrl()}/auth/verify-email`; },
  get resendVerification() { return `${getApiBaseUrl()}/auth/resend-verification`; },
  get forgotPassword() { return `${getApiBaseUrl()}/auth/forgot-password`; },
  get resetPassword() { return `${getApiBaseUrl()}/auth/reset-password`; },
  get googleStart() { return `${getApiBaseUrl()}/auth/google/start`; },
  get githubStart() { return `${getApiBaseUrl()}/auth/github/start`; },
  get linkedinStart() { return `${getApiBaseUrl()}/auth/linkedin/start`; },
  get upload() { return `${getApiBaseUrl()}/upload`; },
  get importPaper() { return `${getApiBaseUrl()}/api/papers/import`; },
  progress: (taskId) => `${getApiBaseUrl()}/progress/${taskId}`,
  get papers() { return `${getApiBaseUrl()}/papers`; },
  getPaper: (id) => `${getApiBaseUrl()}/papers/${id}`,
  savePaper: (id) => `${getApiBaseUrl()}/papers/${id}/save`,
  updatePaper: (id) => `${getApiBaseUrl()}/papers/${id}`,
  classifyPaper: (id) => `${getApiBaseUrl()}/papers/${id}/classify`,
  downloadPaper: (id) => `${getApiBaseUrl()}/papers/${id}/download`,
  downloadSummary: (id) => `${getApiBaseUrl()}/papers/${id}/download-summary`,
  deletePaper: (id) => `${getApiBaseUrl()}/papers/${id}`,
};

const TOKEN_STORAGE_KEY = "researchmate.session_token";

export function getStoredToken() {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY)
      || window.sessionStorage.getItem(TOKEN_STORAGE_KEY)
      || null;
  } catch {
    return null;
  }
}

export function setStoredToken(token, remember = true) {
  try {
    if (!token) {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
      return;
    }
    if (remember) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
      window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    } else {
      window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch (error) {
    console.warn("Could not save session token.", error);
  }
}

export function clearStoredToken() {
  setStoredToken(null);
}

export async function apiFetch(url, options = {}) {
  const token = getStoredToken();
  const headers = { ...(options.headers || {}) };
  if (token && !headers["Authorization"] && !headers["authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  try {
    return await fetch(url, {
      credentials: "include",
      ...options,
      headers,
    });
  } catch (err) {
    if (
      err instanceof TypeError &&
      (err.message === "Failed to fetch" || err.message?.includes("NetworkError") || err.message?.includes("Failed to fetch"))
    ) {
      const isLocal = isLocalApi();
      const target = getApiBaseUrl();
      const msg = isLocal
        ? `Cannot connect to local server at ${target}. Make sure backend is running or switch to Cloud.`
        : `Cannot connect to Cloud server at ${target}. Please check your network connection.`;
      const enriched = new Error(msg);
      enriched.isConnectionError = true;
      enriched.target = target;
      throw enriched;
    }
    throw err;
  }
}

export async function fetchPapers({ search = "", savedOnly = false } = {}) {
  const params = new URLSearchParams();
  if (search.trim()) params.set("search", search.trim());
  if (savedOnly) params.set("saved_only", "true");

  const query = params.toString();
  const response = await apiFetch(`${API.papers}${query ? `?${query}` : ""}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not load papers.");
  return data;
}

export async function fetchPaper(id) {
  const response = await apiFetch(API.getPaper(id));
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not load this paper.");
  return data;
}

export async function togglePaperSaved(id) {
  const response = await apiFetch(API.savePaper(id), { method: "PUT" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not update saved status.");
  return data;
}

export async function removePaper(id) {
  const response = await apiFetch(API.deletePaper(id), { method: "DELETE" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not delete this paper.");
  return data;
}
