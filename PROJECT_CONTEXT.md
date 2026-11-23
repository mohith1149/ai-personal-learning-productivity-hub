# PROJECT_CONTEXT.md — AI Personal Learning & Productivity Hub

> Living document. Updated at the end of every phase. Source of truth for architecture,
> schema, endpoints, progress and known issues.

Last updated: 2026-11-23 — Phases 1–2 complete. Phase 3 in progress: milestone 1 (auth) done.

---

## 1. Purpose

A single-user, self-hosted command center that:

- Tells the user every morning what to learn, build and do (dashboard + email).
- Enforces a **Daily AI Engineering Challenge**: every calendar day must have verified,
  meaningful project work (new AI project milestone or an existing-project Git commit),
  or an explicit excuse. Never auto-completed.
- Tracks courses (DeepLearning.AI Agentic AI, ByteByteGo videos, unlimited custom courses),
  an AI-engineering roadmap, tasks, habits, projects, GitHub activity.
- Provides a Claude-powered assistant with real, backend-connected tool calling and
  confirmation gates for any write.
- Produces weekly/monthly analytics from real database records only.

## 2. Environment (verified 2026-11-23)

| Item | Value |
|---|---|
| OS | Windows 11 Pro |
| Node.js | v20.19.2 at `D:\node.exe` |
| npm | 10.8.2 — **repaired**: `D:\node_modules\npm` was missing; restored from the official, SHA-256-verified `node-v20.19.2-win-x64.zip` |
| Python | 3.11.4 (`C:\Users\user\AppData\Local\Programs\Python\Python311`) |
| Git | 2.55 |
| Docker | not installed (not required; SQLite used) |
| TLS interception | **Kaspersky Anti-Virus re-signs HTTPS** (`CN=Kaspersky Anti-Virus Personal Root Certificate`). Trusted by Windows, not by Python's certifi. Fixes: venv pip upgraded to 26.3 (uses OS trust store via truststore); backend calls `truststore.inject_into_ssl()` at startup so GitHub/Anthropic/SMTP calls work. npm registry is unaffected. |

### How to run (dev)

```powershell
# Backend (terminal 1)
cd ai-learning-hub\backend
.venv\Scripts\python.exe -m alembic upgrade head      # apply migrations
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd ai-learning-hub\frontend
npm run dev                                          # http://localhost:5173 (proxies /api → :8000)

# Tests
cd ai-learning-hub\backend; .venv\Scripts\python.exe -m pytest -q
cd ai-learning-hub\frontend; npm run typecheck
```

`backend/.env` was generated locally with random `SECRET_KEY`, `ENCRYPTION_KEY`,
`AUTOMATION_API_KEY` (git-ignored). Template: `backend/.env.example`.

## 3. Architecture

```
┌───────────────────────────┐        ┌──────────────────────────────────────────────┐
│ React + TS + Tailwind     │  HTTP  │ FastAPI (Python 3.11)                         │
│ (Vite, Recharts,          │ ─────► │  routers/  → services/ → models/ (SQLAlchemy) │
│  TanStack Query, Router)  │  JSON  │  auth (JWT cookie, single user)              │
│ :5173 (dev) → proxy /api  │        │  scheduler (APScheduler, in-process)          │
└───────────────────────────┘        │  integrations: GitHub, Email, Claude          │
                                     └───────┬──────────────┬───────────────┬────────┘
                                             │              │               │
                                    SQLite (dev) ↔    GitHub REST API   Anthropic API
                                    PostgreSQL (later,  (OAuth / PAT)   (tool calling)
                                    via DATABASE_URL)
                                             ▲
                         n8n (optional) ─────┘  calls /api/automation/* with X-Automation-Key
                                                (alternative to the built-in scheduler)
```

### Key design decisions

1. **Layering**: `routers` (HTTP only) → `services` (business rules, reused by routers,
   scheduler, n8n endpoints and AI tools) → `models` (SQLAlchemy 2.0 ORM). The AI assistant
   calls the *same* service functions as the UI — no separate "AI data path", so the AI
   cannot see or produce anything the UI wouldn't.
2. **Database portability**: SQLAlchemy 2.0 + Alembic migrations; only portable column types
   (no SQLite-only features). Switching to PostgreSQL = change `DATABASE_URL` + `alembic upgrade head`.
3. **Single user, multi-user-ready**: every owned table has `user_id` FK. First-run setup
   creates the account; afterwards login is required (bcrypt hash + HTTP-only JWT cookie).
4. **Scheduling**: built-in APScheduler job runs every minute and is *idempotent*
   (unique `(user_id, type, period_key)` on `email_notifications`) → no duplicate emails,
   safe after restarts. `SCHEDULER_MODE=internal|n8n|off`. In `n8n` mode the internal job is
   disabled and n8n cron workflows call `/api/automation/*`.
5. **Email**: provider abstraction — `smtp` (Gmail with App Password; simplest, reliable)
   and `gmail_api` (OAuth). Every attempt is recorded with status `sent|failed|skipped`;
   `sent` is only written after the provider accepted the message.
6. **GitHub**: OAuth App flow (preferred) or Personal Access Token fallback; tokens encrypted
   at rest (Fernet, key from env). Commit verification = `GET /repos/{owner}/{repo}/commits/{sha}`
   (works unauthenticated for public repos). Local `git` verification for local repo paths.
   Unverified commits are stored as `verification_source='unverified'` and never shown as verified.
7. **AI assistant**: Anthropic Python SDK, Messages API, manual tool-use loop hosted in the
   backend (tools need direct access to the local DB). Read tools execute immediately;
   write tools (complete/create/reschedule task, record progress, add course…) create an
   `ai_pending_actions` row and return "awaiting user confirmation" — the UI shows
   Approve/Reject; only approval executes the service call. Model: `claude-opus-5-5`
   with adaptive thinking; server-side refusal fallback enabled.
8. **Accountability rules are enforced server-side** (not just in UI): challenge cannot be
   completed without evidence (verified commit, or milestone with description); past days
   with no completed/excused record become `missed`; nothing is auto-completed.

## 4. Repository layout

```
ai-learning-hub/
  PROJECT_CONTEXT.md        ← this file
  README.md                 ← setup & run (Phase 8 expands)
  backend/
    app/
      main.py               FastAPI app factory, CORS, router registration, scheduler start
      config.py             pydantic-settings (reads .env)
      database.py           engine, SessionLocal, Base
      models/               SQLAlchemy models (one module per domain)
      schemas/              Pydantic request/response models
      routers/              HTTP endpoints
      services/             business logic (tasks, courses, challenges, email, github, ai…)
      core/                 security (JWT, hashing, encryption), deps
      seed.py               first-run seed: categories, roadmap, courses, habits, project ideas
    alembic/                migrations
    tests/                  pytest (in-memory SQLite)
    requirements.txt
    .env.example
  frontend/
    src/
      api/                  typed fetch client + per-domain hooks (TanStack Query)
      components/           layout (Sidebar, Header), ui primitives, charts
      pages/                one per sidebar item
      lib/                  dates, formatting
  n8n/                      exported workflow JSON for daily email / weekly report / missed-day job
```

## 5. Database schema

All tables have `id` (int PK), `created_at`, `updated_at` (UTC) unless noted.
`user_id` → `users.id` ON DELETE CASCADE on every owned table.

| Table | Key columns | Constraints / indexes |
|---|---|---|
| users | email, password_hash, display_name, timezone | unique(email) |
| user_settings | user_id (PK), reminder_email, email_enabled, reminder_time, overdue_reminders_enabled, weekly_report_enabled, weekly_report_day, daily_learning_minutes, bbg_daily_target | 1:1 users |
| task_categories | name, color, is_system | unique(user_id, name) |
| recurring_tasks | title, description, category_id, priority, estimated_minutes, frequency(daily/weekdays/weekly/monthly), days_of_week, day_of_month, start_date, end_date, active, last_generated_date | idx(user_id, active) |
| tasks | title, description, notes, category_id, task_type(one_time/recurring/course_lesson/habit/project_dev), priority(1–4), status(pending/in_progress/completed/cancelled), scheduled_date, due_date, estimated_minutes, actual_minutes, completed_at, recurring_task_id, lesson_id, project_id, challenge_id, carried_from_date, carry_count | idx(user_id, scheduled_date), idx(user_id, status), unique(recurring_task_id, scheduled_date) |
| courses | title, provider, url, kind(course/video_series), status(active/paused/completed/archived), priority, target_date, started_at, completed_at, last_studied_at, description | idx(user_id, status) |
| course_modules | course_id, title, position | idx(course_id, position) |
| course_lessons | module_id, course_id, title, url, lesson_type(lesson/video), duration_minutes, position, status(not_started/in_progress/completed), completed_at, notes | idx(course_id, status, position). **ByteByteGo videos = lessons with lesson_type='video' in a `video_series` course** — this is the "video progress" table |
| learning_sessions | date, minutes, course_id?, lesson_id?, roadmap_topic_id?, notes | idx(user_id, date) |
| learning_resources | title, url, resource_type, roadmap_topic_id?, course_id?, notes | |
| roadmap_stages | title, description, position | |
| roadmap_topics | stage_id, title, description, position, status(not_started/learning/completed), completion_pct(0–100), exercises, project_applications, minutes_spent, completed_at | idx(stage_id, position) |
| habits | name, description, frequency(daily/weekly), target_per_period, target_value, unit, active, archived_at | |
| habit_logs | habit_id, date, completed, value, note | unique(habit_id, date) |
| project_ideas | title, problem_statement, difficulty, concepts(JSON), tech_stack, features, milestones(JSON), learning_outcomes, estimated_hours, status(backlog/in_progress/done/dropped), source(seed/custom/ai), related_topic_id? | |
| projects | title, description, problem_statement, tech_stack, status(active/paused/completed/archived), is_ai_project, idea_id?, repo_url, repository_id?, started_at, completed_at, last_activity_at | idx(user_id, status) |
| project_milestones | project_id, title, description, status(pending/done), position, due_date, completed_at, evidence | |
| git_repositories | provider(github/manual), owner, name, full_name, url, default_branch, is_private, github_id, pushed_at, last_synced_at, project_id? | unique(user_id, full_name) |
| git_commits | repository_id, sha, message, author_name, committed_at, url, additions, deletions, files_changed, verification_source(github_api/local_git/unverified), verified_at, challenge_id? | unique(repository_id, sha) |
| daily_challenges | date, mode(new_project/existing_project), project_id?, planned_task, estimated_minutes, actual_minutes, status(planned/in_progress/completed/missed/excused), implemented_summary, evidence_type(commit/milestone), commit_id?, milestone_id?, excuse_reason, completed_at | unique(user_id, date) |
| daily_checkins | date, main_priority, project_mode, available_minutes, schedule_changes, generated_plan(JSON) | unique(user_id, date) |
| daily_checkouts | date, videos_note, agentic_note, project_done, repo, commit_made, physical_done, pending_note, completion_score, confirmed_at | unique(user_id, date) |
| email_notifications | type(daily_plan/overdue/weekly_report/test), period_key, recipient, subject, body_html, status(pending/sent/failed/skipped), provider, provider_message_id, error, attempts, sent_at | **unique(user_id, type, period_key)** → no duplicates |
| weekly_reports | week_start, week_end, metrics(JSON), ai_summary | unique(user_id, week_start) |
| oauth_tokens | provider, access_token_enc, scope, account_login | unique(user_id, provider) |
| ai_conversations / ai_messages | title / conversation_id, role, content(JSON) | |
| ai_pending_actions | conversation_id, tool_name, tool_input(JSON), status(pending/approved/rejected/executed/failed), result(JSON), resolved_at | |
| activity_log | entity_type, entity_id, action, source(user/ai/system), details(JSON) | idx(user_id, created_at) — audit trail, preserves history |

### 5a. Schema changes since Phase 1 (migration `3fe8e7449f3d`, Phase 3)

| Change | Why |
|---|---|
| `tasks.due_time` | overdue logic needs a time of day |
| `courses.notes`; `roadmap_topics.notes`, `.last_studied_at`; `roadmap_topics.status` now `not_started/in_progress/completed` | Phase 3 spec |
| **new `videos`** (title, url, description, category, status `unwatched/watching/completed`, position, completed_at, notes) with CHECK `(status='completed') = (completed_at IS NOT NULL)` and index `(user_id,status,position)` | dedicated ByteByteGo tracker; **replaces** the Phase 1 idea of storing videos as course lessons |
| `habits.start_date`, `.notes` | Phase 3 spec |
| `projects.objective`, `.notes`, `.priority`, `.target_date`; CHECK priority 1–4 | Phase 3 spec |
| **new `project_sessions`** (project, date, minutes>0, summary, milestone) | development-session tracking |
| `daily_challenges.repo_url`, `.commit_sha`, `.commit_message`, `.evidence_notes`, `.verification_status` (`unverified`/`verified`, default `unverified`); CHECK `completed_needs_commit` | manual evidence now; GitHub verification in Phase 4. **A completed day requires summary + repo URL + commit hash** (stricter than the Phase 1 "milestone" alternative, per the Phase 3 spec) |
| `users.session_version` | server-side session revocation |
| **new `login_attempts`**, **new `ai_memories`** | login lockout; user-visible long-term assistant memory |

Gotcha learned: Alembic autogenerate does **not** detect CHECK constraints on existing tables — they were added to the
migration by hand and verified in the live DB. The migration was round-tripped (up/down/up) on a scratch database.

## 6. API endpoints (prefix `/api`)

Status legend: ✅ implemented & tested · 🚧 in progress · ⏳ planned

| Area | Endpoints | Status |
|---|---|---|
| Health | `GET /health` | ✅ |
| Auth | `GET /auth/status`, `POST /auth/setup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | ✅ (tested + live) |
| Settings | `GET/PATCH /settings` | ⏳ |
| Dashboard | `GET /dashboard/today`, `GET /dashboard/overview` | ⏳ |
| Categories | `GET/POST /categories`, `PATCH/DELETE /categories/{id}` | ⏳ |
| Tasks | `GET /tasks?date&status&category_id`, `POST /tasks`, `GET/PATCH/DELETE /tasks/{id}`, `POST /tasks/{id}/complete`, `/reopen`, `/reschedule`, `POST /tasks/carry-forward` | ⏳ |
| Recurring | `GET/POST /recurring-tasks`, `PATCH/DELETE /recurring-tasks/{id}`, `POST /recurring-tasks/generate?date` | ⏳ |
| Courses | `GET/POST /courses`, `GET/PATCH/DELETE /courses/{id}`, `POST /courses/{id}/pause`, `/resume`, `GET /courses/{id}/next`, `POST /courses/{id}/modules`, `POST /courses/{id}/bulk-lessons`, `PATCH/DELETE /modules/{id}`, `POST /modules/{id}/lessons`, `PATCH/DELETE /lessons/{id}`, `POST /lessons/{id}/complete`, `/uncomplete` | ⏳ |
| ByteByteGo | `GET /learning/bytebytego` (summary, next N videos, daily target) | ⏳ |
| Learning sessions | `GET/POST /learning-sessions`, `DELETE /learning-sessions/{id}` | ⏳ |
| Roadmap | `GET /roadmap`, `POST /roadmap/topics`, `PATCH /roadmap/topics/{id}`, `GET /roadmap/next` | ⏳ |
| Habits | `GET/POST /habits`, `PATCH/DELETE /habits/{id}`, `PUT /habits/{id}/logs/{date}`, `GET /habits/{id}/stats` | ⏳ |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}`, milestones `POST /projects/{id}/milestones`, `PATCH/DELETE /milestones/{id}` | ⏳ |
| Project ideas | `GET/POST /project-ideas`, `PATCH/DELETE /project-ideas/{id}`, `POST /project-ideas/{id}/start`, `GET /project-ideas/recommend` | ⏳ |
| Daily challenge | `GET /challenges/today`, `POST /challenges`, `PATCH /challenges/{id}`, `POST /challenges/{id}/complete`, `/excuse`, `GET /challenges/calendar?start&end` | ⏳ |
| GitHub | `GET /github/status`, `GET /github/oauth/start`, `GET /github/oauth/callback`, `POST /github/token`, `POST /github/disconnect`, `POST /github/sync`, `GET /github/repos`, `GET /github/repos/{id}/commits`, `POST /github/verify-commit` | ⏳ |
| Check-in/out | `GET/PUT /checkins/{date}`, `GET/PUT /checkouts/{date}` | ⏳ |
| Notifications | `GET /notifications`, `POST /notifications/test`, `GET /notifications/preview/daily-plan`, `POST /notifications/run/{type}` | ⏳ |
| Automation (n8n) | `POST /automation/daily-plan`, `/overdue`, `/weekly-report`, `/close-day` (header `X-Automation-Key`) | ⏳ |
| Assistant | `GET/POST /assistant/conversations`, `GET /assistant/conversations/{id}`, `POST /assistant/conversations/{id}/messages`, `POST /assistant/actions/{id}/approve`, `/reject` | ⏳ |
| Reports | `GET /reports/weekly?week_start`, `GET /reports/monthly?month`, `POST /reports/weekly/generate` | ⏳ |
| Export | `GET /export` (full JSON export) | ⏳ |

## 7. AI tool-calling design

Tools (JSON-schema, `strict: true`) map 1:1 to service functions:

| Tool | Kind | Service |
|---|---|---|
| get_today_tasks, get_pending_tasks | read | tasks |
| get_course_progress, get_completed_videos, get_next_video | read | courses |
| get_active_projects, get_github_commits | read | projects / github (DB-synced commits only) |
| get_roadmap_progress, get_habit_status, generate_weekly_report | read | roadmap / habits / reports |
| create_task, complete_task, reschedule_task, add_course, create_project_challenge, record_project_progress | **write → requires confirmation** | ai_pending_actions → service on approval |

System prompt rules: never fabricate progress or commits; only report data returned by tools;
propose writes, don't claim they happened until the tool result says executed.

## 8. n8n workflows (Phase 5)

- `daily-plan.json`: Cron (user's reminder time) → HTTP POST `/api/automation/daily-plan`.
- `weekly-report.json`: Cron (Sun 18:00) → `/api/automation/weekly-report`.
- `close-day.json`: Cron (00:05) → `/api/automation/close-day` (marks yesterday's challenge missed if not completed/excused).
Backend stays the single source of truth (n8n only triggers); idempotency keys prevent duplicates.

## 9. Phases & progress

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, schema, API design, this document | ✅ done |
| 2 | npm repair, git init, backend + frontend scaffolds, env config, SQLite, smoke test | ✅ done |
| 3 | Auth ✅ · app shell · tasks · courses · ByteByteGo · roadmap · habits · projects · daily challenge · planner · dashboard · AI foundation | 🚧 milestone 2 next |
| 4 | Daily AI Engineering Challenge, GitHub OAuth/PAT, commit verification, calendar | ⏳ |
| 5 | Email (SMTP/Gmail), daily/overdue/weekly, scheduler, n8n workflows | ⏳ |
| 6 | Claude assistant, tool calling, confirmations, recommendations, check-in/out planning | ⏳ |
| 7 | Weekly/monthly analytics, full test pass, persistence tests | ⏳ |
| 8 | Docs: setup, deployment, Gmail/Claude/GitHub/n8n configuration | ⏳ |

## 10. Implemented so far

**Phase 2 (done)**
- Backend: FastAPI app factory, pydantic-settings config, SQLAlchemy 2 engine (SQLite WAL +
  foreign keys), `UTCDateTime` type (always tz-aware UTC), all 29 tables from §5, Alembic
  initial migration `6913d7807204` applied, JWT/bcrypt/Fernet security helpers, auth &
  automation-key dependencies, `GET /api/health`.
- Frontend: Vite 7 + React 19 + TS 5.9 + Tailwind 4 + TanStack Query 5 + React Router 7 +
  Recharts 3; dev proxy `/api → :8000`; health-check page.
- Tests (6/6 pass): health endpoint; DB-level rules — completed challenge requires evidence,
  excused requires reason, one challenge per day, email idempotency key, UTC round-trip.
  Frontend typecheck + production build pass. Live check: health OK directly and via proxy.

**Phase 3 — Milestone 1: authentication (done)**
- Backend: `services/auth.py`, `routers/auth.py`, `schemas/auth.py`; middleware that rejects cross-origin writes (403);
  `/docs` and `/openapi.json` only when `ENVIRONMENT` is development/test.
- Rules: exactly one account. The first user is inserted with `id=1`, so a concurrent second setup collides on the
  primary key even if it passes the application check. Setup later returns 409 and cannot overwrite anything.
- Passwords: bcrypt; min 10 chars, must mix letters with digits/symbols, no edge whitespace. E-mail normalised to lower case.
- Session: JWT in an **HttpOnly, SameSite=Lax** cookie (`Secure` via `COOKIE_SECURE`). The token embeds `session_version`;
  logout bumps it, so every previously issued token dies server-side (not just client-side cookie deletion).
- Login: wrong e-mail and wrong password return the same 401 and burn the same bcrypt time; 5 failures / 15 min per e-mail
  → 429 + `Retry-After`; success clears the counter. Responses expose only `id, email, display_name, timezone`.
- Frontend: `api/client.ts` (typed fetch, error mapping incl. 422 and 429), `api/auth.ts` (TanStack Query hooks),
  `pages/AuthPages.tsx` (Setup + Login), `App.tsx` gates routes on server-reported auth state (setup → login → app).
- Tests: 29/29 backend pass (23 new auth tests incl. race, lockout, revocation, CSRF, tamper). A mutation check
  (disabling the version check) made the logout test fail, confirming the test is meaningful.
- Live checks via the Vite proxy: setup → 201, second setup → 409, cookie HttpOnly, restart backend → session and
  login still work, logout → old token 401, DB holds only a bcrypt hash.
- Not yet verified: the setup/login screens in a real browser (no browser automation run yet) — see Known issues.

## 11. Pending work

See phase table. Credentials needed later (asked only when that phase is reached):
Anthropic API key (Phase 6), Gmail App Password or OAuth client (Phase 5),
GitHub OAuth App client ID/secret or PAT (Phase 4).

## 12. Known issues

- npm prints "new major version 12 available" — harmless; staying on npm 10 (matches Node 20).
- Kaspersky HTTPS interception (see §2) — handled; if Kaspersky is uninstalled nothing breaks.
- Commits are authorised by the user after each tested milestone. Local git identity was unset; set repo-local
  (`user.name`/`user.email`) from the account e-mail — change with `git config` if desired.
- UI of the auth screens has been type-checked and built but not yet exercised in a real browser.
- SQLite quirk: a running uvicorn holds `hub.db` open (WAL); stop it before deleting/replacing the file.
