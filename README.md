# AI Personal Learning & Productivity Hub

A single-user, self-hosted command center that tells you every day what to learn, build and do, and keeps you honest about it.
It is also a hands-on AI-engineering project: the backend is built around a provider-neutral LLM interface with tool calling and
approval gates.

> Detailed design notes, decisions and the per-milestone history live in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Status (read this first)

**Works today (tested):** sign-in, tasks, courses, video collections with YouTube import, an AI-engineering roadmap, habits, projects,
a combined daily planner, a daily AI project challenge, a dashboard, and the AI assistant's foundation.

**Not working yet:**

| Not built | Planned |
|---|---|
| Live AI assistant and chat window. The Anthropic adapter exists but has only been tested against a stub, never against the real API. The `/assistant` page shows this honestly. | Phase 6 |
| GitHub account sign-in (OAuth) and repo sync. Not needed: verification and project import work on public repos with no account link, and `GITHUB_TOKEN` covers private ones. | not scheduled |
| Sending real e-mail has not been tried with a live mail account (tests use a fake mail server). Gmail API (OAuth) is not built; SMTP with an App Password is. | needs your credentials |
| The n8n workflow in `docs/n8n-run-due.json` is untested in n8n | optional |
| Weekly/monthly analytics | Phase 7 |
| OpenAI and Gemini adapters | not scheduled |

## What each part does

| Page | What it does |
|---|---|
| Dashboard | Today at a glance: plan, tasks, videos to watch, habits, projects, challenge, roadmap, last 7 days. Computed from the other pages, nothing stored. |
| Daily planner | One list for the day from tasks, course lessons, videos, roadmap topic, habits and projects. Complete, reschedule or excuse items. |
| Tasks | Priorities, categories, due dates, recurring tasks. |
| Courses | Courses, modules, lessons, study sessions. |
| Videos | Collections with a daily target; paste links or import a YouTube playlist. Finished videos are never suggested again. |
| AI roadmap | Your AI-engineering path as stages and topics. |
| Habits | Daily/weekly habits with streaks. |
| Projects | Projects, milestones, development sessions. **Fill from GitHub** reads a repo (name, description or README intro, languages, topics) and fills the empty form fields; nothing is saved until you click Create. |
| Daily challenge | One real piece of AI project work per day: a summary, repo URL, commit hash and minutes, or an explicit excuse. A day is never completed automatically. Streaks and missed days are computed, never stored. **Verify on GitHub** checks the commit exists, matches your message, was made that day and changes code; only a pass shows *Verified*. Public repos need no setup; set `GITHUB_TOKEN` in `backend/.env` for private repos. |
| Settings | Your account (read-only), **e-mail reminders** (daily plan, evening overdue nudge, weekly report; times, test e-mail, history) and a light/dark switch. Editing your profile or timezone is not built. |
| AI assistant | Foundation only: provider interface, 16 tools (10 read, 6 propose-only), approval queue, memory. No chat yet. |

## Run it (Windows, development)

Requirements: Python 3.11, Node 20.

```powershell
# one-time
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env          # then set SECRET_KEY and ENCRYPTION_KEY (commands are in the file)
.venv\Scripts\python.exe -m alembic upgrade head
cd ..\frontend
npm install

# every time (two terminals)
cd backend;  .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
cd frontend; npm run dev        # http://localhost:5173, proxies /api to :8000
```

Open http://localhost:5173 and create the one account on first visit.

## E-mail reminders (optional)

Off until you configure it. In `backend/.env`:

```
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=<Gmail App Password>   # Google Account > Security > 2-Step Verification > App passwords
EMAIL_FROM=you@gmail.com
```

Restart the backend, open Settings, switch reminders on, press **Send a test e-mail**. The page shows the real result: *Sent* only
after the mail server accepted it, otherwise *Failed* with the reason. The built-in scheduler (`SCHEDULER_MODE=internal`, default)
checks every minute; each e-mail goes out once per day (weekly report: once per week), and an empty plan sends nothing.
To use n8n instead, set `SCHEDULER_MODE=n8n`, set `AUTOMATION_API_KEY`, and import `docs/n8n-run-due.json` (never run both).

## Tests

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest -q
cd frontend; npm run typecheck; npm test; npm run build
```

Run `npm test` from a path with an uppercase drive letter (`D:\...`); from Git Bash's `/d/...` Vitest fails to load.
`backend/tests/test_integration.py` runs a whole day through every feature and checks that every route requires login.

## How it is built

- **Backend:** FastAPI, SQLAlchemy 2, Alembic, SQLite (PostgreSQL later via `DATABASE_URL`). Layers: routers, services, models.
  Request models reject unknown fields. All times are stored in UTC; "today" is computed in your timezone.
- **Frontend:** React 19, TypeScript, Vite, Tailwind, TanStack Query, React Router. Tests use Vitest and a fake API.
- **AI:** `backend/app/ai/` holds the provider interface and the tool registry. The model never touches the database. It can only call
  tools, which call the same services as the web pages. Read tools run immediately. Write tools only create a proposal that you approve
  on the AI assistant page. There is deliberately no tool that completes a challenge or deletes anything.

## Security notes

- Passwords are hashed with bcrypt. Sessions are an HTTP-only cookie. Writes from other origins are rejected.
- Exactly one account exists. Every endpoint except health and the sign-in routes requires login, and each user's data is scoped
  to that user.
- API keys live only in `backend/.env` (git-ignored). They are never sent to the browser, logged or returned by the API.
- `.env`, database files and backups are git-ignored.
