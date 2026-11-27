# PROJECT_CONTEXT.md — AI Personal Learning & Productivity Hub

> Living document. Updated at the end of every phase. Source of truth for architecture,
> schema, endpoints, progress and known issues.

Last updated: 2026-11-25 — Phases 4 to 10 complete. Phase 10 added goals with a pace warning and a timer that logs time. (Phase 9: rest days, daily hours with overload flag, roll-over, slipping tasks.)
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
cd ai-learning-hub\frontend; npm run typecheck; npm test      # Vitest + Testing Library (jsdom)
```

> **Windows gotcha:** run `npm test` from a path whose drive letter is **uppercase** (`D:\...`). From Git Bash's
> `/d/...` (lower-case `d:`) Vitest loads two copies of itself and fails with "failed to find the current suite".

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
  README.md                 ← overview, status, quick start; links to docs/
  docs/                     SETUP, INTEGRATIONS, DEPLOYMENT, TROUBLESHOOTING, n8n-run-due.json
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
      components/           AppLayout (sidebar, mobile drawer, header), ThemeSwitcher, ui.tsx primitives,
                            Modal (+ConfirmDialog), forms.tsx (TextInput/TextArea/SelectInput/FormError)
      pages/                AuthPages, ShellPages (dashboard, settings, placeholder, 404); pages/tasks/ (Milestone 3)
      nav.ts                single source of truth for sidebar + routes (status ready|soon per feature)
      theme.tsx             light/dark/system theme (class-based, persisted, no flash on load)
      test/                 Vitest setup + shell tests
      lib/dates.ts          timezone-safe date helpers (todayIn, addDays, describeDue …)
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

**Migration `a1c4e7b92d10` (Milestone 3):** CHECK `completed_consistency` on `tasks`:
`(status = 'completed') = (completed_at IS NOT NULL)`. Hand-written (see gotcha below), repairs any inconsistent rows first,
round-tripped up/down/up, `alembic check` reports no drift.

**Migration `b2d5f8c3a1e7` (Milestone 4):** CHECK `completed_at_matches_status` on `course_lessons`
(`(status='completed') = (completed_at IS NOT NULL)`), hand-written, repairs inconsistent rows first, round-tripped up/down/up,
`alembic check` clean.

**Migration `c3e6a9d4b2f8` (Milestone 5):** new table `video_playlists` (name, source_url, youtube_playlist_id, description,
`daily_target` CHECK 1–50, active; unique `(user_id, name)`); `videos` gains `playlist_id` (NOT NULL, FK ON DELETE CASCADE),
`youtube_video_id`, index `(playlist_id, status, position)` and unique `(playlist_id, youtube_video_id)` (NULL ids exempt).
Hand-written: any pre-existing videos are moved into one "Imported videos" playlist per owner before `playlist_id` becomes NOT NULL
(verified with a row inserted at the previous revision). Round-tripped up/down/up, `alembic check` clean.

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
| Task categories | `GET/POST /task-categories`, `PATCH/DELETE /task-categories/{id}` | ✅ (tested + live) |
| Tasks | `GET /tasks?view=all\|open\|today\|overdue\|upcoming\|completed&status&category_id&priority&q&limit&offset` → `{items,total}`, `GET /tasks/counts`, `POST /tasks`, `GET/PATCH/DELETE /tasks/{id}` (complete/reopen/cancel = `PATCH {status}`) | ✅ (tested + live) |
| Recurring | `GET/POST /recurring-tasks`, `PATCH/DELETE /recurring-tasks/{id}` (generation is automatic and idempotent; no public generate endpoint yet) | ✅ (tested + live) |
| Courses | `GET /courses?status=`, `POST /courses`, `GET/PATCH/DELETE /courses/{id}` (pause/resume/archive = `PATCH {status}`), `GET /courses/{id}/next`, `POST /courses/{id}/modules`, `POST /courses/{id}/bulk-lessons` | ✅ (tested + live) |
| Modules / lessons | `PATCH/DELETE /modules/{id}`, `POST /modules/{id}/move`, `POST /modules/{id}/lessons`, `PATCH/DELETE /lessons/{id}`, `POST /lessons/{id}/move\|start\|complete\|uncomplete` (every one returns the whole updated course) | ✅ (tested + live) |
| Course templates | `GET /course-templates`, `POST /course-templates/{key}` (409 if already added) | ✅ (tested + live) |
| Video playlists | `GET/POST /video-playlists`, `GET/PATCH/DELETE /video-playlists/{id}` (summary: totals, floored percent, `watched_today`, `remaining_today`, `next_video`), `GET /video-playlists/{id}/today` (`up_next` = next `remaining_today` unwatched videos), `GET /video-playlists/{id}/videos?view=all\|open\|completed&q&limit&offset` → `{items,total}`, `POST /video-playlists/{id}/videos`, `POST /video-playlists/{id}/bulk-videos` (`{lines,category}` → `{added,duplicates,invalid}`) | ✅ (tested + live) |
| Videos | `GET /videos/next` (first unwatched video across active playlists), `PATCH/DELETE /videos/{id}`, `POST /videos/{id}/start\|complete\|uncomplete\|move` | ✅ (tested + live) |
| Learning sessions | `GET /learning-sessions?course_id&limit&offset`, `POST /learning-sessions`, `DELETE /learning-sessions/{id}` | ✅ (tested + live) |
| Roadmap | `GET /roadmap`, `POST /roadmap/topics`, `PATCH/DELETE /roadmap/topics/{id}`, `POST /roadmap/topics/{id}/status`, `GET/POST /roadmap/topics/{id}/study` | ✅ (tested) |
| Habits | `GET/POST /habits`, `GET/PATCH/DELETE /habits/{id}`, `PUT/DELETE /habits/{id}/logs/{date}`, `GET /habits/{id}/logs` | ✅ (tested) |
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}`, milestones `POST /projects/{id}/milestones`, `PATCH/DELETE /milestones/{id}` | ⏳ |
| Project ideas | `GET/POST /project-ideas`, `PATCH/DELETE /project-ideas/{id}`, `POST /project-ideas/{id}/start`, `GET /project-ideas/recommend` | ⏳ |
| Daily challenge | `GET /challenges/today`, `POST /challenges`, `PATCH /challenges/{id}`, `POST /challenges/{id}/complete`, `/excuse`, `GET /challenges/calendar?start&end` | ✅ |
| GitHub | `GET /github/status`, `GET /github/oauth/start`, `GET /github/oauth/callback`, `POST /github/token`, `POST /github/disconnect`, `POST /github/sync`, `GET /github/repos`, `GET /github/repos/{id}/commits`, `POST /github/verify-commit` | ⏳ |
| Check-in/out | `GET/PUT /checkins/{date}`, `GET/PUT /checkouts/{date}` | ⏳ |
| Notifications | `GET /notifications`, `POST /notifications/test`, `GET /notifications/preview/daily-plan`, `POST /notifications/run/{type}` | ⏳ |
| Automation (n8n) | `POST /automation/daily-plan`, `/overdue`, `/weekly-report`, `/close-day` (header `X-Automation-Key`) | ⏳ |
| Assistant | `GET/POST /assistant/conversations`, `GET /assistant/conversations/{id}`, `POST /assistant/conversations/{id}/messages`, `POST /assistant/actions/{id}/approve`, `/reject` | ⏳ |
| Reports | `GET /reports/weekly?week_start` (any day in the week; Monday to Sunday), `GET /reports/monthly?month=YYYY-MM` | ✅ (`POST /reports/weekly/generate` not needed: the weekly e-mail already exists) |
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
| 3 | Auth ✅ · app shell ✅ · tasks ✅ · courses ✅ · video playlists ✅ · roadmap · habits · projects · daily challenge · planner · dashboard · AI foundation | 🚧 next: integration tests, docs, final verification |
| 4 | Daily AI Engineering Challenge, GitHub OAuth/PAT, commit verification (✅ verify button), calendar, repo sync; **plus** "import project from a GitHub repo" (no LLM: read repo name, description, languages, README and prefill the project form) | ✅ done (verify + import via public API / optional `GITHUB_TOKEN`). OAuth, repo sync and a separate commit calendar deliberately skipped: the challenge calendar already shows verified days |
| 5 | Email (SMTP/Gmail), daily/overdue/weekly, scheduler, n8n workflows | ✅ built and tested with a fake mail server; real SMTP send needs the owner's App Password. Gmail API not built |
| 6 | Claude assistant, tool calling, confirmations, recommendations, check-in/out planning; **plus** "AI project autofill": give a repo URL or a description, the model reads it through a read-only tool and proposes title, description, objective, tech stack and milestones into the project form. The user reviews and edits before saving; nothing is saved automatically | ✅ done. Chat with real tool calling, model menu (Groq, Gemini, Anthropic), connection test, AI project autofill, GitHub repo lookup and check-in/check-out planning. Run live on Groq and Gemini; Anthropic only against a fake server |
| 7 | Weekly/monthly analytics, full test pass, persistence tests | ✅ done. `GET /reports/weekly`, `/reports/monthly`, the Reports page (charts + table view), restart/crash persistence tests, migration-drift check |
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

**Phase 3 — Milestone 2: application shell and design system (done, branch `feat/app-shell`)**
- Layout: fixed sidebar on desktop (≥1024px), slide-in drawer on mobile (Escape / backdrop / close button / choosing a
  page all close it; page scroll is locked while open), header with theme switcher, user chip and sign-out, skip-to-content link.
- Navigation: `nav.ts` drives both the sidebar and the routes. Unbuilt features are marked **Soon** and render an honest
  "Not built yet · Planned: Milestone N" page, never fake data. Each milestone flips its item to `ready`.
- Theme: Light / Dark / System, class-based (`dark` on `<html>`), saved in `localStorage` (`hub-theme`, wrapped in
  try/catch), applied by an inline script in `index.html` before first paint, follows the OS live while on System.
- Shared primitives (`components/ui.tsx`): Button, Card, PageHeader, EmptyState, Spinner, ErrorNotice, Badge and a
  `StatusBadge` giving completed / pending / in-progress / overdue / excused / not-started / skipped distinct colours.
- Pages: Dashboard (greeting in the user's timezone + empty state, **no numbers until Milestone 11 computes real ones**),
  Settings (real account details + theme), placeholder, 404. Signed-in visits to /login or /setup go to the dashboard.
- **Bug found by the new tests and fixed:** `useLogout` called `queryClient.clear()`, which also deleted the auth query,
  so nothing refetched and the UI stayed on the signed-in screen after sign-out. It now removes every query except auth
  and refetches auth. (Backend revocation was already correct; this was a front-end-only fault.)
- Tests: 17 Vitest tests (auth gating, nav list + Soon flags + active link, placeholder, 404, dashboard shows no digits,
  settings, theme switch/persist/restore/system-follow/corrupt value, drawer behaviours, sign-out). Backend 29/29 still pass.
- Browser verification: headless Edge driven over CDP against the real dev server (only `/api/auth/status` stubbed).
  Screenshots checked for desktop light/dark, mobile light, mobile drawer dark, settings, setup, login dark; no
  horizontal overflow at 390px; `dark` class applied. This was a visual check, not a full interactive end-to-end run.
- Dependencies: added dev-only Vitest 4.1.12, jsdom, Testing Library. Vitest 3.x was rejected (critical tinypool
  advisory); Vitest 5 needs Node 22 (we have 20). `npm audit` reports 0 vulnerabilities.

**Phase 3 — Milestone 3: tasks (done, branch `feat/tasks`)**
- Backend: `services/tasks.py` (all rules), `routers/tasks.py` (thin HTTP), `schemas/tasks.py` (strict validation:
  unknown fields rejected, blank strings → null, priority 1–4, `HH:MM` times), `core/timeutil.py` (user-timezone "today").
  Every query is scoped to the owner; another user's id behaves exactly like "not found".
- **Overdue** is computed, never stored: an open task is overdue the day after its due date, or the minute after its due
  time, **in the user's timezone**. One definition exists twice (Python `is_overdue`, SQL `overdue_clause`) and a test
  proves they agree across 120 combinations and three clock readings. Scheduled-only (no due date) tasks are never overdue.
- **Completion**: `_apply_status` is the only code that sets/clears `completed_at`; the DB CHECK refuses any other state.
  Completing twice keeps the first completion time; reopening/cancelling clears it. Completed work is never "overdue".
- **Views** (`open/today/overdue/upcoming/completed/all`), search (LIKE wildcards escaped), category/priority filters,
  pagination, and `/tasks/counts` (incl. `completed_today` in the user's local day).
- **Recurring** (daily / weekdays / weekly on chosen days / monthly): instances are created for today + 7 days, idempotently
  (`unique(recurring_task_id, scheduled_date)`), lazily whenever tasks are listed. Day 31 falls on the last day of shorter
  months. If the app was closed, missed days are **back-filled (max 31 days) and show as overdue — they never silently
  vanish**. Pausing skips days (resuming does not back-fill the pause). Changing the schedule replaces only future,
  untouched (pending) instances; started/completed/past/today's tasks are kept. Deleting a template keeps its tasks.
  Deleting one generated task does not resurrect it. A recurring task must start today or later.
- Frontend (`pages/tasks/`): tabs with live counts (Open/Today/Overdue/Upcoming/Completed/All/Recurring, tab kept in
  `?view=`), debounced search, category and priority filters, create/edit modal (due time disabled until a due date),
  tick-to-complete, confirm-before-delete, category manager (add/rename/recolour/delete), recurring panel (create, pause/resume,
  delete). Overdue is shown with a red badge + "N days overdue"; completed/in-progress/cancelled have their own badges.
- Tests: backend 121 (92 new: 41 service-level with an injected clock, 51 HTTP-level incl. auth on all 14 endpoints,
  validation, isolation between users, logout locking the API). Frontend 53 (36 new). **Mutation checks: 6/6 backend and
  9/9 frontend deliberate bugs were caught.**
- **Real end-to-end run (24/24 checks):** headless Edge → Vite → FastAPI → throwaway SQLite, nothing stubbed: first-run
  setup through the real form, categories, 3 tasks, overdue marking, counts, complete/reopen, edit, recurring create →
  8 instances, pause, delete with confirm, reload keeps the session and data, sign-out/sign-in, wrong password, no console
  errors, no horizontal overflow at 390px. The saved DB was then inspected directly (bcrypt hash only, no plaintext, no
  inconsistent rows, no duplicate recurring instances). The run is a scratch script, **not yet part of the repo**.
- Found and fixed along the way: filter controls stacked full-width because two Tailwind width classes conflicted
  (screenshot review caught it; unit tests could not); the same-origin (CSRF) guard correctly returned 403 to my test
  server on :5174 until `FRONTEND_URL` was set — i.e. the guard works.
- Dev ops: the real `hub.db` was **backed up** (`backend/data/backups/`, git-ignored) before migrating it, because it now
  holds the owner's account. `frontend/vite.config.ts` accepts an `API_TARGET` env var (dev only) so a second dev server can
  point at a throwaway backend.

**Phase 3 — Milestone 4: courses and lessons (done, branch `feat/courses`)**
- Backend: `services/courses.py` (all rules), `routers/courses.py`, `schemas/courses.py`; shared strict schema base moved to
  `schemas/common.py`. Modules and lessons have no `user_id`, so ownership is always resolved through their course and
  someone else's id is "not found" (tested for every endpoint).
- **Completion is explicit.** A lesson becomes completed only by `complete_lesson` (idempotent: the first completion time is kept);
  a DB CHECK refuses completed without a completion time. Templates never create completed lessons.
- **Course state is derived** from its lessons: it completes when it has lessons, every lesson is done **and no module is still
  empty**; un-completing a lesson or adding one reopens it. Archived courses are never changed automatically. A course with no
  lessons (e.g. a book) can be completed by hand; one with lessons cannot. **Bug found in my own design via the browser run:**
  a course with 5 modules but lessons only in the first showed "Completed" after finishing that one module; fixed (empty modules
  block completion, `progress.empty_modules` exposes the count, UI explains it).
- Progress percent is **floored** (2 of 3 = 66, never 67) so 100 is only shown when every lesson is done. Next lesson = first
  non-completed lesson in module-then-lesson order (an in-progress one counts).
- Study sessions: no future dates, the lesson must belong to the course, time feeds `minutes_studied`; sessions survive deleting
  their course (course_id becomes NULL) so studied time is never lost. `weekly_minutes()` is ready for the dashboard.
- Links are only accepted as `http(s)://` because they become clickable (`javascript:`/`data:` rejected at the API and tested);
  every external link opens with `rel="noreferrer noopener"`.
- **Template `deeplearning-agentic-ai`:** only the five module titles are seeded, taken from
  https://www.deeplearning.ai/courses/agentic-ai (checked 2026-11-23). **No lessons are invented** because the published sources
  disagree on lesson-level details; the user pastes the lessons they actually take. The titles are editable. Added explicitly
  by a button, never automatically; adding twice is refused (409).
- Frontend (`pages/courses/`): list with status tabs (kept in `?status=`), progress bars, next lesson, minutes left, Quick-start
  template card; detail page with progress, Up next (Start / Mark complete / Open), modules and lessons (tick, start, edit, move,
  delete with confirmation), add module/lesson, **paste a list of lessons** (markers like `1.`, `-`, `•` are stripped, count
  previewed), pause/resume/archive/restore, edit, delete, study-time log.
- Tests: backend 203 (82 new in this milestone: 29 service-level, 53 HTTP-level). Frontend 89 (36 new). **Mutation checks: 16/16
  backend and 14/14 UI deliberate bugs caught.**
- **Real end-to-end run (19/19 checks)** in headless Edge against a real backend and throwaway DB, nothing stubbed: setup, empty
  state + template, add template (5 modules, no lessons), paste lessons, complete/start/add-with-duration, study log, the
  not-complete-while-modules-empty rule, module reorder, deleting empty modules completes the course, reopen, pause/resume/archive,
  rejected `javascript:` link, delete lesson with confirmation, reload, sign-out/in, no console errors, no overflow at 390px. The
  saved DB was inspected directly (no inconsistent lessons, no lesson attached to another course, session saved, no plaintext password).
- Bugs found and fixed during the milestone: (1) `populate_existing` reloads overwrote unflushed changes (lost updates) — the loader now
  flushes first; (2) a field named `date` shadowed the `date` type in a Pydantic model; (3) `Card` silently dropped `aria-label`
  (TypeScript does not check hyphenated JSX attributes); (4) the Active tab said "No courses yet" when only a completed course existed.
- Ops: the real `hub.db` was backed up (`backend/data/backups/`, git-ignored) before migrating.

**Phase 3 — Milestone 5: video playlists and the ByteByteGo tracker (done, branch `feat/videos`)**
- The owner chose nothing explicitly between "roadmap version only" and "plus playlists", so the recommended **A** was built:
  ByteByteGo is one playlist among any number, each with a **daily watch target**. Route `/videos` (nav label "Videos").
- Backend: `services/videos.py` (all rules), `routers/videos.py` (thin HTTP), `schemas/videos.py`; models `VideoPlaylist` and an extended `Video`.
- **Recommendation rule lives in SQL**, not the UI: `_open_videos()` = `status != 'completed' ORDER BY position, id`. Everything that
  recommends (`next_videos`, playlist `next_video`, `/today` `up_next`, `GET /videos/next`) goes through that one query. A completed
  video comes back only after the owner explicitly reopens it (`uncomplete`). A "watching" video is still recommended (not finished).
- **Completion is explicit.** Only `complete` sets it; the first completion time is kept on repeat calls; the DB CHECK
  (`completed ⇔ completed_at`) refuses any other state; the API refuses to set `status` directly (unknown field → 422).
- **Watched today** counts completions inside the user's *local* day (`local_day_bounds_utc`), tested across the Kolkata midnight
  boundary (00:30 local counts, 23:30 the evening before does not). `remaining_today = max(target - watched, 0)`.
- Adding videos: paste links one per line (`url`, `Title | url` or `Title - url`) or add one at a time. Only `http(s)` links are
  accepted (`javascript:`/`data:` rejected). YouTube ids are extracted from watch / youtu.be / shorts / embed links and used to skip
  duplicates (also enforced by a DB unique constraint). Titles are never fetched: without a title the line becomes
  "YouTube video <id>". **Importing a whole YouTube playlist (needs a YouTube Data API key) is NOT built** — nothing is faked.
- No ByteByteGo videos are seeded (none are invented). The empty state offers "Start a ByteByteGo playlist", which only pre-fills the
  form (name, channel link, 1/day).
- Deleting a playlist deletes its videos including watched history (cascade); the UI warns with the count. Playlist names are unique per
  owner, case-insensitive.
- Frontend: `api/videos.ts`, `pages/videos/VideosPage.tsx` (playlist tabs, progress, Today card with "Watched X of N today", To watch /
  Watched / All views, search, start / complete / reopen, up/down reorder, edit, confirm-before-delete), `VideoForms.tsx` (playlist form,
  video form, paste modal that shows added / duplicate / unreadable counts). Reordering is switched off while searching or viewing Watched.
- Tests: backend **308** (105 new: 55 service-level with an injected clock, 50 HTTP-level incl. auth on all 16 endpoints, isolation
  between users, validation); frontend **116** (27 new). **Mutation checks: the key recommendation filter removed → 9 backend tests
  failed; 4/4 deliberate UI bugs caught** (swapped complete/reopen, reorder while searching, dropped `noopener`, delete without confirm).
- **Real end-to-end run (23/23 checks), no mocks and no browser:** real uvicorn + throwaway SQLite over HTTP with a session cookie —
  setup, playlist, paste (3 added / 1 duplicate / 2 rejected), complete → next video skips it, target met, reopen, rejected links and
  direct status writes, logout locks the API; then the **server was stopped and restarted** and login, playlist, progress, completion
  time and the recommendation were verified from the saved file. The browser UI itself was verified with Vitest + a fake API and the
  production build only — **not** by driving a real browser this milestone (the earlier headless-Edge runs were scratch scripts).
- Ops: the real `hub.db` was backed up (`backend/data/backups/hub-before-videos-*.db`, git-ignored) before migrating to `c3e6a9d4b2f8`.

**Milestone 5b: YouTube channel & playlist tracker (owner spec #7, branch `feat/youtube-tracker`)**
- **Library model** (migration `d4f7b1c9e3a5`): `videos` is now one row per user per YouTube video (unique `(user_id, youtube_video_id)`), with
  `thumbnail_url, duration_seconds, published_at, channel_id, channel_title, removed_at`; `position`/`playlist_id` are gone. New table
  `video_memberships(playlist_id, video_id, position)` links videos to collections, so one video can be in a channel AND a playlist with shared
  progress. `video_playlists` gained `kind` (collection/playlist/channel), `youtube_channel_id`, `thumbnail_url`, `reported_total` (NULL = YouTube
  did not say, shown as "unavailable"), `retrieved_count`, `recommend_order` (oldest/newest/manual; default oldest). Deleting a playlist keeps its videos.
- **Remove vs delete**: `POST /videos/{id}/remove|restore` (soft, `removed_at`, hidden from lists/counts/recommendations) vs `DELETE /videos/{id}` (permanent).
  Neither touches YouTube. Re-importing a removed video restores it. Status labels: unwatched/watching/completed = Not started/In progress/Completed.
- **Recommendation (SQL)**: `status != 'completed' AND removed_at IS NULL ORDER BY published_at ASC|DESC` (undated videos last, then position). `GET /videos/next?order=oldest|newest`.
- **Progress**: per collection (`total/completed/in_progress/unwatched/percent` + `reported_total` vs `retrieved_count`) and overall `GET /videos/stats`. Library list `GET /videos?view=all|open|completed|removed&status&sort=recommended|newest|oldest|completed|added&q`; `POST /videos/{id}/status`.
- **YouTube** (`services/youtube.py`, `services/youtube_import.py`, `routers/youtube.py`): `GET /youtube/status` (configured? never the key), `POST /youtube/preview {url, limit|null}` (read-only), `POST /youtube/import {url, video_ids, retrieved}` (only ticked videos; metadata re-read server-side). Accepts `@handle`, `/channel/UC..`, `/@x/videos`, `/playlist?list=`, `watch?v=&list=`. Key = `YOUTUBE_API_KEY` in `backend/.env`, sent in the `X-Goog-Api-Key` header (never the URL: httpx logs URLs). Errors: 422 invalid/private, 404 not found, 429 quota, 503 no/bad key, 502 network. A same-named hand-made collection is adopted on import. Paging cap 2000.
- Verified LIVE with the owner's key: ByteByteGo = 172 videos on YouTube, 25 retrieved over page tokens, thumbnails/durations present, playlist "System Design Fundamentals" 104 videos, bad links give clear errors. No watch history is read (the API has none).
- Alembic env now sets `PRAGMA foreign_keys=OFF` during migrations: SQLite batch rebuilds were cascade-deleting child rows (found when testing this migration).
- Frontend: `pages/videos/` (`VideosPage` overview + "Watch next" card + collection tabs + filters/sort + card grid, `VideoCard`, `ImportModal` 3-step, `VideoForms`), `api/youtube.ts`, `lib/format.ts`. Tests: backend 500+ (library, client, import API), frontend 145.
- **Study plan applied (2026-11-24):** the owner's 21-day ByteByteGo plan (`backend/plans/bytebytego_21_day.txt`, 5 videos/day, day 21 has 4) is applied to the
  imported collection "BYTEBYTEGO" via `python backend/scripts/apply_plan.py <plan> "<collection>" [--apply]` (dry run by default; matches titles to videos already
  in the collection, never creates any). Result: `recommend_order='manual'`, `daily_target=5`, all 104 matched; the "revisit" line is a note, not a video. Inside a
  collection the "Watch next" card follows that collection's order. Backup before: `backend/data/backups/hub-before-plan-*.db`.
- Not built: Google Takeout watch-history import; thumbnails are hot-linked from YouTube.

**Milestone 6: AI Engineering roadmap (done, branch `feat/roadmap`)**
- Route `/roadmap` ("AI roadmap"). The owner's five stages and their exact topic lists (51 topics: 8/9/11/11/12) are created for a user **once, on first open**
  (`services/roadmap.ensure_seeded`), all "not started"; nothing is ever auto-completed. Stage descriptions are empty (nothing invented).
- Migration `e5a8c2d1f4b6`: unique stage title per user, unique topic title per stage, CHECK `(status='completed') = (completed_at IS NOT NULL)`.
  (`roadmap_topics.minutes_spent/last_studied_at/completion_pct` columns exist but are unused: study data is derived.)
- Endpoints: `GET /roadmap` (stages + topics + per-stage and overall progress + `next_topic`), `POST /roadmap/topics`, `PATCH/DELETE /roadmap/topics/{id}`
  (PATCH cannot change status), `POST /roadmap/topics/{id}/status` (the ONLY way to complete), `GET/POST /roadmap/topics/{id}/study`; deleting a study entry uses the
  existing `DELETE /learning-sessions/{id}`.
- Study time/dates = real `learning_sessions` rows with `roadmap_topic_id`; minutes, study days and last-studied date are always computed from them. Logging time on a
  not-started topic moves it to in progress (never completed). Progress = floor(completed/total), per stage and overall (over all topics, not an average of stages).
  `next_topic` = first non-completed topic in roadmap order. Deleting a topic keeps its logged study history.
- Frontend: `pages/roadmap/RoadmapPage.tsx`, `api/roadmap.ts`; tests `roadmap.test.tsx` (12) + `fakeRoadmap.ts`; backend `test_roadmap.py`, `test_roadmap_api.py` (33).
- Not built here: roadmap-based daily suggestions (Milestone 9/10), reordering topics, stage CRUD (only topics can be added).

**Milestone 7: Habits (done, branch `feat/habits`)**
- Route `/habits`. Migration `f6b9d3e2a5c7`: unique habit name per user, days-per-week CHECK 1..7, positive `target_value`.
- Endpoints: `GET/POST /habits`, `GET/PATCH/DELETE /habits/{id}`, `PUT /habits/{id}/logs/{date}` (create/replace the day's record), `DELETE /habits/{id}/logs/{date}`,
  `GET /habits/{id}/logs?days=` (history). Every write returns the refreshed habit.
- Everything shown is **computed from `habit_logs`** (`services/habits.py`, pure functions `daily_streak`/`weekly_streak`): daily streak = consecutive completed days (today not
  yet logged doesn't break it); weekly habit (N days/week, weeks Mon-Sun) streak = consecutive weeks meeting N; week/month progress, total, last-28-day strip, `due_today`.
  Days before `start_date` never count; no records in the future (user's timezone) or before the start date. `completed=false` record = a note about a missed day (doesn't count).
- Bug found by tests and fixed: a reply built right after a write used a stale in-session copy (fixed with `populate_existing`).
- Frontend: `pages/habits/HabitsPage.tsx` (cards with Mark done today/Undo, 28-day clickable strip, amount+note dialog, history, edit, delete), `api/habits.ts`; tests `habits.test.tsx` (16), backend `test_habits.py` + `test_habits_api.py` (60).
- Test infra: global Testing Library wait raised to 4s (`src/test/setup.ts`) after a parallel-load flake in the courses test.
- Not built: habit reminders (Phase 5), archive (the `archived_at` column is unused), monthly weekly-habit percent (shown as days done).

**Milestone 8: Projects (done, branch `feat/projects`)**
- Routes `/projects` (cards, status filter) and `/projects/:id` (overview, milestones, tasks, development sessions, notes). Migration `a7c1e4f8b3d9`: `projects.origin`
  (new/existing), `projects.start_date`, unique title per user, CHECK completed<=>completed_at (projects and milestones), unique milestone title per project,
  `project_sessions.task_id/notes` (+ index). The `ProjectSession` model already existed from the Phase 3 schema migration; no duplicate table was added.
- Endpoints: `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}`, `POST /projects/{id}/milestones|tasks|sessions`, `PATCH/DELETE /project-milestones/{id}`,
  `POST /project-milestones/{id}/status`, `DELETE /project-sessions/{id}`. Project writes return the refreshed detail (milestones, tasks, sessions, computed progress).
- **Progress is computed**: (done milestones + completed tasks) / (milestones + non-cancelled tasks), floored; time/days/sessions are sums over `project_sessions`. A project is
  completed (and a milestone done) ONLY by an explicit action; finishing every milestone does not complete the project. `repo_url` must be `https://github.com/owner/repo`
  (normalised, `.git`/trailing slash stripped). "Existing" projects don't get an invented start date.
- Project tasks are real `tasks` rows (`project_id`, `task_type='project_dev'`): they show on the Tasks page and are completed through the normal task status
  (`PATCH /tasks/{id}`), which moves project progress. Deleting a project keeps its tasks (detached) but deletes milestones and sessions.
- Tests: backend `test_projects.py`, `test_projects_api.py` (83), frontend `projects.test.tsx` (24) with `fakeProjects.ts`.
- Not built: GitHub verification of repos/commits (Phase 4), milestone reordering, linking ideas (`project_ideas` table exists, used by Milestone 9).

**Milestone 10: Daily planner (done, branch `feat/planner`)**
- Route `/planner`. Migration `b8d2f5a1c6e3`: table `planner_excusals` (user, kind, ref_id, date, reason; unique per item per day). It is the ONLY stored planner data:
  the plan itself is assembled from the other features on every request (`services/planner.build_day`).
- Endpoints: `GET /planner?day=`, `POST /planner/complete|reopen|excuse|unexcuse` (body `{kind, ref_id, date[, reason]}`), `POST /planner/tasks/{id}/reschedule`
  (`{date, from_date, move_due_date}`). Every action returns the refreshed day plan.
- What shows on a day: TASKS (scheduled/due that day; on today also every open overdue task and anything scheduled earlier = "overdue"); LESSONS (today: next lesson of each active
  course, one per course per day); VIDEOS (today: each active playlist's daily-target videos in that playlist's own order); ROADMAP TOPICS (today: in progress + next); HABITS (daily
  due every day from start date, missed past days = overdue and can still be recorded; weekly due until the week's target is met); PROJECTS (today: "work on X" until a session is logged;
  can't be completed here, link to log a session). Past/other days show what was completed on them (+ open tasks that were planned for that day, as overdue). Future days: tasks only.
- Completing/reopening delegates to the owning service (tasks/courses/videos/roadmap/habits): single source of truth. Only habits can be changed for a past day; everything else only
  on today's plan. Reschedule only moves `scheduled_date` (optionally `due_date`), sets `carried_from_date`/`carry_count`, never changes status: **a rescheduled task is not completed**.
- Excused = skipped for that day with a reason (>=3 chars); not counted as overdue/missed and left out of the day's percentage; completed items and future days can't be excused;
  excuse covers one day only. Summary: total/completed/pending/overdue/excused, floor percent, study minutes (learning_sessions) and project minutes, per-type counts.
- Found by a live check on the real data: items were sorted alphabetically, hiding the 21-day plan order; fixed (stable sort keeps each feature's own order).
- Tests: backend `test_planner.py` (47), `test_planner_api.py` (18); frontend `planner.test.tsx` (16) + `fakePlanner.ts`.
- Not built: weekly view, drag-to-reorder, planner reminders (Phase 5), the dashboard "today" widget (Milestone 11).

**Milestone 9: Daily AI project challenge (done, branch `feat/challenge`)**
- Route `/challenge`. NO migration: the `daily_challenges` table (with its CHECKs) already existed. Endpoints: `GET /challenges/today` (today's challenge + stats + suggestions),
  `GET /challenges/calendar?start&end` (default last 30 days, max 400), `GET /challenges/history`, `POST /challenges` (plan), `GET/PATCH/DELETE /challenges/{id}`,
  `POST /challenges/{id}/start|complete`, `POST /challenges/excuse` (`{date?, reason}`).
- Plan: one per day; today or future only; mode `existing_project` (an ACTIVE project) or `new_project` (creates the project through the projects service, origin "new").
- Complete (today only) needs: summary >= 30 chars with >= 5 words / 4 distinct (and not a copy of the commit message), a GitHub repo URL, commit hash (7-40 hex), a meaningful
  commit message (junk like "update", "wip", "fix", "initial commit", repeated words rejected), minutes. The repo must match the project's repo if it has one (otherwise the project
  adopts it). The same commit (short or long form) can't count for two days. Optional milestone must belong to the project (linked, never auto-completed).
  Completing also logs a normal `project_sessions` row, so project time/planner dev minutes agree. Stored as `verification_status='unverified'`.
- **HONEST LIMIT**: nothing is checked against GitHub, so an empty/fake commit can't be detected yet. That is Phase 4 (GitHub verification flips `verification_status`).
- `missed` is NEVER stored: a planned/in-progress day that has passed, or a past day with no record (after the first record), is computed as missed. Excusing needs a reason (>= 5 chars),
  works for today or any past day (creates a row if none), never the future; a completed day can't be excused or deleted. Deleting an excused/planned row removes the excuse/plan.
- Streaks/totals computed (`streaks()` pure function): completed days count, excused days are skipped (neither add nor break), today not yet done doesn't break the streak.
  Completion rate = completed / (completed + missed), floored.
- Suggestions (no AI): active projects (least recently worked first, with next milestone / open task), next roadmap topic, next lesson of active courses, last challenge's project.
- Tests: backend `test_challenges.py` (64), `test_challenges_api.py` (35); frontend `challenge.test.tsx` (16) + `fakeChallenges.ts`. Shell placeholder test now uses `/assistant`.
- A bug the HTTP tests caught: an unknown project id raised a 500; now 404.
- Not built: GitHub verification (Phase 4), editing evidence after completion, linking `tasks.challenge_id`, `project_ideas` backlog, reminder emails (Phase 5).
- Gotcha: run vitest from PowerShell with the `D:\` path; from Git bash (`/d/...`) every test file fails with "Vitest failed to find the current suite".

**Milestone 11: Dashboard (done, branch `feat/dashboard`)**
- Route `/` (replaces the empty placeholder). NO migration, nothing stored: `GET /api/dashboard` (`services/dashboard.build`) composes the other features' own services on each
  request, so it can't disagree with them: today's plan summary + next 6 open items (planner), videos to watch today (per active collection with a daily target and something left
  to watch: watched X of N + the titles still to watch), challenge status + streaks (challenges), habits (due today, best current streak), tasks (overdue / due today / completed today),
  active projects (<=5, least recently worked first, progress + time), active courses (progress + next lesson), roadmap (completed/total, next topic), last 7 days of study vs project minutes.
- `is_empty` (no tasks, courses, projects, collections, habits or challenge records) shows an honest empty state with links instead of zeros. The roadmap is seeded first (as the
  roadmap page does), so a new account's plan lists its first roadmap topic; a test caught the dashboard and planner disagreeing before this ordering fix.
- Tests: backend `test_dashboard.py` (7); frontend `dashboard.test.tsx` (13) + `fakeDashboard.ts` (the default fake API serves an empty dashboard; `shell.test.tsx` has its own handler).
- Not built: weekly/monthly charts, per-day challenge strip, dashboard reminders by email (Phase 5).

**Milestone 12: AI foundation (done, branch `feat/ai-foundation`)**
- NO live AI. No provider has been called for real; `GET /ai/status` always reports `live_verified: false`. AI is OFF unless `AI_PROVIDER=anthropic` AND `ANTHROPIC_API_KEY` are both set
  in `backend/.env` (a key alone does nothing; default `AI_PROVIDER=none`). The live Claude connection and chat window are Phase 6.
- Tables already existed (`ai_conversations`, `ai_messages`, `ai_pending_actions`, `ai_memories`), so no migration. Code: `app/ai/` (types, providers, tools, prompt), `services/assistant.py`
  (conversations, tool loop, approvals), `services/ai_memory.py`, `routers/assistant.py` (`/api/ai/*`).
- Provider interface `LLMProvider.complete(system, messages, tools) -> LLMResponse`; messages are provider-neutral Anthropic-style blocks (text / tool_use / tool_result).
  `ScriptedProvider` (offline, tests) and `AnthropicProvider` (request/response translation verified ONLY against a stub client; errors are reduced to the exception class so the key never leaks).
- 16 tools = thin wrappers over services, strict pydantic args (`extra=forbid`, no user id argument, so a model can't reach another user's data). 10 READ tools run immediately
  (today/pending tasks, plan, dashboard, courses, next video, projects, roadmap, habits, challenge status). 6 WRITE tools (create_task, complete_task, reschedule_task, record_project_progress,
  create_project_challenge, remember) never run in the loop: they store an `ai_pending_actions` row ("awaiting approval") and run only on `POST /ai/pending/{id}/approve` (args re-validated,
  claimed first so double-approve conflicts, result stored, status executed/failed). There is deliberately NO tool to complete a challenge (evidence must come from the user) or to delete anything.
- Loop: max 6 rounds, max 5 proposals per turn and 20 open, history capped at 40 messages and never starts mid tool-exchange, message <= 4000 chars. System prompt rules: only state facts a tool returned,
  evidence is unverified, proposals aren't done until executed; saved memories are framed as data. Chat answers 503 with no provider, 502 on a provider error.
- Endpoints: `GET /ai/status`, `GET /ai/tools`, `GET/POST/DELETE /ai/memories`, `POST /ai/chat`, `GET /ai/conversations[/{id}]`, `DELETE /ai/conversations/{id}`, `GET /ai/pending?status=`, `POST /ai/pending/{id}/approve|reject`.
- Frontend `/assistant` (now a real page; the "coming soon" placeholder mechanism and its test were removed since nothing is unbuilt in the nav): connection status, approval queue, memory (add/delete), tool list. No chat box yet.
- Tests: backend `test_assistant.py` (38), `test_assistant_api.py` (27); frontend `assistant.test.tsx` (11) + `fakeAssistant.ts`. Frontend test stability: `testTimeout` 20s (vite.config.ts) and Testing Library `asyncUtilTimeout` 10s because the full suite
  (253 tests) is slow under parallel load; two long tests were flaking at the old limits.
- **Later update (Phase 6 live testing).** Gemini was run live and Groq was added. Memory was REMOVED (service, `/ai/memories`, the `remember` tool, the UI card and the prompt notes; the old `ai_memories`
  table is left in existing databases, unused), so there are now 16 tools (11 read, 5 write; `look_up_github_repo` was added at the end of Phase 6). New: `app/ai/groq.py` (OpenAI-style chat completions; tool results are `role: "tool"` messages), `app/ai/catalog.py`
  (`GET /ai/models`: live model list for Groq and Gemini, cached 10 minutes, curated fallback, default always included), per-request `provider`/`model` on chat, check and autofill (only providers with a key,
  model names validated), `ToolCall.meta` (carries Gemini's `thoughtSignature`; stripped for Anthropic). Live findings: Gemini 3 models answer 400 on the second tool turn unless `thoughtSignature` is sent back; `gemini-2.5-flash`
  returned 404 although listed; the Gemini free tier allows ~5 requests a minute. Tests now force `AI_PROVIDER=none` and blank keys so a real `.env` can't leak in. Frontend: redesigned chat (bubbles, markdown renderer in
  `components/Markdown.tsx` that never injects HTML, suggestion chips, Enter to send, typing indicator, optimistic message) and a model menu remembered in localStorage (`hub.ai-model`). Groq is tested only against fake HTTP.
- **Phase 7 (reports, persistence).** `services/reports.py` + `routers/reports.py` + `schemas/reports.py`: per-day counts of finished tasks, lessons, videos and roadmap topics (grouped by the USER's local calendar day, not UTC), study and project minutes, habit check-ins, the daily-challenge status and the planner's own planned/completed figures; totals; a like-for-like comparison with the first N days of the previous period (N = days that have happened); top projects by time; habits. Days that have not happened yet show no activity and are left out of the plan percentage. The assistant has a matching read tool `get_weekly_report`. Frontend `/reports`: Week/Month, previous/next, KPI tiles with wording deltas, four charts hand-built in HTML (thin bars, rounded data end, 2px gap, hairline grid, legend for 2+ series, per-day hover/focus tooltip, a Charts/Tables switch so every value is readable without colour), colour tokens `--viz-*` in `index.css` (light and dark validated with the dataviz validator; light-mode yellow/aqua/magenta are under 3:1, so the table view is the required relief).
- **Persistence tests** (`tests/test_persistence.py`) start the REAL server on a database file: data and login survive a hard kill and a clean restart, a signed-out cookie stays dead, a copied database file is a complete backup, `alembic upgrade head` works on an empty file and twice, and `alembic check` finds no drift between models and migrations. `alembic/env.py` ignores the retired `ai_memories` table on purpose (dropping it would delete the owner's saved note).
- Not built: chat UI and live provider (Phase 6), OpenAI/Gemini adapters, weekly report tool, GitHub commit tool (Phase 4), streaming, conversation memory summarisation, notifying the model when a proposal is approved.

### Phase 3 verification pass (branch `feat/phase3-verification`)

- New `backend/tests/test_integration.py`: (1) a route sweep read from the OpenAPI schema (this FastAPI version nests included routers, so
  `app.routes` is not flat): every method+path except health and the sign-in routes must answer 401 without login; (2) no GET response
  contains a password hash, the signing key or the password; (3) one whole day through tasks, habits, courses, videos, projects, challenge
  and then an assistant proposal that is partly approved and partly rejected, checking after each step that planner = dashboard
  and that a proposal changes nothing until approved; (4) a second user's services return nothing of user 1's data; (5) a test that documents the planner/roadmap contract above.
- **Finding (not changed, by design):** `/api/planner` called on a brand-new account, before the dashboard or roadmap page was ever opened, has no roadmap
  topic, because the roadmap is created lazily and `test_planner` deliberately asserts that merely viewing the planner never creates it. The dashboard
  (the landing page) seeds it, after which both agree. I first "fixed" this by seeding inside the planner, 29 planner tests failed, and I reverted it
  because it overrode that earlier tested decision. The assistant's `get_plan` tool has the same first-call gap.
- README.md rewritten from a 2-line stub: honest status table, what each page does, run/test commands, security notes.
- Owner's Phase 3 list re-checked against the code (see handoff): everything in items 1-10 is built and tested. Settings is read-only
  (account details + theme); profile/timezone editing is not built. Seed data (item 11) exists as course templates, the seeded roadmap and
  `plans/bytebytego_21_day.txt` + `scripts/apply_plan.py`; there is no demo-data generator by design (no invented records).
  No real-browser run lives in the repo (see Known issues): UI is covered by Vitest with a fake API only.

## 10a. Session handoff (read this first in a new session)

Updated 2026-11-24. **Rule from the owner: always save progress in this file (not README) at the end of every step.**

- State: Milestones 1-12 done (12 = AI foundation, no live AI) (auth, shell, tasks, courses, videos+YouTube, AI roadmap, habits, projects, daily planner, **daily AI project challenge**). Real `hub.db` at migration `b8d2f5a1c6e3`. Earlier: Milestone 5 (video playlists) merged to `main`. **Then the owner's spec #7 (YouTube channel & playlist tracker) was built on `feat/youtube-tracker`** (see "Milestone 5b" in §10). Real `hub.db` is migrated to `d4f7b1c9e3a5` (backup `backend/data/backups/hub-before-library-*.db`, git-ignored).
  Done: auth, app shell, tasks, courses, video library + YouTube import.
- Owner's Phase 3 roadmap (pasted 2026-11-24) order: 1 auth ✅, 2 layout ✅, 3 dashboard (shell only; real metrics deferred to
  Milestone 11), 4 tasks ✅, 5 courses ✅, 6 ByteByteGo videos ✅ (= our Milestone 5), 7 AI roadmap ✅ (= our Milestone 6),
  8 habits ✅ (= our Milestone 7), 9 projects ✅ (= our Milestone 8), 10 planner ✅ (built after projects; the planner is what connects tasks, lessons, videos, roadmap, habits and projects into one day view; Milestone 9 daily challenge ✅ (built after the planner); Milestone 11 dashboard ✅; Milestone 12 AI foundation ✅; integration tests + docs + verification pass (Milestone 13) ✅ on `feat/phase3-verification`), 10 planner + daily accountability, 11 seed data, 12 integration tests, 13 docs, 14 final verification.
- Next action: Phase 4 (GitHub verification of challenge commits; needs the owner's GitHub credentials, asked only then). Branch `feat/github-verification`.
- Reminders: pre-commit checks (backend pytest, frontend typecheck, production build, git status, no secrets/.env/db files); explain
  each component to the owner (what, why, endpoints, DB, logic, how to test, concepts); AI provider abstraction + tool-calling docs
  come in Milestone 12 / Phase 6; never mark unfinished work as done.

## 11. Pending work

**Requested by the owner (2026-11-23) — YouTube playlists with a daily watch target.** Built in Milestone 5 (see §10) except the
parts marked below as still pending: importing a playlist link through the YouTube Data API (needs a free API key, asked for only when
we build it), the dashboard reminder (Milestone 11) and reminder emails (Phase 5). Original design for reference:
- New `video_playlists` table (name, source URL, optional YouTube playlist id, `daily_target`, active) and
  `videos.playlist_id` + `videos.youtube_video_id`. Reuses the existing rule: completed videos are never recommended again,
  enforced in the query (`status != 'completed' ORDER BY position`).
- Adding videos: (1) paste video links, one per line (works with no credentials); (2) paste a playlist link, which needs a
  free YouTube Data API key (only requested when this is built; nothing is faked without it).
- "Today's videos": the next N unwatched videos where N = the playlist's daily target, plus "watched X of N today"
  (counted in the user's local day). In-app reminder on the dashboard and Videos page.
- Reminder emails ("you planned N, watched X, Y left") need the Phase 5 email setup (Gmail/SMTP credentials); until then
  reminders are in-app only. The reminder is sent only when the target is not yet met and never duplicates (idempotency key).


See phase table. Credentials needed later (asked only when that phase is reached):
Anthropic API key (Phase 6), Gmail App Password or OAuth client (Phase 5),
GitHub OAuth App client ID/secret or PAT (Phase 4).

## 12. Known issues

- npm prints "new major version 12 available" — harmless; staying on npm 10 (matches Node 20).
- Kaspersky HTTPS interception (see §2) — handled; if Kaspersky is uninstalled nothing breaks.
- Commits are authorised by the user after each tested milestone. Local git identity was unset; set repo-local
  (`user.name`/`user.email`) from the account e-mail — change with `git config` if desired.
- Git workflow (user rule): one branch per milestone (`feat/...`), merged into `main` with `--no-ff` so each milestone
  is a checkpoint; branch and `main` are both pushed to GitHub. Never force-push.
- The browser end-to-end script from Milestone 3 lives only in a scratch folder and relies on a locally installed Edge and
  jsdom's transitive `ws` package. Formalise it (e.g. Playwright) in the integration-testing step so it runs from the repo.
- Courses: no drag-and-drop (reordering uses up/down buttons); there is no "mark module complete" shortcut (by design: only
  lessons carry completion); the course search/filter beyond status tabs is not built.
- Recurring-task edit UI is create/pause/delete only; editing an existing template's title/schedule through the UI is not
  built (the API supports it).
- Tasks created in the Today tab get today's date pre-filled; other tabs start blank. Carry-forward of unfinished tasks to
  the next day belongs to the planner milestone (columns `carried_from_date`, `carry_count` already exist).
- Timezone default `Asia/Kolkata` was assumed (setup form pre-fills the browser's timezone); profile editing is not built.
- SQLite quirk: a running uvicorn holds `hub.db` open (WAL); stop it before deleting/replacing the file.
- Videos: no YouTube playlist import (needs an API key), no title lookup from links, no drag-and-drop (up/down buttons), no "daily target
  history" (only today's count is derived from completion times), and the dashboard/e-mail reminders are not built yet. The
  `LearningResource`/`course_lessons.lesson_type='video'` idea from Phase 1 is superseded by the dedicated `videos` table.
- Test tooling: the `/videos` page is covered by Vitest with a fake API; there is still no real-browser run in the repo (see the Edge-script
  note above). Shell quoting: write multi-line files with the editor tool, not bash heredocs (one failed silently this milestone).


---

## Phase 9: a pace you can keep (rest days, hours, roll-over, slipping)

Requested by a reviewer (items 2, 6 and 9 of their list); the rest of the list is Phases 10 and 11 (goals and pace warnings, a timer that logs
time, a shareable progress page and weekly e-mail, containers).

- **Rest days** (`rest_days` table, `services/rest.py`, `/api/rest-days`): at most `user_settings.rest_days_per_month` (default 4) per calendar month.
  Allowed for today, the last 3 days and up to a year ahead; not on a day whose challenge is completed. Effects: the challenge streak skips the
  day (like an excused day), it is not "missed", the planner turns that day's open items into excused ("Rest day") so nothing is overdue, and
  reports count it as excused. **Habit streaks are not changed.** The calendar has a new `rest` status; `Stats.rest_days` and `Today.rest_day`
  were added.
- **Daily hours** (`user_settings.weekday_minutes`, "m,t,w,t,f,s,s" minutes, null = not set; `/api/planner/preferences`): `DaySummary` gained
  `planned_minutes`, `available_minutes`, `unestimated`, `overloaded`, `rest_day`. Only items with a time count (task estimate, lesson length,
  video length, minutes already logged); open items without one are counted in `unestimated`, never guessed. A rest day is never overloaded.
- **Roll-over** (`POST /api/planner/roll-over`, `dry_run` previews): moves today's open, non-excused tasks to tomorrow (all, or `task_ids`),
  adds one to `carry_count`, and returns tomorrow's load. Lessons, videos, topics and habits reappear on their own, so only tasks move.
- **Slipping** = an open task with `carry_count >= 3` (`planner.SLIP_AT`). `PlanItem` has `carry_count` and `slipping`; the new read tool
  `get_slipping_items` (tool 18) and a prompt rule make the assistant ask ONE short question about why before proposing a change (split it, move
  it, or drop it, each needing approval). The planner links to `/assistant?ask=...`, which pre-fills the chat box without sending.
- Migration `7695ccbb61ae` adds `rest_days` and the two settings columns. Tests: `tests/test_phase9.py`, `tests/test_phase9_api.py`,
  `src/test/phase9.test.tsx`.


---

## Phase 10: goals with a pace warning, and the timer

Reviewer items 4 and 7. Phase 11 (shareable progress page and weekly e-mail, container, portfolio page) is still to do.

- **Goals** (`services/goals.py`, `GET /api/goals`, nothing new stored): an active course or project with a `target_date` is a goal. Pace comes
  from what was really finished: remaining = lessons not completed (course) or milestones plus non-cancelled tasks not done (project); days left =
  today to the target, both included, minus planned rest days; needed = remaining / days left; your pace = items finished in the last 14 local days / 14;
  projected finish = today + remaining / pace. Status: `done`, `overdue`, `behind` (projected after the target), `stalled` (finished things before,
  none in 14 days), `not_started` (warns only if it already needs at least one item a day), `on_track`, `unknown` (nothing to count: no projection is
  invented). `warning` is true for overdue, behind, stalled and a hurried not_started. The server writes the `message`, so the UI and the assistant say
  the same thing. UI: a "Goals and pace" card on today's planner and a pace line on the course and project pages. New read tool `get_goals` (tool 19) and
  a prompt rule (at most one suggested change; the user moves the date themselves).
- **Timer** (`active_timers`, one row per user, `services/timer.py`, `/api/timer`): start on a task, lesson, course, roadmap topic or project; one at a
  time (409 otherwise). It survives a reload because it is stored. Nothing is logged while it runs. Stop logs the minutes (rounded, at least 1; the
  user may correct them; past 24 hours they must) as a development session on the project (a project task logs to its project with the task attached),
  else a study session on the course/lesson or the roadmap topic; a task's `actual_minutes` also grows. Discard logs nothing. The delete of the timer and
  the log share one transaction, so a failure keeps the timer and a success never logs twice. UI: a bar under the header on every page (clock counts from
  the server's elapsed figure, so a wrong local clock is harmless) and "Timer" buttons on planner rows, tasks, lessons, courses, topics and projects.
- Migration `8c8a6ae3b160` adds `active_timers`. Tests: `tests/test_phase10.py`, `tests/test_phase10_api.py`, `src/test/phase10.test.tsx`.
