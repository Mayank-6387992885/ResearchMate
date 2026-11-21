# ResearchMate repository guidance

## Commands

Run backend commands from `backend/` and frontend commands from `frontend/`.

### Backend setup and run

```powershell
cd backend
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

The API is available at `http://localhost:8000`; interactive docs are at `http://localhost:8000/docs`.

For local AI summarization and classification, Ollama must be running at `http://localhost:11434` with `llama3.2:3b`:

```powershell
ollama pull llama3.2:3b
ollama run llama3.2:3b
```

Local uses `backend/researchmate.db` unless `DATABASE_URL` is set. PDFs use `backend/uploads/research_papers/` unless both `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set. `SEND_VERIFICATION_EMAIL=false` allows new accounts to sign in without SMTP; the default in code remains enabled.

### Backend tests

Tests use Python `unittest`, not pytest:

```powershell
cd backend
python -m unittest discover -s tests -v
```

Run one test module or test case:

```powershell
python -m unittest tests.test_summarizer.SummarizerTests.test_call_ollama_streams_plain_text -v
python -m unittest tests.test_auth.AuthHelperTests.test_password_hash_verifies_only_matching_password -v
```

`test_auth.py` uses `fastapi.testclient.TestClient`; its `httpx` dependency is included in `backend/requirements.txt`.

There is no backend lint or formatting script configured.

The root `render.yaml` defines Render web/static services and PostgreSQL. Render deployments need a reachable `OLLAMA_URL`; configure Supabase storage for durable uploaded PDFs. `FRONTEND_URL` and `VITE_API_BASE_URL` must match the deployed service URLs.

### Frontend setup, run, and build

```powershell
cd frontend
npm install
npm run dev
npm run build
npm run preview
```

The Vite development server runs at `http://localhost:5173`. Set `VITE_API_BASE_URL` to override the default API URL in `frontend/src/services/api.js`.

There is no frontend test or lint script configured.

## Architecture

- `backend/main.py` owns the FastAPI app, CORS setup, startup database migrations, progress-task state, PDF upload, and paper endpoints. `backend/auth.py` is mounted as the `/auth` router.
- `backend/models/` contains SQLAlchemy models. `backend/database.py` creates the SQLite or PostgreSQL engine and provides request-scoped database sessions.
- Paper operations live in `backend/services/paper_service.py`. PDFs use the local upload directory unless both Supabase storage credentials are configured, in which case they use `research-papers` objects.
- PDF text extraction uses PyMuPDF in the upload route. `backend/summarizer.py` chunks text, streams Ollama responses, heartbeats long-running progress, and caches resumable chunk/final results in the OS temp directory.
- `backend/classification.py` uses Ollama JSON output for paper classification. It validates selections against fixed taxonomy options and reports field-level progress.
- Progress state is persisted in `ProgressTask` rows by task ID and scoped to the owner user. The frontend polls it after upload instead of relying on WebSockets; `websocket_manager.py` is not the upload progress path.
- The React app is defined in `frontend/src/App.jsx`. It performs authentication at startup, chooses landing/auth/workspace views, and keeps active page and task state in browser storage.
- Frontend API route constants and the cookie-aware `apiFetch` helper are in `frontend/src/services/api.js`. Set `VITE_API_BASE_URL` for deployments.

## Repository conventions

- Run Python modules with `backend/` as the working directory because imports such as `from database import ...`, `from auth import ...`, and `import services.paper_service` are intentionally top-level.
- Every paper and progress operation must remain account-scoped. API routes pass `user.id` into paper/progress helpers and use `get_current_user` rather than trusting a client-provided user.
- Authentication uses a hashed `researchmate_session` cookie token and SQLAlchemy `AuthToken` records. Passwords use `scrypt`; raw session or verification tokens must not be stored.
- New paper fields require updates in `models/research_paper.py`, `paper_to_dict`, and startup migration logic in `main.py`. Startup currently uses `Base.metadata.create_all` plus explicit `ALTER TABLE` compatibility additions for existing SQLite/PostgreSQL databases.
- Summaries and classification must fail safely. Paper upload can succeed with a classification error, which is reported as `classification_error` and should remain retryable from the paper UI.
- When changing classification fields or taxonomy values, update `CLASSIFICATION_OPTIONS`, `CLASSIFICATION_PROGRESS_FIELDS`, `validate_classification`, and frontend classification handling together.
- Supabase object keys are `user-{user_id}/{uuid}.pdf`; deletion and download paths must distinguish local file paths from storage object keys.
- Add/remove API endpoint constants in `frontend/src/services/api.js` and use `apiFetch` so browser credentials are included.
- Frontend navigation is implemented by `activePage` state and `sessionStorage`, not a React router. Persisted keys include active page, active summary task, progress samples, settings section, and color mode.
- UI styling is split across `frontend/src/styles.css` and `frontend/src/styles/*.css`; new global imports belong in `main.jsx`.
- Environment secrets belong in `backend/.env` or deployment environment variables. `.env`, including frontend `.env`, is excluded by `.gitignore`; update `backend/.env.example` when adding backend settings.
