const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

export const API_BASE = API_BASE_URL;

export const API = {
  authConfig: `${API_BASE_URL}/auth/config`,
  currentUser: `${API_BASE_URL}/auth/me`,
  profile: `${API_BASE_URL}/auth/profile`,
  profileImage: `${API_BASE_URL}/auth/profile/image`,
  profileNotifications: `${API_BASE_URL}/auth/profile/notifications`,
  profilePrivacy: `${API_BASE_URL}/auth/profile/privacy`,
  register: `${API_BASE_URL}/auth/register`,
  login: `${API_BASE_URL}/auth/login`,
  sendPhoneLoginCode: `${API_BASE_URL}/auth/phone/login/code`,
  verifyPhoneLoginCode: `${API_BASE_URL}/auth/phone/login/verify`,
  sendPhoneLinkCode: `${API_BASE_URL}/auth/phone/link/code`,
  verifyPhoneLinkCode: `${API_BASE_URL}/auth/phone/link/verify`,
  changePassword: `${API_BASE_URL}/auth/password`,
  logout: `${API_BASE_URL}/auth/logout`,
  verifyEmail: `${API_BASE_URL}/auth/verify-email`,
  resendVerification: `${API_BASE_URL}/auth/resend-verification`,
  forgotPassword: `${API_BASE_URL}/auth/forgot-password`,
  resetPassword: `${API_BASE_URL}/auth/reset-password`,
  googleStart: `${API_BASE_URL}/auth/google/start`,
  githubStart: `${API_BASE_URL}/auth/github/start`,
  linkedinStart: `${API_BASE_URL}/auth/linkedin/start`,
  upload: `${API_BASE_URL}/upload`,
  progress: (taskId) => `${API_BASE_URL}/progress/${taskId}`,
  papers: `${API_BASE_URL}/papers`,
  getPaper: (id) => `${API_BASE_URL}/papers/${id}`,
  savePaper: (id) => `${API_BASE_URL}/papers/${id}/save`,
  updatePaper: (id) => `${API_BASE_URL}/papers/${id}`,
  classifyPaper: (id) => `${API_BASE_URL}/papers/${id}/classify`,
  downloadPaper: (id) => `${API_BASE_URL}/papers/${id}/download`,
  downloadSummary: (id) => `${API_BASE_URL}/papers/${id}/download-summary`,
  deletePaper: (id) => `${API_BASE_URL}/papers/${id}`,
};

export function apiFetch(url, options = {}) {
  return fetch(url, { credentials: "include", ...options });
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
