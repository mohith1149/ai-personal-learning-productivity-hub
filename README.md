# AI Personal Learning & Productivity Hub

A single-user, self-hosted command center that tells you every day what to learn, build and do, and keeps you honest about it.
It is also a hands-on AI-engineering project: the backend is built around a provider-neutral LLM interface with tool calling and
approval gates.

> Guides: [Setup](docs/SETUP.md) · [Integrations](docs/INTEGRATIONS.md) (e-mail, GitHub, YouTube, AI, n8n) · [Deployment and backups](docs/DEPLOYMENT.md) · [Troubleshooting](docs/TROUBLESHOOTING.md).
> Design notes, decisions and the per-milestone history live in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

## Status (read this first)

**Works today (tested):** sign-in, tasks, courses, video collections with YouTube import, an AI-engineering roadmap, habits, projects,
a combined daily planner, a daily AI project challenge, a dashboard, weekly and monthly reports, e-mail reminders and the AI assistant.

**Not working yet:**

| Not built | Planned |
|---|---|
| GitHub account sign-in (OAuth) and repo sync. Not needed: verification and project import work on public repos with no account link, and `GITHUB_TOKEN` covers private ones. | not scheduled |
| Gmail API (OAuth) sending. SMTP with an App Password is built and was tested with a real Gmail account and n8n. | not scheduled |
| OpenAI adapter. Groq, Gemini and Anthropic are built (Anthropic only against a fake server; Groq and Gemini were run live). | not scheduled |

## What each part does

| Page | What it does |
|---|---|
| Dashboard | Today at a glance: plan, tasks, videos to watch, habits, projects, challenge, roadmap, last 7 days. Computed from the other pages, nothing stored. |
| Daily planner | One list for the day from tasks, course lessons, videos, roadmap topic, habits and projects. Complete, reschedule or excuse items. **Rest days:** a limited number per month (default 4) so a sick day or a holiday keeps your challenge streak and shows nothing as overdue. **Daily hours:** set the hours you have each weekday in Settings and the planner flags a day that has more planned than that (only items with a time are added up; the rest are counted, not guessed). **Move unfinished to tomorrow** previews and moves open tasks and shows how loaded tomorrow becomes. A task moved 3 or more times is marked *Slipping*, with a button that asks the assistant why. **Goals and pace:** a course or project with a target date is a goal; the planner shows whether your recent pace gets you there in time (and the projected finish) and warns when you are behind. |
| Tasks | Priorities, categories, due dates, recurring tasks. |
| Courses | Courses, modules, lessons, study sessions. Set a target finish date to get a pace line (on track or behind). |
| Videos | Collections with a daily target; paste links or import a YouTube playlist. Finished videos are never suggested again. |
| AI roadmap | Your AI-engineering path as stages and topics. |
| Habits | Daily/weekly habits with streaks. |
| Projects | Projects, milestones, development sessions. **Suggest with AI** (when a key is set) fills the empty fields and proposes milestones from a repo link and/or your description; you edit before creating. **Fill from GitHub** reads a repo (name, description or README intro, languages, topics) and fills the empty form fields; nothing is saved until you click Create. |
| Daily challenge | One real piece of AI project work per day: a summary, repo URL, commit hash and minutes, or an explicit excuse. A day is never completed automatically. Streaks and missed days are computed, never stored. **Verify on GitHub** checks the commit exists, matches your message, was made that day and changes code; only a pass shows *Verified*. Public repos need no setup; set `GITHUB_TOKEN` in `backend/.env` for private repos. |
| Reports | **Weekly and monthly reports** from your own records: items finished, study and project time, habit check-ins, plan completion and the daily challenge, per day and in total, compared with the same days of the previous period. Charts have a table view. Nothing is estimated; days that have not happened yet are blank. |
| Share | **Settings → Share your progress** makes a private link to a read-only page: your streaks, hours, **verified** commits (first line, short hash, date), projects, finished topics and completed courses. Tasks, habits, notes, write-ups, your e-mail and private repositories are never shown. Make a new link to kill the old one, or stop sharing. The weekly report e-mail includes the link while sharing is on. |
| Timer | A **Timer** button on tasks, lessons, courses, roadmap topics, projects and planner rows starts one stopwatch (shown at the top of every page). **Stop and log** adds the time to the project (a development session), the course or the topic, and to the task's actual time; **Discard** logs nothing. It keeps running if you reload. |
| Settings | Your account (read-only), **planning** (hours per weekday, rest days per month), **e-mail reminders** (daily plan, evening overdue nudge, weekly report; times, test e-mail, history) and a light/dark switch. Editing your profile or timezone is not built. |
| AI assistant | Chat window (shown once a key is set) with a **model menu**, 19 tools (14 read, 5 propose-only; includes a weekly report and slipping tasks), **Morning check-in / Evening check-out** buttons, a GitHub repo lookup (paste a repo link in the chat), approval queue and a **Test the connection** button. The assistant cannot change anything itself. |

## Run it (Windows, development)

Full steps, including updating and where files live: [docs/SETUP.md](docs/SETUP.md).

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

More detail (Gmail App Password steps, retries, n8n): [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).

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
To use n8n instead, set `SCHEDULER_MODE=n8n`, set `AUTOMATION_API_KEY`, and import `docs/n8n-run-due.json` (never run both). In n8n use `127.0.0.1`, not `localhost` (n8n resolves `localhost` to IPv6 and the backend listens on IPv4).

## AI assistant (optional)

Off until you add a key. `AI_PROVIDER` is the default provider; every provider that has a key also shows up in the chat's **model menu**, so
you can switch between them (and between each provider's models) without touching `.env`. Your choice is remembered in the browser.

**Free: Groq** (generous free limits, a good default; Groq may keep free-tier prompts, so keep private data out):

```
AI_PROVIDER=groq
GROQ_API_KEY=<key from https://console.groq.com/keys>
GROQ_MODEL=openai/gpt-oss-120b
```

**Free but tightly limited: Google Gemini** (about 5 requests a minute, which a tool-using chat can hit; Google may use free-tier prompts):

```
AI_PROVIDER=gemini
GEMINI_API_KEY=<key from https://aistudio.google.com/apikey>
```

**Paid, pay-as-you-go: Anthropic**:

```
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=<your key from console.anthropic.com>
```

The model menu asks Groq and Gemini for their current model list (model names get retired), and falls back to a short built-in list.

Restart the backend, open **AI assistant**, press **Test the connection** (a tiny real request). Only then does the chat window appear.
Nothing the assistant proposes happens until you approve it. Keys never leave the backend. The adapters are tested against
fake servers until you run them with a real key (Groq and Gemini have been run live; Anthropic has not).

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

## Deploying and backups

The backend serves only `/api`; put a reverse proxy in front that serves `frontend/dist` and forwards `/api`, run one worker, set
`ENVIRONMENT=production` and `COOKIE_SECURE=true`, and back up with SQLite's backup command. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). **Containers:** `docker compose up --build -d` runs the whole app (Docker or Rancher Desktop); see the Containers section there.

## Security notes

- Passwords are hashed with bcrypt. Sessions are an HTTP-only cookie. Writes from other origins are rejected.
- Exactly one account exists. Every endpoint except health and the sign-in routes requires login, and each user's data is scoped
  to that user.
- API keys live only in `backend/.env` (git-ignored). They are never sent to the browser, logged or returned by the API.
- `.env`, database files and backups are git-ignored.
