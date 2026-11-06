<div align="center">

# ResearchMate

### Make research papers easier to understand.

Turn dense PDFs into clear, section-by-section summaries—and keep every paper organized in one private workspace.

**Upload a paper. Follow the analysis. Get back to what matters.**

[Get started](#get-started) · [Explore features](#made-for-your-research) · [Account setup](#account-sign-in) · [API reference](#api-at-a-glance)

</div>

---

<a id="made-for-your-research"></a>

## ✨ Made for your research

| | |
|:---:|---|
| ⚡ | **Understand papers faster** — Turn research PDFs into readable, section-by-section AI summaries. |
| 👀 | **Stay in the loop** — Follow analysis progress and review completed sections while a paper is processing. |
| 📚 | **Build a research library** — Save papers, search your collection, rename entries, and organize them by category. |
| 🧭 | **Find the right paper** — Sort and group your saved research, then classify papers with AI. |
| 🔒 | **Keep your work private** — Each account has its own paper library and analysis history. |

<details>
<summary><strong>See how analysis and organization work</strong></summary>

- Progress stays below 100% until the completed summary is saved.
- Refresh the page to reconnect to an active analysis. Interrupted work is reported—not shown as complete.
- Completed sections are cached, so a retry can reuse prior work.
- New uploads are classified by research domain, subdomain, methodology, paper type, application area, and AI/ML techniques.
- Add your own **Industry**, **Technology**, **Product**, and **Importance** categories independently of AI classification.
- Change saved-paper titles and classifications, download PDFs and summaries, or remove papers from your library.

</details>

---

<a id="get-started"></a>

## 🚀 Get started

### Before you begin

You’ll need **Python**, **Node.js/npm**, **Ollama**, and an SMTP account to verify new users and send password-reset emails.

### 1 · Configure email

Create your local environment file:

```powershell
Copy-Item backend\.env.example backend\.env
```

Open `backend\.env` and add your SMTP settings:

```dotenv
SMTP_HOST=your-smtp-host
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM="ResearchMate <you@example.com>"
SMTP_USE_SSL=false
```

> **Keep credentials private.** Store real values in `backend\.env` only—never commit or share them. Restart the backend after changing environment settings.

### 2 · Prepare the AI model

ResearchMate connects to Ollama at `http://localhost:11434` and uses `llama3.2:3b`. Install and start Ollama, then download the model:

```powershell
ollama pull llama3.2:3b
```

### 3 · Run the backend

In a PowerShell terminal:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

The API runs at [localhost:8000](http://localhost:8000). Explore the interactive API docs at [localhost:8000/docs](http://localhost:8000/docs).

### 4 · Run the frontend

Open a **second** PowerShell terminal:

```powershell
cd frontend
npm install
npm run dev
```

Visit [localhost:5173](http://localhost:5173), create an account, and verify your email.

> **First account?** When its email is verified, existing papers from the previous shared library are assigned to that account.

---

<a id="account-sign-in"></a>

## 🔐 Account & sign-in

Email and password sign-in is ready once SMTP is configured. To add social sign-in, create an OAuth app with the provider and add its credentials to `backend\.env`.

On the sign-in page, **Remember me** keeps the session active for 14 days and remembers the email on that device. Without it, the session expires after 12 hours and the cookie is cleared when the browser session ends. Passwords are never stored in ResearchMate browser storage; the sign-in form supports your browser’s password manager for securely saving and autofilling them.

Profile settings are organized into personal, academic, research, professional links, account security, notification, and privacy sections. Profile details are private to the signed-in user. Profile images accept PNG, JPEG, or WebP up to 2 MB. Notification and privacy choices are saved, but public profiles and most notification delivery are not currently available.

To enable passwordless SMS sign-in, create a **Twilio Verify** service and set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_VERIFY_SERVICE_SID` in `backend\.env`. Restart the backend. A signed-in user must verify their phone in **Account settings → Phone sign-in** before it can be used to log in. Enter phone numbers in international format (for example, `+14155552671`). Twilio Verify sends and validates the one-time codes; its message and verification charges apply.

| Provider | Required settings | OAuth callback URL |
|---|---|---|
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `http://localhost:8000/auth/google/callback` |
| GitHub | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | `http://localhost:8000/auth/github/callback` |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | `http://localhost:8000/auth/linkedin/callback` |

For LinkedIn, enable **Sign In with LinkedIn using OpenID Connect** in the app settings. A provider appears as available only when both credentials are configured. Restart the backend after adding or changing credentials.

The account menu includes a profile view and settings for updating your password or adding an email password to a social-login account. For local HTTP development, keep `AUTH_COOKIE_SECURE=false`; use `true` when serving the app over HTTPS.

---

<a id="api-at-a-glance"></a>

## 🧭 API at a glance

All paper and analysis endpoints require a signed-in account.

### Papers & analysis

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/upload` | Upload and analyze a PDF |
| `GET` | `/progress/{task_id}` | Check upload or classification progress |
| `GET` | `/papers` | List papers; supports `search`, `saved_only`, and `category` filters |
| `GET` | `/papers/{paper_id}` | Get a paper and its summary |
| `PUT` | `/papers/{paper_id}/save` | Save or unsave a paper |
| `PATCH` | `/papers/{paper_id}` | Update its title or classification |
| `POST` | `/papers/{paper_id}/classify` | Classify a saved paper |
| `GET` | `/papers/{paper_id}/download` | Download its PDF |
| `GET` | `/papers/{paper_id}/download-summary` | Download its summary as text |
| `DELETE` | `/papers/{paper_id}` | Delete a paper |

### Sign-in

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/auth/config` | Check enabled sign-in options |
| `POST` | `/auth/register` | Create an account and send verification |
| `POST` | `/auth/login` | Sign in with email and password |
| `POST` | `/auth/phone/login/code` | Request a phone sign-in code |
| `POST` | `/auth/phone/login/verify` | Verify a phone sign-in code |
| `POST` | `/auth/phone/link/code` | Send a code to verify a phone for the signed-in account |
| `POST` | `/auth/phone/link/verify` | Verify and link the phone number |
| `POST` | `/auth/logout` | Sign out |
| `GET` | `/auth/me` | Get the current account |
| `POST` | `/auth/verify-email` | Verify an email address |
| `POST` | `/auth/resend-verification` | Resend a verification email |
| `POST` | `/auth/forgot-password` | Request a password-reset link |
| `POST` | `/auth/reset-password` | Set a new password |
| `PUT` | `/auth/password` | Update the signed-in account password |

---

## 🗂️ Where your data lives

| Data | Location |
|---|---|
| Database | `backend\researchmate.db` |
| Uploaded PDFs | `backend\uploads\research_papers\` |
| Summaries | Stored with paper records; downloadable as `.txt` |
| Frontend API URL | Defaults to `http://localhost:8000`; set `VITE_API_BASE_URL` when deploying elsewhere |

Existing database tables are kept during startup migrations. The sidebar stays in view while you scroll, and account-owned papers, downloads, uploads, and progress tasks are scoped to the signed-in user.
